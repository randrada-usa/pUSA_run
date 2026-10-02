from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Preferences:
    high_score: int = 0
    camera_index: int = 0
    fullscreen: bool = False
    tutorial_complete: bool = False
    language: str = "en"
    show_camera: bool = True
    music_volume: float = 0.7
    sfx_volume: float = 0.8


def save_directory() -> Path:
    base = os.getenv("APPDATA")
    if base:
        return Path(base) / "pUSA Run"
    return Path.home() / ".pusa_run"


class SaveStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (save_directory() / "save.json")

    def load(self) -> Preferences:
        try:
            raw: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return Preferences()

        allowed = {field.name for field in fields(Preferences)}
        clean = {key: value for key, value in raw.items() if key in allowed}
        try:
            return Preferences(**clean)
        except (TypeError, ValueError):
            return Preferences()

    def save(self, preferences: Preferences) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(preferences), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)

