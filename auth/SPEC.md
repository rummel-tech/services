# Auth Service — Specification

> **Scope:** This document covers the `services/auth` FastAPI backend.
> This is a shared service — not a standalone module or Artemis module. It provides
> centralized identity for the entire Artemis platform.

---

## 1. Purpose & Domain

The Artemis Auth Service is the centralized identity provider for the entire platform.
It issues RS256 JWTs that all other services verify against a distributed public key.
It is the only service that issues `iss: "artemis-auth"` tokens.

**Core responsibilities:**
- User registration and login (email/password)
- Google OAuth login
- RS256 JWT issuance with full Artemis payload
- Token refresh and revocation (blacklisting via Redis)
- Public key distribution for module token verification

**Not a module — no Artemis contract endpoints.** Other services call this service
to verify tokens; this service does not call other modules.

---

## 2. Technology Stack

| Layer | Technology |
|-------|-----------|
| Framework | Python 3.11+, FastAPI |
| Server | Uvicorn |
| Database (prod) | PostgreSQL 15 |
| Database (dev) | SQLite (`auth_dev.db`) |
| JWT algorithm | RS256 (asymmetric) |
| Password hashing | bcrypt |
| Token blacklisting | Redis (`redis://localhost:6379/1`) |
| Rate limiting | slowapi |
| Port | **8090** |

---

## 3. Database Schema

### `users` Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT / UUID | Primary key |
| `email` | TEXT | Unique, not null |
| `hashed_password` | TEXT | bcrypt; null for OAuth-only users |
| `full_name` | TEXT | Display name |
| `google_id` | TEXT | Unique; null for email/password users |
| `is_active` | INTEGER / BOOLEAN | Default 1 (active) |
| `is_admin` | INTEGER / BOOLEAN | Default 0 |
| `enabled_modules` | TEXT | JSON array of module IDs, e.g. `["workout-planner","meal-planner"]` |
| `permissions` | TEXT | JSON array, e.g. `["fitness.calories.read","nutrition.calories.read"]` |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**Indexes:** `email`, `google_id`

### Running Migrations

```bash
cd services/auth
DATABASE_URL=sqlite:///auth_dev.db python -c "from auth.core.database import init_db; import asyncio; asyncio.run(init_db())"
# Or simply start the service — it auto-creates schema on startup
```

---

## 4. API Endpoints

### Auth Endpoints (`/auth/*`)

| Method | Path | Rate Limit (prod) | Description |
|--------|------|-------------------|-------------|
| `POST` | `/auth/register` | 5/min | Register new user |
| `POST` | `/auth/login` | 10/min | Login with email/password |
| `POST` | `/auth/refresh` | 10/min | Refresh access token |
| `POST` | `/auth/logout` | 20/min | Revoke tokens (Redis blacklist) |
| `GET` | `/auth/me` | 20/min | Current user profile |

### Google OAuth

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/google` | Exchange Google ID token for Artemis JWT |

### Public Key Distribution

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| `GET` | `/auth/public-key` | None | Returns the RSA public key for module token verification |

Response:
```json
{
  "public_key": "-----BEGIN PUBLIC KEY-----\n...",
  "algorithm": "RS256"
}
```

### Utility Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | `{"status": "healthy", "service": "artemis-auth"}` |
| `GET /ready` | Readiness probe with db status |

---

## 5. JWT Token Structure

### Access Token Payload

```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "name": "Full Name",
  "iss": "artemis-auth",
  "iat": 1711360800,
  "exp": 1711447200,
  "jti": "unique-token-id",
  "type": "access",
  "modules": ["workout-planner", "meal-planner"],
  "permissions": ["fitness.calories.read", "nutrition.calories.read"]
}
```

### Refresh Token Payload

Same structure but `type: "refresh"` and longer expiry (30 days).

### Token Verification (by modules)

Each module's `require_token` function:
1. Calls `GET /auth/public-key` on first use, caches for 24 hours
2. Verifies the token signature with RS256
3. Checks `iss == "artemis-auth"`
4. Extracts `sub` as `user_id`

---

## 6. RSA Key Management

Keys are generated automatically on first startup if not present.

| Setting | Default | Production Override |
|---------|---------|---------------------|
| Private key path | `keys/private.pem` | `PRIVATE_KEY_PEM` env var (PEM string) |
| Public key path | `keys/public.pem` | `PUBLIC_KEY_PEM` env var (PEM string) |

**Key rotation:** Update the key env vars and restart. All modules will re-fetch the public
key within 24 hours (their cache TTL). For immediate rotation, restart all modules.

---

## 7. Local Development

### Setup

```bash
cd services/auth
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the server
DATABASE_URL=sqlite:///auth_dev.db uvicorn main:app --reload --port 8090
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///auth_dev.db` | Database connection string |
| `REDIS_URL` | `redis://localhost:6379/1` | Redis for token blacklisting |
| `REDIS_ENABLED` | `true` | Set to `false` to skip Redis (dev) |
| `ENVIRONMENT` | `development` | Rate limits are relaxed in dev (10000/min) |
| `PRIVATE_KEY_PEM` | — | RSA private key as PEM string (production) |
| `PUBLIC_KEY_PEM` | — | RSA public key as PEM string (production) |
| `GOOGLE_CLIENT_ID` | — | Required for Google OAuth |

---

## 8. Testing

```bash
source .venv/bin/activate
pytest tests/ -v
```

Tests use a temp SQLite database. Redis is mocked or bypassed in dev mode.

---

## 9. Deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
```

**Production:**
- AWS ECS Fargate via `rummel-tech/infrastructure`
- **Needs its own RDS instance** — auth DB must not be shared with module DBs
  (see infrastructure gap in `ARCHITECTURE_REVIEW.md`)
- Production URL: `https://api.rummeltech.com/auth`
- RSA keys via AWS Secrets Manager (`PRIVATE_KEY_PEM`, `PUBLIC_KEY_PEM`)
- Redis via AWS ElastiCache

---

## 10. Known Issues & Tech Debt

| Issue | Severity | Notes |
|-------|----------|-------|
| No RDS instance in Terraform | High | Auth DB needs separate provisioning before prod deploy |
| `enabled_modules` and `permissions` stored as JSON strings in SQLite | Low | Parsed on read; in PostgreSQL these could be arrays |
| Google OAuth not fully tested end-to-end | Medium | Happy path implemented; edge cases (revoked tokens, account linking) untested |
| No email verification flow | Medium | Users can register with any email; add confirmation email before public launch |
| No password reset flow | Medium | Users cannot recover lost passwords |

---

*Specification last updated: March 2026*
