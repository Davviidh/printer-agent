"""The print assistant as a LangGraph graph.

    planner -> executor (preview) -> approval (human)
        no  -> END
        yes -> executor (submit) -> executor (read) -> checker
                  checker -> wait: executor (read) again
                          -> retry: executor (submit) again
                          -> cancel: executor (cancel) -> END
                          -> done: END

The planner and checker have no tools. Only the executor talks to the
MCP printer server; it writes what it read into the state, and the
checker decides from that (David's decision table).

Run:  .venv/bin/python graph.py "print test_docs/four_pages.pdf odd pages"
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import TypedDict

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import planner

ROOT = Path(__file__).parent
log = logging.getLogger("graph")

POLL_S = 3            # seconds between printer readings
WATCH_LIMIT_S = 300   # stop watching after this, the job stays queued
MAX_RETRIES = 2


class State(TypedDict, total=False):
    request: str          # the user's sentence
    order: dict           # filled in by the planner
    options: dict         # order turned into printer options
    path: str             # the file actually used
    present: bool         # is the printer on? (from the executor)
    preview: dict         # pages and sheets (from the executor)
    note: str             # what the human sees before approving
    decision: str         # the human's answer
    job_id: str           # from the executor after submit
    reading: dict         # last printer reading (from the executor)
    watched_s: float      # how long we have been watching this job
    asked: list           # what the checker already asked about
    retries: int
    next: str             # where the checker sends the graph
    outcome: str          # final result, for the log


def order_to_options(order):
    """Planner's order form -> the option names the printer tools use."""
    opts = {"copies": order["copies"], "number-up": order["number_up"],
            "CNTonerDensity": order["toner_density"],
            "CNDraftMode": "True" if order["toner_save"] else "False"}
    if order.get("page_ranges"):
        opts["page-ranges"] = order["page_ranges"]
    if order.get("page_set"):
        opts["page-set"] = order["page_set"]
    if order.get("reverse"):
        opts["outputorder"] = "reverse"
    return opts


# Until the Downloads file finder exists, a bare file name is looked up
# in test_docs/ as well.
DOC_DIRS = [Path.cwd(), ROOT / "test_docs"]


def resolve(file):
    for d in DOC_DIRS:
        if file and (d / file).is_file():
            return str(d / file)
    return file


def make_note(state):
    o, p = state["order"], state["preview"]
    warnings = list(o["questions"])
    if "error" in p:
        warnings.append(p["error"])
    if not state["present"]:
        warnings.append("printer is OFF: switch it on before printing")
    pages = [n for sheet in p.get("sheet_plan", []) for n in sheet]
    lines = [
        "PRINT ORDER - please check",
        f"File:      {p.get('file', o.get('file'))} ({p.get('doc_pages', '?')} pages)",
        f"Pages:     {o.get('page_set') or o.get('page_ranges') or 'all'} -> {pages}",
        f"Layout:    {o['number_up']} page(s) per sheet, {o['copies']} copy/copies",
        f"Order:     {'reversed (last page first)' if o['reverse'] else 'normal'}",
        f"Paper:     {p.get('sheets', '?')} sheet(s)",
        f"Toner:     density {o['toner_density']}, save mode {'on' if o['toner_save'] else 'off'}",
        f"Printer:   {'ON' if state['present'] else 'OFF'}",
        f"Warnings:  {'; '.join(warnings) if warnings else 'none'}",
        "Reply: yes / no",
    ]
    return "\n".join(lines)


def tool_result(raw):
    """MCP tool output -> dict. Fails loudly on anything unexpected."""
    if isinstance(raw, list):
        raw = "".join(b["text"] for b in raw if b.get("type") == "text")
    if not isinstance(raw, str):
        raise TypeError(f"unexpected tool output: {raw!r}")
    return json.loads(raw)


