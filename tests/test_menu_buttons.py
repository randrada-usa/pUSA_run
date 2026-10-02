from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from pusa_run.app import Button, GameApp


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


if __name__ == "__main__":
    unittest.main()
