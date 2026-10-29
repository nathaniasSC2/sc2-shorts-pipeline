import tempfile
import unittest
from pathlib import Path

from shortslab.knife_edge import Matchup, Search, Store, calibrate, score


def threshold(edge):
    """A deterministic fight: A wins from `edge` units up, by more the further past it."""
    def fight(n):
        if n >= edge:
            return {"winner": "a", "a_hp_frac": min(1, (n - edge + 1) / edge), "b_hp_frac": 0}
        return {"winner": "b", "a_hp_frac": 0, "b_hp_frac": min(1, (edge - n) / edge)}
    return fight


class KnifeEdgeTest(unittest.TestCase):
    def test_finds_the_edge(self):
        for edge in (1, 2, 7, 13, 64, 150, 200):
            r = calibrate(Matchup("x", lo=1, hi=200), threshold(edge))
            self.assertEqual(r["n"], edge, edge)

    def test_few_trials(self):
        tried = []
        f = threshold(37)
        calibrate(Matchup("x", lo=1, hi=200), lambda n: (tried.append(n), f(n))[1])
        self.assertLessEqual(len(tried), 12)  # bracket + bisect + 2 confirmations

    def test_lopsided(self):
        r = calibrate(Matchup("x", lo=1, hi=50), threshold(500))
        self.assertEqual((r["n"], r["note"][:8]), (50, "lopsided"))
        r = calibrate(Matchup("x", lo=5, hi=50), threshold(1))
        self.assertEqual(r["n"], 5)

    def test_fixed_count_fights_once(self):
        tried = []
        calibrate(Matchup("x", fixed=12), lambda n: (tried.append(n), threshold(3)(n))[1])
        self.assertEqual(tried, [12])

    def test_error_stops(self):
        r = calibrate(Matchup("x"), lambda n: {"winner": "error", "error": "client crashed"})
        self.assertEqual((r["n"], r["error"]), (None, "client crashed"))

    def test_timeout_compares_what_was_left(self):
        self.assertGreater(score({"winner": "timeout-a", "a_hp_frac": 0.6, "b_hp_frac": 0.2}), 0)
        self.assertLess(score({"winner": "timeout-b", "a_hp_frac": 0.1, "b_hp_frac": 0.2}), 0)

    def test_confirmation_loss_moves_up_one(self):
        # wins at 10 the first time, loses there on the confirmation fight
        seen = {}

        def fight(n):
            seen[n] = seen.get(n, 0) + 1
            if n == 10 and seen[n] > 1:
                return {"winner": "b", "a_hp_frac": 0, "b_hp_frac": 0.05}
            return threshold(10)(n)

        s = Search(Matchup("x", lo=1, hi=100))
        while (n := s.next_count()) is not None:
            s.record(n, fight(n))
        self.assertEqual(s.final, 11)

    def test_store_keeps_every_trial(self):
        with tempfile.TemporaryDirectory() as d:
            st = Store(Path(d) / "trials.jsonl", engine=3)
            calibrate(Matchup("lings", lo=1, hi=64), threshold(20), st)
            ev = st.evidence()["lings"]
            self.assertIn(20, ev)
            self.assertTrue(all(x > 0 for x in ev[20]))
            self.assertEqual(Store(Path(d) / "trials.jsonl", engine=4).evidence(), {})


if __name__ == "__main__":
    unittest.main()
