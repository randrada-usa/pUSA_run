from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pusa_run.actions import Action
from pusa_run.difficulty import difficulty_at
from pusa_run.gameplay import ObjectKind, RunnerWorld, TrackObject
from pusa_run.save_data import Preferences, SaveStore


class DifficultyTests(unittest.TestCase):
    def test_tier_increases_every_ten_seconds(self) -> None:
        for tier in range(1, 25):
            self.assertEqual(difficulty_at(tier * 10 - 0.01).tier, tier - 1)
            self.assertEqual(difficulty_at(tier * 10).tier, tier)
            self.assertGreater(
                difficulty_at(tier * 10).scroll_speed,
                difficulty_at(tier * 10 - 0.01).scroll_speed,
            )
        self.assertEqual(difficulty_at(250).tier, 24)

    def test_curve_rises_and_caps(self) -> None:
        start = difficulty_at(0)
        middle = difficulty_at(120)
        late = difficulty_at(10_000)
        self.assertLess(start.scroll_speed, middle.scroll_speed)
        self.assertLess(middle.scroll_speed, late.scroll_speed)
        self.assertEqual(late.scroll_speed, 445.0)
        self.assertGreaterEqual(late.spawn_interval, 0.95)
        self.assertLessEqual(late.double_obstacle_chance, 0.48)


class PlayerTests(unittest.TestCase):
    def test_lane_changes_are_bounded(self) -> None:
        world = RunnerWorld(seed=1)
        for _ in range(5):
            world.apply_action(Action.MOVE_LEFT)
        self.assertEqual(world.player.lane, 0)
        for _ in range(5):
            world.apply_action(Action.MOVE_RIGHT)
        self.assertEqual(world.player.lane, 2)

    def test_absolute_camera_lanes(self) -> None:
        world = RunnerWorld(seed=1)
        world.apply_action(Action.LANE_LEFT)
        self.assertEqual(world.player.lane, 0)
        world.apply_action(Action.LANE_RIGHT)
        self.assertEqual(world.player.lane, 2)
        world.apply_action(Action.LANE_CENTER)
        self.assertEqual(world.player.lane, 1)

    def test_jump_leaves_and_returns_to_ground(self) -> None:
        world = RunnerWorld(seed=1)
        world.apply_action(Action.JUMP)
        for _ in range(15):
            world.player.update(1 / 60)
        self.assertGreater(world.player.jump_height, 38)
        for _ in range(90):
            world.player.update(1 / 60)
        self.assertEqual(world.player.jump_height, 0)

    def test_shield_consumes_hit_without_losing_heart(self) -> None:
        world = RunnerWorld(seed=1)
        world.player.shield_timer = 8
        world.objects = [
            TrackObject(ObjectKind.OBSTACLE, world.player.lane, 570, 92)
        ]
        world._handle_interactions(collision_grace=False)
        self.assertEqual(world.player.hearts, 3)
        self.assertEqual(world.player.shield_timer, 0)

    def test_damage_is_not_repeated_during_invulnerability(self) -> None:
        world = RunnerWorld(seed=1)
        world.objects = [
            TrackObject(ObjectKind.OBSTACLE, world.player.lane, 570, 92),
            TrackObject(ObjectKind.OBSTACLE, world.player.lane, 570, 92),
        ]
        world._handle_interactions(collision_grace=False)
        self.assertEqual(world.player.hearts, 2)

    def test_tracking_grace_blocks_damage(self) -> None:
        world = RunnerWorld(seed=1)
        world.objects = [
            TrackObject(ObjectKind.OBSTACLE, world.player.lane, 570, 92)
        ]
        world._handle_interactions(collision_grace=True)
        self.assertEqual(world.player.hearts, 3)

    def test_fish_restores_only_one_heart(self) -> None:
        world = RunnerWorld(seed=1)
        world.player.hearts = 1
        world.objects = [
            TrackObject(ObjectKind.FISH, world.player.lane, 570, 54)
        ]
        world._handle_interactions(collision_grace=False)
        self.assertEqual(world.player.hearts, 2)

    def test_spawn_pattern_always_leaves_a_lane_open(self) -> None:
        world = RunnerWorld(seed=4)
        hard = difficulty_at(10_000)
        for _ in range(300):
            world.objects.clear()
            world._spawn_pattern(hard)
            blocked = {
                item.lane
                for item in world.objects
                if item.kind == ObjectKind.OBSTACLE
            }
            self.assertLessEqual(len(blocked), 2)


class SaveTests(unittest.TestCase):
    def test_round_trip_and_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "save.json"
            store = SaveStore(path)
            expected = Preferences(high_score=1234, camera_index=2)
            store.save(expected)
            self.assertEqual(store.load().high_score, 1234)
            path.write_text(
                '{"high_score": 9, "camera_index": 1, "future": true}',
                encoding="utf-8",
            )
            loaded = store.load()
            self.assertEqual(loaded.high_score, 9)
            self.assertEqual(loaded.camera_index, 1)


if __name__ == "__main__":
    unittest.main()
