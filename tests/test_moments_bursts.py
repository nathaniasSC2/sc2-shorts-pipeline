import unittest

from shortslab.bursts import densest, unit_name
from shortslab.moments import rank


def seg(start, text, words=None):
    return {"start": start, "end": start + 4, "text": text, "words": (words or text.split())}


class MomentsTest(unittest.TestCase):
    def setUp(self):
        self.tr = [seg(t, "so I'm going to build a few more units here") for t in range(0, 1200, 5)]

    def test_reaction_plus_chat_plus_fight_wins(self):
        tr = list(self.tr)
        tr[120] = seg(600, "oh my god let's go no no no what the hell")
        chat = [{"t": 600 + k, "text": "KEKW what a fight"} for k in range(5, 20)]
        game = [{"t": 598, "kind": "fight", "tag": "fight@10:00"}]
        top = rank(tr, chat, game, top=3)
        self.assertTrue(570 <= top[0].start <= 600 <= top[0].end, top[0])
        self.assertIn("fight@10:00", top[0].tags)
        self.assertIn("oh my god", top[0].text)

    def test_windows_dont_overlap(self):
        tr = list(self.tr)
        for i in (40, 41, 42, 100, 160):
            tr[i] = seg(i * 5, "holy shit that was insane")
        top = rank(tr, top=5)
        starts = sorted(m.start for m in top)
        self.assertTrue(all(b - a >= 45 for a, b in zip(starts, starts[1:])), starts)

    def test_chat_is_credited_to_what_it_reacts_to(self):
        chat = [{"t": 900, "text": "LUL"}] * 10
        top = rank(self.tr, chat, top=1)
        self.assertLess(top[0].start, 900)  # chat lags the moment by 3-25 s


class BurstsTest(unittest.TestCase):
    def test_densest_first_and_spaced(self):
        kills = [(100 + i * 0.5, False, False) for i in range(8)]  # 8 kills in 4 s
        kills += [(300 + i, True, False) for i in range(5)]  # 5 workers in 5 s
        kills += [(500, False, True), (501, False, False)]  # too few
        b = densest(kills)
        self.assertEqual([x["n"] for x in b], [8, 4])
        self.assertEqual(b[1]["workers"], 4)
        self.assertEqual(b[0]["clock"], "1:40")

    def test_mode_names_fold(self):
        self.assertEqual(unit_name("SiegeTankSieged"), "Siege Tank")
        self.assertEqual(unit_name("BattleHellion"), "Hellbat")
        self.assertEqual(unit_name("Battlecruiser"), "Battlecruiser")


if __name__ == "__main__":
    unittest.main()
