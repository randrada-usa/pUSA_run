from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from pusa_run.app import (
    GameApp,
    Screen,
    _GAMEPLAY_REVEAL_SECONDS,
    _INTRO_AUDIO_FADE_MS,
    _MusicTrack,
)
from pusa_run.constants import LOGICAL_SIZE, resource_path
from pusa_run.intro_video import IntroVideo


class IntroVideoTests(unittest.TestCase):
    def test_supplied_video_opens_and_decodes(self) -> None:
        video = IntroVideo(resource_path("assets", "start_vid.mp4"))
        try:
            self.assertTrue(video.available)
            self.assertAlmostEqual(video.duration, 3.23, places=1)
            self.assertFalse(video.update(0.5))
            self.assertIsNotNone(video.frame)

            canvas = pygame.Surface(LOGICAL_SIZE)
            video.draw(canvas)
            self.assertNotEqual(canvas.get_at((640, 360))[:3], (0, 0, 0))
        finally:
            video.release()

    def test_completed_calibration_starts_intro_before_gameplay(self) -> None:
        app = GameApp.__new__(GameApp)
        app.calibration_destination = Screen.PLAYING
        app.calibration_return_screen = Screen.MENU
        app.preferences = SimpleNamespace(tutorial_complete=True)
        app._start_intro = Mock()

        app._after_calibration()

        app._start_intro.assert_called_once_with()

    def test_recalibration_returns_to_settings_without_starting_intro(self) -> None:
        app = GameApp.__new__(GameApp)
        app.calibration_destination = Screen.MENU
        app.calibration_return_screen = Screen.SETTINGS
        app.preferences = SimpleNamespace(tutorial_complete=True)
        app._start_intro = Mock()

        app._after_calibration()

        self.assertEqual(app.screen, Screen.SETTINGS)
        app._start_intro.assert_not_called()

    @patch("pusa_run.app.IntroVideo")
    def test_video_still_starts_when_audio_is_unavailable(
        self,
        video_type: Mock,
    ) -> None:
        video = Mock(available=True)
        video_type.return_value = video
        app = GameApp.__new__(GameApp)
        app._intro_video = None
        app._intro_channel = None
        app._audio_available = False

        app._start_intro()

        self.assertEqual(app.screen, Screen.INTRO)
        self.assertIs(app._intro_video, video)

    @patch("pygame.mixer.music.fadeout")
    @patch("pusa_run.app.IntroVideo")
    def test_intro_audio_fades_in_with_the_video(
        self,
        video_type: Mock,
        fadeout: Mock,
    ) -> None:
        video_type.return_value = Mock(available=True)
        channel = Mock()
        sound = Mock()
        sound.play.return_value = channel
        app = GameApp.__new__(GameApp)
        app._intro_video = None
        app._intro_channel = None
        app._intro_sound = sound
        app._audio_available = True
        app._music_playing = True
        app.preferences = SimpleNamespace(music_volume=0.6)

        app._start_intro()

        fadeout.assert_called_once_with(_INTRO_AUDIO_FADE_MS)
        sound.play.assert_called_once_with(fade_ms=_INTRO_AUDIO_FADE_MS)
        channel.set_volume.assert_called_once_with(0.6)

    def test_finishing_intro_reveals_a_fresh_run(self) -> None:
        app = GameApp.__new__(GameApp)
        channel = Mock()
        video = Mock()
        app._intro_channel = channel
        app._intro_video = video
        app._start_run = Mock()

        app._finish_intro()

        channel.stop.assert_called_once_with()
        video.release.assert_called_once_with()
        app._start_run.assert_called_once_with()
        self.assertEqual(app._gameplay_fade_timer, _GAMEPLAY_REVEAL_SECONDS)
        self.assertIsNone(app._intro_video)
        self.assertIsNone(app._intro_channel)

    def test_gameplay_music_fades_in_after_intro(self) -> None:
        app = GameApp.__new__(GameApp)
        app._audio_available = True
        app._load_and_play = Mock()

        app._handle_music_transition(Screen.INTRO, Screen.PLAYING)

        app._load_and_play.assert_called_once_with(
            _MusicTrack.RADAHALL_NORMAL,
            fade_in_ms=round(_GAMEPLAY_REVEAL_SECONDS * 1000),
        )


if __name__ == "__main__":
    unittest.main()
