from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from pusa_run.gameplay import ObjectKind, RunnerWorld
from pusa_run.app import (
    GameApp,
    Screen,
    _MENU_FADE_IN_MS,
    _RAT_SQUEAK_BY_HEARTS,
    _MusicTrack,
)


class AudioBehaviorTests(unittest.TestCase):
    def test_move_sounds_match_successful_action(self) -> None:
        app = GameApp.__new__(GameApp)
        app._jump_sound = Mock()
        app._dodge_sound = Mock()

        app._play_move_sound("jump")
        app._play_move_sound("dodge")
        app._play_move_sound(None)

        app._jump_sound.play.assert_called_once_with()
        app._dodge_sound.play.assert_called_once_with()

    def test_cat_food_pickup_plays_sound_and_clears_queue(self) -> None:
        app = GameApp.__new__(GameApp)
        app._catfood_sound = Mock()
        app.world = RunnerWorld(seed=1)
        app.world.pickups = [ObjectKind.FISH, ObjectKind.CAT_FOOD]

        app._play_pickup_sounds()

        app._catfood_sound.play.assert_called_once_with()
        self.assertEqual(app.world.pickups, [])

    def test_fish_pickup_does_not_play_cat_food_sound(self) -> None:
        app = GameApp.__new__(GameApp)
        app._catfood_sound = Mock()
        app.world = RunnerWorld(seed=1)
        app.world.pickups = [ObjectKind.FISH]

        app._play_pickup_sounds()

        app._catfood_sound.play.assert_not_called()

    def test_hit_sound_plays_once_and_clears_counter(self) -> None:
        app = GameApp.__new__(GameApp)
        app._hit_sound = Mock()
        app.world = RunnerWorld(seed=1)
        app.world.hits_taken = 1

        app._play_hit_sound()
        app._play_hit_sound()

        app._hit_sound.play.assert_called_once_with()
        self.assertEqual(app.world.hits_taken, 0)

    def _squeak_app(self, hearts: int, timer: float) -> GameApp:
        app = GameApp.__new__(GameApp)
        app._rat_sound = Mock()
        app._rat_channel = Mock()
        app._rat_squeak_timer = timer
        app.world = RunnerWorld(seed=1)
        app.world.player.hearts = hearts
        return app

    def test_rat_squeak_interval_and_volume_follow_hearts(self) -> None:
        for hearts, (interval, volume) in _RAT_SQUEAK_BY_HEARTS.items():
            app = self._squeak_app(hearts, timer=0.05)

            app._update_rat_squeak(0.1)

            app._rat_channel.play.assert_called_once_with(app._rat_sound)
            app._rat_channel.set_volume.assert_called_once_with(volume)
            self.assertEqual(app._rat_squeak_timer, interval)

    def test_rat_does_not_squeak_before_timer_expires(self) -> None:
        app = self._squeak_app(3, timer=2.0)

        app._update_rat_squeak(0.5)

        app._rat_channel.play.assert_not_called()
        self.assertAlmostEqual(app._rat_squeak_timer, 1.5)

    def test_losing_a_heart_shortens_the_wait(self) -> None:
        app = self._squeak_app(1, timer=3.0)

        app._update_rat_squeak(0.1)

        self.assertAlmostEqual(app._rat_squeak_timer, 0.8)

    def test_rat_is_silent_at_game_over_or_without_audio(self) -> None:
        app = self._squeak_app(1, timer=0.0)
        app.world.game_over = True
        app._update_rat_squeak(0.1)
        app._rat_channel.play.assert_not_called()

        app = self._squeak_app(1, timer=0.0)
        app._rat_sound = None
        app._update_rat_squeak(0.1)
        app._rat_channel.play.assert_not_called()

    @patch("pygame.mixer.music.stop")
    def test_game_over_sting_defers_menu_music(self, stop_music: Mock) -> None:
        app = GameApp.__new__(GameApp)
        channel = Mock()
        app._audio_available = True
        app._crossfading_to_fast = True
        app._music_playing = True
        app._game_over_sting = Mock()
        app._game_over_sting.play.return_value = channel
        app._sting_channel = None
        app._menu_music_pending = False
        app._load_and_play = Mock()

        app._handle_music_transition(Screen.PLAYING, Screen.GAME_OVER)

        stop_music.assert_called_once_with()
        self.assertFalse(app._music_playing)
        self.assertTrue(app._menu_music_pending)
        self.assertIs(app._sting_channel, channel)
        app._load_and_play.assert_not_called()

    @patch("pygame.time.get_ticks", return_value=900)
    def test_finished_sting_hands_off_to_menu_music(self, _ticks: Mock) -> None:
        app = GameApp.__new__(GameApp)
        app.screen = Screen.GAME_OVER
        app._menu_music_pending = True
        app._sting_ended_at = 100
        app._sting_channel = Mock()
        app._sting_channel.get_busy.return_value = False
        app._load_and_play = Mock()

        app._update_sting_handoff()

        self.assertFalse(app._menu_music_pending)
        self.assertIsNone(app._sting_ended_at)
        app._load_and_play.assert_called_once_with(
            _MusicTrack.BG_THEME,
            fade_in_ms=_MENU_FADE_IN_MS,
        )

    def test_audio_unavailable_skips_transition(self) -> None:
        app = GameApp.__new__(GameApp)
        app._audio_available = False
        app._game_over_sting = Mock()

        app._handle_music_transition(Screen.PLAYING, Screen.GAME_OVER)

        app._game_over_sting.play.assert_not_called()


if __name__ == "__main__":
    unittest.main()
