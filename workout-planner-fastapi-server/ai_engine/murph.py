class MurphModel:
    def process(self, workout):
        run1 = workout.get("run1_s", 600)
        calis = workout.get("calis_s", 1800)
        run2 = workout.get("run2_s", 650)

        total = run1 + calis + run2

        return {"run1": run1, "calis": calis, "run2": run2, "total": total}
