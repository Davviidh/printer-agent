"""Connector: the only code that touches the real printer.

Commands go out through CUPS (lp, cancel). Readings come back from
USB presence (ioreg) and CUPS job state (lpstat). Every call is logged.
"""

import json
import math
import re
import subprocess
import time
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation

QUEUE = "Canon_LBP6020"
MAX_SHEETS = 20          # safety: refuse bigger jobs
STUCK_AFTER_S = 60       # safety: a job unfinished after this is "stuck"
LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "actions.jsonl"
JOBS_FILE = LOG_DIR / "jobs.json"   # job id -> submit time, sheets

# Allowed options and how to check each value. Anything else is refused.
ALLOWED = {
    "page-ranges": lambda v: re.fullmatch(r"\d+(-\d+)?(,\d+(-\d+)?)*", v),
    "page-set": lambda v: v in ("odd", "even"),
    "copies": lambda v: v.isdigit() and 1 <= int(v) <= 5,
    "number-up": lambda v: v in ("1", "2", "4"),
    "outputorder": lambda v: v in ("normal", "reverse"),
    "CNTonerDensity": lambda v: v.isdigit() and 1 <= int(v) <= 16,
    "CNDraftMode": lambda v: v in ("True", "False"),
    "CNBrightness": lambda v: v.isdigit() and 1 <= int(v) <= 11,
    "CNContrast": lambda v: v.isdigit() and 1 <= int(v) <= 11,
    "CNGamma": lambda v: v in ("1.0", "1.4", "1.8", "2.2"),
    "CNHalftone": lambda v: v in ("pattern1", "pattern2", "Off"),
}


def _log(action, args, result):
    LOG_DIR.mkdir(exist_ok=True)
    line = {"ts": time.time(), "action": action, "args": args, "result": result}
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(line) + "\n")


def _run(cmd):
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return out.returncode, out.stdout + out.stderr


def _load_jobs():
    return json.loads(JOBS_FILE.read_text()) if JOBS_FILE.exists() else {}


def _save_jobs(jobs):
    LOG_DIR.mkdir(exist_ok=True)
    JOBS_FILE.write_text(json.dumps(jobs, indent=1))


# ---------- reading: is the printer there? ----------

def printer_present():
    """True if the Canon is on USB. lpstat can't tell us this: it says
    'idle' even when the printer is switched off."""
    _, out = _run(["ioreg", "-p", "IOUSB"])
    present = "canon" in out.lower()
    _log("printer_present", {}, present)
    return present


# ---------- planning: what would this job print? ----------

def _selected_pages(n_pages, options):
    pages = list(range(1, n_pages + 1))
    if "page-ranges" in options:
        keep = set()
        for part in options["page-ranges"].split(","):
            a, _, b = part.partition("-")
            keep.update(range(int(a), int(b or a) + 1))
        pages = [p for p in pages if p in keep]
    if options.get("page-set") == "odd":
        pages = pages[0::2]
    elif options.get("page-set") == "even":
        pages = pages[1::2]
    return pages


# Options the Canon driver ignores (its filter skips the CUPS step that
# applies them), so the connector does them itself by building a new PDF.
LAYOUT = ("page-ranges", "page-set", "copies", "number-up", "outputorder")


def preview(path, options=None):
    """Check a job without printing it. Returns the pages in print order,
    the sheet count and the driver options, or an 'error' if refused."""
    options = {k: str(v) for k, v in (options or {}).items()}
    path = Path(path).expanduser()
    if not path.is_file() or path.suffix.lower() != ".pdf":
        return {"error": f"not a PDF file: {path}"}
    for k, v in options.items():
        if k not in ALLOWED:
            return {"error": f"option not allowed: {k}"}
        if not ALLOWED[k](v):
            return {"error": f"bad value for {k}: {v}"}

    try:
        n_pages = len(PdfReader(path).pages)
    except Exception as e:
        return {"error": f"can't read PDF: {e}"}
    pages = _selected_pages(n_pages, options)
    if not pages:
        return {"error": "no pages selected"}
    up = int(options.get("number-up", 1))
    copies = int(options.get("copies", 1))
    sheets_per_copy = [pages[i:i + up] for i in range(0, len(pages), up)]
    if options.get("outputorder") == "reverse":
        sheets_per_copy.reverse()
    sheet_plan = sheets_per_copy * copies
    result = {"file": str(path), "doc_pages": n_pages,
              "sheet_plan": sheet_plan, "sheets": len(sheet_plan),
              "driver_options": {k: v for k, v in options.items()
                                 if k not in LAYOUT}}
    if len(sheet_plan) > MAX_SHEETS:
        result["error"] = f"{len(sheet_plan)} sheets is over the cap of {MAX_SHEETS}"
    return result


