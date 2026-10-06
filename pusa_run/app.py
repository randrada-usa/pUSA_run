from __future__ import annotations

import math
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum, auto

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from .actions import Action, InputEvent
from .assets import GameAssets
from .constants import COLORS, FPS, GAME_TITLE, LOGICAL_HEIGHT, LOGICAL_SIZE, LOGICAL_WIDTH, resource_path
from .fonts import fitted_ui_font, ui_font
from .gameplay import ObjectKind, RunnerWorld, TrackObject, draw_world
from .intro_video import IntroVideo
from .pose_controller import CalibrationStatus, PoseController, PoseSnapshot
from .save_data import Preferences, SaveStore


class Screen(str, Enum):
    MENU = "menu"
    CALIBRATION = "calibration"
    TUTORIAL = "tutorial"
    INTRO = "intro"
    PLAYING = "playing"
    PAUSED = "paused"
    SETTINGS = "settings"
    GAME_OVER = "game_over"


class _MusicTrack(Enum):
    """Which music file is currently loaded in the mixer."""
    NONE = auto()
    BG_THEME = auto()
    RADAHALL_NORMAL = auto()
    RADAHALL_FAST = auto()


# Seconds of gameplay before crossfading to the fast track.
_FAST_TRACK_THRESHOLD = 60.0
# Fadeout duration in milliseconds for the crossfade.
_CROSSFADE_MS = 1500
_STING_GAP_MS = 700  # silence between the game over sting and the menu theme
_MENU_FADE_IN_MS = 1500

_MENU_CHASE_SPEED = 280.0
_MENU_CHASE_GAP = 160.0
_MENU_CHASE_WAIT_SECONDS = 3.5
_MENU_CHASE_EDGE_X = 100.0
_INTRO_AUDIO_FADE_MS = 500
_GAMEPLAY_REVEAL_SECONDS = 0.45

# Rat squeak by remaining hearts: (seconds between squeaks, volume 0-1).
# The rat gets closer as hearts drop, so squeaks get faster and louder.
_RAT_SQUEAK_BY_HEARTS = {
    3: (3.0, 0.35),
    2: (1.8, 0.65),
    1: (0.9, 1.0),
}


@dataclass(slots=True)
class Button:
    label: str
    rect: pygame.Rect
    action: str

    def draw(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font,
        mouse: tuple[int, int],
    ) -> None:
        hovered = self.rect.collidepoint(mouse)
        color = COLORS["orange"] if hovered else COLORS["gold"]
        pygame.draw.rect(surface, COLORS["brown"], self.rect.move(0, 5), border_radius=12)
        pygame.draw.rect(surface, color, self.rect, border_radius=12)
        pygame.draw.rect(surface, COLORS["cream"], self.rect, 3, border_radius=12)
        text = font.render(self.label, True, COLORS["dark"])
        surface.blit(text, text.get_rect(center=self.rect.center))


