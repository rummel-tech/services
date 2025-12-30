from logging_config import get_logger

log = get_logger("domain.plan.daily")


class DailyPlanGenerator:
    def generate(self, user_data, readiness):
        if readiness < 0.3:
            plan = {
                "warmup": ["10 minutes easy mobility"],
                "main": ["Light day: 20-minute zone 2 cardio"],
                "cooldown": ["Breathing exercises"],
                "intensity": "low"
            }
        else:
            plan = {
                "warmup": ["5 minutes dynamic warmup"],
                "main": ["Strength + endurance hybrid session"],
                "cooldown": ["Foam rolling & stretching"],
                "intensity": "moderate"
            }
        log.info("daily_plan_generated", extra={"readiness": readiness, "intensity": plan["intensity"], "warmup_count": len(plan["warmup"]), "main_count": len(plan["main"])})
        return plan
