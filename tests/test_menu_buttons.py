from __future__ import annotations

import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from pusa_run.app import Button, GameApp, Screen, _MusicTrack
from pusa_run.gameplay import RunnerWorld
from pusa_run.pose_controller import CalibrationStatus, PoseSnapshot


class MenuButtonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.button = Button("PLAY", pygame.Rect(10, 10, 100, 50), "play")

    def test_click_activates_on_release(self) -> None:
        events = [pygame.event.Event(pygame.MOUSEBUTTONUP, button=1)]
        self.assertEqual(
            GameApp._clicked(events, [self.button], (50, 30)),
            "play",
        )

    def test_press_does_not_activate_until_release(self) -> None:
        events = [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1)]
        self.assertIsNone(GameApp._clicked(events, [self.button], (50, 30)))

    def test_release_outside_does_not_activate(self) -> None:
        events = [pygame.event.Event(pygame.MOUSEBUTTONUP, button=1)]
        self.assertIsNone(GameApp._clicked(events, [self.button], (500, 500)))

    def test_valid_click_plays_sound_once(self) -> None:
        app = GameApp.__new__(GameApp)
        app._play_click = Mock()
        events = [pygame.event.Event(pygame.MOUSEBUTTONUP, button=1)]

        action = app._clicked_with_sound(events, [self.button], (50, 30))

        self.assertEqual(action, "play")
        app._play_click.assert_called_once_with()

    def test_invalid_click_does_not_play_sound(self) -> None:
        app = GameApp.__new__(GameApp)
        app._play_click = Mock()
        events = [pygame.event.Event(pygame.MOUSEBUTTONUP, button=1)]

        action = app._clicked_with_sound(events, [self.button], (500, 500))

        self.assertIsNone(action)
        app._play_click.assert_not_called()

    def test_calibration_has_only_centered_keyboard_button(self) -> None:
        buttons = GameApp._calibration_buttons(None)
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].action, "keyboard")
        self.assertEqual(buttons[0].rect.centerx, 640)
        self.assertEqual(
            GameApp._clicked(
                [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)],
                buttons,
                (-1, -1),
            ),
            "keyboard",
        )

    def test_escape_from_calibration_returns_to_source_screen(self) -> None:
        escape = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)]
        for source in (Screen.MENU, Screen.SETTINGS, Screen.PAUSED):
            for status in (CalibrationStatus.WAITING, CalibrationStatus.READY):
                app = GameApp.__new__(GameApp)
                app.screen = Screen.CALIBRATION
                app.calibration_return_screen = source
                app._update_calibration(
                    escape, PoseSnapshot(calibration=status), (-1, -1)
                )
                self.assertEqual(app.screen, source)

    def test_pause_menu_uses_restart_instead_of_recalibrate(self) -> None:
        actions = [button.action for button in GameApp._pause_buttons(None)]

        self.assertEqual(actions, ["restart", "resume", "settings", "menu"])

    def test_restart_resets_run_and_does_not_resume_old_music_position(self) -> None:
        app = GameApp.__new__(GameApp)
        old_world = RunnerWorld(seed=1)
        old_world.elapsed = 42.0
        app.world = old_world
        app.screen = Screen.PAUSED
        app._resume_track = _MusicTrack.RADAHALL_FAST
        app._resume_pos_s = 37.5
        app._crossfading_to_fast = True
        app._rat_squeak_timer = 0.1

        app._restart_run()

        self.assertIsNot(app.world, old_world)
        self.assertEqual(app.world.elapsed, 0)
        self.assertEqual(app.screen, Screen.PLAYING)
        self.assertIsNone(app._resume_track)
        self.assertEqual(app._resume_pos_s, 0)
        self.assertFalse(app._crossfading_to_fast)

    def test_main_menu_resets_run_before_showing_menu(self) -> None:
        app = GameApp.__new__(GameApp)
        old_world = RunnerWorld(seed=1)
        old_world.elapsed = 42.0
        old_world.distance = 900.0
        app.world = old_world
        app.screen = Screen.PAUSED
        app._resume_track = _MusicTrack.RADAHALL_FAST
        app._resume_pos_s = 37.5
        app._crossfading_to_fast = True
        app._rat_squeak_timer = 0.1

        app._return_to_main_menu()

        self.assertIsNot(app.world, old_world)
        self.assertEqual(app.world.elapsed, 0)
        self.assertEqual(app.world.distance, 0)
        self.assertEqual(app.screen, Screen.MENU)
        self.assertIsNone(app._resume_track)
        self.assertEqual(app._resume_pos_s, 0)


if __name__ == "__main__":
    unittest.main()
