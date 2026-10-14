"""The smart taster: Bayesian optimisation of the print settings.

Loop:  try settings -> print -> photo -> OCR -> score -> pick next settings

Score (David's choice B, balanced):
    score = readability - TONER_PENALTY * toner used
    toner used: 1.0 = the ink a perfect print of the letters needs, 2.0 = twice
    readability = 1 - average OCR error rate over the 4..12 pt lines

Picking the next settings: a Gaussian process (GP) learns a rough map
"settings -> score" from the tries so far, with an uncertainty for every
point. Expected improvement (EI) then rates each untried setting by how
much better than the best so far it could be. High EI comes from a good
predicted score (exploitation) OR a big uncertainty (exploration).

Run on the fake printer:  .venv/bin/python quality/optimise.py
Also save each fake print:  .venv/bin/python quality/optimise.py --save-images
  (pictures go to quality/runs/<date_time>/)
"""

import json
import logging
import sys
import time
from itertools import product
from pathlib import Path

import numpy as np
from scipy.stats import norm
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import measure  # noqa: E402
import sim_print  # noqa: E402

log = logging.getLogger("optimise")

# Each extra "1x" of toner costs 0.05 readability. This keeps the balance of
# the first version (0.1 per % of page, when the page had 1/5 of the text).
TONER_PENALTY = 0.05
SEED = 509

# every setting the printer driver allows for these three knobs
DENSITIES = range(1, 17)
TONER_SAVE = [False, True]
GAMMAS = [1.0, 1.4, 1.8, 2.2]
ALL = [dict(density=d, toner_save=s, gamma=g) for d, s, g in product(DENSITIES, TONER_SAVE, GAMMAS)]


def features(s):
    """Settings -> numbers between 0 and 1, which is what the GP works with."""
    return [(s["density"] - 1) / 15, float(s["toner_save"]), (s["gamma"] - 1.0) / 1.2]


def score(cer, toner):
    readability = 1 - float(np.mean(list(cer.values())))
    return readability - TONER_PENALTY * toner, readability


def expected_improvement(mu, sigma, best):
    sigma = np.maximum(sigma, 1e-9)
    z = (mu - best) / sigma
    return (mu - best) * norm.cdf(z) + sigma * norm.pdf(z)


def fit_gp(tried):
    X = np.array([features(t["settings"]) for t in tried])
    y = np.array([t["score"] for t in tried])
    # Matern: nearby settings give similar scores. WhiteKernel: measurements are noisy.
    return GaussianProcessRegressor(Matern(length_scale=0.3, nu=2.5) + WhiteKernel(0.01),
                                    normalize_y=True, random_state=SEED).fit(X, y)


def recommend(tried):
    """The final answer: the setting the GP PREDICTS is best, using all tries
    together, instead of the single try that happened to score highest
    (which may just have been lucky). Only tried settings are candidates, so
    the answer is always something we actually saw on paper."""
    gp = fit_gp(tried)
    mu = gp.predict(np.array([features(t["settings"]) for t in tried]))
    i = int(np.argmax(mu))
    return tried[i]["settings"], round(float(mu[i]), 3)


def next_setting(tried, rng):
    """First 3 tries spread out on purpose, then the GP + EI decide."""
    untried = [s for s in ALL if s not in [t["settings"] for t in tried]]
    if len(tried) < 3:
        starts = [dict(density=3, toner_save=False, gamma=1.4),
                  dict(density=12, toner_save=True, gamma=1.0),
                  dict(density=8, toner_save=False, gamma=2.2)]
        return starts[len(tried)], None
    y = np.array([t["score"] for t in tried])
    gp = fit_gp(tried)
    mu, sigma = gp.predict(np.array([features(s) for s in untried]), return_std=True)
    ei = expected_improvement(mu, sigma, y.max())
    i = int(np.argmax(ei))
    return untried[i], {"predicted": round(float(mu[i]), 3),
                        "uncertainty": round(float(sigma[i]), 3), "ei": round(float(ei[i]), 4)}


def run(tries=12, printer="sim", save_images=False):
    rng = np.random.default_rng(SEED)
    tried = []
    stamp = time.strftime('%Y%m%d_%H%M%S')
    img_dir = HERE / "runs" / stamp
    if save_images:
        img_dir.mkdir(parents=True)
    for n in range(1, tries + 1):
        settings, why = next_setting(tried, rng)
        if printer != "sim":
            raise NotImplementedError("real printer comes later")
        photo, toner = sim_print.print_and_photo(**settings, rng=rng)
        cer = measure.cer_per_size(photo)
        if save_images:
            name = (f"try{n:02d}_density{settings['density']}_save{'On' if settings['toner_save'] else 'Off'}"
                    f"_gamma{settings['gamma']}")
            sim_print.save_picture(photo, img_dir / name)
        s, readability = score(cer, toner)
        tried.append({"try": n, "settings": settings, "score": round(s, 3),
                      "readability": round(readability, 3), "toner": round(toner, 2),
                      "cer": cer, "why": why})
        best = max(tried, key=lambda t: t["score"])
        log.info(f"try {n:>2}: density {settings['density']:>2} save {str(settings['toner_save']):5} "
                 f"gamma {settings['gamma']}  -> readability {readability:.2f} toner {toner:.2f}x "
                 f"score {s:.3f}   (best so far: try {best['try']})"
                 + (f"   [GP predicted {why['predicted']} +/- {why['uncertainty']}]" if why else "   [start]"))
    rec, predicted = recommend(tried)
    out = HERE / f"run_{stamp}.json"
    out.write_text(json.dumps({"penalty": TONER_PENALTY, "tries": tried,
                               "best_measured": best["settings"],
                               "recommended": rec, "recommended_predicted": predicted},
                              indent=1))
    log.info(f"best single try:  {best['settings']} measured {best['score']}")
    log.info(f"RECOMMENDED (GP): {rec} predicted {predicted} -> saved {out.name}")
    if save_images:
        log.info(f"pictures of all {tries} fake prints: {img_dir}")
    return tried


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(HERE / "optimise.log")])
    run(save_images="--save-images" in sys.argv)
