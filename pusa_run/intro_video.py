from __future__ import annotations

from pathlib import Path

import cv2
import pygame


INTRO_FADE_IN_SECONDS = 0.35
INTRO_FADE_OUT_SECONDS = 0.5


class IntroVideo:
    """Decode a short MP4 into a Pygame surface using the existing OpenCV runtime."""

    def __init__(self, path: Path) -> None:
        self.capture = cv2.VideoCapture(str(path))
        self.fps = self.capture.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count = max(
            0,
            int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT)),
        )
        self.duration = self.frame_count / self.fps if self.frame_count else 0.0
        self.elapsed = 0.0
        self.frame_index = -1
        self.frame: pygame.Surface | None = None
        self.available = self.capture.isOpened() and self.frame_count > 0
        if self.available:
            self._decode_through(0)

    @property
    def fade_out_started(self) -> bool:
        return self.elapsed >= max(0.0, self.duration - INTRO_FADE_OUT_SECONDS)

    def update(self, dt: float) -> bool:
        """Advance playback and return True once the video has ended."""
        if not self.available:
            return True
        self.elapsed = min(self.duration, self.elapsed + max(0.0, dt))
        target = min(self.frame_count - 1, int(self.elapsed * self.fps))
        if not self._decode_through(target):
            return True
        return self.elapsed >= self.duration

    def draw(self, target: pygame.Surface) -> None:
        target.fill((0, 0, 0))
        if self.frame is None:
            return

        width, height = target.get_size()
        source_width, source_height = self.frame.get_size()
        scale = max(width / source_width, height / source_height)
        scaled_size = (
            max(1, round(source_width * scale)),
            max(1, round(source_height * scale)),
        )
        frame = pygame.transform.smoothscale(self.frame, scaled_size)
        target.blit(frame, frame.get_rect(center=(width // 2, height // 2)))

        fade_in = min(1.0, self.elapsed / INTRO_FADE_IN_SECONDS)
        fade_out = min(
            1.0,
            max(0.0, self.duration - self.elapsed) / INTRO_FADE_OUT_SECONDS,
        )
        visibility = min(fade_in, fade_out)
        if visibility < 1.0:
            overlay = pygame.Surface(target.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, round((1.0 - visibility) * 255)))
            target.blit(overlay, (0, 0))

    def release(self) -> None:
        self.capture.release()

    def _decode_through(self, target_index: int) -> bool:
        while self.frame_index < target_index:
            ok, image = self.capture.read()
            if not ok:
                return False
            self.frame_index += 1
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            height, width = rgb.shape[:2]
            self.frame = pygame.image.frombuffer(
                rgb.tobytes(),
                (width, height),
                "RGB",
            ).copy()
        return self.frame is not None
