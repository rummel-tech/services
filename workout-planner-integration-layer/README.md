# Backend Integration Layer (Supabase → AI Engine)

This package implements the full backend automation pipeline:
- Supabase SQL triggers
- Edge Functions (event listeners)
- AI Orchestration Function (aggregates data + calls Python AI)
- Response writer to store readiness, daily plan, weekly plan, insights

This is the core backend automation system for the Rummel Fitness AI coach.
