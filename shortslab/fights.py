"""The beats of a StarCraft II game from its replay: fights, hero runs and the army lead.

A gameplay edit compresses a 15-minute game into its beats, so they have to be found first:
  - fights: every death clustered wherever the gap is under 7 s, kept when both sides lost 600
    resources between them, with the peak second (the most value dying within 2 s), who lost what,
    and which of the player's units did the killing
  - hero runs: one unit's most kills inside 20 s, when that's 6 or more
  - the army lead: army value in play, player minus opponent, from the 10 s stats samples, with its low point

  python -m shortslab.fights REPLAY... --player "Name"
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict

LPS = 22.4  # game loops per second at Faster speed
SKIP = re.compile(r"Larva|Egg|Broodling|Interceptor|Locust|AutoTurret|MULE|Changeling|Cocoon|Creep|Shape|Beacon|"
                  r"Adept.*Phase|Disruptor.*Phase|KD8|ParasiticBomb|Lurker.*Egg")
WORKERS = {"SCV", "Probe", "Drone"}
TOWNHALLS = {"CommandCenter", "OrbitalCommand", "PlanetaryFortress", "Nexus", "Hatchery", "Lair", "Hive"}


def clock(s: float) -> str:
    return f"{int(s // 60)}:{int(s % 60):02d}"


def pretty(name: str) -> str:
    """Unit name as a viewer says it: modes folded (SiegeTankSieged is a Siege Tank), words split."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name.replace("SiegeTankSieged", "SiegeTank").replace("VikingAssault", "Viking")
                  .replace("VikingFighter", "Viking").replace("WidowMineBurrowed", "WidowMine").replace("ThorAP", "Thor")
                  .replace("LiberatorAG", "Liberator").replace("HellionTank", "Hellbat").replace("CycloneLockOn", "Cyclone"))


def value(unit) -> int:
    return (getattr(unit, "minerals", 0) or 0) + (getattr(unit, "vespene", 0) or 0)


def deaths(replay, me) -> list[dict]:
    """Every real unit or building that died, in game order, from me's side (mine = me lost it)."""
    out = []
    for e in replay.tracker_events:
        if type(e).__name__ != "UnitDiedEvent" or e.unit is None or e.unit.owner is None:
            continue
        n = e.unit.name or ""
        if SKIP.search(n):
            continue
        ku = getattr(e, "killing_unit", None)
        out.append({"t": e.frame / LPS, "mine": e.unit.owner is me, "unit": pretty(n), "value": value(e.unit),
                    "worker": n in WORKERS, "building": bool(e.unit.is_building), "hall": n in TOWNHALLS,
                    "killer": pretty(ku.name) if ku is not None and ku.name else None,
                    "killer_id": ku.id if ku is not None else None,
                    "killer_mine": (ku.owner is me) if ku is not None and ku.owner is not None else None})
    return out


def fights(ds: list[dict], gap: float = 7.0, min_size: int = 600) -> list[dict]:
    """Deaths (from deaths()) clustered into fights, in game order. Times are game seconds."""
    groups, cur = [], []
    for d in ds:
        if cur and d["t"] - cur[-1]["t"] > gap:
            groups.append(cur)
            cur = []
        cur.append(d)
    if cur:
        groups.append(cur)
    out = []
    for f in groups:
        lost = sum(d["value"] for d in f if d["mine"])
        killed = sum(d["value"] for d in f if not d["mine"])
        if lost + killed < min_size:
            continue
        kill_units = defaultdict(int)
        for d in f:
            if not d["mine"] and d["killer_mine"] and d["killer"]:
                kill_units[d["killer"]] += 1
        peak = max(f, key=lambda d: sum(x["value"] for x in f if abs(x["t"] - d["t"]) <= 2))["t"]
        out.append({"start": round(f[0]["t"], 1), "end": round(f[-1]["t"], 1), "peak": round(peak, 1),
                    "size": lost + killed, "lost": lost, "killed": killed, "net": killed - lost,
                    "workers_killed": sum(1 for d in f if d["worker"] and not d["mine"]),
                    "workers_lost": sum(1 for d in f if d["worker"] and d["mine"]),
                    "halls": [("mine" if d["mine"] else "theirs") + " " + d["unit"] for d in f if d["hall"]],
                    "killers": sorted(kill_units.items(), key=lambda kv: -kv[1])[:4]})
    return out


