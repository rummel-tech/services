from logging_config import get_logger

log = get_logger("domain.murph")


class MurphModel:
    def process(self, workout):
        run1 = workout.get("run1_s") or 600
        calis = workout.get("calis_s") or 1800
        run2 = workout.get("run2_s") or 650
        total = run1 + calis + run2
        result = {"run1_s": run1, "calis_s": calis, "run2_s": run2, "total_s": total}
        log.info("murph_analytics_computed", extra=result)
        return result
