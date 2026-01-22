# Kwami AI LiveKit

LiveKit token endpoint and cloud agent for Kwami AI.

## Quick Start

```bash
# Copy and configure environment
cp .env.sample .env
# Edit .env with your credentials

# Run API server (token endpoint)
make api-install
make api

# Run agent locally (in another terminal)
make agent-install
make agent
```

## Project Structure

```
kwami-ai-lk/
├── api/                  # Token endpoint API (deploy anywhere)
│   ├── main.py           # FastAPI entry point
│   ├── config.py         # Settings
│   ├── token_utils.py    # Token generation
│   ├── routes/           # API endpoints
│   ├── pyproject.toml
│   └── Dockerfile
├── agent/                # LiveKit Cloud agent
│   ├── agent.py          # Agent entry point
│   ├── config.py         # Kwami configuration
│   ├── plugins.py        # STT/LLM/TTS factories
│   ├── pyproject.toml
│   └── livekit.toml      # LiveKit Cloud config
├── .env                  # Shared credentials
├── Makefile
└── README.md
```

## Commands

| Command | Description |
|---------|-------------|
| `make api-install` | Install API dependencies |
| `make api` | Run token API locally (http://localhost:8080) |
| `make agent-install` | Install agent dependencies |
| `make agent` | Run agent locally for testing |
| `make agent-deploy` | Deploy agent to LiveKit Cloud |
| `make lint` | Run linter on both projects |
| `make format` | Format code in both projects |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /` | GET | API info |
| `GET /health` | GET | Health check |
| `POST /token` | POST | Generate LiveKit token |
| `GET /token` | GET | Generate token (simple) |
| `GET /docs` | GET | OpenAPI documentation |

### Token Request

```bash
curl -X POST http://localhost:8080/token \
  -H "Content-Type: application/json" \
  -d '{
    "room_name": "my-room",
    "participant_name": "user-123"
  }'
```

## Deployment

### API (Token Endpoint)

Deploy the `api/` folder to any hosting provider:

```bash
# Docker
make docker-build
make docker-up

# Or deploy to Railway, Fly.io, Render, etc.
```

### Agent (LiveKit Cloud)

Deploy the agent to LiveKit Cloud:

```bash
cd agent

# Configure your LiveKit Cloud project
lk agent config

# Deploy to LiveKit Cloud
lk agent deploy
```

LiveKit Cloud handles scaling, lifecycle, and hosting automatically.

## Environment Variables

Create a `.env` file in the project root:

```env
# LiveKit (required)
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# AI Providers (required for agent)
OPENAI_API_KEY=your-openai-key
DEEPGRAM_API_KEY=your-deepgram-key
CARTESIA_API_KEY=your-cartesia-key

# API Config (optional)
APP_ENV=development
DEBUG=true
API_PORT=8080
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

## License

Apache 2.0
