import unittest

from shortslab.fights import fights, hero_runs, pretty

try:
    import numpy as np
except ImportError:  # align needs numpy: pip install -e .[audio]
    np = None


def death(t, mine, unit="Marine", value=50, killer=None, killer_id=None, worker=False, hall=False):
    return {"t": t, "mine": mine, "unit": unit, "value": value, "worker": worker, "building": hall, "hall": hall,
            "killer": killer, "killer_id": killer_id, "killer_mine": None if killer is None else not mine}


class FightsTest(unittest.TestCase):
    def test_clusters_on_gaps_and_drops_skirmishes(self):
        ds = [death(100 + i, False, value=100, killer="Cyclone", killer_id=1) for i in range(6)]   # 600: a fight
        ds += [death(120, True, value=50), death(121, False, value=50)]                           # 100: a skirmish
        ds += [death(200 + i * 0.5, i % 2 == 0, value=200, killer="Marine", killer_id=2) for i in range(8)]
        fs = fights(ds)
        self.assertEqual([(f["start"], f["end"]) for f in fs], [(100, 105), (200, 203.5)])
        self.assertEqual((fs[0]["killed"], fs[0]["lost"], fs[0]["net"]), (600, 0, 600))
        self.assertEqual(fs[0]["killers"], [("Cyclone", 6)])
        self.assertEqual(fs[1]["net"], 0)

    def test_peak_is_where_most_value_dies(self):
        ds = [death(10, False, value=100), death(14, False, value=100), death(20, False, value=400),
              death(21, True, value=400), death(25, False, value=100)]
        self.assertEqual(fights(ds)[0]["peak"], 20)

    def test_workers_and_halls(self):
        ds = [death(50 + i, False, unit="SCV", worker=True, value=50) for i in range(10)]
        ds.append(death(58, False, unit="Command Center", value=400, hall=True))
        f = fights(ds)[0]
        self.assertEqual((f["workers_killed"], f["workers_lost"], f["halls"]), (10, 0, ["theirs Command Center"]))

    def test_hero_run_needs_six_kills_inside_20s(self):
        ds = [death(300 + i * 3, False, killer="Battlecruiser", killer_id=7) for i in range(8)]   # 7 inside 20 s
        ds += [death(300 + i * 5, False, killer="Thor", killer_id=8) for i in range(5)]
        runs = hero_runs(ds)
        self.assertEqual(runs, [{"unit": "Battlecruiser", "kills": 7, "total": 8, "start": 300}])

    def test_pretty_names(self):
        self.assertEqual(pretty("SiegeTankSieged"), "Siege Tank")
        self.assertEqual(pretty("HellionTank"), "Hellbat")
        self.assertEqual(pretty("PlanetaryFortress"), "Planetary Fortress")


@unittest.skipIf(np is None, "numpy not installed")
class AlignTest(unittest.TestCase):
    def test_finds_offset_in_noise(self):
        from shortslab.align import offset

        rng = np.random.default_rng(3)
        sr = 8000
        ref = rng.standard_normal(24 * sr).astype(np.float32)
        start = 5.375
        clip = ref[int(start * sr): int(start * sr) + 8 * sr] + 0.5 * rng.standard_normal(8 * sr).astype(np.float32)
        at, score = offset(clip, ref, sr)
        self.assertAlmostEqual(at, start, places=4)
        self.assertGreater(score, 0.8)

    def test_no_match_scores_low(self):
        from shortslab.align import offset

        rng = np.random.default_rng(4)
        _, score = offset(rng.standard_normal(8000 * 8).astype(np.float32),
                          rng.standard_normal(8000 * 24).astype(np.float32))
        self.assertLess(score, 0.1)


if __name__ == "__main__":
    unittest.main()
