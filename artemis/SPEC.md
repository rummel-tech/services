# Artemis Platform — Service Specification

> **Scope:** This document covers `services/artemis` — the central platform backend.
> For the module integration contract, see `rummel-tech/resources/ARTEMIS_MODULE_CONTRACT.md`.
> For individual module specs, see `SPEC.md` in each `services/<module>` directory.

---

## 1. Purpose

The Artemis platform service is the central hub that orchestrates all Artemis-compatible
modules. It does not own any user data — it aggregates from modules using their APIs.

**Core responsibilities:**
- Module registry: discover and health-check all registered modules on startup
- Dashboard aggregation: fan out to all module widget endpoints and merge results
- AI agent: Claude-powered assistant with auto-generated tools from module manifests
- Token relay: forward the user's Artemis JWT to every module call

---

## 2. Technology Stack

| Layer | Technology |
|-------|-----------|
| Framework | Python 3.11+, FastAPI |
| Server | Uvicorn |
| AI agent | Claude (`claude-sonnet-4-6`) via Anthropic SDK |
| HTTP client | httpx (async) |
| Module config | YAML (`config/modules.yaml`) |
| Auth | RS256 JWT via `artemis-auth` public key |
| Port | **8080** |

No database — this service is stateless. Module registry is in-memory, rebuilt on startup.

---

## 3. Configuration

### `config/modules.yaml`

Defines all registered modules. Edit this file to add, remove, or disable modules.

```yaml
modules:
  - id: workout-planner
    manifest_url: http://localhost:8000/artemis/manifest
    prod_manifest_url: https://api.rummeltech.com/workout-planner/artemis/manifest
    enabled: true

  - id: meal-planner
    manifest_url: http://localhost:8010/artemis/manifest
    prod_manifest_url: https://api.rummeltech.com/meal-planner/artemis/manifest
    enabled: true

  - id: home-manager
    manifest_url: http://localhost:8020/artemis/manifest
    prod_manifest_url: https://api.rummeltech.com/home-manager/artemis/manifest
    enabled: true

  - id: vehicle-manager
    manifest_url: http://localhost:8030/artemis/manifest
    prod_manifest_url: https://api.rummeltech.com/vehicle-manager/artemis/manifest
    enabled: true
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ARTEMIS_AUTH_URL` | `http://localhost:8090` | Auth service URL for public key |
| `MODULES_CONFIG` | `config/modules.yaml` | Path to module registry config |
| `REGISTRY_REFRESH_SECONDS` | `300` | Background manifest re-poll interval (0 = disabled) |
| `ANTHROPIC_API_KEY` | — | Required for the AI agent |
| `AGENT_MODEL` | `claude-sonnet-4-6` | Claude model for the agent |
| `ENVIRONMENT` | `development` | Set to `production` for strict auth |

---

## 4. API Endpoints

All endpoints except `/health` and `/ready` require `Authorization: Bearer <artemis_token>`.

### Utility

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /health` | None | Health with module count |
| `GET /ready` | None | Readiness probe |

### Module Registry (`/modules`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/modules` | List all registered modules with health status |
| `GET` | `/modules/{id}` | Full details for a specific module |
| `GET` | `/modules/{id}/manifest` | Cached manifest for a module |

### Dashboard (`/dashboard`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/dashboard` | Aggregate widget data from all healthy modules |
| `GET` | `/dashboard/widgets` | List available widgets without fetching data |
| `GET` | `/dashboard/quick-actions` | Aggregate quick actions from all modules |

### Agent (`/agent`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/agent/chat` | HTTP chat — send a message, get a response |
| `GET` | `/agent/tools` | List all available Claude tool definitions |
| `WS` | `/agent/ws` | WebSocket — streaming agent interactions |

---

## 5. Module Registry

On startup (`lifespan`), the registry:
1. Reads `config/modules.yaml`
2. Concurrently fetches `{module.manifest_url}` for each enabled module
3. Caches the manifest JSON and marks the module healthy/unhealthy
4. Optionally starts a background refresh loop every `REGISTRY_REFRESH_SECONDS`

A module is considered healthy only if its manifest endpoint returns HTTP 200.
Unhealthy modules are excluded from dashboard aggregation and agent tools.

