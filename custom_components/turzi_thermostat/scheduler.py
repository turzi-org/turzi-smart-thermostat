"""Schedule resolution engine for Turzi Smart Thermostat."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Any

from .const import DAYS_OF_WEEK, SCHEDULE_MODE_OFFSETS, ScheduleMode

_LOGGER = logging.getLogger(__name__)


def _parse_time(time_str: str) -> time:
    """Parse a time string (HH:MM) into a time object."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


class ScheduleBlock:
    """A single schedule block definition."""

    def __init__(self, days: list[str], start: str, end: str, mode: str, temp_override: float | None = None) -> None:
        self.days = [d.lower() for d in days]
        self.start_time = _parse_time(start)
        self.end_time = _parse_time(end)
        self.mode = mode
        self.temp_override = temp_override
        self._start_str = start
        self._end_str = end

    @property
    def crosses_midnight(self) -> bool:
        return self.end_time <= self.start_time

    def contains(self, day: str, t: time) -> bool:
        day_lower = day.lower()
        if day_lower not in self.days:
            if self.crosses_midnight:
                prev_day_idx = (DAYS_OF_WEEK.index(day_lower) - 1) % 7
                prev_day = DAYS_OF_WEEK[prev_day_idx]
                if prev_day in self.days and t < self.end_time:
                    return True
            return False
        if self.crosses_midnight:
            return t >= self.start_time or t < self.end_time
        return self.start_time <= t < self.end_time

    def as_dict(self) -> dict:
        result = {"days": self.days, "start": self._start_str, "end": self._end_str, "mode": self.mode}
        if self.temp_override is not None:
            result["temp_override"] = self.temp_override
        return result


class ScheduleResult:
    """Result of a schedule resolution."""

    def __init__(self, mode: str, temp_offset: float | None, temp_override: float | None, next_transition: datetime | None, next_mode: str | None) -> None:
        self.mode = mode
        self.temp_offset = temp_offset
        self.temp_override = temp_override
        self.next_transition = next_transition
        self.next_mode = next_mode

    def get_effective_target(self, base_target: float) -> float | None:
        if self.mode == ScheduleMode.OFF:
            return None
        if self.temp_override is not None:
            return self.temp_override
        if self.temp_offset is not None:
            return base_target + self.temp_offset
        return base_target


class TurziScheduler:
    """Resolves schedule modes for spaces."""

    def __init__(self) -> None:
        self._schedules: dict[str, list[ScheduleBlock]] = {}

    def load_schedules(self, schedule_data: dict[str, list[dict]]) -> None:
        self._schedules = {}
        for space_id, blocks in schedule_data.items():
            self._schedules[space_id] = [
                ScheduleBlock(
                    days=block.get("days", []),
                    start=block.get("start", "00:00"),
                    end=block.get("end", "23:59"),
                    mode=block.get("mode", ScheduleMode.COMFORT),
                    temp_override=block.get("temp_override"),
                )
                for block in blocks
            ]

    def resolve(self, space_id: str, dt: datetime | None = None) -> ScheduleResult:
        """Resolve active mode for a space. Last matching block wins."""
        if dt is None:
            dt = datetime.now()
        day_name = DAYS_OF_WEEK[dt.weekday()]
        current_time = dt.time()
        blocks = self._schedules.get(space_id, [])
        active_mode = ScheduleMode.COMFORT
        active_override = None
        for block in blocks:
            if block.contains(day_name, current_time):
                active_mode = block.mode
                active_override = block.temp_override
        next_transition, next_mode = self._find_next_transition(space_id, dt, active_mode)
        temp_offset = SCHEDULE_MODE_OFFSETS.get(active_mode, 0.0)
        return ScheduleResult(mode=active_mode, temp_offset=temp_offset, temp_override=active_override, next_transition=next_transition, next_mode=next_mode)

    def _find_next_transition(self, space_id: str, dt: datetime, current_mode: str) -> tuple[datetime | None, str | None]:
        """Look ahead up to 48h for the next mode change."""
        blocks = self._schedules.get(space_id, [])
        if not blocks:
            return None, None
        check_interval = timedelta(minutes=15)
        max_lookahead = timedelta(hours=48)
        check_time = dt + check_interval
        while check_time - dt < max_lookahead:
            day_name = DAYS_OF_WEEK[check_time.weekday()]
            t = check_time.time()
            future_mode = ScheduleMode.COMFORT
            for block in blocks:
                if block.contains(day_name, t):
                    future_mode = block.mode
            if future_mode != current_mode:
                return check_time, future_mode
            check_time += check_interval
        return None, None


class EnergyTierScheduler:
    """Resolves energy rate tiers for time slots."""

    def __init__(self) -> None:
        self._tiers: list[dict] = []
        self._schedule: list[ScheduleBlock] = []

    def load(self, energy_rates: dict[str, Any]) -> None:
        self._tiers = energy_rates.get("tiers", [])
        raw_schedule = energy_rates.get("schedule", [])
        self._schedule = [
            ScheduleBlock(days=b.get("days", []), start=b.get("start", "00:00"), end=b.get("end", "23:59"), mode=b.get("tier", ""))
            for b in raw_schedule
        ]

    @property
    def is_configured(self) -> bool:
        return bool(self._tiers) and bool(self._schedule)

    @property
    def tiers(self) -> list[dict]:
        return self._tiers

    def resolve(self, dt: datetime | None = None) -> str | None:
        if not self.is_configured:
            return None
        if dt is None:
            dt = datetime.now()
        day_name = DAYS_OF_WEEK[dt.weekday()]
        current_time = dt.time()
        active_tier = None
        for block in self._schedule:
            if block.contains(day_name, current_time):
                active_tier = block.mode
        return active_tier

    def get_next_tier_change(self, dt: datetime | None = None) -> tuple[datetime | None, str | None]:
        if not self.is_configured:
            return None, None
        if dt is None:
            dt = datetime.now()
        current_tier = self.resolve(dt)
        check_interval = timedelta(minutes=15)
        max_lookahead = timedelta(hours=48)
        check_time = dt + check_interval
        while check_time - dt < max_lookahead:
            future_tier = self.resolve(check_time)
            if future_tier != current_tier:
                return check_time, future_tier
            check_time += check_interval
        return None, None

    def is_high_rate(self, tier_name: str | None) -> bool:
        if tier_name is None or not self._tiers:
            return False
        return tier_name == self._tiers[-1].get("name", "")

    def is_low_rate(self, tier_name: str | None) -> bool:
        if tier_name is None or not self._tiers:
            return False
        return tier_name == self._tiers[0].get("name", "")
