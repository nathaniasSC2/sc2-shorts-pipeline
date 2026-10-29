"""Pin a game's 0:00 to a stream VOD by reading the on-screen game clock.

A replay's save time only places a game within ~10 s of the VOD, and the game clock drifts against
VOD time (about 1 s a minute on a real stream, rate ~0.98), so one offset doesn't hold across a
20-minute game. Instead: read the clock every 15 s with tesseract, then fit VOD = vod0 + rate * clock
through the readings, ignoring OCR misreads (a 5 read as a 3 scatters; the truth lies on a line).

  python -m shortslab.clocksync VOD START LENGTH --crop "crop=110:34:487:480,..."
"""
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

CLOCK = re.compile(r"(\d{1,2}):(\d{2})")


def fit(pts: list[tuple[float, float]], tol: float = 1.5, min_inliers: int = 4) -> tuple[float, float, int] | None:
    """Robust line through (vod_second, clock_second) readings: the pair-line with the most readings
    within tol seconds, then least squares on those. Returns (vod0, rate, inliers) or None."""
    best: list[tuple[float, float]] = []
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            (v1, c1), (v2, c2) = pts[i], pts[j]
            if abs(c2 - c1) < 60:
                continue  # too close together to pin a rate
            b = (v2 - v1) / (c2 - c1)
            if not 0.95 < b < 1.05:
                continue
            a = v1 - b * c1
            inl = [(v, c) for v, c in pts if abs(v - (a + b * c)) <= tol]
            if len(inl) > len(best):
                best = inl
    if len(best) < min_inliers:
        return None
    n = len(best)
    mc, mv = sum(c for _, c in best) / n, sum(v for v, _ in best) / n
    b = sum((c - mc) * (v - mv) for v, c in best) / sum((c - mc) ** 2 for _, c in best)
    # +0.5: a clock showing m:ss has been showing it for half a second on average
    return mv - b * mc + 0.5, b, n


def parse_clock(text: str) -> int | None:
    m = CLOCK.fullmatch(text.strip())
    if m and int(m[2]) < 60:
        return int(m[1]) * 60 + int(m[2])
    return None


def read_clock(vod: str, t: float, crops: list[str], tmp: str) -> int | None:
    """OCR the game clock at VOD second t, trying each ffmpeg crop/filter chain in turn."""
    png = f"{tmp}/clock.png"
    for crop in crops:
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", vod, "-frames:v", "1",
                        "-vf", crop, png], check=True)
        out = subprocess.run(["tesseract", png, "-", "--psm", "7", "-c", "tessedit_char_whitelist=0123456789:"],
                             capture_output=True, text=True).stdout
        if (c := parse_clock(out)) is not None:
            return c
    return None


def sync(vod: str, start: float, length: float, crops: list[str], every: float = 15.0):
    """Read the clock through one game (start = the replay-time estimate of its 0:00 on the VOD)."""
    pts = []
    with tempfile.TemporaryDirectory() as tmp:
        t = 30.0
        while t < length - 10:
            if (c := read_clock(vod, start + t, crops, tmp)) is not None:
                pts.append((start + t, c))
            t += every
    return fit(pts), len(pts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("vod")
    ap.add_argument("start", type=float, help="estimated VOD second of the game's 0:00")
    ap.add_argument("length", type=float, help="game length in seconds")
    ap.add_argument("--crop", action="append", required=True, help="ffmpeg -vf chain isolating the clock (repeatable)")
    a = ap.parse_args()
    if not Path(a.vod).exists():
        raise SystemExit(f"no such file: {a.vod}")
    f, n = sync(a.vod, a.start, a.length, a.crop)
    if f is None:
        print(f"too few clean clock readings ({n}); keep the estimate {a.start:.1f}")
    else:
        print(f"vod0 {f[0]:.2f}  rate {f[1]:.5f}  ({f[2]} of {n} readings on the line)")


if __name__ == "__main__":
    main()
