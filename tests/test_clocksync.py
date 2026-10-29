import random
import unittest

from shortslab.clocksync import fit, parse_clock


class ClockSyncTest(unittest.TestCase):
    def readings(self, vod0=1234.0, rate=0.98, length=1200, misreads=0.2, seed=1):
        rng = random.Random(seed)
        pts = []
        t = 30.0
        while t < length:
            vod = vod0 + rate * t
            clock = int(t)  # what the overlay shows: whole seconds
            if rng.random() < misreads:
                clock += rng.choice([-20, -10, 10, 20, 120])  # a 5 read as a 3, a dropped digit
            pts.append((vod, clock))
            t += 15
        return pts

    def test_recovers_line_despite_misreads(self):
        vod0, rate, n = fit(self.readings())
        self.assertAlmostEqual(rate, 0.98, places=3)
        self.assertAlmostEqual(vod0, 1234.0, delta=1.0)
        self.assertGreater(n, 40)

    def test_too_few_readings(self):
        self.assertIsNone(fit([(100.0, 10), (200.0, 110)]))
        self.assertIsNone(fit([]))

    def test_rejects_implausible_rates(self):
        pts = [(100 + 2 * c, c) for c in range(0, 600, 15)]  # rate 2.0: not a game clock
        self.assertIsNone(fit(pts))

    def test_parse_clock(self):
        self.assertEqual(parse_clock("12:07\n"), 727)
        self.assertEqual(parse_clock("4:53"), 293)
        self.assertIsNone(parse_clock("4:73"))
        self.assertIsNone(parse_clock("PLAYER ONE"))


if __name__ == "__main__":
    unittest.main()
