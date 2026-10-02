from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["APPDATA"] = str(PROJECT_ROOT / "tmp" / "smoke-profile")

import pygame

from pusa_run.app import GameApp, Screen
from pusa_run.gameplay import RunnerWorld, draw_world
from pusa_run.pose_controller import PoseSnapshot


def main() -> None:
    output = PROJECT_ROOT / "tmp" / "screens"
    output.mkdir(parents=True, exist_ok=True)
    with patch("pusa_run.pose_controller.PoseController.start"):
        app = GameApp()
    try:
        app._draw_menu((-1, -1))
        pygame.image.save(app.canvas, output / "menu.png")

        world = RunnerWorld(seed=12)
        for _ in range(360):
            world.update(1 / 60)
        draw_world(app.canvas, world, "")
        pygame.image.save(app.canvas, output / "gameplay.png")

        app.screen = Screen.CALIBRATION
        pose = PoseSnapshot(
            tracking=True,
            calibration_progress=0.67,
        )
        app._draw_calibration(pose, (-1, -1))
        pygame.image.save(app.canvas, output / "calibration.png")
    finally:
        app.camera.stop()
        pygame.quit()


if __name__ == "__main__":
    main()
