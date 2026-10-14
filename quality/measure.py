"""Measure: how well can OCR read each line of the test page?

Takes an image of the page (a photo/scan of a real print, or the
simulator's fake print), cuts out each size's block of lines using the
positions saved by test_page.py, lets Tesseract read it, and compares
with the true text.

Character error rate (CER) = edits needed to turn the OCR text into the
true text, divided by the true length. 0 = perfect, 1 = nothing right.
"""

import json
import logging
from pathlib import Path

import pytesseract
from PIL import Image

HERE = Path(__file__).parent
log = logging.getLogger("measure")


def edit_distance(a, b):
    """Fewest single-letter inserts, deletes or swaps to turn a into b."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer_per_size(image: Image.Image, truth_file=HERE / "test_page.json"):
    """{font size: CER} for one page image (any resolution, A4 shape)."""
    truth = json.loads(Path(truth_file).read_text())
    page_w, page_h = truth["page"]
    sx, sy = image.width / page_w, image.height / page_h
    result = {}
    for block in truth["lines"]:
        x0, y0, x1, y1 = block["box"]
        # PDF y goes up from the bottom, image y goes down from the top
        crop = image.crop((int(x0 * sx), int((page_h - y1) * sy),
                           int(x1 * sx), int((page_h - y0) * sy)))
        # --psm 6: a block of text; all whitespace removed before comparing
        read = "".join(pytesseract.image_to_string(crop, config="--psm 6").split())
        want = "".join(block["rows"])
        cer = min(1.0, edit_distance(read, want) / len(want))
        result[block["size"]] = round(cer, 3)
        log.debug(f"{block['size']:>2} pt  cer={cer:.3f}  read={read[:40]!r}...")
    return result
