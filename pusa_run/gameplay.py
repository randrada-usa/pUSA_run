from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import pygame

from .actions import Action
from .constants import (
    COLORS,
    DAMAGE_INVULNERABILITY_SECONDS,
    LANE_CENTERS,
    MAX_HEARTS,
    PLAYER_Y,
    SHIELD_SECONDS,
)
from .difficulty import DifficultySnapshot, difficulty_at
from .fonts import fitted_ui_font, ui_font

if TYPE_CHECKING:
    from .assets import GameAssets

RAT_BASE_Y = 753.0
RAT_DISTANCE_STEP = 38.0
RAT_TRANSITION_SPEED = 140.0


class ObjectKind(str, Enum):
    OBSTACLE = "obstacle"
    CAT_FOOD = "cat_food"
    FISH = "fish"


@dataclass(slots=True)
class TrackObject:
    kind: ObjectKind
    lane: int
    y: float
    size: int
    variant: int = 0
    collected: bool = False

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(LANE_CENTERS[self.lane] - self.size / 2),
            int(self.y - self.size / 2),
            self.size,
            self.size,
        )


@dataclass(slots=True)
class Player:
    lane: int = 1
    x: float = float(LANE_CENTERS[1])
    jump_height: float = 0.0
    jump_velocity: float = 0.0
    hearts: int = MAX_HEARTS
    shield_timer: float = 0.0
    damage_timer: float = 0.0
    hurt_flash: float = 0.0

    @property
    def airborne(self) -> bool:
        return self.jump_height > 38.0

    def apply(self, action: Action) -> None:
        if action == Action.MOVE_LEFT:
            self.lane = max(0, self.lane - 1)
        elif action == Action.MOVE_RIGHT:
            self.lane = min(2, self.lane + 1)
        elif action == Action.LANE_LEFT:
            self.lane = 0
        elif action == Action.LANE_CENTER:
            self.lane = 1
        elif action == Action.LANE_RIGHT:
            self.lane = 2
        elif action == Action.JUMP and self.jump_height <= 1.0:
            self.jump_velocity = 720.0

    def update(self, dt: float) -> None:
        target_x = float(LANE_CENTERS[self.lane])
        self.x += (target_x - self.x) * min(1.0, dt * 12.0)

        if self.jump_height > 0.0 or self.jump_velocity > 0.0:
            self.jump_height += self.jump_velocity * dt
            self.jump_velocity -= 1700.0 * dt
            if self.jump_height <= 0.0:
                self.jump_height = 0.0
                self.jump_velocity = 0.0

        self.shield_timer = max(0.0, self.shield_timer - dt)
        self.damage_timer = max(0.0, self.damage_timer - dt)
        self.hurt_flash = max(0.0, self.hurt_flash - dt)

    def take_damage(self) -> bool:
        if self.damage_timer > 0.0:
            return False
        if self.shield_timer > 0.0:
            self.shield_timer = 0.0
            self.damage_timer = 0.7
            return False
        self.hearts = max(0, self.hearts - 1)
        self.damage_timer = DAMAGE_INVULNERABILITY_SECONDS
        self.hurt_flash = 0.45
        return True


