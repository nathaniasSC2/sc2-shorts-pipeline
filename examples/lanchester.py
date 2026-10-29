"""Calibrate a few matchups against a toy fight model instead of the game.

In production fight(n) spawns both armies in the real engine and reports what was left; here it's
Lanchester's square law with some noise, which is enough to watch the search bracket and bisect.

  python examples/lanchester.py
"""
import random

from shortslab.knife_edge import Matchup, calibrate

# side A unit: (hp, dps); side B: (count, hp, dps)
MATCHUPS = {
    "zerglings-vs-thor": ((35, 10), (1, 400, 40)),
    "marines-vs-ultralisks": ((45, 9.8), (2, 500, 35)),
    "scvs-vs-archon": ((45, 5), (1, 360, 25)),
}


def fight(a_unit, b_side, n, rng):
    """Square law: strength is count^2 * hp * dps; the stronger side wins with sqrt(1 - weaker/stronger) left."""
    (ahp, adps), (bn, bhp, bdps) = a_unit, b_side
    sa = n * n * ahp * adps * rng.uniform(0.85, 1.15)  # surface area, pathing, focus fire: noise
    sb = bn * bn * bhp * bdps
    if sa > sb:
        return {"winner": "a", "a_hp_frac": (1 - sb / sa) ** 0.5, "b_hp_frac": 0.0}
    return {"winner": "b", "a_hp_frac": 0.0, "b_hp_frac": (1 - sa / sb) ** 0.5}


if __name__ == "__main__":
    rng = random.Random(7)
    for slug, (a, b) in MATCHUPS.items():
        trials = []

        def f(n):
            trials.append(n)
            return fight(a, b, n, rng)

        r = calibrate(Matchup(slug, lo=1, hi=200), f)
        print(f"{slug:24} n={r['n']:3}  margin {r['margin']}  {r['note']}  (fought {trials})")
