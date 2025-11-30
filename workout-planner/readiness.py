from logging_config import get_logger

log = get_logger("domain.readiness")


class ReadinessModel:
    def score(self, user_data):
        hrv = user_data.get("hrv") or 40
        sleep = user_data.get("sleep_hours") or 6
        rhr = user_data.get("resting_hr") or 60
        score = 0.0
        score += (hrv / 100) * 0.4
        score += (sleep / 10) * 0.4
        score += max(0, (80 - rhr) / 80) * 0.2
        final = round(score, 3)
        log.info("readiness_score_computed", extra={"hrv": hrv, "sleep_hours": sleep, "resting_hr": rhr, "score": final})
        return final
