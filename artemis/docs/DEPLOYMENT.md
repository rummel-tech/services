# Artemis Deployment

## Overview

This guide covers deploying the Artemis Personal OS backend and frontend.

## Local Development

### Backend

```bash
cd artemis
pip install -r requirements.txt
python run_server.py
# API available at http://localhost:8000
```

### Frontend

```bash
cd artemis/artemis_app
flutter pub get
flutter run -d chrome
```

## Production Deployment

### Backend

The backend can be deployed to AWS ECS via the infrastructure workflows:

```bash
gh workflow run deploy-artemis-backend.yml \
  --repo rummel-tech/infrastructure
```

### Frontend

The frontend can be deployed to GitHub Pages:

```bash
gh workflow run deploy-artemis-frontend.yml \
  --repo rummel-tech/infrastructure
```

## Environment Configuration

### Backend

Create `.env` file:
```bash
DATABASE_URL=postgresql://user:pass@host:5432/artemis
SECRET_KEY=your-secret-key
```

### Frontend

Pass API URL at build time:
```bash
flutter build web --dart-define=PRODUCTION_API_URL=https://api.example.com
```

## Verification

1. Check backend: `curl http://localhost:8000/health`
2. View API docs: `http://localhost:8000/docs`
3. Open frontend in browser

---

[Back to Artemis](../) | [Platform Documentation](../../docs/)