def _build_pdf(path, sheet_plan):
    """Write a new PDF with exactly one PDF page per sheet to print.
    With 2 or 4 pages per sheet, the pages are shrunk into a grid."""
    reader = PdfReader(path)
    writer = PdfWriter()
    up = max(len(sheet) for sheet in sheet_plan)
    for sheet in sheet_plan:
        if up == 1:
            writer.add_page(reader.pages[sheet[0] - 1])
            continue
        w = float(reader.pages[0].mediabox.width)
        h = float(reader.pages[0].mediabox.height)
        out = writer.add_blank_page(w, h)
        for i, num in enumerate(sheet):
            if up == 2:
                # turn the page on its side, shrink it, stack two halves
                s = min(w / h, h / 2 / w)
                y0 = 0 if i == 0 else h / 2   # reads left-right once turned
                t = (Transformation().rotate(90).translate(h, 0).scale(s)
                     .translate((w - h * s) / 2, y0 + (h / 2 - w * s) / 2))
            else:
                # 2x2 grid, reading order left-right then top-bottom
                col, row = i % 2, i // 2
                t = Transformation().scale(0.5).translate(
                    col * w / 2, h / 2 - row * h / 2)
            out.merge_transformed_page(reader.pages[num - 1], t)
    dest = LOG_DIR / "prepared" / f"{int(time.time() * 1000)}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        writer.write(f)
    return dest


# ---------- commanding: print and cancel ----------

def submit(path, options=None):
    """Send a job to the printer. Returns the job id, or an error."""
    plan = preview(path, options)
    if "error" in plan:
        _log("submit", {"path": str(path), "options": options}, plan)
        return plan
    prepared = _build_pdf(Path(path).expanduser(), plan["sheet_plan"])
    cmd = ["lp", "-d", QUEUE]
    for k, v in plan["driver_options"].items():
        cmd += ["-o", f"{k}={v}"]
    cmd.append(str(prepared))
    code, out = _run(cmd)
    m = re.search(rf"request id is ({QUEUE}-\d+)", out)
    if code != 0 or not m:
        result = {"error": f"lp failed: {out.strip()}"}
    else:
        job_id = m.group(1)
        jobs = _load_jobs()
        jobs[job_id] = {"submitted": time.time(), "sheets": plan["sheets"]}
        _save_jobs(jobs)
        result = {"job_id": job_id, "sheets": plan["sheets"],
                  "prepared": str(prepared)}
    _log("submit", {"path": str(path), "options": options}, result)
    return result


def cancel(job_id):
    code, out = _run(["cancel", job_id])
    result = {"ok": code == 0, "output": out.strip()}
    _log("cancel", {"job_id": job_id}, result)
    return result


# ---------- reading: what happened to the job? ----------

def _find_job(job_id, which):
    """Look the job up in lpstat's 'not-completed' or 'completed' list.
    Returns its Status and Alerts lines, or None if it isn't there."""
    _, out = _run(["lpstat", "-l", "-W", which, "-o", QUEUE])
    blocks = re.split(rf"\n(?={QUEUE}-\d+\s)", out)
    for block in blocks:
        if block.split()[:1] == [job_id]:
            status = re.search(r"Status: (.*)", block)
            alerts = re.search(r"Alerts: (.*)", block)
            return {"status": status.group(1).strip() if status else "",
                    "alerts": alerts.group(1).strip() if alerts else ""}
    return None


def job_state(job_id):
    """State of a job: pending, printing, completed, canceled, failed or
    unknown; plus seconds since submit and whether it counts as stuck.
    Note: 'completed' only means the data reached the printer. Tested
    13 Oct: CUPS said completed after 1 s, the sheet came out after ~10 s."""
    info = _find_job(job_id, "not-completed")
    if info:
        _, p = _run(["lpstat", "-p", QUEUE])
        state = "printing" if f"now printing {job_id}" in p else "pending"
    else:
        info = _find_job(job_id, "completed") or {"status": "", "alerts": ""}
        reasons = info["alerts"]
        if "canceled" in reasons:
            state = "canceled"
        elif "aborted" in reasons or "error" in reasons:
            state = "failed"
        elif reasons:
            state = "completed"
        else:
            state = "unknown"

    submitted = _load_jobs().get(job_id, {}).get("submitted")
    elapsed = round(time.time() - submitted) if submitted else None
    stuck = state in ("pending", "printing") and elapsed is not None \
        and elapsed > STUCK_AFTER_S
    result = {"job_id": job_id, "state": state, "elapsed_s": elapsed,
              "stuck": stuck, **info}
    _log("job_state", {"job_id": job_id}, result)
    return result
