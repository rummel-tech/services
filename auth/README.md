# Auth Service

Central authentication service for the Artemis platform. Issues RS256 JWTs consumed by all other modules.

## Overview

- Issues RS256 signed access and refresh token pairs
- Email/password registration and login
- Google OAuth sign-in (optional)
- Token blacklisting via Redis (optional)
- Public key endpoint so modules can verify tokens without a shared secret

**Port:** 8090

## Quick Start (SQLite dev mode)

```bash
cd auth

# Generate RSA keys
mkdir -p keys
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem

# Install dependencies
pip install -r requirements.txt

# Run
uvicorn main:app --port 8090 --reload
```

No `ARTEMIS_AUTH_URL` or Redis needed for local development. The service uses SQLite by default.

## Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/register` | No | Register new user, returns token pair |
| POST | `/auth/login` | No | Email/password login, returns token pair |
| POST | `/auth/refresh` | Bearer (refresh token) | Exchange refresh token for new token pair |
| POST | `/auth/logout` | Bearer | Blacklist current token |
| GET | `/auth/me` | Bearer | Get current user profile |
| POST | `/auth/google` | No | Google ID token exchange, returns token pair |
| GET | `/auth/public-key` | No | RSA public key (PEM) for token verification |
| GET | `/health` | No | Health check |
| GET | `/ready` | No | Readiness check |

### Token response shape

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./auth.db` | SQLite or PostgreSQL connection string |
| `PRIVATE_KEY_PATH` | `keys/private.pem` | Path to RSA private key file |
| `PUBLIC_KEY_PATH` | `keys/public.pem` | Path to RSA public key file |
| `PRIVATE_KEY_PEM` | — | Private key as PEM string (overrides path, use in prod) |
| `PUBLIC_KEY_PEM` | — | Public key as PEM string (overrides path, use in prod) |
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID (required for `/auth/google`) |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `REDIS_ENABLED` | `false` | Enable Redis token blacklisting |
| `ENVIRONMENT` | `development` | Set to `production` to enable rate limiting |

## RSA Key Generation

```bash
openssl genrsa -out keys/private.pem 2048
openssl rsa -in keys/private.pem -pubout -out keys/public.pem
```

Keys are gitignored. Never commit private keys.

## Docker

Build context must be the `services/` root (the Dockerfile uses the `auth/` subdirectory as the package):

```bash
# From services/ root
docker build -f auth/Dockerfile -t auth .
docker run -p 8090:8090 \
  -e DATABASE_URL=sqlite:///./auth.db \
  -v $(pwd)/keys:/app/keys \
  auth
```

## Docker Compose

```bash
# From services/ root
docker compose up auth
```

## Integration with Other Services

Other modules set `ARTEMIS_AUTH_URL=http://localhost:8090` to enable JWT verification. On startup they fetch the public key from `GET /auth/public-key` and cache it for 24 hours.

Without `ARTEMIS_AUTH_URL` set, modules run in dev fallback mode and accept any token (development only — rejected in production).
