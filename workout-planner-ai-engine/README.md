# Workout Planner AI Engine

Core AI logic modules for the fitness coaching system.

## Overview

The AI Engine provides specialized algorithms for fitness planning, readiness scoring, and workout analytics. It serves as the computational core that powers the Workout Planner API's AI features.

## Architecture

```
workout-planner-ai-engine/
├── ai_engine.py      # Main orchestrator
├── daily_plan.py     # Daily workout generation
├── weekly_plan.py    # Weekly schedule generation
├── readiness.py      # Readiness score calculation
├── strength.py       # Strength training analytics
├── swim.py           # Swimming workout analytics
├── murph.py          # Murph workout processing
├── goals.py          # Goal evaluation and tracking
└── __init__.py       # Package exports
```

## Components

### AIFitnessEngine (`ai_engine.py`)

Main orchestrator that coordinates all AI modules.

```python
from ai_engine import AIFitnessEngine

engine = AIFitnessEngine()

# Generate daily plan with readiness
result = engine.generate_daily_plan(user_data)
# Returns: {"readiness": score, "plan": daily_plan}

# Generate weekly plan
weekly = engine.generate_weekly_plan(user_data)

# Process workout metrics
swim_metrics = engine.process_swim_metrics(workout)
strength_metrics = engine.process_strength_metrics(workout)
murph_result = engine.process_murph(workout)

# Evaluate goals
progress = engine.evaluate_goals(goals, metrics)
```

### Daily Plan Generator (`daily_plan.py`)

Generates personalized daily workout plans based on:
- User fitness profile
- Current readiness score
- Training history
- Goals and preferences

### Weekly Plan Generator (`weekly_plan.py`)

Creates balanced weekly training schedules considering:
- Workout frequency targets
- Recovery requirements
- Progressive overload principles
- Goal alignment

### Readiness Model (`readiness.py`)

Calculates user readiness scores using:
- Sleep quality and duration
- Previous workout intensity
- Recovery indicators
- Stress levels
- Health metrics (HRV, resting HR)

### Strength Model (`strength.py`)

Processes strength training data:
- Volume calculations
- Intensity tracking
- Progressive overload analysis
- Personal record tracking

### Swim Analytics (`swim.py`)

Analyzes swimming workouts:
- Pace calculations
- Distance tracking
- Stroke analysis
- Training zone distribution

### Murph Model (`murph.py`)

Specialized processing for Murph workouts:
- Time tracking
- Partition analysis
- Progress comparison
- Performance predictions

### Goal Manager (`goals.py`)

Evaluates progress toward fitness goals:
- Goal tracking
- Progress calculations
- Milestone detection
- Recommendations

## Integration

The AI Engine is used by the Workout Planner API backend:

```python
# In workout-planner/main.py
from workout_planner_ai_engine import AIFitnessEngine

engine = AIFitnessEngine()

@app.get("/readiness/{user_id}")
async def get_readiness(user_id: str):
    user_data = fetch_user_data(user_id)
    return engine.generate_daily_plan(user_data)
```

## Data Flow

```
User Request → API Router → AI Engine → Algorithm Module → Response
                                ↓
                         User Data +
                         Health Metrics +
                         Training History
```

## Related Components

- **Workout Planner API** - FastAPI backend that calls the engine
- **Integration Layer** - Supabase triggers that invoke AI processing
- **Flutter Frontend** - Displays AI-generated insights and plans