def build(tools):
    """tools: the MCP printer tools, given ONLY to the executor node."""
    by_name = {t.name: t for t in tools}

    def planner_node(state):
        order = planner.plan(state["request"]).model_dump()
        return {"order": order, "options": order_to_options(order)}

    async def executor_node(state):
        status = tool_result(await by_name["printer_status"].ainvoke({}))
        path = resolve(state["order"].get("file") or "")
        preview = tool_result(await by_name["preview_print"].ainvoke(
            {"path": path, "options": state["options"]}))
        log.info(f"executor: present={status['present']} preview={preview}")
        return {"present": status["present"], "preview": preview, "path": path}

    def approval_node(state):
        note = make_note(state)
        answer = interrupt(note)          # graph pauses here for the human
        log.info(f"human answered: {answer!r}")
        return {"note": note, "decision": answer.strip().lower()}

    def after_approval(state):
        blocked = "error" in state["preview"] or state["order"]["questions"]
        if state["decision"] in ("yes", "y") and not blocked:
            return "submit"
        return END

    async def submit_node(state):
        res = tool_result(await by_name["submit_print"].ainvoke(
            {"path": state["path"], "options": state["options"]}))
        if "error" in res:
            log.error(f"submit refused: {res['error']}")
            raise RuntimeError(f"submit refused: {res['error']}")
        log.info(f"executor: submitted {res}")
        return {"job_id": res["job_id"], "watched_s": 0.0, "asked": []}

    async def read_node(state):
        if state.get("reading"):
            await asyncio.sleep(POLL_S)
        present = tool_result(await by_name["printer_status"].ainvoke({}))["present"]
        job = tool_result(await by_name["job_status"].ainvoke({"job_id": state["job_id"]}))
        reading = {"present": present, **job}
        log.info(f"executor: reading {reading}")
        return {"reading": reading, "watched_s": state["watched_s"] + POLL_S}

    def checker_node(state):
        """David's decision table. Presence is checked FIRST, because an
        off printer also makes the job look stuck."""
        r, asked = state["reading"], list(state["asked"])
        sheets = state["preview"]["sheets"]

        if state["watched_s"] > WATCH_LIMIT_S:
            return {"next": "end", "outcome": f"stopped watching after {WATCH_LIMIT_S} s, job {state['job_id']} still queued"}

        if not r["present"]:
            # off + waiting: ask to switch it on, keep watching, never resubmit
            if "power" not in asked:
                interrupt("The printer is OFF. Your job is waiting in the queue.\n"
                          "Switch the printer on, then press Enter. (Nothing will be sent twice.)")
                asked.append("power")
            return {"next": "wait", "asked": asked}

        if r["state"] == "completed":
            # on + finished: CUPS only knows the data was sent, so ask
            ans = interrupt(f"The printer got the job. Did {sheets} sheet(s) come out? yes / no")
            ok = ans.strip().lower() in ("yes", "y")
            return {"next": "end", "outcome": "done, human confirmed" if ok
                    else "human says pages are missing: check the printer"}

        if r["state"] in ("failed", "canceled", "unknown"):
            # on + failed: the job is gone, so a retry cannot print twice
            if state.get("retries", 0) >= MAX_RETRIES:
                return {"next": "end", "outcome": f"failed after {MAX_RETRIES} retries"}
            ans = interrupt(f"The job {r['state']}. Please check the printer (paper, jam, cable).\n"
                            "Retry? yes / no")
            if ans.strip().lower() in ("yes", "y"):
                return {"next": "retry", "retries": state.get("retries", 0) + 1, "reading": {}}
            return {"next": "end", "outcome": f"job {r['state']}, human chose not to retry"}

        if r["stuck"]:
            # on + stuck: ask, never retry (the job might still come out)
            if "stuck" not in asked:
                ans = interrupt(f"The job has not finished after {r['elapsed_s']} s and the printer is on.\n"
                                "Please check it. I will NOT resend (it could print twice).\n"
                                "Type 'wait' to keep watching or 'cancel' to cancel the job.")
                asked.append("stuck")
                if ans.strip().lower() == "cancel":
                    return {"next": "cancel", "asked": asked}
            return {"next": "wait", "asked": asked}

        return {"next": "wait", "asked": asked}

    async def cancel_node(state):
        res = tool_result(await by_name["cancel_job"].ainvoke({"job_id": state["job_id"]}))
        log.info(f"executor: cancel {res}")
        return {"outcome": f"job canceled by human: {res}"}

    g = StateGraph(State)
    g.add_node("planner", planner_node)
    g.add_node("executor", executor_node)
    g.add_node("approval", approval_node)
    g.add_node("executor_submit", submit_node)
    g.add_node("executor_read", read_node)
    g.add_node("checker", checker_node)
    g.add_node("executor_cancel", cancel_node)
    g.add_edge(START, "planner")
    g.add_edge("planner", "executor")
    g.add_edge("executor", "approval")
    g.add_conditional_edges("approval", after_approval,
                            {"submit": "executor_submit", END: END})
    g.add_edge("executor_submit", "executor_read")
    g.add_edge("executor_read", "checker")
    g.add_conditional_edges("checker", lambda s: s["next"], {
        "wait": "executor_read", "retry": "executor_submit",
        "cancel": "executor_cancel", "end": END})
    g.add_edge("executor_cancel", END)
    return g.compile(checkpointer=InMemorySaver())


async def run(request):
    client = MultiServerMCPClient({"printer": {
        "command": sys.executable, "args": [str(ROOT / "printer_server.py")],
        "transport": "stdio",
        "env": {**os.environ, "PRINTER_BACKEND": os.environ.get("PRINTER_BACKEND", "sim")},
    }})
    # one session for the whole run, so the printer's state is kept
    async with client.session("printer") as session:
        tools = await load_mcp_tools(session, handle_tool_errors=False)
        app = build(tools)
        cfg = {"configurable": {"thread_id": "1"}}
        result = await app.ainvoke({"request": request}, cfg)
        while "__interrupt__" in result:
            note = result["__interrupt__"][0].value
            answer = input("\n" + note + "\n> ")
            result = await app.ainvoke(Command(resume=answer), cfg)
        log.info(f"decision: {result.get('decision')}, outcome: {result.get('outcome')}")
        return result


if __name__ == "__main__":
    asyncio.run(run(" ".join(sys.argv[1:])))
