from logging_config import get_logger
import metrics  # assumes metrics.py placed alongside this module

log = get_logger("domain.swim")


class SwimAnalytics:
    def process(self, workout):
        dist = workout.get("distance_m")
        time_s = workout.get("time_s")
        strokes = workout.get("strokes")  # optional total stroke count
        if dist is None or time_s is None:
            log.warning(
                "missing_swim_fields",
                extra={"provided_keys": list(workout.keys())}
            )
            # Provide safe defaults (1km in 25 min) if absent
            dist = dist or 1000
            time_s = time_s or 1500

        valid = dist > 0 and time_s > 0
        pace_per_meter = (time_s / dist) if valid else None  # seconds per meter
        speed_m_per_s = (dist / time_s) if valid else None
        pace_per_100m = (pace_per_meter * 100) if pace_per_meter else None
        stroke_rate_spm = None
        stroke_efficiency = None
        if strokes and strokes > 0 and valid:
            stroke_rate_spm = (strokes / (time_s / 60))  # strokes per minute
            stroke_efficiency = dist / strokes  # meters per stroke

        result = {
            "distance_m": dist,
            "time_s": time_s,
            "pace_per_meter_s": pace_per_meter,
            "pace_per_100m_s": pace_per_100m,
            "speed_m_per_s": speed_m_per_s,
            "stroke_rate_spm": stroke_rate_spm,
            "stroke_efficiency_m_per_stroke": stroke_efficiency,
        }
        log.info("swim_analytics_computed", extra=result)
        metrics.record_domain_event("swim_analytics_computed")
        return result
