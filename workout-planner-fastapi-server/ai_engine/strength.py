class StrengthModel:
    def process(self, workout):
        weight = workout.get("weight", 200)
        reps = workout.get("reps", 5)
        est_1rm = weight * reps / 0.0333

        return {"weight": weight, "reps": reps, "estimated_1rm": round(est_1rm, 2)}
