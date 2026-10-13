"""MCP server: offers the printer's actions and readings as tools.

The agent never imports connector.py itself. It starts this server and
calls its tools by name. Which printer is behind it is chosen with the
PRINTER_BACKEND environment variable: "sim" (default) or "real".

Run it on its own to try the tools:  mcp dev printer_server.py
"""

import os
import time

from mcp.server.fastmcp import FastMCP

import connector
from sim_printer import SimPrinter

BACKEND = os.environ.get("PRINTER_BACKEND", "sim")
if BACKEND == "real":
    printer = connector
else:
    printer = SimPrinter(powered=os.environ.get("SIM_POWERED", "1") == "1",
                         fault=os.environ.get("SIM_FAULT") or None)

_last = time.monotonic()
_start = _last
# for tests: the simulated printer is switched on after this many seconds
_on_after = float(os.environ["SIM_ON_AFTER"]) if os.environ.get("SIM_ON_AFTER") else None


def _tick():
    """In the server the simulator follows real time between calls."""
    global _last
    if BACKEND != "real":
        now = time.monotonic()
        printer.advance(now - _last)
        _last = now
        if _on_after is not None and now - _start >= _on_after:
            printer.powered = True


mcp = FastMCP("printer")


@mcp.tool()
def printer_status() -> dict:
    """Is the printer switched on and connected? Check this first: the
    print queue looks 'idle' even when the printer is off."""
    _tick()
    return {"backend": BACKEND, "present": printer.printer_present()}


@mcp.tool()
def preview_print(path: str, options: dict | None = None) -> dict:
    """Plan a print job WITHOUT printing. Returns the pages on each sheet,
    the sheet count and the printer settings, or an 'error' if the job is
    refused (not a PDF, unknown option, over the sheet cap).
    Options: page-ranges ("2-5" or "1,3,5-7"), page-set ("odd"/"even"),
    copies (1-5), number-up (1/2/4), outputorder ("normal"/"reverse"),
    CNTonerDensity (1-16, default 4), CNDraftMode ("True" = toner save),
    CNBrightness and CNContrast (1-11, default 6), CNGamma (1.0/1.4/1.8/2.2),
    CNHalftone (pattern1/pattern2/Off)."""
    _tick()
    return printer.preview(path, options)


@mcp.tool()
def submit_print(path: str, options: dict | None = None) -> dict:
    """Print a job. Only call this after a human approved the preview.
    Returns the job id. Takes the same options as preview_print."""
    _tick()
    return printer.submit(path, options)


@mcp.tool()
def job_status(job_id: str) -> dict:
    """State of a job: pending, printing, completed, canceled, failed or
    unknown, with seconds since submit and 'stuck' (unfinished after 60 s).
    'completed' only means the data reached the printer: paper comes out
    about 10 s later, so a human must confirm the pages."""
    _tick()
    return printer.job_state(job_id)


@mcp.tool()
def cancel_job(job_id: str) -> dict:
    """Cancel a job that is still pending or printing."""
    _tick()
    return printer.cancel(job_id)


if __name__ == "__main__":
    mcp.run()
