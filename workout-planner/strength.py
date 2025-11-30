from logging_config import get_logger

log = get_logger("domain.strength")


class StrengthModel:
    def process(self, workout):
        weight = workout.get("weight") or 200
        reps = workout.get("reps") or 5
        est_1rm = weight * reps / 0.0333
        result = {"weight": weight, "reps": reps, "estimated_1rm": round(est_1rm, 2)}
        log.info("strength_analytics_computed", extra=result)
        return result
