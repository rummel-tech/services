from fastapi import FastAPI
from pydantic import BaseModel
from ai_engine import AIFitnessEngine

app = FastAPI()
engine = AIFitnessEngine()

class UserData(BaseModel):
    hrv: float | None = None
    sleep_hours: float | None = None
    resting_hr: float | None = None

class WorkoutData(BaseModel):
    distance_m: float | None = None
    time_s: float | None = None
    weight: float | None = None
    reps: int | None = None
    run1_s: float | None = None
    calis_s: float | None = None
    run2_s: float | None = None

@app.post("/daily")
def daily_plan(user: UserData):
    return engine.generate_daily_plan(user.dict())

@app.post("/weekly")
def weekly_plan(user: UserData):
    return engine.generate_weekly_plan(user.dict())

@app.post("/process/swim")
def swim_metrics(workout: WorkoutData):
    return engine.process_swim_metrics(workout.dict())

@app.post("/process/strength")
def strength_metrics(workout: WorkoutData):
    return engine.process_strength_metrics(workout.dict())

@app.post("/process/murph")
def murph_metrics(workout: WorkoutData):
    return engine.process_murph(workout.dict())
