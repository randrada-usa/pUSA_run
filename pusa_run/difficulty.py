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
    """Ramp quickly through the first minute, then grow more slowly."""
    elapsed = max(0.0, elapsed)
    # Frame-time sums can land a few nanoseconds below an exact tier boundary.
    tier = min(24, int((elapsed + 1e-6) // 10.0))
    introduction = min(1.0, elapsed / 20.0)
    first_minute_tiers = min(tier, 6)
    later_tiers = max(0, tier - 6)
    scroll_speed = 245.0 + 20.0 * introduction + 30.0 * first_minute_tiers
    scroll_speed += 10.0 * later_tiers
    scroll_speed = min(scroll_speed, 745.0)
    spawn_interval = max(0.78, 1.75 - 0.08 * first_minute_tiers - 0.012 * later_tiers)
    double_chance = min(0.75, max(0.0, (first_minute_tiers - 1) * 0.07) + 0.01 * later_tiers)
    return DifficultySnapshot(
        elapsed=elapsed,
        tier=tier,
        scroll_speed=scroll_speed,
        spawn_interval=spawn_interval,
        double_obstacle_chance=double_chance,
    )

