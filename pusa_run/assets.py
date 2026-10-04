from __future__ import annotations

from pathlib import Path

import pygame

from .constants import LOGICAL_SIZE, resource_path


def _load(name: str, *, alpha: bool = True) -> pygame.Surface:
    return _load_path(
        resource_path("assets", "images", name),
        alpha=alpha,
    )


def _load_button(name: str) -> pygame.Surface:
    return _load_path(resource_path("assets", "pUSARUN_buttons", name))


def _load_path(path: Path, *, alpha: bool = True) -> pygame.Surface:
    surface = pygame.image.load(str(path))
    return surface.convert_alpha() if alpha else surface.convert()


def _crop_alpha(surface: pygame.Surface) -> pygame.Surface:
    bounds = surface.get_bounding_rect(min_alpha=1)
    if bounds.width <= 0 or bounds.height <= 0:
        return surface
    return surface.subsurface(bounds).copy()


def scale_to_width(surface: pygame.Surface, width: int) -> pygame.Surface:
    height = max(1, round(surface.get_height() * width / surface.get_width()))
    return pygame.transform.scale(surface, (width, height))


def scale_to_height(surface: pygame.Surface, height: int) -> pygame.Surface:
    width = max(1, round(surface.get_width() * height / surface.get_height()))
    return pygame.transform.scale(surface, (width, height))


def scale_by(surface: pygame.Surface, factor: float) -> pygame.Surface:
    size = (
        max(1, round(surface.get_width() * factor)),
        max(1, round(surface.get_height() * factor)),
    )
    return pygame.transform.scale(surface, size)


def scale_cover(surface: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    target_width, target_height = size
    scale = max(
        target_width / surface.get_width(),
        target_height / surface.get_height(),
    )
    scaled_size = (
        max(1, round(surface.get_width() * scale)),
        max(1, round(surface.get_height() * scale)),
    )
    scaled = pygame.transform.scale(surface, scaled_size)
    x = (scaled.get_width() - target_width) // 2
    y = (scaled.get_height() - target_height) // 2
    return scaled.subsurface((x, y, target_width, target_height)).copy()


class GameAssets:
    """Load and pre-scale supplied pixel-art assets once."""

    def __init__(self) -> None:
        self.main_background = scale_cover(
            _load("main_screen_bg.png", alpha=False),
            LOGICAL_SIZE,
        )
        self.title = scale_to_width(_crop_alpha(_load("title.png")), 570)
        self.menu_pipin = scale_to_height(
            _crop_alpha(_load("pipin.png")),
            245,
        )
        self.menu_rat = scale_to_height(
            _crop_alpha(_load("rat.png")),
            270,
        )
        self.app_art = _crop_alpha(_load("app_art.png"))
        self.app_icon = pygame.transform.scale(self.app_art, (64, 64))
        self.high_score_panel = scale_to_width(
            _crop_alpha(_load("high_score_panel.png")),
            290,
        )
        self.menu_tagline = scale_to_width(
            _crop_alpha(_load("pawsitive.png")),
            380,
        )
        self.keyboard_only_button = scale_to_width(
            _crop_alpha(_load("keyboard_only_button.png")),
            330,
        )

        track = scale_to_width(
            _load("palace_corridor.png"),
            LOGICAL_SIZE[0],
        )
        self.track_segment_height = track.get_height()
        self.gameplay_track = pygame.Surface(
            (track.get_width(), track.get_height() * 2),
            pygame.SRCALPHA,
        )
        self.gameplay_track.blit(track, (0, 0))
        self.gameplay_track.blit(
            pygame.transform.flip(track, False, True),
            (0, track.get_height()),
        )

        self.player = scale_to_height(
            _crop_alpha(_load("pipin.png")),
            126,
        )
        # Keep each run frame on its original 128 px canvas so Pipin's feet
        # stay anchored while the frames alternate.
        self.player_run_frames = tuple(
            scale_to_height(
                _load_path(
                    resource_path("assets", "images", "pipin_sprites", filename)
                ),
                146,
            )
            for filename in ("3.png", "4.png")
        )
        self.player_jump = scale_to_height(
            _load_path(
                resource_path("assets", "images", "pipin_sprites", "jump.png")
            ),
            146,
        )
        self.shield = scale_to_height(
            _load("shield.png"),
            215,
        )
        self.rat = scale_to_height(
            _crop_alpha(_load("rat.png")),
            96,
        )
        # Preserve the shared 160 px canvas so the rat stays grounded while
        # its two running poses alternate.
        self.rat_run_frames = tuple(
            scale_to_height(
                _load_path(
                    resource_path("assets", "images", "rat_sprites", filename)
                ),
                112,
            )
            for filename in ("1.png", "2.png")
        )
        self.fish = scale_to_height(
            _crop_alpha(_load("fish_item.png")),
            68,
        )
        self.cat_food = scale_to_height(
            _crop_alpha(_load("catfood_item.png")),
            72,
        )
        self.obstacles = tuple(
            scale_to_height(
                _crop_alpha(
                    _load_path(
                        resource_path("assets", "images", "obstacles", filename)
                    )
                ),
                125,
            )
            for filename in (
                "obstkl_books.png",
                "obstkl_table.png",
                "obstkl_trash.png",
            )
        )

        self.menu_buttons: dict[str, dict[str, pygame.Surface]] = {}
        target_widths = {
            "play": 230,
            "settings": 210,
            "exit": 210,
        }
        for action in ("play", "settings", "exit"):
            source_states = {
                state: _crop_alpha(
                    _load_button(f"{action}_{filename_state}.png")
                )
                for state, filename_state in (
                    ("default", "default"),
                    ("hover", "hover"),
                    ("pressed", "press"),
                )
            }
            scale = target_widths[action] / source_states["default"].get_width()
            self.menu_buttons[action] = {
                state: scale_by(image, scale)
                for state, image in source_states.items()
            }

        self.menu_buttons["settings"]["default"] = scale_to_height(
            _crop_alpha(_load_button("settings_icon_default.png")),
            64,
        )
        self.menu_buttons["exit"]["default"] = scale_to_height(
            _crop_alpha(_load_button("exit_icon_left.png")),
            64,
        )
