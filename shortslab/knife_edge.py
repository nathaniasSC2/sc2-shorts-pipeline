"""Knife-edge calibration: tune one side's unit count until a fight is a coin flip.

Each matchup ("N zerglings vs 1 Thor") has a variable count for side A. The search finds the
smallest N that wins: start at the geometric middle of the allowed range, grow or halve to bracket
the edge, bisect, then fight once more at the edge and once just below it to confirm. Every trial
goes to an append-only JSONL store, the lab's memory of what beat what, so a rerun or a related
matchup can start from evidence instead of from scratch.

A fight result is a dict: {"winner": "a" | "b" | "timeout-a" | "timeout-b" | "error",
"a_hp_frac": float, "b_hp_frac": float} (the share of each army's total HP left at the end).
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class Matchup:
    slug: str
    lo: int = 1  # the allowed range for side A's count
    hi: int = 200
    fixed: int | None = None  # a hand-set count: fight it once, no search


def score(result: dict) -> float:
    """> 0: A won (by what it had left); < 0: B won; a timeout compares what each had left."""
    w = result.get("winner")
    if w == "a":
        return max(result["a_hp_frac"], 1e-3)
    if w == "b":
        return -max(result["b_hp_frac"], 1e-3)
    if w in ("timeout-a", "timeout-b"):
        return result["a_hp_frac"] - result["b_hp_frac"]
    return 0.0


@dataclass
class Search:
    """The search for one matchup. Ask next_count() for the next count to fight, record() the result."""

    mu: Matchup
    tries: dict[int, list[float]] = field(default_factory=dict)
    lose: int | None = None  # the largest count seen to lose
    win: int | None = None  # the smallest count seen to win
    final: int | None = None
    note: str = ""
    error: str | None = None
    _confirm: list[int] = field(default_factory=list)
    _confirming: bool = False

    def record(self, n: int, result: dict) -> None:
        if result.get("winner") == "error":
            self.error = result.get("error") or "error"
            return
        s = score(result)
        self.tries.setdefault(n, []).append(s)
        if not self._confirming:
            if s > 0:
                self.win = n if self.win is None else min(self.win, n)
            else:
                self.lose = n if self.lose is None else max(self.lose, n)

    def next_count(self) -> int | None:
        """The next count to fight, or None when the search is over (see final and note)."""
        mu = self.mu
        if self.error:
            return None
        if mu.fixed is not None:
            if mu.fixed in self.tries:
                self.final, self.note = mu.fixed, "fixed"
                return None
            return mu.fixed
        if self._confirming:
            if self._confirm:
                return self._confirm.pop(0)
            w = self.win
            won_again = self.tries[w][-1] > 0
            self.final = w if won_again else min(w + 1, mu.hi)
            self.note = f"edge at {w}: won {sum(x > 0 for x in self.tries[w])}/{len(self.tries[w])}"
            return None
        if self.win is None and self.lose is None:
            return max(mu.lo, min(mu.hi, round(math.sqrt(mu.lo * mu.hi))))
        if self.win is None:  # only losses: grow
            if self.lose >= mu.hi:
                self.final, self.note = mu.hi, "lopsided: B wins even at the top of the range"
                return None
            return min(mu.hi, max(self.lose + 1, self.lose * 2))
        if self.lose is None:  # only wins: halve
            if self.win <= mu.lo:
                self.final, self.note = mu.lo, "lopsided: A wins even at the bottom of the range"
                return None
            return max(mu.lo, self.win // 2)
        if self.win - self.lose > 1:
            return (self.win + self.lose) // 2
        self._confirming = True
        self._confirm = [self.win] + ([self.win - 1] if self.win - 1 >= mu.lo else [])
        return self.next_count()

    def summary(self) -> dict:
        at = self.tries.get(self.final, []) if self.final is not None else []
        return {"n": self.final, "note": self.note, "error": self.error,
                "margin": round(sum(abs(x) for x in at) / len(at), 3) if at else None,
                "tries": {str(k): [round(x, 3) for x in v] for k, v in sorted(self.tries.items())}}


class Store:
    """Every trial ever fought, one JSON line each. Appends are line-sized, so parallel sessions can share it."""

    def __init__(self, path: Path | str, engine: int = 1) -> None:
        self.path, self.engine = Path(path), engine

    def remember(self, slug: str, n: int, result: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "engine": self.engine, "slug": slug, "n": n, "result": result}) + "\n")

    def evidence(self) -> dict[str, dict[int, list[float]]]:
        """slug -> count -> scores, for trials fought by the current engine version."""
        out: dict[str, dict[int, list[float]]] = {}
        if not self.path.exists():
            return out
        for line in self.path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("engine") != self.engine or r["result"].get("winner") in (None, "error"):
                continue
            out.setdefault(r["slug"], {}).setdefault(int(r["n"]), []).append(score(r["result"]))
        return out


def calibrate(mu: Matchup, fight: Callable[[int], dict], store: Store | None = None) -> dict:
    """Run one matchup's search to the end, fighting with fight(n). Returns Search.summary()."""
    s = Search(mu)
    while (n := s.next_count()) is not None:
        result = fight(n)
        if store is not None:
            store.remember(mu.slug, n, result)
        s.record(n, result)
    return s.summary()