The registry builds Claude tool definitions from cached manifests:

```
tool name format: {module_id_with_underscores}__{tool_id}
e.g.: workout_planner__get_todays_workout
```

---

## 6. Dashboard Aggregation

`GET /dashboard` fans out concurrently to all healthy modules:

```
For each healthy module:
  For each widget in module.manifest.capabilities.dashboard_widgets:
    GET {module.api_base}{widget.data_endpoint}
    Headers: Authorization: Bearer {user_token}
```

Results are merged and returned with module metadata. Widget failures are included
as `{data: null, error: "..."}` — individual failures don't break the dashboard.

---

## 7. AI Agent

The agent uses a full agentic loop (up to 8 turns):

1. Build system prompt from user's token payload (name, modules, today's date)
2. Auto-generate Claude tool definitions from the module registry
3. Call `claude-sonnet-4-6` with the user's message and tools
4. If `stop_reason == "tool_use"`: proxy each tool call to the correct module's
   `POST /artemis/agent/{tool_id}` endpoint, forwarding the user's token
5. Feed tool results back to Claude as `tool_result` blocks
6. Repeat until `end_turn` or max turns reached

### WebSocket Protocol

```
Client → Server: {"message": "...", "token": "Bearer <token>"}
Server → Client: {"type": "connected", "user": "Name"}
Server → Client: {"type": "tool_call", "tool": "...", "result": {...}}
Server → Client: {"type": "text", "content": "..."}  (chunked)
Server → Client: {"type": "done"}
Server → Client: {"type": "error", "detail": "..."}
```

---

## 8. Authentication

All platform endpoints validate the Artemis JWT:

1. Fetch public key from `ARTEMIS_AUTH_URL/auth/public-key` (cached; re-fetched on TTL)
2. Verify RS256 signature
3. Check `iss == "artemis-auth"`

**Dev fallback:** When `ENVIRONMENT != "production"` and the auth service is unreachable,
unverified claims are accepted (for local development without the auth service running).
In production, unreachable auth service → HTTP 503.

---

## 9. Local Development

### Setup

```bash
cd services/artemis
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start with modules also running (or with only some running — unhealthy ones are skipped)
ANTHROPIC_API_KEY=sk-ant-... uvicorn main:app --reload --port 8080
```

The service starts cleanly even if no modules are running. The registry will mark all
modules unhealthy and the dashboard/agent will return empty results.

---

## 10. Testing

```bash
source .venv/bin/activate
pytest tests/test_platform.py -v
```

Tests run without any real module services. The registry starts empty (modules.yaml
points to unreachable localhost ports). Tests cover: startup, auth enforcement,
health endpoints, empty registry responses, agent with no API key configured.

---

## 11. Deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Production:**
- AWS ECS Fargate via `rummel-tech/infrastructure`
- ECS task definition, target group, and ALB listener rule defined in `infrastructure/terraform/` (port 8080, `artemis` entry in `applications` map)
- Production URL: `https://api.rummeltech.com`
- `ANTHROPIC_API_KEY` via AWS Secrets Manager
- `MODULES_CONFIG` should point to a production `modules.yaml` using prod manifest URLs

---

## 12. Adding a New Module

1. Implement the Artemis Module Contract in the new service (see `ARTEMIS_MODULE_CONTRACT.md`)
2. Add an entry to `config/modules.yaml`:
   ```yaml
   - id: finance-tracker
     manifest_url: http://localhost:8040/artemis/manifest
     prod_manifest_url: https://api.rummeltech.com/finance-tracker/artemis/manifest
     enabled: true
   ```
3. Restart the Artemis platform service (or wait for the background refresh)
4. The new module's widgets and agent tools are automatically available

No code changes required in the platform service itself.

---

## 13. Known Issues & Tech Debt

| Issue | Severity | Notes |
|-------|----------|-------|
| No ECS task definition in Terraform | High | Must be added to `rummel-tech/infrastructure` before production deploy |
| Agent WebSocket doesn't stream natively | Low | Currently buffers full response then chunks text. Use streaming SDK for true streaming |

---

*Specification last updated: March 2026*
