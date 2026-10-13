import unittest

from bhcoach.analysis import EARLY_POOL_SEC
from bhcoach.metrics import FRAME_SEC, extract_player_metrics, fmt_time


def build(frame, pid, name, x, y):
    return {"Frame": frame, "PlayerID": pid, "Type": {"Name": "Build"}, "Unit": {"Name": name}, "Pos": {"X": x, "Y": y}}


def morph(frame, pid, name, kind="Unit Morph"):
    return {"Frame": frame, "PlayerID": pid, "Type": {"Name": kind}, "Unit": {"Name": name}}


def sec(s):
    return int(s / FRAME_SEC)


class MetricsTest(unittest.TestCase):
    def test_protoss_cannon_dedup_and_counts(self):
        cmds = [
            build(sec(70), 0, "Forge", 10, 10),
            build(sec(100), 0, "Photon Cannon", 12, 10),
            build(sec(101), 0, "Photon Cannon", 12, 10),   # 같은 위치 반복 클릭 → 1회
            build(sec(200), 0, "Photon Cannon", 14, 10),
            build(sec(400), 0, "Photon Cannon", 16, 10),   # 5분 이후
            build(sec(50), 1, "Photon Cannon", 1, 1),       # 다른 플레이어
        ]
        m = extract_player_metrics(cmds, 0, "Protoss")
        self.assertEqual(fmt_time(m["forge"]), "1:10")
        self.assertEqual(fmt_time(m["cannon"]), "1:40")
        self.assertEqual(m["cannon@3"], 1)
        self.assertEqual(m["cannon@5"], 2)
        self.assertEqual(m["cannon@8"], 3)
        self.assertIsNone(m["stargate"])

    def test_zerg_first_events(self):
        cmds = [
            build(sec(38), 3, "Spawning Pool", 5, 5),
            morph(sec(180), 3, "Lair", "Building Morph"),
            morph(sec(330), 3, "Mutalisk"),
        ]
        m = extract_player_metrics(cmds, 3, "Zerg")
        self.assertLessEqual(m["pool"], EARLY_POOL_SEC)
        self.assertEqual(fmt_time(m["lair"]), "3:00")
        self.assertEqual(fmt_time(m["mutal"]), "5:30")


if __name__ == "__main__":
    unittest.main()
