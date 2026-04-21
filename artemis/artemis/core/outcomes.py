"""Daily outcomes logging + correlation analysis.

Logs daily snapshots of inputs (training done, sleep hours, practices done) and
outcomes (readiness, goals completed, mood, energy) to memory/outcomes/YYYY-MM.json.

Over time, correlation analysis surfaces what actually works for Shawn — not
what he thinks works. A simple mean-difference test across inputs.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from artemis.core.memory import MEMORY_DIR, load_running_context

log = logging.getLogger("artemis.outcomes")

OUTCOMES_DIR = MEMORY_DIR / "outcomes"

# Boolean inputs we track (controllable behaviors)
INPUT_FIELDS = [
    "training_done",
    "protein_target_hit",
    "morning_practice_done",
    "evening_review_done",
    "sabbath_observed",
    "deep_work_hit_target",
]

# Numeric inputs (observables)
INPUT_NUMERIC = [
    "sleep_hours",
    "deep_work_hours",
    "workouts_this_week",
]

# Outcomes we care about
OUTCOME_FIELDS = [
    "readiness",                # 0-100
    "mood",                      # 1-5
    "energy",                    # 1-5
    "goals_completed_today",    # count
    "deep_work_quality",        # 1-5 (subjective)
]


def _month_file(day: date) -> Path:
    OUTCOMES_DIR.mkdir(parents=True, exist_ok=True)
    return OUTCOMES_DIR / f"{day.year:04d}-{day.month:02d}.json"


def _load_month(day: date) -> list[dict]:
    f = _month_file(day)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_month(day: date, entries: list[dict]) -> None:
    _month_file(day).write_text(
        json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def log_daily_outcome(
    day: Optional[str] = None,
    inputs: Optional[dict] = None,
    outcomes: Optional[dict] = None,
) -> dict:
    """Append (or replace) the outcome entry for a given day. Returns the entry."""
    d = date.fromisoformat(day) if day else date.today()
    entries = _load_month(d)

    iso = d.isoformat()
    entry = next((e for e in entries if e["date"] == iso), None)
    if entry is None:
        entry = {"date": iso, "inputs": {}, "outcomes": {}, "updated_at": None}
        entries.append(entry)

    if inputs:
        entry["inputs"].update(inputs)
    if outcomes:
        entry["outcomes"].update(outcomes)
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()

    _save_month(d, entries)
    return entry


def snapshot_outcome_from_context() -> dict:
    """Build today's entry from the current running_context (auto-log)."""
    ctx = load_running_context()
    body = ctx.get("body", {}) or {}
    work = ctx.get("work", {}) or {}
    spirit = ctx.get("spirit", {}) or {}

    dw = work.get("deep_work_hours_this_week") or 0
    dw_target = work.get("deep_work_target_hours") or 20
    weekday_fraction = max((date.today().weekday() + 1) / 7.0, 0.01)
    pro_rata_target = dw_target * weekday_fraction

    inputs = {
        "workouts_this_week": body.get("weekly_workouts_completed"),
        "deep_work_hours": dw,
        "morning_practice_done": (spirit.get("morning_practice_streak") or 0) > 0,
        "evening_review_done": (spirit.get("evening_review_streak") or 0) > 0,
        "sabbath_observed": bool(spirit.get("sabbath_observed_last_week")),
        "deep_work_hit_target": dw >= pro_rata_target,
        "protein_target_hit": body.get("nutrition_on_track"),
    }
    outcomes = {
        "readiness": body.get("current_readiness"),
        "goals_completed_today": work.get("goal_completion_this_week", 0),
    }
    return log_daily_outcome(inputs=inputs, outcomes=outcomes)


def load_recent_outcomes(n_days: int = 60) -> list[dict]:
    """Load all outcome entries from the last n_days across month files."""
    today = date.today()
    cutoff = today - timedelta(days=n_days)
    all_entries: list[dict] = []

    months_seen: set[tuple[int, int]] = set()
    d = cutoff
    while d <= today:
        if (d.year, d.month) not in months_seen:
            months_seen.add((d.year, d.month))
            all_entries.extend(_load_month(d))
        d = d.replace(day=28) + timedelta(days=4)
        d = d.replace(day=1)

    filtered = [
        e for e in all_entries
        if e.get("date") and cutoff.isoformat() <= e["date"] <= today.isoformat()
    ]
    return sorted(filtered, key=lambda e: e["date"])


# ---------------------------------------------------------------------------
# Correlation analysis
# ---------------------------------------------------------------------------

def _mean(values: list[float]) -> Optional[float]:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def correlate_boolean_input(
    entries: list[dict],
    input_field: str,
    outcome_field: str,
) -> Optional[dict]:
    """For a boolean input, return mean outcome when True vs False + sample sizes."""
    true_outcomes = []
    false_outcomes = []
    for e in entries:
        iv = e.get("inputs", {}).get(input_field)
        ov = e.get("outcomes", {}).get(outcome_field)
        if iv is None or ov is None:
            continue
        if iv:
            true_outcomes.append(ov)
        else:
            false_outcomes.append(ov)

    m_true = _mean(true_outcomes)
    m_false = _mean(false_outcomes)
    if m_true is None or m_false is None:
        return None

    return {
        "input": input_field,
        "outcome": outcome_field,
        "mean_when_true": round(m_true, 2),
        "mean_when_false": round(m_false, 2),
        "delta": round(m_true - m_false, 2),
        "n_true": len(true_outcomes),
        "n_false": len(false_outcomes),
    }


def analyze_patterns(n_days: int = 60, min_sample: int = 5) -> dict:
    """Run correlations across all inputs × outcomes. Returns strongest signals."""
    entries = load_recent_outcomes(n_days=n_days)
    if len(entries) < min_sample:
        return {
            "insufficient_data": True,
            "days_logged": len(entries),
            "days_needed": min_sample,
            "correlations": [],
        }

    correlations: list[dict] = []
    for inp in INPUT_FIELDS:
        for out in OUTCOME_FIELDS:
            c = correlate_boolean_input(entries, inp, out)
            if c is None:
                continue
            if c["n_true"] < min_sample // 2 or c["n_false"] < min_sample // 2:
                continue
            if abs(c["delta"]) < 0.5 and out != "readiness":
                continue
            if out == "readiness" and abs(c["delta"]) < 3:
                continue
            correlations.append(c)

    correlations.sort(key=lambda c: abs(c["delta"]), reverse=True)

    return {
        "insufficient_data": False,
        "days_logged": len(entries),
        "correlations": correlations[:10],
        "top_insight": _phrase_top_insight(correlations[0]) if correlations else None,
    }


def _phrase_top_insight(c: dict) -> str:
    """Turn a correlation into a human-readable insight."""
    input_name = c["input"].replace("_", " ")
    outcome_name = c["outcome"].replace("_", " ")
    direction = "higher" if c["delta"] > 0 else "lower"
    magnitude = abs(c["delta"])

    if c["outcome"] == "readiness":
        mag_str = f"{magnitude:.0f} points"
    else:
        mag_str = f"{magnitude:.1f} points (1-5 scale)"

    return (
        f"On days when '{input_name}' was done, your {outcome_name} "
        f"averaged {mag_str} {direction} "
        f"(n={c['n_true']} vs n={c['n_false']} control days)."
    )
