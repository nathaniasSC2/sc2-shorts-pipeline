"""The densest kill bursts per unit in StarCraft II replays: the money shots for a 30 s unit cut.

Reads each replay's death events with sc2reader, credits kills to the killing unit (folding mode
names like SiegeTankSieged into "Siege Tank"), and finds 4 s windows with the most kills, at least
6 s apart. Optionally maps game time onto a VOD with the line clocksync fitted.

  python -m shortslab.bursts REPLAY... --player "Name" --units "Battlecruiser,Thor"
"""
from __future__ import annotations

import argparse
import json

LPS = 22.4  # game loops per second at Faster speed
MODES = {"HellionTank": "Hellbat", "BattleHellion": "Hellbat", "SiegeTankSieged": "Siege Tank", "SiegeTank": "Siege Tank",
         "ThorAP": "Thor", "LiberatorAG": "Liberator", "WidowMineBurrowed": "Widow Mine", "CycloneLockOn": "Cyclone",
         "VikingFighter": "Viking", "VikingAssault": "Viking", "PlanetaryFortress": "Planetary Fortress"}
NOT_KILLS = ("Larva", "Egg", "Broodling", "Interceptor", "Locust", "Creep", "Changeling")
WORKERS = ("SCV", "Probe", "Drone")


def unit_name(name: str) -> str:
    return MODES.get(name, name)


def densest(kills: list[tuple[float, bool, bool]], window: float = 4.0, min_kills: int = 4,
            spacing: float = 6.0) -> list[dict]:
    """kills: (game second, was a worker, was a building). The densest windows, densest first.
    Each has its start t in game seconds (unrounded, for mapping onto a VOD) and its m:ss clock."""
    ks = sorted(kills)
    best = []
    for t, _, _ in ks:
        win = [k for k in ks if t <= k[0] < t + window]
        best.append((len(win), t, sum(k[1] for k in win), sum(k[2] for k in win)))
    best.sort(key=lambda b: (-b[0], b[1]))
    used, out = [], []
    for n, t, workers, buildings in best:
        if n < min_kills or any(abs(t - u) < spacing for u in used):
            continue
        used.append(t)
        out.append({"n": n, "t": t, "workers": workers, "buildings": buildings,
                    "clock": f"{int(t // 60)}:{int(t % 60):02d}"})
    return out


def kills_by_unit(replay, player, units: set[str]) -> dict[str, list[tuple[float, bool, bool]]]:
    """Kills by each of player's units (a name, or one of replay.players), keyed by folded unit name."""
    me = player
    if isinstance(player, str):
        me = next((p for p in replay.players if p.name == player), None)
        if me is None:
            raise SystemExit(f"no player {player!r} in {replay.filename}; players: {', '.join(p.name for p in replay.players)}")
    out: dict[str, list[tuple[float, bool, bool]]] = {}
    for e in replay.tracker_events:
        if type(e).__name__ != "UnitDiedEvent" or e.unit is None or e.unit.owner is None or e.unit.owner is me:
            continue
        ku = getattr(e, "killing_unit", None)
        if ku is None or ku.owner is not me or unit_name(ku.name) not in units:
            continue
        victim = e.unit.name or ""
        if any(s in victim for s in NOT_KILLS):
            continue
        out.setdefault(unit_name(ku.name), []).append((e.frame / LPS, victim in WORKERS, e.unit.is_building))
    return out


def main() -> None:
    import sc2reader

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("replays", nargs="+")
    ap.add_argument("--player", required=True, help="the player whose units' kills count")
    ap.add_argument("--units", default="Cyclone,Battlecruiser,Hellion,Hellbat")
    ap.add_argument("--vod0", type=float, help="VOD second of game 0:00 (from clocksync)")
    ap.add_argument("--rate", type=float, default=1.0, help="VOD seconds per game second (from clocksync)")
    a = ap.parse_args()
    units = set(a.units.split(","))
    for path in a.replays:
        r = sc2reader.load_replay(path, load_level=4)
        for unit, ks in kills_by_unit(r, a.player, units).items():
            for b in densest(ks):
                if a.vod0 is not None:
                    b["vod"] = round(a.vod0 + a.rate * b["t"], 1)
                b["t"] = round(b["t"], 1)
                print(json.dumps({"replay": path, "unit": unit, **b}))


if __name__ == "__main__":
    main()
