"""Rank short-worthy moments in a stream VOD from three signals on VOD time.

  - the streamer: excited phrases and fast talk in a word-timed transcript
  - chat: messages (laughs and hype weigh more) arriving 3-25 s after the moment, i.e. viewer latency
  - the game: big fights, comebacks, blunders and game ends from replay analysis

Each signal is normalised by its own 95th percentile so a chatty day doesn't drown the others, then
30 s windows are scored and the best non-overlapping ones kept, with their transcript, for an editor
to pick from.

Inputs (JSON):
  transcript: [{"start", "end", "text", "words": [...]}]
  chat:       [{"t": seconds on VOD time, "text": "..."}]
  game:       [{"t": seconds on VOD time, "kind": "fight" | "comeback" | "blunder" | "end", "weight"?: float, "tag"?: "..."}]
              (weight 0 only tags the moment, e.g. a sub or a raid)

  python -m shortslab.moments transcript.json --chat chat.json --game game.json --top 30
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass

HOT = {
    r"\boh my god\b": 3, r"\bholy (shit|crap|cow|moly)\b": 3, r"\blet'?s go+\b": 3, r"\bno no no\b": 3,
    r"\bwhat the (fuck|hell|heck)\b": 3, r"\bare you (kidding|serious)\b": 3, r"\bi can'?t believe\b": 2,
    r"\bwhat\?": 1, r"\bdude\b": 1, r"\bha(ha)+\b": 2, r"\blol\b": 1, r"\bgg\b": 1, r"\bclutch\b": 2,
    r"\binsane\b": 2, r"\bunbelievable\b": 2, r"\bcome on\b": 1, r"\bwow\b": 1, r"\byes+\b": 1, r"\bnooo+\b": 2,
}
LAUGH = re.compile(r"(?i)\b(lul|kekw|omegalul|lmao+|lol+|haha+|xd)\b|😂|🤣")
HYPE = re.compile(r"(?i)\b(pog\w*|gg+|wtf|omg|holy|insane|clutch|nuts|wow|letsgo|let'?s go)\b|!!")
GAME_WEIGHT = {"fight": 2, "comeback": 4, "blunder": 1.5, "end": 2}


@dataclass
class Moment:
    rank: int
    start: int
    end: int
    score: float
    streamer: float
    chat: float
    game: float
    tags: list[str]
    text: str


def rank(transcript: list[dict], chat: list[dict] = (), game: list[dict] = (), top: int = 40,
         step: int = 5, window: int = 30, hot: dict[str, float] | None = None) -> list[Moment]:
    """The best non-overlapping windows, best first. hot: phrase regex -> weight (default HOT)."""
    hot = HOT if hot is None else hot
    end = int(transcript[-1]["end"]) + window if transcript else window
    n = end // step + 1
    me, ch, gm = [0.0] * n, [0.0] * n, [0.0] * n
    tags: list[set[str]] = [set() for _ in range(n)]

    def at(sec: float) -> int:
        return max(0, min(n - 1, int(sec // step)))

    for s in transcript:
        x = s["text"].lower()
        sc = sum(w * len(re.findall(p, x)) for p, w in hot.items())
        if len(s.get("words", [])) / max(0.5, s["end"] - s["start"]) > 3.6:
            sc += 1  # fast, excited talk
        if "!" in s["text"]:
            sc += 0.5
        me[at(s["start"])] += sc
    for m in chat:
        w = 1 + 1.5 * bool(LAUGH.search(m["text"])) + bool(HYPE.search(m["text"]))
        for k in range(3, 26, step):  # credit the moment chat is reacting to
            ch[at(m["t"] - k)] += w / 5
    for e in game:
        gm[at(e["t"])] += e.get("weight", GAME_WEIGHT.get(e["kind"], 1))
        tags[at(e["t"])].add(e.get("tag") or e["kind"])

    def norm(a: list[float]) -> list[float]:
        p95 = sorted(a)[int(len(a) * 0.95)] or 1
        return [min(2.0, v / p95) for v in a]

    me, ch, gm = norm(me), norm(ch), norm(gm)
    w = window // step
    scored = []
    for i in range(max(0, n - w)):
        sm, sc, sg = sum(me[i:i + w]), sum(ch[i:i + w]), sum(gm[i:i + w])
        # the streamer and chat reacting together is the strongest sign
        scored.append((1.2 * sm + 1.0 * sc + 0.8 * sg + 0.6 * min(sm, sc), i, sm, sc, sg))
    scored.sort(reverse=True)
    taken: list[tuple] = []
    for t in scored:
        if any(abs(t[1] - u[1]) < w * 1.5 for u in taken):
            continue
        taken.append(t)
        if len(taken) >= top:
            break
    out = []
    for r, (s, i, sm, sc, sg) in enumerate(taken, 1):
        a, b = i * step, (i + w) * step
        text = " ".join(x["text"] for x in transcript if x["end"] > a - 5 and x["start"] < b + 5)
        tg = sorted(set().union(*tags[max(0, i - 2):i + w + 2]))
        out.append(Moment(r, a, b, round(s, 2), round(sm, 2), round(sc, 2), round(sg, 2), tg, text))
    return out


def hms(s: float) -> str:
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("transcript")
    ap.add_argument("--chat")
    ap.add_argument("--game")
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()
    load = lambda p: json.load(open(p, encoding="utf-8")) if p else []
    for m in rank(load(a.transcript), load(a.chat), load(a.game), a.top):
        print(f"#{m.rank:2} {hms(m.start)}-{hms(m.end)} score {m.score:5.2f} "
              f"(streamer {m.streamer:.1f} chat {m.chat:.1f} game {m.game:.1f})  {' '.join(m.tags)}")
        print("     ", m.text[:600])


if __name__ == "__main__":
    main()