class RunnerWorld:
    def __init__(self, seed: int | None = None) -> None:
        self.random = random.Random(seed)
        self.player = Player()
        self.objects: list[TrackObject] = []
        self.elapsed = 0.0
        self.distance = 0.0
        self.collectible_score = 0
        self.hits_taken = 0
        self.shield_blocks = 0
        self.pickups: list[ObjectKind] = []
        self.spawn_timer = 1.35
        self.scroll_offset = 0.0
        self.background_scroll = 0.0
        self.hit_slow_timer = 0.0
        self.rat_y = RAT_BASE_Y
        self.game_over = False
        self.last_difficulty = difficulty_at(0.0)

    @property
    def score(self) -> int:
        return int(self.distance) + self.collectible_score

    def apply_action(self, action: Action) -> str | None:
        """Apply *action*; return "jump" or "dodge" if it caused one, else None."""
        if self.game_over:
            return None
        was_jumping = self.player.jump_velocity > 0.0
        lane_before = self.player.lane
        self.player.apply(action)
        if action == Action.JUMP and not was_jumping and self.player.jump_velocity > 0.0:
            return "jump"
        if self.player.lane != lane_before:
            return "dodge"
        return None

    def update(self, dt: float, collision_grace: bool = False) -> None:
        if self.game_over:
            return
        # Keep collision steps small without discarding normal low-FPS frame time.
        remaining = min(max(dt, 0.0), 0.25)
        while remaining > 1e-9 and not self.game_over:
            step = min(remaining, 0.05)
            self._update_step(step, collision_grace)
            remaining -= step

    def _update_step(self, dt: float, collision_grace: bool) -> None:
        self.elapsed += dt
        self.player.update(dt)
        difficulty = difficulty_at(self.elapsed)
        self.last_difficulty = difficulty

        speed_factor = 0.58 if self.hit_slow_timer > 0.0 else 1.0
        self.hit_slow_timer = max(0.0, self.hit_slow_timer - dt)
        speed = difficulty.scroll_speed * speed_factor
        self.scroll_offset = (self.scroll_offset + speed * dt) % 96.0
        self.background_scroll += speed * dt
        self.distance += speed * dt / 22.0

        for item in self.objects:
            item.y += speed * dt
        self.spawn_timer -= dt
        if self.spawn_timer <= 0.0:
            self._spawn_pattern(difficulty)
            jitter = self.random.uniform(-0.12, 0.18)
            self.spawn_timer = max(0.78, difficulty.spawn_interval + jitter)

        self._handle_interactions(collision_grace)
        self._update_rat_position(dt)
        self.objects = [item for item in self.objects if item.y < 800 and not item.collected]
        self.game_over = self.player.hearts <= 0

    def _update_rat_position(self, dt: float) -> None:
        target_y = RAT_BASE_Y - (MAX_HEARTS - self.player.hearts) * RAT_DISTANCE_STEP
        if self.player.hearts <= 0:
            self.rat_y = target_y
            return
        distance = target_y - self.rat_y
        max_step = RAT_TRANSITION_SPEED * dt
        if abs(distance) <= max_step:
            self.rat_y = target_y
        else:
            self.rat_y += math.copysign(max_step, distance)

    def _spawn_pattern(self, difficulty: DifficultySnapshot) -> None:
        lanes = [0, 1, 2]
        first = self.random.choice(lanes)
        blocked = [first]
        if self.random.random() < difficulty.double_obstacle_chance:
            second = self.random.choice([lane for lane in lanes if lane != first])
            blocked.append(second)
        for lane in blocked:
            self.objects.append(
                TrackObject(
                    ObjectKind.OBSTACLE,
                    lane,
                    -70.0,
                    92,
                    variant=self.random.randrange(3),
                )
            )

        free = [lane for lane in lanes if lane not in blocked]
        item_roll = self.random.random()
        if self.player.hearts < MAX_HEARTS and item_roll < 0.08:
            self.objects.append(TrackObject(ObjectKind.FISH, self.random.choice(free), -185.0, 54))
        elif item_roll < 0.22:
            self.objects.append(TrackObject(ObjectKind.CAT_FOOD, self.random.choice(free), -175.0, 58))

    def _handle_interactions(self, collision_grace: bool) -> None:
        player_lane = self.player.lane
        for item in self.objects:
            if item.collected or item.lane != player_lane:
                continue
            vertical_distance = abs(item.y - PLAYER_Y)
            if item.kind == ObjectKind.OBSTACLE:
                if vertical_distance <= 58 and not self.player.airborne and not collision_grace:
                    consumed_shield = self.player.shield_timer > 0.0
                    damaged = self.player.take_damage()
                    if damaged:
                        self.hit_slow_timer = 0.8
                        self.hits_taken += 1
                    elif consumed_shield and self.player.shield_timer == 0.0:
                        self.shield_blocks += 1
                    if damaged or consumed_shield:
                        item.collected = True
            elif vertical_distance <= 62:
                item.collected = True
                self.pickups.append(item.kind)
                if item.kind == ObjectKind.CAT_FOOD:
                    self.player.shield_timer = SHIELD_SECONDS
                    self.collectible_score += 100
                elif item.kind == ObjectKind.FISH:
                    self.player.hearts = min(MAX_HEARTS, self.player.hearts + 1)
                    self.collectible_score += 150


