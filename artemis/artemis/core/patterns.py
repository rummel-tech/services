"""Cross-domain pattern detector.

Reads the running context + active signals and detects compound patterns
that no single module can see. Returns a list of Pattern objects with
severity and Artemis-voice messages ready for injection into the briefing.

Patterns are evaluated in priority order. Once a critical pattern fires,
lower-priority patterns in the same domain are suppressed to avoid noise.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from artemis.core.signals import get_active_signals

log = logging.getLogger("artemis.patterns")

Severity = Literal["insight", "warning", "critical"]


@dataclass
class DetectedPattern:
    name: str
    severity: Severity
    domains: list[str]          # which domains this pattern spans
    headline: str               # short label (for UI badges)
    message: str                # what Artemis says — in Artemis voice
    signal_to_publish: Optional[tuple[str, str, dict]] = None  # (source, type, data) to auto-publish


def _days_since(iso_date: Optional[str]) -> Optional[int]:
    """Return integer days since an ISO date string, or None if not set."""
    if not iso_date:
        return None
    try:
        dt = datetime.fromisoformat(iso_date).date()
        return (date.today() - dt).days
    except (ValueError, TypeError):
        return None


def _pct(completed: Optional[float], target: Optional[float]) -> Optional[float]:
    """Return completion percentage, or None if data missing."""
    if completed is None or target is None or target == 0:
        return None
    return (completed / target) * 100


# ---------------------------------------------------------------------------
# Individual pattern detectors
# ---------------------------------------------------------------------------

def _detect_burnout_early_warning(ctx: dict, signals: list[dict]) -> Optional[DetectedPattern]:
    body = ctx.get("body", {})
    work = ctx.get("work", {})
    spirit = ctx.get("spirit", {})
    travel = ctx.get("travel", {})
    wealth = ctx.get("wealth", {})

    score = 0
    reasons = []

    # Low readiness
    readiness = body.get("current_readiness")
    if readiness is not None and readiness < 65:
        score += 2
        reasons.append(f"readiness at {readiness}")

    # Training falling behind
    workout_pct = _pct(body.get("weekly_workouts_completed"), body.get("weekly_workouts_target"))
    if workout_pct is not None and workout_pct < 50:
        score += 1
        reasons.append(f"only {workout_pct:.0f}% of workouts completed this week")

    # Work pressure signals
    if any(s["type"] == "deadline_approaching" for s in signals):
        score += 1
        reasons.append("deadline pressure active")
    if wealth.get("financial_pressure_level") in ("medium", "high"):
        score += 1
        reasons.append("financial pressure elevated")

    # Deep work deficit
    dw_pct = _pct(work.get("deep_work_hours_this_week"), work.get("deep_work_target_hours"))
    if dw_pct is not None and dw_pct < 40:
        score += 1
        reasons.append(f"deep work at {dw_pct:.0f}% of target")

    # No travel recovery in a long time
    days_no_travel = _days_since(
        travel.get("last_trip_end") or travel.get("last_trip_date")
    )
    if days_no_travel is not None and days_no_travel > 60:
        score += 1
        reasons.append(f"no meaningful break in {days_no_travel} days")

    # Spirit practice lapsing
    review_streak = spirit.get("evening_review_streak", 0)
    morning_streak = spirit.get("morning_practice_streak", 0)
    if review_streak == 0 and morning_streak == 0:
        score += 1
        reasons.append("no Stoic/reflection practice active")

    if score >= 4:
        severity = "critical" if score >= 6 else "warning"
        reasons_str = "; ".join(reasons)
        return DetectedPattern(
            name="burnout_early_warning",
            severity=severity,
            domains=["body", "work", "spirit"],
            headline="Burnout Warning",
            message=(
                f"The data is telling a story that deserves your attention: {reasons_str}. "
                "This is not a motivation problem. It is a systems problem — the inputs that "
                "sustain performance are being depleted faster than they're being restored. "
                "Einstein would ask: what is the actual constraint? Musk would say you're "
                "optimizing the wrong variable. Franklin would look at your evenings. "
                "What has to change this week — not someday — to reverse this trajectory?"
            ),
            signal_to_publish=("orchestrator", "burnout_risk", {"score": score}),
        )
    return None


def _detect_peak_performance_window(ctx: dict, signals: list[dict]) -> Optional[DetectedPattern]:
    body = ctx.get("body", {})
    work = ctx.get("work", {})

    readiness = body.get("current_readiness")
    if readiness is None or readiness < 80:
        return None

    dw_pct = _pct(work.get("deep_work_hours_this_week"), work.get("deep_work_target_hours"))
    has_deadline = any(s["type"] == "deadline_approaching" for s in signals)
    nutrition_ok = body.get("nutrition_on_track") is True

    if readiness >= 80 and not has_deadline and (dw_pct is None or dw_pct >= 70):
        return DetectedPattern(
            name="peak_performance_window",
            severity="insight",
            domains=["body", "work"],
            headline="Peak Window",
            message=(
                f"Your readiness is at {readiness} — that puts you in the top tier of "
                "performance availability. There's no major deadline bearing down and "
                "your deep work target is being met. "
                "This is a rare window. What is the hardest, highest-leverage thing you "
                "have been avoiding because it requires your full cognitive presence? "
                "Schedule it for tomorrow's first 90 minutes."
            ),
        )
    return None


def _detect_physical_neglect(ctx: dict, signals: list[dict]) -> Optional[DetectedPattern]:
    body = ctx.get("body", {})

    workout_pct = _pct(body.get("weekly_workouts_completed"), body.get("weekly_workouts_target"))
    readiness = body.get("current_readiness")
    nutrition_ok = body.get("nutrition_on_track")

    neglect_signals = sum([
        1 if workout_pct is not None and workout_pct < 40 else 0,
        1 if readiness is not None and readiness < 55 else 0,
        1 if nutrition_ok is False else 0,
        1 if any(s["type"] == "low_readiness" for s in signals) else 0,
    ])

    if neglect_signals >= 2:
        return DetectedPattern(
            name="physical_neglect",
            severity="warning",
            domains=["body"],
            headline="Physical Reset Needed",
            message=(
                "The body domain is showing multiple red flags simultaneously. "
                "The body is not a separate category from the work — it is the machine "
                "that runs all of it. When the machine is neglected, every other domain "
                "pays the tax. Not eventually. Now. "
                "One question: what is the single physical non-negotiable you will "
                "protect tomorrow regardless of what else is happening?"
            ),
            signal_to_publish=("orchestrator", "low_readiness", {"detected_by": "pattern"}),
        )
    return None


def _detect_learning_application_lag(ctx: dict, signals: list[dict]) -> Optional[DetectedPattern]:
    mind = ctx.get("mind", {})
    work = ctx.get("work", {})

    queue_depth = mind.get("content_queue_depth", 0)
    has_overload = any(s["type"] == "learning_overload" for s in signals)
    goal_completion = work.get("goal_completion_this_week", 0)

    # Queue bloated AND work goals not moving
    if (queue_depth > 12 or has_overload) and goal_completion < 2:
        return DetectedPattern(
            name="learning_application_lag",
            severity="warning",
            domains=["mind", "work"],
            headline="Learning-Action Gap",
            message=(
                f"Your content queue is at {queue_depth} items and work goal completion "
                "is lagging. This is a pattern worth naming: you are accumulating knowledge "
                "faster than you are deploying it. "
                "da Vinci filled notebooks — but he also built things. "
                "Information without application is entertainment. "
                "This week: what is one thing you've learned in the last 30 days that "
                "you haven't yet applied to your actual work?"
            ),
        )
    return None


def _detect_drift_from_values(ctx: dict, signals: list[dict]) -> Optional[DetectedPattern]:
    spirit = ctx.get("spirit", {})
    work = ctx.get("work", {})

    morning_streak = spirit.get("morning_practice_streak", 0)
    review_streak = spirit.get("evening_review_streak", 0)
    last_review = _days_since(spirit.get("last_evening_review"))
    sabbath = spirit.get("sabbath_observed_last_week")
    goal_completion = work.get("goal_completion_this_week", 0)

    drift_signals = sum([
        1 if morning_streak == 0 else 0,
        1 if review_streak == 0 else 0,
        1 if last_review is not None and last_review > 5 else 0,
        1 if sabbath is False else 0,
        1 if goal_completion == 0 else 0,
    ])

    if drift_signals >= 3:
        return DetectedPattern(
            name="drift_from_values",
            severity="warning",
            domains=["spirit", "work"],
            headline="Values Drift",
            message=(
                "There's a growing gap between your stated values and your daily actions. "
                "The Stoic and Christian practices you committed to have lapsed. "
                "Work goals have not moved. This is drift — it happens gradually, "
                "then all at once. "
                "The question is not why it happened. The question is: what is the "
                "one practice you reinstall tomorrow morning, before anything else, "
                "that begins to close this gap?"
            ),
        )
    return None


def _detect_financial_anxiety_spiral(ctx: dict, signals: list[dict]) -> Optional[DetectedPattern]:
    wealth = ctx.get("wealth", {})
    mind = ctx.get("mind", {})

    pressure = wealth.get("financial_pressure_level", "low")
    revenue = wealth.get("monthly_recurring_revenue", 0)
    has_financial_signal = any(s["type"] == "financial_pressure" for s in signals)

    if pressure in ("medium", "high") or (has_financial_signal and revenue == 0):
        return DetectedPattern(
            name="financial_anxiety",
            severity="warning",
            domains=["wealth", "work"],
            headline="Financial Focus",
            message=(
                "Financial pressure is elevated. Before we solve strategy, let's "
                "separate two different things: the real situation and the narrative "
                "your mind is building around it. "
                "Real situation: what is the actual number, the actual timeline, "
                "the actual constraint? "
                "Narrative: what story are you telling yourself about what it means? "
                "One question: what is the single action this week that most directly "
                "moves the revenue needle — not the most comfortable action, the most "
                "direct one?"
            ),
        )
    return None


def _detect_open_loop_accumulation(ctx: dict, signals: list[dict]) -> Optional[DetectedPattern]:
    open_loops = ctx.get("open_loops", [])
    if len(open_loops) >= 7:
        return DetectedPattern(
            name="open_loop_accumulation",
            severity="warning",
            domains=["work"],
            headline="Open Loop Overload",
            message=(
                f"You have {len(open_loops)} open loops tracked. "
                "An open loop is a tax — it consumes background attention even when "
                "you're not consciously thinking about it. "
                "GTD principle: every open loop either needs a next action, "
                "a calendar date, or a deletion. Nothing else is honest. "
                "Let's close or delete half of these in the next 10 minutes."
            ),
        )
    return None


# ---------------------------------------------------------------------------
# Main detector
# ---------------------------------------------------------------------------

# All detectors in priority order. Earlier entries take precedence.
_DETECTORS = [
    _detect_burnout_early_warning,
    _detect_physical_neglect,
    _detect_peak_performance_window,
    _detect_learning_application_lag,
    _detect_drift_from_values,
    _detect_financial_anxiety_spiral,
    _detect_open_loop_accumulation,
]


def detect_patterns(
    context: Optional[dict] = None,
    signals: Optional[list] = None,
) -> list[DetectedPattern]:
    """Run all pattern detectors and return active patterns, highest severity first."""
    from artemis.core.memory import load_running_context

    ctx = context if context is not None else load_running_context()
    sigs = signals if signals is not None else get_active_signals()

    detected: list[DetectedPattern] = []
    suppressed_domains: set[str] = set()

    for detector in _DETECTORS:
        pattern = detector(ctx, sigs)
        if pattern is None:
            continue

        # Suppress lower-priority patterns in domains already covered by critical
        if pattern.severity == "critical":
            for d in pattern.domains:
                suppressed_domains.add(d)
        elif any(d in suppressed_domains for d in pattern.domains):
            continue

        detected.append(pattern)

    # Sort: critical first, then warning, then insight
    order = {"critical": 0, "warning": 1, "insight": 2}
    detected.sort(key=lambda p: order[p.severity])
    return detected


def format_patterns_for_briefing(patterns: list[DetectedPattern]) -> str:
    """Format detected patterns as a concise briefing section."""
    if not patterns:
        return ""

    lines = ["**PATTERNS ARTEMIS IS TRACKING**"]
    severity_icons = {"critical": "🔴", "warning": "⚠️", "insight": "💡"}

    for p in patterns:
        icon = severity_icons.get(p.severity, "•")
        lines.append(f"\n{icon} **{p.headline}** [{'/'.join(p.domains)}]")
        lines.append(p.message)

    return "\n".join(lines)
