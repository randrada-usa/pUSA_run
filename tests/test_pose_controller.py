from __future__ import annotations

import unittest
from dataclasses import dataclass

from pusa_run.actions import Action
from pusa_run.pose_controller import CalibrationStatus, PoseController


@dataclass
class Landmark:
    x: float
    y: float
    visibility: float = 1.0
    presence: float = 1.0


def pose(shoulder_x: float, shoulder_y: float) -> list[Landmark]:
    values = [Landmark(0.5, 0.3) for _ in range(33)]
    values[11] = Landmark(shoulder_x - 0.08, shoulder_y)
    values[12] = Landmark(shoulder_x + 0.08, shoulder_y)
    values[23] = Landmark(shoulder_x - 0.06, shoulder_y + 0.28)
    values[24] = Landmark(shoulder_x + 0.06, shoulder_y + 0.28)
    return values


class PoseControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = PoseController(show_window=False)
        self.controller._update_snapshot(
            calibration=CalibrationStatus.READY,
            neutral_x=0.5,
            neutral_y=0.36,
            lane_threshold=0.07,
            jump_threshold=0.31,
        )
        self.controller._last_zone = 1

    def test_camera_zones_map_to_absolute_lanes(self) -> None:
        self.controller._process_landmarks(pose(0.40, 0.36))
        first = self.controller.poll_actions()
        self.assertEqual([event.action for event in first], [Action.LANE_LEFT])

        self.controller._process_landmarks(pose(0.40, 0.36))
        self.assertEqual(self.controller.poll_actions(), [])

        self.controller._process_landmarks(pose(0.50, 0.36))
        middle = self.controller.poll_actions()
        self.assertEqual([event.action for event in middle], [Action.LANE_CENTER])

        self.controller._process_landmarks(pose(0.61, 0.36))
        right = self.controller.poll_actions()
        self.assertEqual([event.action for event in right], [Action.LANE_RIGHT])

    def test_jump_requires_two_frames_and_resets(self) -> None:
        self.controller._process_landmarks(pose(0.5, 0.28))
        self.assertEqual(self.controller.poll_actions(), [])
        self.controller._process_landmarks(pose(0.5, 0.28))
        self.assertEqual(
            [event.action for event in self.controller.poll_actions()],
            [Action.JUMP],
        )
        self.controller._process_landmarks(pose(0.5, 0.28))
        self.assertEqual(self.controller.poll_actions(), [])
        self.controller._process_landmarks(pose(0.5, 0.36))
        self.controller._process_landmarks(pose(0.5, 0.28))
        self.controller._process_landmarks(pose(0.5, 0.28))
        self.assertEqual(
            [event.action for event in self.controller.poll_actions()],
            [Action.JUMP],
        )


if __name__ == "__main__":
    unittest.main()
