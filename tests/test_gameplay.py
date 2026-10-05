from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from pusa_run.actions import Action
from pusa_run.difficulty import difficulty_at
from pusa_run.gameplay import (
    ObjectKind,
    RunnerWorld,
    TrackObject,
    _hurt_flash_sprite,
    _rat_dodge_offset,
)
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
        one_minute = difficulty_at(60)
        middle = difficulty_at(120)
        late = difficulty_at(10_000)
        self.assertEqual(one_minute.scroll_speed, 565.0)
        self.assertAlmostEqual(one_minute.spawn_interval, 0.85)
        self.assertAlmostEqual(one_minute.double_obstacle_chance, 0.60)
        self.assertLess(start.scroll_speed, one_minute.scroll_speed)
        self.assertLess(one_minute.scroll_speed, middle.scroll_speed)
        self.assertLess(middle.scroll_speed, late.scroll_speed)
        self.assertEqual(middle.scroll_speed, 625.0)
        self.assertAlmostEqual(middle.spawn_interval, 0.78)
        self.assertAlmostEqual(middle.double_obstacle_chance, 0.66)
        self.assertEqual(late.scroll_speed, 745.0)
        self.assertGreaterEqual(late.spawn_interval, 0.78)
        self.assertLessEqual(late.double_obstacle_chance, 0.75)


class PlayerTests(unittest.TestCase):
    def test_low_fps_frame_advances_full_time(self) -> None:
        world = RunnerWorld(seed=1)
        world.spawn_timer = 99.0
        world.update(0.1)
        self.assertAlmostEqual(world.elapsed, 0.1)
        self.assertGreater(world.background_scroll, 24.0)

    def test_one_minute_ramp_at_ten_fps(self) -> None:
        world = RunnerWorld(seed=1)
        for _ in range(600):
            world.update(0.1, collision_grace=True)
        self.assertAlmostEqual(world.elapsed, 60.0)
        self.assertEqual(world.last_difficulty.tier, 6)
        self.assertEqual(world.last_difficulty.scroll_speed, 565.0)

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

    def test_successful_actions_report_their_sound_kind(self) -> None:
        world = RunnerWorld(seed=1)

        self.assertEqual(world.apply_action(Action.MOVE_LEFT), "dodge")
        self.assertIsNone(world.apply_action(Action.MOVE_LEFT))
        self.assertEqual(world.apply_action(Action.JUMP), "jump")
        self.assertIsNone(world.apply_action(Action.JUMP))

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

    def test_obstacle_damage_is_recorded_once_during_invulnerability(self) -> None:
        world = RunnerWorld(seed=1)
        world.objects = [
            TrackObject(ObjectKind.OBSTACLE, world.player.lane, 570, 92),
            TrackObject(ObjectKind.OBSTACLE, world.player.lane, 570, 92),
        ]
        world._handle_interactions(collision_grace=False)
        self.assertEqual(world.hits_taken, 1)

    def test_shield_absorbs_one_obstacle_and_records_a_block(self) -> None:
        world = RunnerWorld(seed=1)
        world.player.shield_timer = 5.0
        world.objects = [
            TrackObject(ObjectKind.OBSTACLE, world.player.lane, 570, 92),
            TrackObject(ObjectKind.OBSTACLE, world.player.lane, 570, 92),
        ]
        world._handle_interactions(collision_grace=False)
        self.assertEqual(world.hits_taken, 0)
        self.assertEqual(world.shield_blocks, 1)
        self.assertEqual(world.player.hearts, 3)

    def test_obstacle_during_iframes_is_not_a_shield_block(self) -> None:
        world = RunnerWorld(seed=1)
        world.player.shield_timer = 5.0
        world.player.damage_timer = 0.5
        world.objects = [TrackObject(ObjectKind.OBSTACLE, world.player.lane, 570, 92)]
        world._handle_interactions(collision_grace=False)
        self.assertEqual(world.shield_blocks, 0)

    def test_dodged_obstacle_is_not_a_hit(self) -> None:

        world = RunnerWorld(seed=1)
        world.player.jump_height = 100.0
        world.objects = [TrackObject(ObjectKind.OBSTACLE, world.player.lane, 570, 92)]
        world._handle_interactions(collision_grace=False)
        self.assertEqual(world.hits_taken, 0)

    def test_cat_food_pickup_is_recorded_once(self) -> None:
        world = RunnerWorld(seed=1)
        world.objects = [
            TrackObject(ObjectKind.CAT_FOOD, world.player.lane, 570, 58)
        ]
        world._handle_interactions(collision_grace=False)
        world._handle_interactions(collision_grace=False)
        self.assertEqual(world.pickups, [ObjectKind.CAT_FOOD])

    def test_missed_cat_food_is_not_recorded(self) -> None:
        world = RunnerWorld(seed=1)
        other_lane = (world.player.lane + 1) % 3
        world.objects = [TrackObject(ObjectKind.CAT_FOOD, other_lane, 570, 58)]
        world._handle_interactions(collision_grace=False)
        self.assertEqual(world.pickups, [])

    def test_rat_smoothly_retreats_after_heart_is_restored(self) -> None:
        world = RunnerWorld(seed=1)
        world.player.hearts = 1
        world.rat_y = 677.0
        world.player.hearts = 2

        world._update_rat_position(0.1)
        self.assertGreater(world.rat_y, 677.0)
        self.assertLess(world.rat_y, 715.0)

        for _ in range(10):
            world._update_rat_position(0.1)
        self.assertEqual(world.rat_y, 715.0)

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

    def test_spawned_obstacles_use_all_art_variants(self) -> None:
        world = RunnerWorld(seed=4)
        hard = difficulty_at(10_000)
        variants = set()
        for _ in range(100):
            world.objects.clear()
            world._spawn_pattern(hard)
            variants.update(
                item.variant
                for item in world.objects
                if item.kind == ObjectKind.OBSTACLE
            )
        self.assertEqual(variants, {0, 1, 2})

    def test_rat_dodges_obstacles_in_its_lane(self) -> None:
        world = RunnerWorld(seed=1)
        rat_y = 715.0
        world.objects = [
            TrackObject(ObjectKind.OBSTACLE, world.player.lane, rat_y - 48, 92)
        ]
        self.assertGreater(abs(_rat_dodge_offset(world, rat_y)), 115.0)

        world.objects[0].lane = 0
        self.assertEqual(_rat_dodge_offset(world, rat_y), 0.0)

    def test_hurt_flash_preserves_transparent_pixels(self) -> None:
        sprite = pygame.Surface((2, 2), pygame.SRCALPHA)
        sprite.set_at((1, 1), (100, 100, 100, 255))

        flash = _hurt_flash_sprite(sprite)

        self.assertEqual(flash.get_at((0, 0)).a, 0)
        self.assertEqual(flash.get_at((1, 1)).a, 255)


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
