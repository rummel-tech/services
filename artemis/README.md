# Artemis Personal OS

Artemis is a personal operating system for efficiently achieving goals across multiple life domains. It provides a single pane of glass solution with integrated modules for:

- **Work Management**: Task tracking, project management, and productivity
- **Fitness**: Workout logging and fitness goal tracking
- **Nutrition**: Meal planning, nutrition tracking, and recipe management
- **Entrepreneurship**: Business ventures, ideas, and milestone tracking
- **Finance**: Budget management, transaction tracking, and financial goals
- **Assets**: Management of physical assets (home, car, motorcycle, etc.)

## Architecture

Artemis uses a multi-layered architecture:

### Backend (Python)
- **Core Module System**: Plugin-based architecture with base module interface
- **Module Registry**: Central registry for module management and integration
- **REST API**: FastAPI-based API for module interaction
- **Modules**: Six domain-specific modules (work, fitness, nutrition, entrepreneurship, finance, assets)

### Frontend (Flutter/Dart)
- **Cross-platform UI**: Single codebase for web and mobile (iOS/Android)
- **Single Pane of Glass**: Unified interface across all modules
- **Responsive Design**: Adapts to different screen sizes
- **API Integration**: Communicates with backend via REST API

## Quick Start

### Backend Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Run the API server:
```bash
python run_server.py
```

The API will be available at `http://localhost:8000`

### Flutter App Setup

1. Navigate to the Flutter app directory:
```bash
cd artemis_app
```

2. Install dependencies:
```bash
flutter pub get
```

3. Run the app:
```bash
# For web
flutter run -d chrome

# For mobile (with device/emulator connected)
flutter run
```

## API Documentation

Once the backend is running, visit:
- API Documentation: `http://localhost:8000/docs`
- Alternative Documentation: `http://localhost:8000/redoc`

## Project Structure

```
artemis/
├── src/artemis/          # Python backend
│   ├── core/             # Core module system
│   ├── modules/          # Domain modules
│   └── api/              # FastAPI application
├── artemis_app/          # Flutter application
│   ├── lib/
│   │   ├── models/       # Data models
│   │   ├── services/     # API services
│   │   ├── screens/      # UI screens
│   │   └── widgets/      # Reusable widgets
│   └── test/             # Flutter tests
├── tests/                # Python tests
├── requirements.txt      # Python dependencies
└── pyproject.toml        # Project configuration
```

## Module Actions

Each module supports specific actions. Examples:

### Work Module
- `create_task`: Create a new task
- `create_project`: Create a new project
- `list_tasks`: List all tasks
- `list_projects`: List all projects

### Fitness Module
- `log_workout`: Log a workout
- `set_goal`: Set a fitness goal
- `list_workouts`: List all workouts
- `list_goals`: List all fitness goals

### Nutrition Module
- `log_meal`: Log a meal
- `add_recipe`: Add a recipe
- `set_goal`: Set a nutrition goal
- `list_meals`: List all meals

### Entrepreneurship Module
- `create_venture`: Create a business venture
- `add_idea`: Add a business idea
- `set_milestone`: Set a milestone
- `list_ventures`: List all ventures

### Finance Module
- `add_transaction`: Add a transaction
- `create_budget`: Create a budget
- `set_goal`: Set a financial goal
- `list_transactions`: List all transactions

### Assets Module
- `add_asset`: Add an asset
- `log_maintenance`: Log maintenance
- `add_document`: Add a document
- `list_assets`: List all assets

## Development

### Running Tests

Python tests:
```bash
pytest
```

Flutter tests:
```bash
cd artemis_app
flutter test
```

### Code Quality

Python linting:
```bash
black src/
ruff check src/
mypy src/
```

## Documentation

- [Objectives](./OBJECTIVES.md) - Goals, requirements, and success criteria
- [Architecture](docs/ARCHITECTURE.md) - System design
- [Implementation](docs/IMPLEMENTATION.md) - Implementation details
- [Deployment](docs/DEPLOYMENT.md) - Deployment guide
- [Changelog](./CHANGELOG.md) - Version history

## License

MIT License - see LICENSE file for details

---

[Platform Documentation](../docs/) | [Product Overview](../docs/products/artemis.md)
