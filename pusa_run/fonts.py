from __future__ import annotations

from functools import lru_cache

import pygame

from .constants import resource_path


@lru_cache(maxsize=16)
def ui_font(size: int) -> pygame.font.Font:
    path = resource_path("assets", "fonts", "PressStart2P-Regular.ttf")
    return pygame.font.Font(str(path), size)


def fitted_ui_font(text: str, max_width: int, preferred_size: int) -> pygame.font.Font:
    for size in range(preferred_size, 11, -1):
        font = ui_font(size)
        if font.size(text)[0] <= max_width:
            return font
    return ui_font(12)
