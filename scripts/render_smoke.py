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
from pusa_run.constants import resource_path
from pusa_run.gameplay import ObjectKind, RunnerWorld, TrackObject, draw_world
from pusa_run.intro_video import IntroVideo
from pusa_run.pose_controller import PoseSnapshot


def main() -> None:
    output = PROJECT_ROOT / "tmp" / "screens"
    output.mkdir(parents=True, exist_ok=True)
    with patch("pusa_run.pose_controller.PoseController.start"):
        app = GameApp()
    try:
        app.preferences.high_score = 4_459
        app._menu_chase_x = 968.0
        app._menu_chase_elapsed = 1.0
        app._draw_menu((-1, -1))
        pygame.image.save(app.canvas, output / "menu.png")

        app._draw_menu((640, 380))
        pygame.image.save(app.canvas, output / "menu_hover.png")

        with patch(
            "pygame.mouse.get_pressed",
            return_value=(True, False, False),
        ):
            app._draw_menu((640, 380))
        pygame.image.save(app.canvas, output / "menu_pressed.png")

        app._menu_chase_direction = -1
        app._menu_chase_x = 312.0
        app._menu_chase_elapsed = 2.0
        app._draw_menu((-1, -1))
        pygame.image.save(app.canvas, output / "menu_reverse.png")

        intro = IntroVideo(resource_path("assets", "start_vid.mp4"))
        try:
            intro.update(1.0)
            intro.draw(app.canvas)
            pygame.image.save(app.canvas, output / "intro.png")
        finally:
            intro.release()

        world = RunnerWorld(seed=12)
        world.elapsed = 18.0
        world.distance = 640.0
        world.background_scroll = 310.0
        world.spawn_timer = 99.0
        world.objects = [
            TrackObject(ObjectKind.FISH, 0, 250.0, 68),
            TrackObject(ObjectKind.OBSTACLE, 1, 245.0, 92),
            TrackObject(ObjectKind.CAT_FOOD, 2, 250.0, 72),
        ]
        draw_world(app.canvas, world, "", app.assets)
        pygame.image.save(app.canvas, output / "gameplay.png")

        app.screen = Screen.CALIBRATION
        pose = PoseSnapshot(
            tracking=True,
            calibration_progress=0.67,
        )
        app._draw_calibration(pose, (-1, -1))
        pygame.image.save(app.canvas, output / "calibration.png")

        app._draw_settings(PoseSnapshot(), (-1, -1))
        pygame.image.save(app.canvas, output / "settings.png")

        draw_world(app.canvas, world, "", app.assets)
        app.final_score = 12_340
        app.new_high_score = True
        app._draw_game_over((-1, -1))
        pygame.image.save(app.canvas, output / "game_over.png")
    finally:
        app.camera.stop()
        pygame.quit()


if __name__ == "__main__":
    main()
