from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from pusa_run.app import Button, GameApp, Screen
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


if __name__ == "__main__":
    unittest.main()
