class SwimAnalytics:
    def process(self, workout):
        dist = workout.get("distance_m", 1000)
        time = workout.get("time_s", 1500)
        pace = time / dist if dist > 0 else None

        return {"distance": dist, "time": time, "pace_per_meter": pace}
