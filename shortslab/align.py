"""Find where a downloaded VOD section really starts, by matching its audio against the full audio track.

yt-dlp cuts a section on the keyframe before the second you asked for, so its first frame can sit a few
seconds early. Cut points chosen on the transcript's word times would then land mid-word. Instead: take
the section's first 8 s of audio and cross-correlate it (FFT) against 24 s of the full track around the
asked-for start; the peak is the true start, and its height says how clean the match was.

  python -m shortslab.align SECTION.mp4 AUDIO.m4a NOMINAL
"""
from __future__ import annotations

import argparse
import subprocess

import numpy as np

SR = 8000  # plenty for speech and game sound, and fast


def pcm(path: str, ss: float | None = None, dur: float | None = None, sr: int = SR) -> np.ndarray:
    """Mono float32 samples of a media file's audio (ffmpeg), from ss for dur seconds."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-i", path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32)


def offset(clip: np.ndarray, ref: np.ndarray, sr: int = SR) -> tuple[float, float]:
    """Seconds into ref where clip begins, and the match score (near 1 for a clean match, near 0 for none)."""
    clip = (clip - clip.mean()) / (clip.std() + 1e-9)
    ref = (ref - ref.mean()) / (ref.std() + 1e-9)
    n = len(clip) + len(ref)
    f = np.fft.irfft(np.fft.rfft(ref, n) * np.conj(np.fft.rfft(clip, n)), n)
    lag = int(np.argmax(f[: len(ref)]))
    return lag / sr, float(f[lag] / len(clip))


def true_start(section: str, audio: str, nominal: float, lead: float = 8.0, clip: float = 8.0,
               span: float = 24.0, sr: int = SR) -> tuple[float, float]:
    """Second of the full track where section's first sample sits, and the match score. nominal is the start
    that was asked for; the search covers lead seconds before it to span - lead after."""
    ref0 = max(0, nominal - lead)
    off, score = offset(pcm(section, 0, clip, sr), pcm(audio, ref0, span, sr), sr)
    return ref0 + off, score


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("section", help="the downloaded section")
    ap.add_argument("audio", help="the full VOD's audio track")
    ap.add_argument("nominal", type=float, help="the VOD second the section was asked to start at")
    a = ap.parse_args()
    s0, score = true_start(a.section, a.audio, a.nominal)
    print(f"starts at {s0:.3f} ({s0 - a.nominal:+.3f} s from the asked start; match {score:.2f})")


if __name__ == "__main__":
    main()
