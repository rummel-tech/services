class DailyPlanGenerator:
    def generate(self, user_data, readiness):
        # Placeholder logic
        if readiness < 0.3:
            return {
                "warmup": ["10 minutes easy mobility"],
                "main": ["Light day: 20-minute zone 2 cardio"],
                "cooldown": ["Breathing exercises"]
            }
        else:
            return {
                "warmup": ["5 minutes dynamic warmup"],
                "main": ["Strength + endurance hybrid session"],
                "cooldown": ["Foam rolling & stretching"]
            }
