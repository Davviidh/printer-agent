"""Answer key: try ALL 128 settings on the fake printer (no paper).

Then compare with the optimiser's latest run: did its 12 tries find the
best, or close to it?

Run:  .venv/bin/python quality/check_all.py        (about 4 minutes)
      .venv/bin/python quality/check_all.py 5      (only the first 5, a quick test)
      add --save-images to keep a picture of every fake print
      (in quality/runs/check_all_<date_time>/)
"""

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import measure  # noqa: E402
import optimise  # noqa: E402
import sim_print  # noqa: E402

log = logging.getLogger("check_all")


def label(s):
    return f"density {s['density']:>2}, toner save {'on ' if s['toner_save'] else 'off'}, gamma {s['gamma']}"


def main(limit=None, save_images=False):
    rng = np.random.default_rng(optimise.SEED)
    settings = optimise.ALL[:limit] if limit else optimise.ALL
    img_dir = HERE / "runs" / f"check_all_{time.strftime('%Y%m%d_%H%M%S')}"
    if save_images:
        img_dir.mkdir(parents=True)
    results = []
    for i, s in enumerate(settings, 1):
        photo, toner = sim_print.print_and_photo(**s, rng=rng)
        if save_images:
            sim_print.save_picture(photo, img_dir / f"density{s['density']:02d}_save{'On' if s['toner_save'] else 'Off'}"
                                  f"_gamma{s['gamma']}")
        score, readability = optimise.score(measure.cer_per_size(photo), toner)
        results.append({"settings": s, "score": round(score, 3)})
        log.info(f"{i:>3}/{len(settings)}  {label(s)}  score {score:.3f}")

    results.sort(key=lambda r: r["score"], reverse=True)
    (HERE / "check_all.json").write_text(json.dumps(results, indent=1))
    if save_images:
        log.info(f"pictures: {img_dir}")
    log.info("TOP 5 of all settings:")
    for rank, r in enumerate(results[:5], 1):
        log.info(f"  {rank}. {label(r['settings'])}  score {r['score']}")

    runs = sorted(HERE.glob("run_*.json"))
    if runs:
        run = json.loads(runs[-1].read_text())
        n = len(run["tries"])
        picks = {"best single try": max(run["tries"], key=lambda t: t["score"])["settings"]}
        if "recommended" in run:
            picks["GP recommendation"] = run["recommended"]
        for name, pick in picks.items():
            found = [(i, r) for i, r in enumerate(results, 1) if r["settings"] == pick]
            if not found:
                log.info(f"Optimiser ({n} tries), {name}: {label(pick)} - not in this partial check")
                continue
            rank, r = found[0]
            log.info(f"Optimiser ({n} tries), {name}: {label(pick)} -> rank {rank} of "
                     f"{len(results)}, {results[0]['score'] - r['score']:.3f} below the best")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for name in ("PIL", "pytesseract"):
        logging.getLogger(name).setLevel(logging.WARNING)
    numbers = [a for a in sys.argv[1:] if a.isdigit()]
    main(int(numbers[0]) if numbers else None, save_images="--save-images" in sys.argv)
