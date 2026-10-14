"""Test page for the print-quality loop.

One A4 page with a line of random letters at each font size from 4 to
12 pt. Random letters (not words) so the OCR cannot guess from context.
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
FONT = "Helvetica"
# letters that are easy to confuse even when printed perfectly are left out
ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "lI1O0o")
SEED = 509


def make(out=HERE / "test_page.pdf"):
    rng = random.Random(SEED)
    width, height = A4
    c = canvas.Canvas(str(out), pagesize=A4)
    lines = []
    y = height - 72                     # start 1 inch from the top
    for size in SIZES:
        text = "".join(rng.choice(ALPHABET) for _ in range(LINE_CHARS))
        c.setFont(FONT, size)
        c.drawString(72, y, text)
        # box around the line in PDF points (from bottom-left), with margin
        lines.append({"size": size, "text": text,
                      "box": [60, y - size * 0.5, width - 60, y + size * 1.3]})
        y -= max(40, size * 4)
    c.save()
    truth = {"page": [width, height], "font": FONT, "lines": lines}
    out.with_suffix(".json").write_text(json.dumps(truth, indent=1))
    log.info(f"wrote {out} and {out.with_suffix('.json').name}")
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    make()
