from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .models import TaskInstance


SCORING_VERSION = "individual-points-2026.08"


@dataclass(frozen=True)
class ScoreResult:
    points: int
    reason: str


def local_minute(value: datetime, timezone: str) -> int:
    localized = value.astimezone(ZoneInfo(timezone))
    return localized.hour * 60 + localized.minute


def score_completed_task(
    task: TaskInstance,
    *,
    completed_at: datetime,
    timezone: str,
) -> ScoreResult:
    minute = local_minute(completed_at, timezone)
    on_time = minute <= task.available_until_minute
    on_time_bonus = round(task.base_points * 0.1) if on_time else 0
    points = min(task.maximum_points, task.base_points + on_time_bonus)
    reason = (
        f"{task.base_points} base + {on_time_bonus} on-time bonus"
        if on_time_bonus
        else f"{task.base_points} base points"
    )
    return ScoreResult(points=points, reason=reason)
