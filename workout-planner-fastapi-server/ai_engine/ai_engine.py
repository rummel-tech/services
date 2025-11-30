from .daily_plan import DailyPlanGenerator
from .weekly_plan import WeeklyPlanGenerator
from .readiness import ReadinessModel
from .swim import SwimAnalytics
from .strength import StrengthModel
from .murph import MurphModel
from .goals import GoalManager

class AIFitnessEngine:
    def __init__(self):
        self.daily = DailyPlanGenerator()
        self.weekly = WeeklyPlanGenerator()
        self.readiness = ReadinessModel()
        self.swim = SwimAnalytics()
        self.strength = StrengthModel()
        self.murph = MurphModel()
        self.goals = GoalManager()

    def generate_daily_plan(self, user_data):
        readiness = self.readiness.score(user_data)
        plan = self.daily.generate(user_data, readiness)
        return {"readiness": readiness, "plan": plan}

    def generate_weekly_plan(self, user_data):
        return self.weekly.generate(user_data)

    def process_swim_metrics(self, workout):
        return self.swim.process(workout)

    def process_strength_metrics(self, workout):
        return self.strength.process(workout)

    def process_murph(self, workout):
        return self.murph.process(workout)

    def evaluate_goals(self, goals, metrics):
        return self.goals.evaluate(goals, metrics)
