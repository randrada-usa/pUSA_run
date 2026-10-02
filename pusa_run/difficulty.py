from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DifficultySnapshot:
    elapsed: float
    tier: int
    scroll_speed: float
    spawn_interval: float
    double_obstacle_chance: float


def difficulty_at(elapsed: float) -> DifficultySnapshot:
    """Return a gradual, capped difficulty curve for a run."""
    elapsed = max(0.0, elapsed)
    tier = min(24, int(elapsed // 10.0))
    introduction = min(1.0, elapsed / 20.0)
    scroll_speed = 245.0 + 20.0 * introduction + 7.5 * tier
    scroll_speed = min(scroll_speed, 445.0)
    spawn_interval = max(0.95, 1.75 - 0.035 * tier)
    double_chance = min(0.48, max(0.0, (tier - 1) * 0.025))
    return DifficultySnapshot(
        elapsed=elapsed,
        tier=tier,
        scroll_speed=scroll_speed,
        spawn_interval=spawn_interval,
        double_obstacle_chance=double_chance,
    )

