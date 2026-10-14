"""Test page for the print-quality loop.

One A4 page with a block of 5 lines of random letters at each font size
from 4 to 12 pt (150 letters per size, so one misread letter is <1%). Random letters (not words) so the OCR cannot guess from context.
The exact text and where each line sits are saved next to the PDF, so
the measuring step knows the right answer and where to look.

Run:  .venv/bin/python quality/test_page.py
"""

import json
import logging
import random
import string
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent
log = logging.getLogger("test_page")

SIZES = [4, 5, 6, 7, 8, 9, 10, 11, 12]   # font sizes in points
LINE_CHARS = 30
LINES_PER_SIZE = 5
FONT = "Helvetica"
# letters that are easy to confuse even when printed perfectly are left out
ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "lI1O0o")
SEED = 509


def make(out=HERE / "test_page.pdf"):
    rng = random.Random(SEED)
    width, height = A4
    c = canvas.Canvas(str(out), pagesize=A4)
    lines = []
    y = height - 60                     # baseline of the first line
    for size in SIZES:
        pitch = max(10, size * 1.6)     # distance between lines of one block
        rows = ["".join(rng.choice(ALPHABET) for _ in range(LINE_CHARS))
                for _ in range(LINES_PER_SIZE)]
        top = y + size * 1.0
        c.setFont(FONT, size)
        for row in rows:
            c.drawString(72, y, row)
            y -= pitch
        bottom = y + pitch - size * 0.35
        # one box around the whole block, in PDF points (from bottom-left)
        lines.append({"size": size, "rows": rows, "box": [60, bottom, width - 60, top]})
        y -= 10                         # gap before the next size
    c.save()
    truth = {"page": [width, height], "font": FONT, "lines": lines}
    out.with_suffix(".json").write_text(json.dumps(truth, indent=1))
    log.info(f"wrote {out} and {out.with_suffix('.json').name}")
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    make()
