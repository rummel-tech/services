from logging_config import get_logger

log = get_logger("domain.plan.weekly")


class WeeklyPlanGenerator:
    def generate(self, user_data):
        plan = {
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
        log.info("weekly_plan_generated", extra={"focus": plan["focus"], "days_count": len(plan["days"])})
        return plan
