from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from enum import Enum

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from .actions import Action, InputEvent
from .assets import GameAssets
from .constants import COLORS, FPS, GAME_TITLE, LOGICAL_HEIGHT, LOGICAL_SIZE, LOGICAL_WIDTH
from .fonts import fitted_ui_font, ui_font
from .gameplay import ObjectKind, RunnerWorld, TrackObject, draw_world
from .pose_controller import CalibrationStatus, PoseController, PoseSnapshot
from .save_data import Preferences, SaveStore


class Screen(str, Enum):
    MENU = "menu"
    CALIBRATION = "calibration"
    TUTORIAL = "tutorial"
    PLAYING = "playing"
    PAUSED = "paused"
    SETTINGS = "settings"
    GAME_OVER = "game_over"


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
                self._update(events, camera_actions, pose, dt, mouse_logical)
                self._draw(pose, mouse_logical)
                self._present()
            return 0
        finally:
            self.preferences.fullscreen = self.fullscreen
            self.store.save(self.preferences)
            self.camera.stop()
            pygame.quit()

    def _handle_global_events(self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
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
            self._update_menu(events, mouse)
        elif self.screen == Screen.SETTINGS:
            self._update_settings(events, mouse)
        elif self.screen == Screen.CALIBRATION:
            self._update_calibration(events, pose, mouse)
        elif self.screen == Screen.TUTORIAL:
            self._update_tutorial(events, actions, dt)
        elif self.screen == Screen.PLAYING:
            self._update_playing(events, actions, pose, dt)
        elif self.screen == Screen.PAUSED:
            self._update_pause(events, mouse)
        elif self.screen == Screen.GAME_OVER:
            self._update_game_over(events, mouse)

    def _menu_buttons(self) -> list[Button]:
        return [
            Button("PLAY", pygame.Rect(490, 510, 300, 96), "play"),
            Button("EXIT", pygame.Rect(18, 18, 76, 76), "exit"),
            Button("SETTINGS", pygame.Rect(18, 102, 76, 76), "settings"),
        ]

    def _update_menu(
        self, events: list[pygame.event.Event], mouse: tuple[int, int]
    ) -> None:
        action = self._clicked(events, self._menu_buttons(), mouse)
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

    def _settings_buttons(self) -> list[Button]:
        return [
            Button("<", pygame.Rect(470, 278, 72, 62), "camera_down"),
            Button(">", pygame.Rect(738, 278, 72, 62), "camera_up"),
            Button(
                "CAMERA WINDOW", pygame.Rect(440, 374, 400, 65), "camera_window"
            ),
            Button("RECALIBRATE", pygame.Rect(440, 459, 400, 65), "recalibrate"),
            Button("BACK", pygame.Rect(490, 565, 300, 65), "back"),
        ]

    def _update_settings(
        self, events: list[pygame.event.Event], mouse: tuple[int, int]
    ) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.screen = self.previous_screen
                return
        action = self._clicked(events, self._settings_buttons(), mouse)
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
        action = self._clicked(events, self._calibration_buttons(), mouse)
        if action == "keyboard":
            self.keyboard_only = True
            self._after_calibration()

    def _after_calibration(self) -> None:
        if self.calibration_destination == Screen.PAUSED:
            self.screen = Screen.PAUSED
        elif not self.preferences.tutorial_complete:
            self._start_tutorial()
        else:
            self._start_run()

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
                self.tutorial_world.apply_action(item.action)
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
        self._start_run()

    def _start_run(self) -> None:
        self.world = RunnerWorld()
        self.screen = Screen.PLAYING

    def _update_playing(
        self,
        events: list[pygame.event.Event],
        actions: list[InputEvent],
        pose: PoseSnapshot,
        dt: float,
    ) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.screen = Screen.PAUSED
                return
        for item in actions:
            self.world.apply_action(item.action)

        now = time.monotonic()
        grace = (
            pose.last_seen > 0
            and not pose.tracking
            and (now - pose.last_seen) <= 2.0
        )
        self.world.update(dt, collision_grace=grace)
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
            Button("RESUME", pygame.Rect(480, 310, 320, 66), "resume"),
            Button("RECALIBRATE", pygame.Rect(480, 396, 320, 66), "recalibrate"),
            Button("SETTINGS", pygame.Rect(480, 482, 320, 66), "settings"),
            Button("MAIN MENU", pygame.Rect(480, 568, 320, 66), "menu"),
        ]

    def _update_pause(
        self, events: list[pygame.event.Event], mouse: tuple[int, int]
    ) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.screen = Screen.PLAYING
                return
        action = self._clicked(events, self._pause_buttons(), mouse)
        if action == "resume":
            self.screen = Screen.PLAYING
        elif action == "recalibrate":
            self.calibration_destination = Screen.PAUSED
            self.calibration_return_screen = Screen.PAUSED
            self.camera.recalibrate()
            self.screen = Screen.CALIBRATION
        elif action == "settings":
            self.previous_screen = Screen.PAUSED
            self.screen = Screen.SETTINGS
        elif action == "menu":
            self.screen = Screen.MENU

    def _game_over_buttons(self) -> list[Button]:
        return [
            Button("PLAY AGAIN", pygame.Rect(470, 480, 340, 70), "retry"),
            Button("MAIN MENU", pygame.Rect(470, 570, 340, 70), "menu"),
        ]

    def _update_game_over(
        self, events: list[pygame.event.Event], mouse: tuple[int, int]
    ) -> None:
        action = self._clicked(events, self._game_over_buttons(), mouse)
        if action == "retry":
            self._start_run()
        elif action == "menu":
            self.screen = Screen.MENU

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

    def _draw(self, pose: PoseSnapshot, mouse: tuple[int, int]) -> None:
        if self.screen == Screen.MENU:
            self._draw_menu(mouse)
        elif self.screen == Screen.SETTINGS:
            self._draw_settings(pose, mouse)
        elif self.screen == Screen.CALIBRATION:
            self._draw_calibration(pose, mouse)
        elif self.screen == Screen.TUTORIAL:
            self._draw_tutorial()
        elif self.screen == Screen.PLAYING:
            draw_world(
                self.canvas,
                self.world,
                self._tracking_warning(pose),
                self.assets,
            )
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

        tagline = self.assets.menu_tagline
        self.canvas.blit(tagline, tagline.get_rect(center=(640, 650)))

        self.canvas.blit(
            self.assets.menu_pipin,
            self.assets.menu_pipin.get_rect(midbottom=(190, 708)),
        )
        self.canvas.blit(
            self.assets.menu_rat,
            self.assets.menu_rat.get_rect(midbottom=(1088, 710)),
        )

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
        score_font = fitted_ui_font(value, 177, 37)
        score = score_font.render(value, False, (255, 187, 27))
        self.canvas.blit(
            score,
            score.get_rect(center=(panel_rect.left + 155, panel_rect.top + 61)),
        )

    def _draw_settings(
        self, pose: PoseSnapshot, mouse: tuple[int, int]
    ) -> None:
        self._draw_background()
        heading = self.font_large.render("SETTINGS", True, COLORS["cream"])
        self.canvas.blit(heading, heading.get_rect(center=(640, 112)))
        panel = pygame.Rect(380, 190, 520, 470)
        pygame.draw.rect(self.canvas, COLORS["dark"], panel, border_radius=18)
        label = self.font_medium.render("Camera", True, COLORS["white"])
        self.canvas.blit(label, label.get_rect(center=(640, 239)))
        index = self.font_medium.render(
            str(self.preferences.camera_index), True, COLORS["gold"]
        )
        self.canvas.blit(index, index.get_rect(center=(640, 309)))
        state = "ON" if self.preferences.show_camera else "OFF"
        detail_text = f"Separate camera window: {state}"
        detail = fitted_ui_font(detail_text, panel.width - 36, 18).render(
            detail_text, True, COLORS["cream"]
        )
        self.canvas.blit(detail, detail.get_rect(center=(640, 354)))
        for button in self._settings_buttons():
            button.draw(self.canvas, self.font_small, mouse)
        if pose.camera_error:
            error = self.font_small.render(
                "Camera unavailable - keyboard remains active",
                True,
                (255, 170, 170),
            )
            self.canvas.blit(error, error.get_rect(center=(640, 545)))

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
            button.draw(self.canvas, self.font_small, mouse)

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
            button.draw(self.canvas, self.font_small, mouse)

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
