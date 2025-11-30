class WeeklyPlanGenerator:
    def generate(self, user_data):
        return {
            "focus": "hybrid",
            "days": [
                {"day": "Mon", "type": "strength"},
                {"day": "Tue", "type": "swim"},
                {"day": "Wed", "type": "mobility"},
                {"day": "Thu", "type": "run"},
                {"day": "Fri", "type": "strength"},
                {"day": "Sat", "type": "murph prep"},
                {"day": "Sun", "type": "rest"},
            ]
        }