def draw_world(
    surface: pygame.Surface,
    world: RunnerWorld,
    tracking_warning: str = "",
    assets: GameAssets | None = None,
) -> None:
    width, height = surface.get_size()
    if assets is not None:
        loop = assets.gameplay_track
        period = loop.get_height()
        offset = int(world.background_scroll % period)
        surface.blit(loop, (0, offset - period))
        surface.blit(loop, (0, offset))
    else:
        surface.fill(COLORS["hall"])
        road = pygame.Rect(310, 0, 660, height)
        pygame.draw.rect(surface, COLORS["floor_dark"], road)
        pygame.draw.rect(surface, COLORS["floor"], road.inflate(-20, 0))

        for lane_x in (530, 750):
            y = -96 + int(world.scroll_offset)
            while y < height:
                pygame.draw.rect(
                    surface,
                    (188, 208, 125),
                    (lane_x - 3, y, 6, 44),
                    border_radius=3,
                )
                y += 96

        for y in range(-80 + int(world.scroll_offset), height, 96):
            pygame.draw.line(surface, (178, 139, 82), (0, y), (300, y), 3)
            pygame.draw.line(surface, (178, 139, 82), (980, y), (width, y), 3)

    for item in sorted(world.objects, key=lambda entity: entity.y):
        if item.kind == ObjectKind.OBSTACLE:
            _draw_obstacle(surface, item, assets)
        elif item.kind == ObjectKind.CAT_FOOD:
            _draw_cat_food(surface, item, assets)
        else:
            _draw_fish(surface, item, assets)

    _draw_player_shadow(surface, world.player, assets)
    _draw_player(surface, world.player, world.elapsed, assets)
    _draw_rat(surface, world, assets)
    _draw_hud(surface, world, tracking_warning)


