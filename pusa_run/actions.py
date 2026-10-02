from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class Action(Enum):
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    LANE_LEFT = auto()
    LANE_CENTER = auto()
    LANE_RIGHT = auto()
    JUMP = auto()


@dataclass(slots=True)
class InputEvent:
    action: Action
    source: str
    timestamp: float