class GameApp:
    def __init__(self) -> None:
        pygame.init()
        # Attempt to initialise the audio mixer; fall back to silent mode if no audio device is available
        try:
            pygame.mixer.init()
            self._audio_available = True
        except pygame.error:
            self._audio_available = False
        pygame.display.set_caption(GAME_TITLE)
        self.store = SaveStore()
        self.preferences: Preferences = self.store.load()
        self.fullscreen = self.preferences.fullscreen
        self.display = self._create_display()
        self.assets = GameAssets()
        pygame.display.set_icon(self.assets.app_icon)
        self.canvas = pygame.Surface(LOGICAL_SIZE)
        self.clock = pygame.time.Clock()
        self.font_large = ui_font(55)
        self.font_title = ui_font(70)
        self.font_medium = ui_font(32)
        self.font_small = ui_font(18)

        # Music track paths
        self._track_paths = {
            _MusicTrack.BG_THEME: str(resource_path("assets", "sound", "bg_theme.ogg")),
            _MusicTrack.RADAHALL_NORMAL: str(resource_path("assets", "sound", "radahall_normal.ogg")),
            _MusicTrack.RADAHALL_FAST: str(resource_path("assets", "sound", "radahall_fast.ogg")),
        }
        self._current_track = _MusicTrack.NONE
        self._music_playing = False
        self._resume_track: _MusicTrack | None = None
        self._resume_pos_s = 0.0
        self._crossfading_to_fast = False
        self._game_over_sting = None
        self._sting_channel = None
        self._menu_music_pending = False
        self._sting_ended_at: int | None = None
        self._click_sound = None
        self._jump_sound = None
        self._dodge_sound = None
        self._catfood_sound = None
        self._fish_sound = None
        self._hit_sound = None
        self._shield_sound = None
        self._rat_sound = None
        self._rat_channel = None
        self._intro_sound = None
        self._intro_channel = None
        self._intro_video: IntroVideo | None = None
        self._intro_audio_fading = False
        self._gameplay_fade_timer = 0.0
        self._rat_squeak_timer = _RAT_SQUEAK_BY_HEARTS[3][0]
        if self._audio_available:
            try:
                self._game_over_sting = pygame.mixer.Sound(
                    str(resource_path("assets", "sound", "game over.wav"))
                )
                self._game_over_sting.set_volume(self.preferences.sfx_volume)
            except (pygame.error, FileNotFoundError):
                self._game_over_sting = None
            try:
                self._click_sound = pygame.mixer.Sound(
                    str(resource_path("assets", "sound", "click.wav"))
                )
                self._click_sound.set_volume(self.preferences.sfx_volume)
            except (pygame.error, FileNotFoundError):
                self._click_sound = None
            try:
                self._jump_sound = pygame.mixer.Sound(
                    str(resource_path("assets", "sound", "jump.wav"))
                )
                self._jump_sound.set_volume(self.preferences.sfx_volume * 0.75)
            except (pygame.error, FileNotFoundError):
                self._jump_sound = None
            try:
                self._dodge_sound = pygame.mixer.Sound(
                    str(resource_path("assets", "sound", "dodge.wav"))
                )
                self._dodge_sound.set_volume(self.preferences.sfx_volume * 0.75)
            except (pygame.error, FileNotFoundError):
                self._dodge_sound = None
            try:
                self._catfood_sound = pygame.mixer.Sound(
                    str(resource_path("assets", "sound", "catfood_pickup.wav"))
                )
                self._catfood_sound.set_volume(self.preferences.sfx_volume * 0.75)
            except (pygame.error, FileNotFoundError):
                self._catfood_sound = None
            try:
                self._fish_sound = pygame.mixer.Sound(
                    str(resource_path("assets", "sound", "item_fish.wav"))
                )
                self._fish_sound.set_volume(self.preferences.sfx_volume * 0.75)
            except (pygame.error, FileNotFoundError):
                self._fish_sound = None
            try:
                self._hit_sound = pygame.mixer.Sound(
                    str(resource_path("assets", "sound", "obstacle_hit.wav"))
                )
                self._hit_sound.set_volume(self.preferences.sfx_volume)
            except (pygame.error, FileNotFoundError):
                self._hit_sound = None
            try:
                self._shield_sound = pygame.mixer.Sound(
                    str(resource_path("assets", "sound", "shield_block.wav"))
                )
                self._shield_sound.set_volume(self.preferences.sfx_volume)
            except (pygame.error, FileNotFoundError):
                self._shield_sound = None
            try:
                self._rat_sound = pygame.mixer.Sound(
                    str(resource_path("assets", "sound", "rat_threat.wav"))
                )
                self._rat_sound.set_volume(self.preferences.sfx_volume)
                # reserve a channel so squeaks never steal or get stolen by other sfx
                pygame.mixer.set_reserved(1)
                self._rat_channel = pygame.mixer.Channel(0)
            except (pygame.error, FileNotFoundError):
                self._rat_sound = None
                self._rat_channel = None
            try:
                self._intro_sound = pygame.mixer.Sound(
                    str(resource_path("assets", "start_vid_audio.ogg"))
                )
            except (pygame.error, FileNotFoundError):
                self._intro_sound = None
            pygame.mixer.music.set_volume(self.preferences.music_volume)
            pygame.mixer.music.set_endevent(pygame.USEREVENT + 1)

        self.running = True
        self.screen = Screen.MENU
        self.previous_screen = Screen.MENU
        self.world = RunnerWorld()
        self.final_score = 0
        self.new_high_score = False
        self.camera = PoseController(
            camera_index=self.preferences.camera_index,
            show_window=self.preferences.show_camera,
        )
        self.camera.start()
        self.keyboard_only = False
        self.tutorial_actions = [
            {Action.MOVE_LEFT, Action.LANE_LEFT},
            {Action.MOVE_RIGHT, Action.LANE_RIGHT},
            {Action.JUMP},
        ]
        self.tutorial_index = 0
        self.tutorial_world = RunnerWorld(seed=7)
        self.tutorial_done_timer = 0.0
        self.calibration_destination = Screen.TUTORIAL
        self.calibration_return_screen = Screen.MENU
        self._reset_menu_chase()
        # Start music for the initial menu screen
        self._load_and_play(_MusicTrack.BG_THEME)

    # ── Music helpers ───────────────────────────────────────────────

    def _load_and_play(
        self, track: _MusicTrack, fadeout_ms: int = 0, fade_in_ms: int = 0
    ) -> None:
        """Load *track* into the mixer and loop it. Reloads only when needed."""
        if not self._audio_available:
            return
        if fadeout_ms and self._music_playing:
            pygame.mixer.music.fadeout(fadeout_ms)
        else:
            pygame.mixer.music.stop()
        if self._current_track != track:
            pygame.mixer.music.load(self._track_paths[track])
            self._current_track = track
        pygame.mixer.music.play(loops=-1, fade_ms=fade_in_ms)
        self._music_playing = True
        self._crossfading_to_fast = False

    def _handle_music_transition(self, prev: Screen, current: Screen) -> None:
        """React to screen changes with the correct music track."""
        if not self._audio_available:
            return

        # run just ended: play the sting, then bring the menu theme in after it
        if current == Screen.GAME_OVER and prev in (Screen.PLAYING, Screen.TUTORIAL):
            self._crossfading_to_fast = False
            pygame.mixer.music.stop()
            self._music_playing = False
            if self._game_over_sting is not None:
                self._sting_channel = self._game_over_sting.play()
            if self._sting_channel is not None:
                self._menu_music_pending = True
                return
            self._load_and_play(_MusicTrack.BG_THEME)
            return

        # entering a menu screen
        if current in (Screen.MENU, Screen.GAME_OVER):
            if self._current_track != _MusicTrack.BG_THEME or not self._music_playing:
                self._load_and_play(_MusicTrack.BG_THEME)
            return

        # Intro video/audio are started together by _start_intro.
        if current == Screen.INTRO:
            return

        # entering gameplay
        if current in (Screen.PLAYING, Screen.TUTORIAL):
            if prev == Screen.PAUSED and self._resume_track is not None:
                track, start_s = self._resume_track, self._resume_pos_s
                self._resume_track = None
                pygame.mixer.music.stop()
                pygame.mixer.music.load(self._track_paths[track])
                self._current_track = track
                try:
                    pygame.mixer.music.play(loops=-1, start=start_s)
                except pygame.error:
                    pygame.mixer.music.play(loops=-1)
                self._music_playing = True
                return
            # fresh run or tutorial
            fade_in_ms = (
                round(_GAMEPLAY_REVEAL_SECONDS * 1000)
                if prev == Screen.INTRO
                else 0
            )
            self._load_and_play(
                _MusicTrack.RADAHALL_NORMAL,
                fade_in_ms=fade_in_ms,
            )
            return

        # entering pause: switch to menu music, remembering where gameplay music was
        if current == Screen.PAUSED:
            if prev in (Screen.PLAYING, Screen.TUTORIAL):
                track = self._current_track
                if self._crossfading_to_fast:
                    track = _MusicTrack.RADAHALL_FAST
                    pos_s = 0.0
                else:
                    pos_s = max(pygame.mixer.music.get_pos(), 0) / 1000.0
                self._crossfading_to_fast = False
                self._resume_track = track
                self._resume_pos_s = pos_s
                self._load_and_play(_MusicTrack.BG_THEME)
            return

        # settings / calibration are overlay screens that don't need their own music

    def _update_sting_handoff(self) -> None:
        if not self._menu_music_pending:
            return
        if self.screen != Screen.GAME_OVER:
            # left game over before the sting finished; the new screen owns the music
            self._menu_music_pending = False
            self._sting_ended_at = None
            if self._sting_channel is not None:
                self._sting_channel.stop()
            return
        if self._sting_channel is not None and self._sting_channel.get_busy():
            return
        now = pygame.time.get_ticks()
        if self._sting_ended_at is None:
            self._sting_ended_at = now
        if now - self._sting_ended_at >= _STING_GAP_MS:
            self._menu_music_pending = False
            self._sting_ended_at = None
            self._load_and_play(_MusicTrack.BG_THEME, fade_in_ms=_MENU_FADE_IN_MS)

    def _check_gameplay_crossfade(self) -> None:
        # If the player survives long enough, crossfade to the fast track.
        if not self._audio_available:
            return
        if (
            self._current_track == _MusicTrack.RADAHALL_NORMAL
            and not self._crossfading_to_fast
            and self.world.elapsed >= _FAST_TRACK_THRESHOLD
        ):
            self._crossfading_to_fast = True
            pygame.mixer.music.fadeout(_CROSSFADE_MS)

    def _handle_music_end_event(self) -> None:
        """Called when the mixer fires its end-of-track event (after fadeout)."""
        if self._crossfading_to_fast:
            self._load_and_play(_MusicTrack.RADAHALL_FAST)

    def _create_display(self) -> pygame.Surface:
        flags = pygame.RESIZABLE
        size = LOGICAL_SIZE
        if self.fullscreen:
            flags = pygame.FULLSCREEN
            size = (0, 0)
        return pygame.display.set_mode(size, flags)

    def run(self) -> int:
        try:
            while self.running:
                dt = self.clock.tick(FPS) / 1000.0
                mouse_logical = self._to_logical(pygame.mouse.get_pos())
                pose = self.camera.snapshot()
                camera_actions = self.camera.poll_actions()
                events = pygame.event.get()
                self._handle_global_events(events)
                prev_screen = self.screen
                self._update(events, camera_actions, pose, dt, mouse_logical)
                if self.screen != prev_screen:
                    if self.screen == Screen.MENU:
                        self._reset_menu_chase()
                    self._handle_music_transition(prev_screen, self.screen)
                self._update_sting_handoff()
                self._draw(pose, mouse_logical)
                self._present()
            return 0
        finally:
            self._release_intro_video()
            self.preferences.fullscreen = self.fullscreen
            self.store.save(self.preferences)
            self.camera.stop()
            if self._audio_available:
                pygame.mixer.music.stop()
            pygame.quit()

    def _handle_global_events(self, events: list[pygame.event.Event]) -> None:
        music_end_type = pygame.USEREVENT + 1
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == music_end_type:
                self._handle_music_end_event()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                self.fullscreen = not self.fullscreen
                self.preferences.fullscreen = self.fullscreen
                self.display = self._create_display()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F2:
                self.preferences.show_camera = not self.preferences.show_camera
                self.camera.set_window_visible(self.preferences.show_camera)

    def _keyboard_actions(
        self, events: list[pygame.event.Event]
    ) -> list[InputEvent]:
        output: list[InputEvent] = []
        now = time.monotonic()
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if event.key in (pygame.K_LEFT, pygame.K_a):
                output.append(InputEvent(Action.MOVE_LEFT, "keyboard", now))
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                output.append(InputEvent(Action.MOVE_RIGHT, "keyboard", now))
            elif event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                output.append(InputEvent(Action.JUMP, "keyboard", now))
        return output

    def _update(
        self,
        events: list[pygame.event.Event],
        camera_actions: list[InputEvent],
        pose: PoseSnapshot,
        dt: float,
        mouse: tuple[int, int],
    ) -> None:
        actions = self._keyboard_actions(events) + camera_actions

        if self.screen == Screen.MENU:
            self._update_menu(events, mouse, dt)
        elif self.screen == Screen.SETTINGS:
            self._update_settings(events, mouse)
        elif self.screen == Screen.CALIBRATION:
            self._update_calibration(events, pose, mouse)
        elif self.screen == Screen.TUTORIAL:
            self._update_tutorial(events, actions, dt)
        elif self.screen == Screen.INTRO:
            self._update_intro(events, dt)
        elif self.screen == Screen.PLAYING:
            self._update_playing(events, actions, pose, dt)
        elif self.screen == Screen.PAUSED:
            self._update_pause(events, mouse)
        elif self.screen == Screen.GAME_OVER:
            self._update_game_over(events, mouse)

    def _menu_buttons(self) -> list[Button]:
        return [
            Button("PLAY", pygame.Rect(525, 510, 230, 96), "play"),
            Button("EXIT", pygame.Rect(18, 18, 76, 76), "exit"),
            Button("SETTINGS", pygame.Rect(18, 102, 76, 76), "settings"),
        ]

    def _update_menu(
        self,
        events: list[pygame.event.Event],
        mouse: tuple[int, int],
        dt: float,
    ) -> None:
        self._update_menu_chase(dt)
        action = self._clicked_with_sound(events, self._menu_buttons(), mouse)
        if action == "play":
            pose = self.camera.snapshot()
            if pose.calibration == CalibrationStatus.READY or self.keyboard_only:
                self._after_calibration()
            else:
                self.calibration_destination = (
                    Screen.TUTORIAL
                    if not self.preferences.tutorial_complete
                    else Screen.PLAYING
                )
                self.calibration_return_screen = Screen.MENU
                self.camera.recalibrate()
                self.screen = Screen.CALIBRATION
        elif action == "settings":
            self.previous_screen = Screen.MENU
            self.screen = Screen.SETTINGS
        elif action == "exit":
            self.running = False

    def _reset_menu_chase(self) -> None:
        self._menu_chase_direction = 1
        self._menu_chase_x = -_MENU_CHASE_EDGE_X
        self._menu_chase_wait = 0.0
        self._menu_chase_elapsed = 0.0

    def _update_menu_chase(self, dt: float) -> None:
        self._menu_chase_elapsed += max(0.0, dt)
        if self._menu_chase_wait > 0.0:
            self._menu_chase_wait = max(0.0, self._menu_chase_wait - dt)
            if self._menu_chase_wait > 0.0:
                return
            self._menu_chase_direction *= -1
            self._menu_chase_x = (
                LOGICAL_WIDTH + _MENU_CHASE_EDGE_X
                if self._menu_chase_direction < 0
                else -_MENU_CHASE_EDGE_X
            )
            return

        self._menu_chase_x += self._menu_chase_direction * _MENU_CHASE_SPEED * dt
        rat_x = (
            self._menu_chase_x
            - self._menu_chase_direction * _MENU_CHASE_GAP
        )
        exited_right = (
            self._menu_chase_direction > 0
            and rat_x >= LOGICAL_WIDTH + _MENU_CHASE_EDGE_X
        )
        exited_left = (
            self._menu_chase_direction < 0
            and rat_x <= -_MENU_CHASE_EDGE_X
        )
        if exited_right or exited_left:
            self._menu_chase_wait = _MENU_CHASE_WAIT_SECONDS

    def _settings_buttons(self) -> list[Button]:
        return [
            Button("<", pygame.Rect(470, 229, 72, 62), "camera_down"),
            Button(">", pygame.Rect(738, 229, 72, 62), "camera_up"),
            Button(
                "CAMERA WINDOW", pygame.Rect(490, 372, 300, 76), "camera_window"
            ),
            Button("RECALIBRATE", pygame.Rect(490, 466, 300, 76), "recalibrate"),
            Button("BACK", pygame.Rect(520, 590, 240, 76), "back"),
        ]

    def _update_settings(
        self, events: list[pygame.event.Event], mouse: tuple[int, int]
    ) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.screen = self.previous_screen
                return
        action = self._clicked_with_sound(events, self._settings_buttons(), mouse)
        if action in ("camera_down", "camera_up"):
            delta = -1 if action == "camera_down" else 1
            self.preferences.camera_index = max(
                0, min(9, self.preferences.camera_index + delta)
            )
            self.camera.set_camera(self.preferences.camera_index)
        elif action == "camera_window":
            self.preferences.show_camera = not self.preferences.show_camera
            self.camera.set_window_visible(self.preferences.show_camera)
        elif action == "recalibrate":
            self.calibration_destination = self.previous_screen
            self.calibration_return_screen = Screen.SETTINGS
            self.camera.recalibrate()
            self.screen = Screen.CALIBRATION
        elif action == "back":
            self.screen = self.previous_screen

    def _calibration_buttons(self) -> list[Button]:
        return [
            Button(
                "KEYBOARD ONLY", pygame.Rect(475, 545, 330, 95), "keyboard"
            ),
        ]

    def _update_calibration(
        self,
        events: list[pygame.event.Event],
        pose: PoseSnapshot,
        mouse: tuple[int, int],
    ) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.screen = self.calibration_return_screen
                return
        if pose.calibration == CalibrationStatus.READY:
            self.keyboard_only = False
            self._after_calibration()
            return
        action = self._clicked_with_sound(events, self._calibration_buttons(), mouse)
        if action == "keyboard":
            self.keyboard_only = True
            self._after_calibration()

    def _after_calibration(self) -> None:
        if self.calibration_return_screen == Screen.SETTINGS:
            self.screen = Screen.SETTINGS
            return
        if self.calibration_destination == Screen.PAUSED:
            self.screen = Screen.PAUSED
        elif not self.preferences.tutorial_complete:
            self._start_tutorial()
        else:
            self._start_intro()

    def _start_tutorial(self) -> None:
        self.tutorial_index = 0
        self.tutorial_done_timer = 0.0
        self.tutorial_world = RunnerWorld(seed=7)
        self.tutorial_world.spawn_timer = 9999.0
        self.screen = Screen.TUTORIAL

    def _update_tutorial(
        self,
        events: list[pygame.event.Event],
        actions: list[InputEvent],
        dt: float,
    ) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.screen = Screen.MENU
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                self._finish_tutorial()
                return

        if self.tutorial_index < len(self.tutorial_actions):
            expected = self.tutorial_actions[self.tutorial_index]
            for item in actions:
                self._play_move_sound(self.tutorial_world.apply_action(item.action))
                if item.action in expected:
                    self.tutorial_index += 1
                    if self.tutorial_index == 2:
                        self.tutorial_world.player.lane = 1
                    if self.tutorial_index >= len(self.tutorial_actions):
                        self.tutorial_done_timer = 1.25
                    break
        self.tutorial_world.player.update(dt)
        self.tutorial_world.elapsed += dt
        if self.tutorial_done_timer > 0:
            self.tutorial_done_timer -= dt
            if self.tutorial_done_timer <= 0:
                self._finish_tutorial()

    def _finish_tutorial(self) -> None:
        self.preferences.tutorial_complete = True
        self.store.save(self.preferences)
        self._start_intro()

    def _reset_run_state(self) -> None:
        self.world = RunnerWorld()
        self._crossfading_to_fast = False
        self._resume_track = None
        self._resume_pos_s = 0.0
        self._gameplay_fade_timer = 0.0
        self._rat_squeak_timer = _RAT_SQUEAK_BY_HEARTS[3][0]

    def _start_run(self) -> None:
        self._reset_run_state()
        self.screen = Screen.PLAYING

    def _start_intro(self) -> None:
        self._release_intro_video()
        intro = IntroVideo(resource_path("assets", "start_vid.mp4"))
        if not intro.available:
            intro.release()
            self._start_run()
            return

        self._intro_video = intro
        self._intro_audio_fading = False
        if self._audio_available:
            if self._music_playing:
                pygame.mixer.music.fadeout(_INTRO_AUDIO_FADE_MS)
                self._music_playing = False
            if self._intro_sound is not None:
                self._intro_channel = self._intro_sound.play(
                    fade_ms=_INTRO_AUDIO_FADE_MS
                )
                if self._intro_channel is not None:
                    self._intro_channel.set_volume(self.preferences.music_volume)
        self.screen = Screen.INTRO

    def _update_intro(
        self,
        events: list[pygame.event.Event],
        dt: float,
    ) -> None:
        skip = any(
            event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            for event in events
        )
        if self._intro_video is None or skip:
            self._finish_intro()
            return

        finished = self._intro_video.update(dt)
        if (
            self._intro_video.fade_out_started
            and not self._intro_audio_fading
            and self._intro_channel is not None
        ):
            self._intro_channel.fadeout(_INTRO_AUDIO_FADE_MS)
            self._intro_audio_fading = True
        if finished:
            self._finish_intro()

    def _finish_intro(self) -> None:
        if self._intro_channel is not None:
            self._intro_channel.stop()
            self._intro_channel = None
        self._release_intro_video()
        self._start_run()
        self._gameplay_fade_timer = _GAMEPLAY_REVEAL_SECONDS

    def _release_intro_video(self) -> None:
        if self._intro_video is not None:
            self._intro_video.release()
            self._intro_video = None

    def _restart_run(self) -> None:
        self._start_run()

    def _return_to_main_menu(self) -> None:
        self._reset_run_state()
        self.screen = Screen.MENU

    def _update_playing(
        self,
        events: list[pygame.event.Event],
        actions: list[InputEvent],
        pose: PoseSnapshot,
        dt: float,
    ) -> None:
        self._gameplay_fade_timer = max(
            0.0,
            self._gameplay_fade_timer - dt,
        )
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.screen = Screen.PAUSED
                return
        for item in actions:
            self._play_move_sound(self.world.apply_action(item.action))

        now = time.monotonic()
        grace = (
            pose.last_seen > 0
            and not pose.tracking
            and (now - pose.last_seen) <= 2.0
        )
        self.world.update(dt, collision_grace=grace)
        self._play_pickup_sounds()
        self._play_hit_sound()
        self._update_rat_squeak(dt)
        self._check_gameplay_crossfade()
        if self.world.game_over:
            self.final_score = self.world.score
            self.new_high_score = self.final_score > self.preferences.high_score
            self.preferences.high_score = max(
                self.preferences.high_score, self.final_score
            )
            self.store.save(self.preferences)
            self.screen = Screen.GAME_OVER

    def _pause_buttons(self) -> list[Button]:
        return [
            Button("RESTART", pygame.Rect(480, 310, 320, 66), "restart"),
            Button("RESUME", pygame.Rect(480, 422, 320, 66), "resume"),
            Button("SETTINGS", pygame.Rect(480, 508, 320, 66), "settings"),
            Button("MAIN MENU", pygame.Rect(480, 594, 320, 66), "menu"),
        ]

    def _update_pause(
        self, events: list[pygame.event.Event], mouse: tuple[int, int]
    ) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.screen = Screen.PLAYING
                return
        action = self._clicked_with_sound(events, self._pause_buttons(), mouse)
        if action == "resume":
            self.screen = Screen.PLAYING
        elif action == "restart":
            self._restart_run()
        elif action == "settings":
            self.previous_screen = Screen.PAUSED
            self.screen = Screen.SETTINGS
        elif action == "menu":
            self._return_to_main_menu()

    def _game_over_buttons(self) -> list[Button]:
        return [
            Button("RESTART", pygame.Rect(470, 480, 340, 70), "restart"),
            Button("MAIN MENU", pygame.Rect(470, 570, 340, 70), "menu"),
        ]

    def _update_game_over(
        self, events: list[pygame.event.Event], mouse: tuple[int, int]
    ) -> None:
        action = self._clicked_with_sound(events, self._game_over_buttons(), mouse)
        if action == "restart":
            self._restart_run()
        elif action == "menu":
            self._return_to_main_menu()

    @staticmethod
    def _clicked(
        events: list[pygame.event.Event],
        buttons: list[Button],
        mouse: tuple[int, int],
    ) -> str | None:
        enter = any(
            event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN
            for event in events
        )
        if enter and buttons:
            return buttons[0].action
        for event in events:
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                for button in buttons:
                    if button.rect.collidepoint(mouse):
                        return button.action
        return None

    def _clicked_with_sound(
        self,
        events: list[pygame.event.Event],
        buttons: list[Button],
        mouse: tuple[int, int],
    ) -> str | None:
        action = self._clicked(events, buttons, mouse)
        if action is not None:
            self._play_click()
        return action

    def _update_rat_squeak(self, dt: float) -> None:
        """Squeak on a timer that shortens as Pipin loses hearts.

        Only called while playing, so the timer is frozen during pause.
        """
        if self._rat_sound is None or self._rat_channel is None:
            return
        hearts = self.world.player.hearts
        if self.world.game_over or hearts <= 0:
            return
        interval, volume = _RAT_SQUEAK_BY_HEARTS[min(max(hearts, 1), 3)]
        # after a hit, don't wait out the old, longer interval
        self._rat_squeak_timer = min(self._rat_squeak_timer, interval) - dt
        if self._rat_squeak_timer <= 0.0:
            self._rat_channel.play(self._rat_sound)
            self._rat_channel.set_volume(volume)
            self._rat_squeak_timer = interval

    def _play_hit_sound(self) -> None:
        hits, self.world.hits_taken = self.world.hits_taken, 0
        blocks, self.world.shield_blocks = self.world.shield_blocks, 0
        if hits and self._hit_sound is not None:
            self._hit_sound.play()
        elif blocks and self._shield_sound is not None:
            self._shield_sound.play()

    def _play_pickup_sounds(self) -> None:
        pickups, self.world.pickups = self.world.pickups, []
        for kind, sound in (
            (ObjectKind.CAT_FOOD, self._catfood_sound),
            (ObjectKind.FISH, self._fish_sound),
        ):
            if kind in pickups and sound is not None:
                sound.play()

    def _play_move_sound(self, move: str | None) -> None:
        sound = {"jump": self._jump_sound, "dodge": self._dodge_sound}.get(move)
        if sound is not None:
            sound.play()

    def _play_click(self) -> None:
        if self._click_sound is not None:
            self._click_sound.play()

    def _draw(self, pose: PoseSnapshot, mouse: tuple[int, int]) -> None:
        if self.screen == Screen.MENU:
            self._draw_menu(mouse)
        elif self.screen == Screen.SETTINGS:
            self._draw_settings(pose, mouse)
        elif self.screen == Screen.CALIBRATION:
            self._draw_calibration(pose, mouse)
        elif self.screen == Screen.TUTORIAL:
            self._draw_tutorial()
        elif self.screen == Screen.INTRO:
            if self._intro_video is None:
                self.canvas.fill((0, 0, 0))
            else:
                self._intro_video.draw(self.canvas)
        elif self.screen == Screen.PLAYING:
            draw_world(
                self.canvas,
                self.world,
                self._tracking_warning(pose),
                self.assets,
            )
            if self._gameplay_fade_timer > 0.0:
                overlay = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
                alpha = round(
                    255
                    * self._gameplay_fade_timer
                    / _GAMEPLAY_REVEAL_SECONDS
                )
                overlay.fill((0, 0, 0, alpha))
                self.canvas.blit(overlay, (0, 0))
        elif self.screen == Screen.PAUSED:
            draw_world(self.canvas, self.world, "", self.assets)
            self._draw_overlay("PAUSED", self._pause_buttons(), mouse)
        elif self.screen == Screen.GAME_OVER:
            draw_world(self.canvas, self.world, "", self.assets)
            self._draw_game_over(mouse)

    def _draw_background(self) -> None:
        self.canvas.fill(COLORS["cream"])
        circle_data = (
            (COLORS["gold"], (130, 100)),
            (COLORS["orange"], (630, 290)),
            (COLORS["rust"], (1130, 480)),
        )
        for color, center in circle_data:
            pygame.draw.circle(self.canvas, color, center, 240, 16)
        pygame.draw.rect(
            self.canvas, COLORS["floor_dark"], (305, 0, 670, LOGICAL_HEIGHT)
        )
        pygame.draw.rect(
            self.canvas, COLORS["floor"], (325, 0, 630, LOGICAL_HEIGHT)
        )
        for x in (535, 745):
            pygame.draw.line(
                self.canvas,
                (191, 208, 125),
                (x, 0),
                (x, LOGICAL_HEIGHT),
                5,
            )

    def _draw_logo(self, subtitle: str = "WHOLE-BODY CAMPUS RUNNER") -> None:
        title = self.font_title.render("pUSA RUN", True, COLORS["gold"])
        shadow = self.font_title.render("pUSA RUN", True, COLORS["brown"])
        center = (LOGICAL_WIDTH // 2, 168)
        self.canvas.blit(
            shadow, shadow.get_rect(center=(center[0] + 6, center[1] + 7))
        )
        self.canvas.blit(title, title.get_rect(center=center))
        subtitle_text = self.font_small.render(subtitle, True, COLORS["white"])
        self.canvas.blit(
            subtitle_text, subtitle_text.get_rect(center=(640, 245))
        )

    def _draw_menu(self, mouse: tuple[int, int]) -> None:
        self.canvas.blit(self.assets.main_background, (0, 0))
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((28, 19, 10, 28))
        self.canvas.blit(shade, (0, 0))

        title_rect = self.assets.title.get_rect(midtop=(640, 15))
        self.canvas.blit(self.assets.title, title_rect)

        logo_rect = self.assets.menu_logo.get_rect(center=(1018, 465))
        self.canvas.blit(self.assets.menu_logo, logo_rect)

        direction = self._menu_chase_direction
        pipin = (
            self.assets.home_pipin
            if direction > 0
            else self.assets.home_pipin_flipped
        )
        rat = (
            self.assets.home_rat
            if direction > 0
            else self.assets.home_rat_flipped
        )
        pipin_x = round(self._menu_chase_x)
        rat_x = round(self._menu_chase_x - direction * _MENU_CHASE_GAP)
        pipin_bob = round(math.sin(self._menu_chase_elapsed * 11.0) * 3.0)
        rat_bob = round(math.sin(self._menu_chase_elapsed * 12.0 + 1.2) * 3.0)
        self.canvas.blit(
            rat,
            rat.get_rect(midbottom=(rat_x, 654 + rat_bob)),
        )
        self.canvas.blit(
            pipin,
            pipin.get_rect(midbottom=(pipin_x, 669 + pipin_bob)),
        )

        tagline = self.assets.menu_tagline
        self.canvas.blit(tagline, tagline.get_rect(center=(640, 650)))

        for button in self._menu_buttons():
            self._draw_menu_button(button, mouse)

        self._draw_high_score_panel()
        self._draw_camera_badge(self.camera.snapshot())

    def _draw_menu_button(
        self,
        button: Button,
        mouse: tuple[int, int],
    ) -> None:
        hovered = button.rect.collidepoint(mouse)
        pressed = hovered and pygame.mouse.get_pressed(num_buttons=3)[0]
        image = self.assets.menu_buttons[button.action]["default"]
        center = button.rect.center

        if pressed:
            image = pygame.transform.scale_by(image, 0.97)
            image.fill((18, 18, 18, 0), special_flags=pygame.BLEND_RGB_SUB)
            center = (center[0], center[1] + 3)
        elif hovered:
            image = pygame.transform.scale_by(image, 1.04)
            image.fill((16, 16, 16, 0), special_flags=pygame.BLEND_RGB_ADD)
            center = (center[0], center[1] - 1)

        self.canvas.blit(image, image.get_rect(center=center))

    def _draw_high_score_panel(self) -> None:
        panel = self.assets.high_score_panel
        panel_rect = panel.get_rect(topright=(1250, 18))
        self.canvas.blit(panel, panel_rect)

        value = f"{self.preferences.high_score:,}"
        score_font = fitted_ui_font(value, 177, 28)
        score = score_font.render(value, False, (255, 187, 27))
        self.canvas.blit(
            score,
            score.get_rect(center=(panel_rect.left + 155, panel_rect.top + 61)),
        )

    def _draw_settings(
        self, pose: PoseSnapshot, mouse: tuple[int, int]
    ) -> None:
        if self.previous_screen == Screen.PAUSED:
            draw_world(self.canvas, self.world, "", self.assets)
        else:
            self.canvas.blit(self.assets.main_background, (0, 0))
        overlay = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        overlay.fill((20, 18, 28, 205))
        self.canvas.blit(overlay, (0, 0))
        heading = self.font_large.render("SETTINGS", True, COLORS["cream"])
        self.canvas.blit(heading, heading.get_rect(center=(640, 100)))
        label = self.font_medium.render("Camera", True, COLORS["white"])
        self.canvas.blit(label, label.get_rect(center=(640, 190)))
        index = self.font_medium.render(
            str(self.preferences.camera_index), True, COLORS["gold"]
        )
        self.canvas.blit(index, index.get_rect(center=(640, 260)))
        state = "ON" if self.preferences.show_camera else "OFF"
        detail_text = f"Separate camera window: {state}"
        detail = fitted_ui_font(detail_text, 520, 18).render(
            detail_text, True, COLORS["cream"]
        )
        self.canvas.blit(detail, detail.get_rect(center=(640, 330)))
        for button in self._settings_buttons():
            self._draw_screen_button(button, mouse)
        if pose.camera_error:
            error = self.font_small.render(
                "Camera unavailable - keyboard remains active",
                True,
                (255, 170, 170),
            )
            self.canvas.blit(error, error.get_rect(center=(640, 700)))

    def _draw_calibration(
        self, pose: PoseSnapshot, mouse: tuple[int, int]
    ) -> None:
        self.canvas.blit(self.assets.main_background, (0, 0))
        board = pygame.Rect(80, 25, 1120, 660)
        pygame.draw.rect(self.canvas, (63, 35, 21), board.move(8, 9))
        pygame.draw.rect(self.canvas, (94, 51, 27), board)
        pygame.draw.rect(self.canvas, (191, 115, 44), board.inflate(-12, -12))
        pygame.draw.rect(self.canvas, (235, 178, 75), board.inflate(-24, -24))
        pygame.draw.rect(self.canvas, (29, 69, 48), board.inflate(-38, -38))
        pygame.draw.rect(self.canvas, (47, 94, 61), board.inflate(-48, -48), 2)

        board_center = board.centerx
        heading = self.font_large.render(
            "CAMERA CALIBRATION", False, COLORS["cream"]
        )
        self.canvas.blit(heading, heading.get_rect(center=(board_center, 115)))
        instructions = [
            "Stand centered about 1-1.5 metres from the camera.",
            "Keep your head, shoulders, torso, and hips visible.",
            "Hold still until the calibration bar is full.",
        ]
        for index, line in enumerate(instructions):
            rendered = ui_font(20).render(line, False, COLORS["cream"])
            self.canvas.blit(
                rendered,
                rendered.get_rect(center=(board_center, 210 + index * 65)),
            )
        pygame.draw.rect(
            self.canvas, (15, 39, 30), (360, 375, 560, 44)
        )
        progress = int(548 * pose.calibration_progress)
        pygame.draw.rect(
            self.canvas,
            (255, 191, 53),
            (366, 381, progress, 32),
        )
        status = fitted_ui_font(pose.calibration.value, 1030, 26).render(
            pose.calibration.value, False, COLORS["cream"]
        )
        self.canvas.blit(status, status.get_rect(center=(board_center, 470)))
        if pose.camera_error:
            error_text = pose.camera_error[:55]
            error = fitted_ui_font(error_text, 1030, 18).render(
                error_text, False, (255, 170, 170)
            )
            self.canvas.blit(error, error.get_rect(center=(board_center, 505)))
        for button in self._calibration_buttons():
            self._draw_keyboard_only_button(button, mouse)

    def _draw_keyboard_only_button(
        self, button: Button, mouse: tuple[int, int]
    ) -> None:
        hovered = button.rect.collidepoint(mouse)
        pressed = hovered and pygame.mouse.get_pressed(num_buttons=3)[0]
        image = self.assets.keyboard_only_button
        label_offset = 36
        face_center_fraction = 40 / 95
        center = button.rect.center

        if pressed:
            image = pygame.transform.scale_by(image, 0.97)
            image.fill((18, 18, 18, 0), special_flags=pygame.BLEND_RGB_SUB)
            center = (center[0], center[1] + 3)
        elif hovered:
            image = pygame.transform.scale_by(image, 1.04)
            image.fill((16, 16, 16, 0), special_flags=pygame.BLEND_RGB_ADD)
            center = (center[0], center[1] - 1)

        image_rect = image.get_rect(center=center)
        self.canvas.blit(image, image_rect)
        label = ui_font(16).render(button.label, False, (69, 36, 10))
        glyph = label.get_bounding_rect(min_alpha=1)
        label_rect = label.get_rect()
        # Center the visible letters within the space beside each icon.
        label_rect.x = center[0] + label_offset - glyph.left - glyph.width // 2
        # The shadow and font surface both have asymmetric padding.
        face_center_y = image_rect.top + round(
            image_rect.height * face_center_fraction
        )
        label_rect.y = face_center_y - glyph.top - glyph.height // 2
        self.canvas.blit(label, label_rect)

    def _draw_tutorial(self) -> None:
        has_obstacle = any(
            obj.kind == ObjectKind.OBSTACLE
            for obj in self.tutorial_world.objects
        )
        if self.tutorial_index == 2 and not has_obstacle:
            self.tutorial_world.objects.append(
                TrackObject(ObjectKind.OBSTACLE, 1, 500.0, 92)
            )
        draw_world(
            self.canvas,
            self.tutorial_world,
            "TUTORIAL",
            self.assets,
        )
        labels = ["MOVE LEFT", "MOVE RIGHT", "JUMP OVER THE OBSTACLE"]
        message = (
            "READY!"
            if self.tutorial_index >= len(labels)
            else labels[self.tutorial_index]
        )
        rendered = fitted_ui_font(message, 1150, 55).render(
            message, True, COLORS["white"]
        )
        box = rendered.get_rect(center=(640, 180)).inflate(50, 28)
        pygame.draw.rect(self.canvas, COLORS["dark"], box, border_radius=16)
        self.canvas.blit(rendered, rendered.get_rect(center=box.center))
        skip = self.font_small.render(
            "Press Enter to skip tutorial", True, COLORS["white"]
        )
        self.canvas.blit(skip, skip.get_rect(center=(640, 235)))

    def _draw_overlay(
        self,
        title: str,
        buttons: list[Button],
        mouse: tuple[int, int],
    ) -> None:
        overlay = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        overlay.fill((20, 18, 28, 205))
        self.canvas.blit(overlay, (0, 0))
        heading = self.font_large.render(title, True, COLORS["cream"])
        self.canvas.blit(heading, heading.get_rect(center=(640, 210)))
        for button in buttons:
            self._draw_screen_button(button, mouse)

    def _draw_screen_button(
        self,
        button: Button,
        mouse: tuple[int, int],
    ) -> None:
        hovered = button.rect.collidepoint(mouse)
        pressed = hovered and pygame.mouse.get_pressed(num_buttons=3)[0]
        image = self.assets.screen_buttons[button.action]
        center = button.rect.center

        if pressed:
            image = pygame.transform.scale_by(image, 0.97)
            image.fill((18, 18, 18, 0), special_flags=pygame.BLEND_RGB_SUB)
            center = (center[0], center[1] + 3)
        elif hovered:
            image = pygame.transform.scale_by(image, 1.04)
            image.fill((16, 16, 16, 0), special_flags=pygame.BLEND_RGB_ADD)
            center = (center[0], center[1] - 1)

        self.canvas.blit(image, image.get_rect(center=center))

    def _draw_game_over(self, mouse: tuple[int, int]) -> None:
        overlay = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        overlay.fill((36, 20, 25, 220))
        self.canvas.blit(overlay, (0, 0))
        title = self.font_title.render("CAUGHT!", True, COLORS["gold"])
        self.canvas.blit(title, title.get_rect(center=(640, 180)))
        score = self.font_large.render(
            f"Score {self.final_score:06d}", True, COLORS["white"]
        )
        self.canvas.blit(score, score.get_rect(center=(640, 315)))
        if self.new_high_score:
            high = self.font_medium.render(
                "NEW HIGH SCORE!", True, COLORS["green"]
            )
            self.canvas.blit(high, high.get_rect(center=(640, 390)))
        for button in self._game_over_buttons():
            self._draw_screen_button(button, mouse)

    def _draw_camera_badge(self, pose: PoseSnapshot) -> None:
        if pose.camera_error:
            label = "CAMERA OFFLINE - KEYBOARD READY"
            color = COLORS["rust"]
        elif pose.calibration == CalibrationStatus.READY:
            label = "CAMERA READY"
            color = COLORS["green"]
        else:
            label = "CAMERA NEEDS CALIBRATION"
            color = COLORS["orange"]
        rendered = fitted_ui_font(label, 540, 18).render(
            label, True, COLORS["white"]
        )
        box = rendered.get_rect(bottomleft=(20, 704)).inflate(20, 12)
        pygame.draw.rect(self.canvas, color, box, border_radius=9)
        self.canvas.blit(rendered, rendered.get_rect(center=box.center))

    @staticmethod
    def _tracking_warning(pose: PoseSnapshot) -> str:
        if pose.camera_error:
            return "CAMERA OFFLINE - KEYBOARD ACTIVE"
        if pose.last_seen > 0 and not pose.tracking:
            return "TRACKING LOST - KEEP RUNNING"
        return ""

    def _present(self) -> None:
        window_width, window_height = self.display.get_size()
        scale = min(
            window_width / LOGICAL_WIDTH, window_height / LOGICAL_HEIGHT
        )
        draw_width = max(1, int(LOGICAL_WIDTH * scale))
        draw_height = max(1, int(LOGICAL_HEIGHT * scale))
        x = (window_width - draw_width) // 2
        y = (window_height - draw_height) // 2
        self.display.fill((9, 10, 15))
        scaled = pygame.transform.scale(
            self.canvas, (draw_width, draw_height)
        )
        self.display.blit(scaled, (x, y))
        pygame.display.flip()

    def _to_logical(self, position: tuple[int, int]) -> tuple[int, int]:
        window_width, window_height = self.display.get_size()
        scale = min(
            window_width / LOGICAL_WIDTH, window_height / LOGICAL_HEIGHT
        )
        draw_width = LOGICAL_WIDTH * scale
        draw_height = LOGICAL_HEIGHT * scale
        offset_x = (window_width - draw_width) / 2
        offset_y = (window_height - draw_height) / 2
        return (
            int((position[0] - offset_x) / max(scale, 0.001)),
            int((position[1] - offset_y) / max(scale, 0.001)),
        )


def main() -> int:
    try:
        if "--camera-self-test" in sys.argv:
            controller = PoseController(show_window=False)
            landmarker = controller._create_landmarker()
            landmarker.close()
            return 0
        if "--asset-self-test" in sys.argv:
            pygame.init()
            pygame.display.set_mode((1, 1), pygame.HIDDEN)
            GameAssets()
            pygame.quit()
            return 0
        return GameApp().run()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        return 1
