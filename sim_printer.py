"""Simulated printer: same functions as connector.py, no paper used.

It copies what the real Canon did in tests on 13 Oct:
- printer off: printer_present() is False and jobs wait as "pending"
- printer on: "printing" at once, "completed" after ~1 s,
  but the sheets only reach the tray after ~10 s
Faults can be switched on to test the agent: "stuck" (job never
finishes) and "fail" (job is aborted).

Time is a fake clock moved with advance(), so evals run instantly.
"""

from pathlib import Path

import connector

DATA_SENT_S = 1       # CUPS says "completed" after this
FIRST_SHEET_S = 10    # paper reaches the tray after this
PER_SHEET_S = 4       # each further sheet (LBP6020 is ~18 pages/min)


class SimPrinter:
    def __init__(self, powered=True, fault=None):
        self.powered = powered
        self.fault = fault        # None, "stuck" or "fail"
        self.now = 0.0
        self.jobs = {}
        self._next_id = 1

    # ---------- controls for tests (the "world") ----------

    def advance(self, seconds):
        """Let time pass. A job only runs while the printer is on."""
        for _ in range(int(seconds * 10)):
            self.now += 0.1
            for job in self.jobs.values():
                # paper keeps moving after CUPS already says "completed"
                busy = job["state"] in ("pending", "printing") or (
                    job["state"] == "completed"
                    and job["sheets_out"] < job["sheets"])
                if self.powered and busy:
                    job["run_s"] = round(job["run_s"] + 0.1, 1)
                    self._update(job)

    def tray(self):
        """What a human would see: sheets that actually came out."""
        return sum(j["sheets_out"] for j in self.jobs.values())

    def _update(self, job):
        if self.fault == "stuck":
            job["state"] = "printing"
            return
        if self.fault == "fail":
            job["state"] = "failed"
            job["alerts"] = "aborted-by-system"
            return
        if job["run_s"] >= DATA_SENT_S:
            job["state"] = "completed"
        else:
            job["state"] = "printing"
        if job["run_s"] >= FIRST_SHEET_S:
            done = 1 + int((job["run_s"] - FIRST_SHEET_S) // PER_SHEET_S)
            job["sheets_out"] = min(done, job["sheets"])

    def _log(self, action, args, result):
        connector._log("sim." + action, args, result)

    # ---------- same functions as connector.py ----------

    def printer_present(self):
        self._log("printer_present", {}, self.powered)
        return self.powered

    def preview(self, path, options=None):
        # the real safety checks; preview never touches the printer
        return connector.preview(path, options)

    def submit(self, path, options=None):
        plan = self.preview(path, options)
        if "error" in plan:
            self._log("submit", {"path": str(path), "options": options}, plan)
            return plan
        job_id = f"SIM-{self._next_id}"
        self._next_id += 1
        self.jobs[job_id] = {"state": "pending", "alerts": "", "run_s": 0.0,
                             "submitted": self.now, "sheets": plan["sheets"],
                             "sheets_out": 0}
        if self.powered:
            self._update(self.jobs[job_id])
        result = {"job_id": job_id, "sheets": plan["sheets"]}
        self._log("submit", {"path": str(path), "options": options}, result)
        return result

    def cancel(self, job_id):
        job = self.jobs.get(job_id)
        ok = bool(job) and job["state"] in ("pending", "printing")
        if ok:
            job["state"] = "canceled"
            job["alerts"] = "job-canceled-by-user"
        result = {"ok": ok}
        self._log("cancel", {"job_id": job_id}, result)
        return result

    def job_state(self, job_id):
        job = self.jobs.get(job_id)
        if not job:
            result = {"job_id": job_id, "state": "unknown", "elapsed_s": None,
                      "stuck": False, "status": "", "alerts": ""}
        else:
            elapsed = round(self.now - job["submitted"])
            stuck = job["state"] in ("pending", "printing") \
                and elapsed > connector.STUCK_AFTER_S
            result = {"job_id": job_id, "state": job["state"],
                      "elapsed_s": elapsed, "stuck": stuck, "status": "",
                      "alerts": job["alerts"]}
        self._log("job_state", {"job_id": job_id}, result)
        return result


if __name__ == "__main__":
    doc = Path(__file__).parent / "test_docs" / "four_pages.pdf"
    cases = [("on, normal", True, None), ("off", False, None),
             ("on, stuck", True, "stuck"), ("on, failed", True, "fail")]
    for name, powered, fault in cases:
        sim = SimPrinter(powered=powered, fault=fault)
        job = sim.submit(doc, {"page-ranges": "1-2"})["job_id"]
        print(f"--- {name}")
        for wait in (1, 14, 60):
            sim.advance(wait)
            s = sim.job_state(job)
            print(f"t={sim.now:4.0f}s present={sim.printer_present()!s:5} "
                  f"state={s['state']:9} stuck={s['stuck']!s:5} "
                  f"tray={sim.tray()}")
