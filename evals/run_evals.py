"""Run the eval cases through the whole graph on the simulated printer.

Every question the graph asks is answered "yes" automatically (approve,
pages came out). Then the result is compared field by field with the
case's "expect". No AI judges the result: only plain comparisons.

Run:  .venv/bin/python evals/run_evals.py            (all cases)
      .venv/bin/python evals/run_evals.py typo-1     (some cases)
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: E402
from langchain_mcp_adapters.tools import load_mcp_tools  # noqa: E402
from langgraph.types import Command  # noqa: E402

# the evals' documents live in test_docs/, not in ~/Downloads
os.environ["FINDER_DIR"] = str(ROOT / "test_docs")

import graph  # noqa: E402  (also sets up logging via planner)

log = logging.getLogger("evals")


def one_copy_pages(sheet_plan, copies):
    """Page numbers of one copy, in print order."""
    one_copy = sheet_plan[:len(sheet_plan) // copies] if copies else sheet_plan
    return [n for sheet in one_copy for n in sheet]


async def run_case(case):
    """Run one request through the graph. Returns what actually happened."""
    client = MultiServerMCPClient({"printer": {
        "command": sys.executable, "args": [str(ROOT / "printer_server.py")],
        "transport": "stdio", "env": {**os.environ, "PRINTER_BACKEND": "sim"},
    }})
    async with client.session("printer") as session:   # fresh simulator per case
        tools = await load_mcp_tools(session, handle_tool_errors=False)
        app = graph.build(tools)
        cfg = {"configurable": {"thread_id": case["id"]}}
        state = await app.ainvoke({"request": case["request"]}, cfg)
        while "__interrupt__" in state:
            state = await app.ainvoke(Command(resume="yes"), cfg)

    order, preview = state["order"], state.get("preview", {})
    return {
        "prints": bool(state.get("job_id")),
        "asks": bool(order["questions"]),
        "pages": one_copy_pages(preview.get("sheet_plan", []), order["copies"]),
        "sheets": preview.get("sheets"),
        "copies": order["copies"],
        "number_up": order["number_up"],
        "toner_density": order["toner_density"],
        "toner_save": order["toner_save"],
        "reverse": order["reverse"],
        "refused": preview.get("error"),
        "questions": order["questions"],
    }


def compare(expect, got):
    """List of mismatches, one per expected field that differs."""
    return [f"{k}: expected {v!r}, got {got.get(k)!r}"
            for k, v in expect.items() if got.get(k) != v]


async def main(only):
    cases = json.loads((ROOT / "evals" / "cases.json").read_text())
    if only:
        cases = [c for c in cases if c["id"] in only]
    results = []
    for case in cases:
        t = time.time()
        try:
            got = await run_case(case)
            problems = compare(case["expect"], got)
        except Exception as e:
            # a crash is a failed case, reported loudly, not skipped
            log.error(f"{case['id']} crashed: {type(e).__name__}: {e}")
            got, problems = None, [f"crashed: {type(e).__name__}: {str(e)[:200]}"]
        ok = not problems
        results.append({**case, "got": got, "ok": ok, "problems": problems,
                        "seconds": round(time.time() - t)})
        log.info(f"{'PASS' if ok else 'FAIL'} {case['id']:9} {case['request']!r}"
                 + ("" if ok else f"  -> {'; '.join(problems)}"))

    passed = sum(r["ok"] for r in results)
    log.info(f"SCORE: {passed}/{len(results)}")
    for group in dict.fromkeys(r["group"] for r in results):
        rs = [r for r in results if r["group"] == group]
        log.info(f"  {group:18} {sum(r['ok'] for r in rs)}/{len(rs)}")
    out = ROOT / "evals" / f"results_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps({"model": graph.planner.MODEL, "score": f"{passed}/{len(results)}",
                               "results": results}, indent=1))
    log.info(f"saved {out.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