def hero_runs(ds: list[dict], window: float = 20.0, min_kills: int = 6) -> list[dict]:
    """Each of my units' most kills inside window seconds, best first."""
    by_unit = defaultdict(list)
    for d in ds:
        if not d["mine"] and d["killer_mine"] and d["killer_id"]:
            by_unit[(d["killer_id"], d["killer"])].append(d["t"])
    runs = []
    for (_, uname), ts in by_unit.items():
        ts.sort()
        best = (0, 0)
        j = 0
        for i in range(len(ts)):
            while ts[i] - ts[j] > window:
                j += 1
            if i - j + 1 > best[0]:
                best = (i - j + 1, ts[j])
        if best[0] >= min_kills:
            runs.append({"unit": uname, "kills": best[0], "total": len(ts), "start": round(best[1], 1)})
    runs.sort(key=lambda x: -x["kills"])
    return runs


def army_lead(replay, me, opp) -> tuple[list[dict], dict | None]:
    """Every 10 s: army value in play (me minus opp), resources-lost trade, both armies, both worker counts.
    Also the low point (the sample where me was furthest behind), or None for an empty replay."""
    stats = defaultdict(list)
    for e in replay.tracker_events:
        if type(e).__name__ == "PlayerStatsEvent" and e.pid in (me.pid, opp.pid):
            stats[e.pid].append((e.frame / LPS, e.minerals_used_active_forces + e.vespene_used_active_forces,
                                 e.minerals_lost_army + e.vespene_lost_army, e.workers_active_count))
    lead = []
    for a, b in zip(stats[me.pid], stats[opp.pid]):
        lead.append({"t": round(a[0]), "army": a[1] - b[1], "trade": b[2] - a[2], "my_army": a[1], "their_army": b[1],
                     "workers": [a[3], b[3]]})
    return lead, (min(lead, key=lambda x: x["army"]) if lead else None)


def main() -> None:
    import sc2reader

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("replays", nargs="+")
    ap.add_argument("--player", required=True, help="whose side the beats are told from")
    ap.add_argument("--json", action="store_true", help="one JSON line a replay instead of a beat sheet")
    a = ap.parse_args()
    for path in a.replays:
        r = sc2reader.load_replay(path, load_level=4)
        me = next((p for p in r.players if p.name == a.player), None)
        if me is None or len(r.players) != 2:
            print(f"skip {path}: not a 1v1 with {a.player!r}")
            continue
        opp = next(p for p in r.players if p is not me)
        ds = deaths(r, me)
        fs, runs = fights(ds), hero_runs(ds)
        lead, low = army_lead(r, me, opp)
        if a.json:
            print(json.dumps({"replay": path, "result": me.result, "opp": opp.name, "fights": fs, "hero_runs": runs[:5],
                              "low": low}))
            continue
        print(f"\n{me.result} vs {opp.name} ({opp.play_race}) {r.map_name} {clock(r.frames / LPS)}")
        if low and low["army"] < -1500:
            print(f"   behind by {-low['army']} army value at {clock(low['t'])}")
        for f in sorted(fs, key=lambda x: -x["size"])[:6]:
            tag = "WON " if f["net"] > 300 else "LOST" if f["net"] < -300 else "EVEN"
            print(f"   fight {tag} {clock(f['start'])}-{clock(f['end'])} peak {clock(f['peak'])} size {f['size']} "
                  f"net {f['net']:+} by {f['killers']}")
        for h in runs[:3]:
            print(f"   hero run: {h['unit']} {h['kills']} kills in 20 s from {clock(h['start'])}, {h['total']} total")


if __name__ == "__main__":
    main()
