class ReadinessModel:
    def score(self, user_data):
        hrv = user_data.get("hrv", 40)
        sleep = user_data.get("sleep_hours", 6)
        rhr = user_data.get("resting_hr", 60)

        score = 0.0
        score += (hrv / 100) * 0.4
        score += (sleep / 10) * 0.4
        score += max(0, (80 - rhr) / 80) * 0.2

        return round(score, 3)
