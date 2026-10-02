from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

from .actions import Action, InputEvent
from .constants import (
    CAMERA_FPS,
    CAMERA_HEIGHT,
    CAMERA_WIDTH,
    CAMERA_WINDOW,
    resource_path,
)


class CalibrationStatus(str, Enum):
    WAITING = "Stand centered - head to hips visible"
    SAMPLING = "Hold still while calibrating"
    READY = "Calibrated"


@dataclass(slots=True)
class PoseSnapshot:
    tracking: bool = False
    last_seen: float = 0.0
    shoulder_x: float = 0.5
    shoulder_y: float = 0.35
    hip_y: float = 0.65
    confidence: float = 0.0
    action_text: str = "NO POSE"
    calibration: CalibrationStatus = CalibrationStatus.WAITING
    calibration_progress: float = 0.0
    neutral_x: float = 0.5
    neutral_y: float = 0.35
    lane_threshold: float = 0.09
    jump_threshold: float = 0.29
    camera_error: str = ""


class PoseController:
    """Own the webcam and turn upper-body landmarks into discrete actions."""

    CONNECTIONS = (
        (0, 11), (0, 12), (11, 12),
        (11, 13), (13, 15), (12, 14), (14, 16),
        (11, 23), (12, 24), (23, 24),
    )

    def __init__(
        self,
        camera_index: int = 0,
        model_path: Path | None = None,
        show_window: bool = True,
    ) -> None:
        self.camera_index = camera_index
        self.model_path = model_path or resource_path("models", "pose_landmarker_lite.task")
        self._show_window = show_window
        self._events: queue.SimpleQueue[InputEvent] = queue.SimpleQueue()
        self._snapshot = PoseSnapshot()
        self._snapshot_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._recalibrate = threading.Event()
        self._camera_switch: queue.SimpleQueue[int] = queue.SimpleQueue()

        self._neutral_samples: list[tuple[float, float, float, float]] = []
        self._lane_armed = True
        self._jump_armed = True
        self._jump_frames = 0
        self._last_lane_action = 0.0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="pose-camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        cv2.destroyAllWindows()

    def set_camera(self, index: int) -> None:
        self.camera_index = max(0, int(index))
        self._camera_switch.put(self.camera_index)
        self.recalibrate()

    def set_window_visible(self, visible: bool) -> None:
        self._show_window = visible
        if not visible:
            try:
                cv2.destroyWindow(CAMERA_WINDOW)
            except cv2.error:
                pass

    def recalibrate(self) -> None:
        self._recalibrate.set()

    def snapshot(self) -> PoseSnapshot:
        with self._snapshot_lock:
            return replace(self._snapshot)

    def poll_actions(self) -> list[InputEvent]:
        events: list[InputEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events

    def _update_snapshot(self, **changes: object) -> None:
        with self._snapshot_lock:
            for key, value in changes.items():
                setattr(self._snapshot, key, value)

    def _reset_calibration(self) -> None:
        self._neutral_samples.clear()
        self._lane_armed = True
        self._jump_armed = True
        self._jump_frames = 0
        self._update_snapshot(
            calibration=CalibrationStatus.WAITING,
            calibration_progress=0.0,
            action_text="CENTER YOUR BODY",
        )

    def _open_camera(self, index: int) -> cv2.VideoCapture:
        backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
        capture = cv2.VideoCapture(index, backend)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        capture.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return capture

    def _create_landmarker(self):
        if not self.model_path.exists():
            raise FileNotFoundError(f"Pose model not found: {self.model_path}")
        base_options = mp.tasks.BaseOptions(model_asset_path=str(self.model_path))
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.55,
            min_pose_presence_confidence=0.55,
            min_tracking_confidence=0.55,
            output_segmentation_masks=False,
        )
        return mp.tasks.vision.PoseLandmarker.create_from_options(options)

    def _run(self) -> None:
        capture: cv2.VideoCapture | None = None
        landmarker = None
        timestamp_ms = 0
        try:
            landmarker = self._create_landmarker()
            capture = self._open_camera(self.camera_index)
            if not capture.isOpened():
                raise RuntimeError(f"Could not open camera {self.camera_index}")
            self._reset_calibration()

            while not self._stop.is_set():
                while True:
                    try:
                        new_index = self._camera_switch.get_nowait()
                    except queue.Empty:
                        break
                    capture.release()
                    capture = self._open_camera(new_index)
                    if not capture.isOpened():
                        raise RuntimeError(f"Could not open camera {new_index}")

                if self._recalibrate.is_set():
                    self._recalibrate.clear()
                    self._reset_calibration()

                ok, frame = capture.read()
                if not ok:
                    self._update_snapshot(tracking=False, camera_error="Camera frame unavailable")
                    time.sleep(0.03)
                    continue

                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb = np.ascontiguousarray(rgb)
                timestamp_ms += max(1, int(1000 / CAMERA_FPS))
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect_for_video(image, timestamp_ms)
                landmarks = result.pose_landmarks[0] if result.pose_landmarks else None
                self._process_landmarks(landmarks)
                self._decorate_frame(frame, landmarks)

                if self._show_window:
                    cv2.imshow(CAMERA_WINDOW, frame)
                    cv2.waitKey(1)

        except Exception as exc:  # Camera failures should not take down keyboard play.
            self._update_snapshot(
                tracking=False,
                camera_error=str(exc),
                action_text="CAMERA OFFLINE - KEYBOARD ACTIVE",
            )
        finally:
            if capture is not None:
                capture.release()
            if landmarker is not None:
                landmarker.close()
            cv2.destroyAllWindows()

    @staticmethod
    def _visible(landmark: object, minimum: float = 0.45) -> bool:
        visibility = getattr(landmark, "visibility", None)
        presence = getattr(landmark, "presence", None)
        return (visibility is None or visibility >= minimum) and (
            presence is None or presence >= minimum
        )

    def _process_landmarks(self, landmarks: list[object] | None) -> None:
        now = time.monotonic()
        if not landmarks or len(landmarks) < 25:
            self._update_snapshot(tracking=False, action_text="TRACKING LOST")
            return

        required = [landmarks[i] for i in (11, 12, 23, 24)]
        if not all(self._visible(item) for item in required):
            self._update_snapshot(tracking=False, action_text="HEAD TO HIPS MUST BE VISIBLE")
            return

        left_shoulder, right_shoulder, left_hip, right_hip = required
        shoulder_x = (left_shoulder.x + right_shoulder.x) / 2.0
        shoulder_y = (left_shoulder.y + right_shoulder.y) / 2.0
        hip_y = (left_hip.y + right_hip.y) / 2.0
        shoulder_width = abs(left_shoulder.x - right_shoulder.x)
        torso_length = max(0.08, hip_y - shoulder_y)
        confidence_values = [
            value
            for landmark in required
            for value in (getattr(landmark, "visibility", None),)
            if value is not None
        ]
        confidence = min(confidence_values) if confidence_values else 1.0

        snapshot = self.snapshot()
        if snapshot.calibration != CalibrationStatus.READY:
            centered = 0.28 <= shoulder_x <= 0.72 and 0.10 <= shoulder_y <= 0.62
            if centered:
                self._neutral_samples.append(
                    (shoulder_x, shoulder_y, shoulder_width, torso_length)
                )
                progress = min(1.0, len(self._neutral_samples) / 60.0)
                self._update_snapshot(
                    tracking=True,
                    last_seen=now,
                    shoulder_x=shoulder_x,
                    shoulder_y=shoulder_y,
                    hip_y=hip_y,
                    confidence=confidence,
                    calibration=CalibrationStatus.SAMPLING,
                    calibration_progress=progress,
                    action_text="HOLD STILL",
                    camera_error="",
                )
                if len(self._neutral_samples) >= 60:
                    samples = np.asarray(self._neutral_samples, dtype=np.float32)
                    neutral_x, neutral_y, width, torso = np.median(samples, axis=0)
                    lane_threshold = max(0.055, float(width) * 0.38)
                    jump_line = float(neutral_y) - max(0.035, float(torso) * 0.18)
                    self._update_snapshot(
                        calibration=CalibrationStatus.READY,
                        calibration_progress=1.0,
                        neutral_x=float(neutral_x),
                        neutral_y=float(neutral_y),
                        lane_threshold=lane_threshold,
                        jump_threshold=jump_line,
                        action_text="READY",
                    )
            else:
                self._neutral_samples.clear()
                self._update_snapshot(
                    tracking=True,
                    last_seen=now,
                    shoulder_x=shoulder_x,
                    shoulder_y=shoulder_y,
                    hip_y=hip_y,
                    confidence=confidence,
                    calibration=CalibrationStatus.WAITING,
                    calibration_progress=0.0,
                    action_text="CENTER YOUR BODY",
                    camera_error="",
                )
            return

        action_text = "CENTER"
        delta_x = shoulder_x - snapshot.neutral_x
        reset_band = snapshot.lane_threshold * 0.45
        if abs(delta_x) <= reset_band:
            self._lane_armed = True
        elif self._lane_armed and now - self._last_lane_action >= 0.28:
            if delta_x <= -snapshot.lane_threshold:
                self._emit(Action.MOVE_LEFT, now)
                action_text = "LEFT"
                self._lane_armed = False
                self._last_lane_action = now
            elif delta_x >= snapshot.lane_threshold:
                self._emit(Action.MOVE_RIGHT, now)
                action_text = "RIGHT"
                self._lane_armed = False
                self._last_lane_action = now

        if shoulder_y < snapshot.jump_threshold:
            self._jump_frames += 1
            if self._jump_armed and self._jump_frames >= 2:
                self._emit(Action.JUMP, now)
                action_text = "JUMP"
                self._jump_armed = False
        else:
            self._jump_frames = 0
            if shoulder_y > snapshot.jump_threshold + 0.025:
                self._jump_armed = True

        self._update_snapshot(
            tracking=True,
            last_seen=now,
            shoulder_x=shoulder_x,
            shoulder_y=shoulder_y,
            hip_y=hip_y,
            confidence=confidence,
            action_text=action_text,
            camera_error="",
        )

    def _emit(self, action: Action, timestamp: float) -> None:
        self._events.put(InputEvent(action=action, source="camera", timestamp=timestamp))

    def _decorate_frame(self, frame: np.ndarray, landmarks: list[object] | None) -> None:
        height, width = frame.shape[:2]
        snapshot = self.snapshot()

        if landmarks:
            for start, end in self.CONNECTIONS:
                if start >= len(landmarks) or end >= len(landmarks):
                    continue
                a, b = landmarks[start], landmarks[end]
                if self._visible(a, 0.25) and self._visible(b, 0.25):
                    cv2.line(
                        frame,
                        (int(a.x * width), int(a.y * height)),
                        (int(b.x * width), int(b.y * height)),
                        (58, 219, 255),
                        2,
                        cv2.LINE_AA,
                    )

        if snapshot.calibration == CalibrationStatus.READY:
            left = int((snapshot.neutral_x - snapshot.lane_threshold) * width)
            right = int((snapshot.neutral_x + snapshot.lane_threshold) * width)
            jump = int(snapshot.jump_threshold * height)
            cv2.line(frame, (left, 0), (left, height), (255, 166, 47), 2)
            cv2.line(frame, (right, 0), (right, height), (255, 166, 47), 2)
            cv2.line(frame, (0, jump), (width, jump), (69, 218, 102), 2)
            cv2.putText(frame, "JUMP LINE", (12, max(25, jump - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (69, 218, 102), 2)

        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (width, 78), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
        status = snapshot.action_text
        if snapshot.calibration != CalibrationStatus.READY:
            status = f"{snapshot.calibration.value} {int(snapshot.calibration_progress * 100)}%"
        cv2.putText(frame, status, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, "F2 hides this window", (16, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (210, 210, 210), 1, cv2.LINE_AA)

