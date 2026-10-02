from __future__ import annotations

from pathlib import Path
import sys

GAME_TITLE = "pUSA Run"
LOGICAL_WIDTH = 1280
LOGICAL_HEIGHT = 720
LOGICAL_SIZE = (LOGICAL_WIDTH, LOGICAL_HEIGHT)
FPS = 60

LANE_CENTERS = (420, 640, 860)
PLAYER_Y = 570

CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30
CAMERA_WINDOW = "pUSA Run - Camera"

TRACKING_GRACE_SECONDS = 2.0
DAMAGE_INVULNERABILITY_SECONDS = 2.0
SHIELD_SECONDS = 8.0
MAX_HEARTS = 3

COLORS = {
    "cream": (255, 244, 211),
    "gold": (245, 176, 45),
    "orange": (230, 106, 46),
    "rust": (154, 56, 42),
    "brown": (91, 57, 43),
    "dark": (31, 29, 43),
    "hall": (226, 194, 126),
    "floor": (77, 135, 79),
    "floor_dark": (53, 102, 59),
    "white": (250, 250, 245),
    "red": (222, 55, 64),
    "green": (65, 181, 112),
    "blue": (69, 135, 196),
    "shadow": (29, 47, 35),
}


def project_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return project_root().joinpath(*parts)
