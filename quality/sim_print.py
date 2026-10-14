"""Fake printer + fake phone photo for the print-quality loop. No paper.

It is a made-up model, not physics. It only has to behave like a laser
printer in the ways that matter here:
- too little toner: thin strokes break up and letters fade
- too much toner: strokes spread, small letters merge into blobs
- toner save: about half the toner, so everything is lighter
- gamma: shifts the result a little lighter or darker
- every print and photo is slightly different (random noise)

How it works: blur the perfect page, then keep as ink everything above a
threshold. A dark setting lowers the threshold (fatter letters), a light
one raises it (thinner, broken letters).
"""

import logging
from pathlib import Path

import numpy as np
from pdf2image import convert_from_path
from PIL import Image, ImageFilter

HERE = Path(__file__).parent
log = logging.getLogger("sim_print")

DPI = 300            # printer resolution of the fake print
PHOTO_DPI = 200      # the phone photo is a bit less sharp
_page = None


def _perfect_page():
    global _page
    if _page is None:
        _page = convert_from_path(HERE / "test_page.pdf", dpi=DPI, grayscale=True)[0]
    return _page


def darkness(density, toner_save, gamma):
    """Settings -> one number, 0 (no toner) to about 1 (very dark)."""
    d = density / 16
    if toner_save:
        d *= 0.55
    return d * (1.4 / gamma) ** 0.5


def print_and_photo(density=4, toner_save=False, gamma=1.4, rng=None):
    """Returns (photo of the printed page, toner used as % of page area)."""
    rng = rng or np.random.default_rng()
    d = darkness(density, toner_save, gamma)
    ink = 1 - np.asarray(_perfect_page(), dtype=float) / 255           # 1 = black
    spread = np.asarray(Image.fromarray((ink * 255).astype(np.uint8))
                        .filter(ImageFilter.GaussianBlur(2.2)), dtype=float) / 255
    spread += rng.normal(0, 0.05, spread.shape)                         # toner grain
    threshold = np.clip(0.62 - 0.55 * d, 0.12, 0.95)   # floor: no toner on blank paper
    printed = (spread > threshold) * min(1.0, 0.35 + 1.2 * d)          # light = grey
    toner = 100 * printed.mean()

    # the phone photo: a bit of blur, lower resolution, sensor noise
    paper = Image.fromarray((255 * (1 - printed)).astype(np.uint8))
    photo = paper.filter(ImageFilter.GaussianBlur(0.8)).resize(
        (int(paper.width * PHOTO_DPI / DPI), int(paper.height * PHOTO_DPI / DPI)))
    photo = np.asarray(photo, dtype=float) + rng.normal(0, 6, (photo.height, photo.width))
    photo = Image.fromarray(np.clip(photo, 0, 255).astype(np.uint8))
    log.debug(f"density={density} save={toner_save} gamma={gamma} -> "
              f"darkness={d:.2f} toner={toner:.2f}%")
    return photo, toner
