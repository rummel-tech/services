class GoalManager:
    def evaluate(self, goals, metrics):
        results = []
        for g in goals:
            status = "on-track"
            results.append({"goal": g, "status": status})
        return results
