# Workout Planner Integration Layer

Supabase-to-AI automation pipeline for the fitness coaching system.

## Overview

This package implements the backend automation that connects Supabase events to the Python AI engine. When users log workouts or morning routines, SQL triggers automatically invoke Edge Functions that orchestrate AI processing and store results.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Flutter App    │────▶│   Supabase   │────▶│  SQL Triggers   │
│  (User Input)   │     │   Database   │     │                 │
└─────────────────┘     └──────────────┘     └────────┬────────┘
                                                      │
                                                      ▼
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Supabase DB    │◀────│    Python    │◀────│ Edge Function   │
│  (Results)      │     │  AI Engine   │     │ ai-orchestrator │
└─────────────────┘     └──────────────┘     └─────────────────┘
```

## Directory Structure

```
workout-planner-integration-layer/
├── README.md
├── docs/
│   └── data_flow.yaml       # Event flow documentation
├── functions/
│   └── ai-orchestrator/
│       ├── index.ts         # Edge Function (Deno)
│       └── config.json      # Function configuration
└── sql/
    ├── morning_routine_trigger.sql  # Morning routine trigger
    └── workout_trigger.sql          # Workout ingest trigger
```

## Components

### SQL Triggers

Database triggers that fire on data insertion and call the Edge Function.

#### Morning Routine Trigger (`sql/morning_routine_trigger.sql`)

Fires when a user logs their morning routine (sleep, HRV, resting HR).

```sql
-- Triggers on: INSERT to morning_routine table
-- Calls: /ai-orchestrator Edge Function
-- Payload: { user_id, routine_id, source: 'morning_routine' }
```

#### Workout Trigger (`sql/workout_trigger.sql`)

Fires when a new workout is ingested from HealthKit/Google Fit.

```sql
-- Triggers on: INSERT to workouts table
-- Calls: /ai-orchestrator Edge Function
-- Payload: { user_id, workout_id, source: 'workout_ingest' }
```

### Edge Function: AI Orchestrator (`functions/ai-orchestrator/index.ts`)

Deno-based Supabase Edge Function that:

1. **Gathers Data** - Pulls latest user metrics from Supabase
   - Morning routine (HRV, sleep hours, resting HR)
   - Latest workout data

2. **Calls AI Engine** - Sends aggregated metrics to Python AI server
   - Endpoint: `$AI_SERVER_URL/daily`
   - Method: POST with JSON payload

3. **Writes Results** - Stores AI output back to Supabase
   - `readiness_scores` table
   - `daily_plans` table

```typescript
// Environment variables required:
// - SUPABASE_URL
// - SUPABASE_SERVICE_ROLE_KEY
// - AI_SERVER_URL
```

## Data Flow

```yaml
# Event: Workout Inserted
Workout Insert → workouts table → SQL Trigger → ai-orchestrator

# Event: Morning Routine Inserted
Morning Routine → morning_routine table → SQL Trigger → ai-orchestrator

# AI Orchestrator Process
ai-orchestrator:
  gathers:
    - morning_routine.latest
    - workouts.latest
  calls: Python AI Server /daily
  writes:
    - readiness_scores
    - daily_plans
    - ai_insights
```

## Deployment

### 1. Deploy SQL Triggers

```bash
# Apply to Supabase via SQL editor or CLI
supabase db push sql/morning_routine_trigger.sql
supabase db push sql/workout_trigger.sql
```

### 2. Deploy Edge Function

```bash
# Deploy to Supabase
supabase functions deploy ai-orchestrator
```

### 3. Configure Environment

Set required secrets in Supabase dashboard:
- `AI_SERVER_URL` - Python AI Engine endpoint

### 4. Configure App Settings

```sql
-- Set Edge Function URL in database settings
ALTER DATABASE postgres SET "app.settings.edge_url" = 'https://your-project.supabase.co/functions/v1';
```

## Tables Written To

| Table | Fields | Description |
|-------|--------|-------------|
| `readiness_scores` | user_id, readiness, details | Daily readiness score |
| `daily_plans` | user_id, plan | AI-generated workout plan |
| `ai_insights` | user_id, insights | Coaching recommendations |

## Related Components

- **AI Engine** (`workout-planner-ai-engine/`) - Python algorithms called by orchestrator
- **Workout Planner API** - FastAPI backend (alternative to Supabase flow)
- **Flutter Frontend** - Displays readiness scores and daily plans

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key for DB access |
| `AI_SERVER_URL` | Python AI Engine base URL |
