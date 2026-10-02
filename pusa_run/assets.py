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

        track = scale_to_width(
            _load("gameplay_hall.png"),
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
        self.rat = scale_to_height(
            _crop_alpha(_load("rat.png")),
            96,
        )
        self.fish = scale_to_height(
            _crop_alpha(_load("fish_item.png")),
            68,
        )
        self.cat_food = scale_to_height(
            _crop_alpha(_load("catfood_item.png")),
            72,
        )

        self.menu_buttons: dict[str, dict[str, pygame.Surface]] = {}
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
            scale = 300 / source_states["default"].get_width()
            self.menu_buttons[action] = {
                state: scale_by(image, scale)
                for state, image in source_states.items()
            }