def _draw_player_shadow(
    surface: pygame.Surface,
    player: Player,
    assets: GameAssets | None,
) -> None:
    x = int(player.x)
    ground_y = PLAYER_Y + (40 if assets is not None else 48)
    shadow_width = max(34, int(86 - player.jump_height * 0.18))
    pygame.draw.ellipse(
        surface,
        COLORS["shadow"],
        (x - shadow_width // 2, ground_y, shadow_width, 20),
    )


def _draw_player(
    surface: pygame.Surface,
    player: Player,
    elapsed: float,
    assets: GameAssets | None,
) -> None:
    x = int(player.x)
    y = int(PLAYER_Y - player.jump_height)

    blink = player.damage_timer > 0 and int(player.damage_timer * 10) % 2 == 0
    if blink:
        return
    if assets is not None:
        if player.jump_height > 1.0:
            sprite = assets.player_jump
        else:
            frame_index = int(elapsed * 8.0) % len(assets.player_run_frames)
            sprite = assets.player_run_frames[frame_index]
        sprite_rect = sprite.get_rect(midbottom=(x, y + 50))
        if player.shield_timer > 0:
            shield_rect = assets.shield.get_rect(center=sprite_rect.center)
            surface.blit(assets.shield, shield_rect)
        surface.blit(sprite, sprite_rect)
        if player.hurt_flash > 0:
            flash = _hurt_flash_sprite(sprite)
            surface.blit(flash, sprite_rect)
        return

    bob = int(math.sin(elapsed * 11.0) * 3) if player.jump_height <= 1 else 0
    y += bob
    body_color = (235, 137, 61) if player.hurt_flash <= 0 else COLORS["red"]
    pygame.draw.ellipse(surface, body_color, (x - 38, y - 24, 76, 72))
    pygame.draw.circle(surface, body_color, (x, y - 38), 42)
    pygame.draw.polygon(surface, body_color, [(x - 35, y - 68), (x - 12, y - 55), (x - 32, y - 34)])
    pygame.draw.polygon(surface, body_color, [(x + 35, y - 68), (x + 12, y - 55), (x + 32, y - 34)])
    pygame.draw.circle(surface, COLORS["dark"], (x - 14, y - 42), 5)
    pygame.draw.circle(surface, COLORS["dark"], (x + 14, y - 42), 5)
    pygame.draw.polygon(surface, (244, 184, 181), [(x, y - 31), (x - 5, y - 25), (x + 5, y - 25)])
    pygame.draw.line(surface, COLORS["brown"], (x - 6, y - 20), (x - 19, y - 17), 2)
    pygame.draw.line(surface, COLORS["brown"], (x + 6, y - 20), (x + 19, y - 17), 2)

    if player.shield_timer > 0:
        radius = 61 + int(math.sin(elapsed * 8) * 3)
        pygame.draw.circle(surface, (93, 210, 236), (x, y - 10), radius, 4)


def _hurt_flash_sprite(sprite: pygame.Surface) -> pygame.Surface:
    """Tint Pipin red without making transparent canvas pixels visible."""
    flash = sprite.copy()
    flash.fill((255, 80, 80, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return flash


def _draw_rat(
    surface: pygame.Surface,
    world: RunnerWorld,
    assets: GameAssets | None,
) -> None:
    rat_y = world.rat_y
    x = int(world.player.x + _rat_dodge_offset(world, rat_y))
    if assets is not None:
        frame_index = int(world.elapsed * 8.0) % len(assets.rat_run_frames)
        sprite = assets.rat_run_frames[frame_index]
        shadow_width = max(48, round(sprite.get_width() * 0.68))
        shadow_height = max(12, round(sprite.get_height() * 0.13))
        pygame.draw.ellipse(
            surface,
            COLORS["shadow"],
            (
                x - shadow_width // 2,
                round(rat_y) - 10,
                shadow_width,
                shadow_height,
            ),
        )
        surface.blit(sprite, sprite.get_rect(midbottom=(x, rat_y)))
        return
    pygame.draw.ellipse(surface, COLORS["shadow"], (x - 30, rat_y - 8, 60, 12))
    pygame.draw.ellipse(surface, (107, 105, 117), (x - 30, rat_y - 40, 60, 48))
    pygame.draw.circle(surface, (125, 123, 137), (x, rat_y - 48), 28)
    pygame.draw.circle(surface, (235, 158, 177), (x - 18, rat_y - 66), 10)
    pygame.draw.circle(surface, (235, 158, 177), (x + 18, rat_y - 66), 10)
    pygame.draw.circle(surface, COLORS["dark"], (x - 9, rat_y - 50), 4)
    pygame.draw.circle(surface, COLORS["dark"], (x + 9, rat_y - 50), 4)


def _rat_dodge_offset(world: RunnerWorld, rat_y: float) -> float:
    """Return a smooth sideways dodge around obstacles in the rat's lane."""
    approach_distance = 150.0
    pass_distance = 55.0
    arc_span = approach_distance + pass_distance
    dodge_offset = 0.0
    for item in world.objects:
        if (
            item.kind != ObjectKind.OBSTACLE
            or item.collected
            or item.lane != world.player.lane
        ):
            continue
        progress = (item.y - (rat_y - approach_distance)) / arc_span
        if 0.0 <= progress <= 1.0:
            strength = math.sin(math.pi * progress) * 120.0
            if world.player.lane == 0:
                direction = 1.0
            elif world.player.lane == 2:
                direction = -1.0
            else:
                direction = -1.0 if item.variant % 2 == 0 else 1.0
            candidate = direction * strength
            if abs(candidate) > abs(dodge_offset):
                dodge_offset = candidate
    return dodge_offset


def _draw_obstacle(
    surface: pygame.Surface,
    item: TrackObject,
    assets: GameAssets | None,
) -> None:
    rect = item.rect
    if assets is not None:
        sprite = assets.obstacles[item.variant % len(assets.obstacles)]
        surface.blit(sprite, sprite.get_rect(midbottom=(rect.centerx, rect.bottom)))
        return
    pygame.draw.rect(surface, (119, 76, 48), rect, border_radius=8)
    pygame.draw.rect(surface, (183, 124, 65), rect.inflate(-10, -12), border_radius=5)
    for offset in (20, 44, 68):
        pygame.draw.line(surface, (245, 218, 159), (rect.left + 12, rect.top + offset), (rect.right - 12, rect.top + offset), 5)


def _draw_cat_food(
    surface: pygame.Surface,
    item: TrackObject,
    assets: GameAssets | None,
) -> None:
    rect = item.rect
    if assets is not None:
        surface.blit(
            assets.cat_food,
            assets.cat_food.get_rect(center=rect.center),
        )
        return
    pygame.draw.ellipse(surface, (220, 149, 71), rect)
    pygame.draw.ellipse(surface, (245, 207, 129), rect.inflate(-10, -18))
    pygame.draw.circle(surface, COLORS["brown"], rect.center, 7)
    pygame.draw.circle(surface, COLORS["brown"], (rect.centerx - 14, rect.centery + 4), 5)
    pygame.draw.circle(surface, COLORS["brown"], (rect.centerx + 14, rect.centery + 4), 5)


def _draw_fish(
    surface: pygame.Surface,
    item: TrackObject,
    assets: GameAssets | None,
) -> None:
    rect = item.rect
    if assets is not None:
        surface.blit(assets.fish, assets.fish.get_rect(center=rect.center))
        return
    pygame.draw.ellipse(surface, (238, 124, 70), rect.inflate(-8, -18))
    pygame.draw.polygon(surface, (238, 124, 70), [(rect.left + 6, rect.centery), (rect.left - 12, rect.top + 7), (rect.left - 12, rect.bottom - 7)])
    pygame.draw.circle(surface, COLORS["dark"], (rect.right - 15, rect.centery - 5), 3)


def _draw_hud(surface: pygame.Surface, world: RunnerWorld, tracking_warning: str) -> None:
    font = ui_font(20)
    small = ui_font(16)
    pygame.draw.rect(surface, (31, 29, 43, 220), (24, 20, 270, 126), border_radius=14)
    for index in range(MAX_HEARTS):
        color = COLORS["red"] if index < world.player.hearts else (100, 91, 92)
        _draw_heart(surface, 55 + index * 55, 51, color)
    score_text = f"Score  {world.score:06d}"
    score = fitted_ui_font(score_text, 230, 20).render(
        score_text, True, COLORS["white"]
    )
    surface.blit(score, (45, 94))

    difficulty = small.render(f"Speed tier {world.last_difficulty.tier + 1}", True, COLORS["cream"])
    surface.blit(difficulty, (1020, 31))
    if world.player.shield_timer > 0:
        shield = small.render(f"Shield {world.player.shield_timer:0.1f}s", True, (107, 225, 243))
        surface.blit(shield, (1020, 63))

    if tracking_warning:
        warning = fitted_ui_font(tracking_warning, 1120, 20).render(
            tracking_warning, True, COLORS["white"]
        )
        box = warning.get_rect(center=(640, 88)).inflate(34, 22)
        pygame.draw.rect(surface, COLORS["rust"], box, border_radius=12)
        surface.blit(warning, warning.get_rect(center=box.center))


def _draw_heart(surface: pygame.Surface, x: int, y: int, color: tuple[int, int, int]) -> None:
    pygame.draw.circle(surface, color, (x - 9, y), 12)
    pygame.draw.circle(surface, color, (x + 9, y), 12)
    pygame.draw.polygon(surface, color, [(x - 21, y + 4), (x + 21, y + 4), (x, y + 29)])
