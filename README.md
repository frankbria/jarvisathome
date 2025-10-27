# Jarvis at Home - Alexa LLM Bridge

An async middleware API that bridges Alexa Skills with AI models (Anthropic Claude & OpenAI GPT), solving the 8-second Lambda timeout constraint through intelligent job queuing and polling.

## Architecture Overview

```
┌─────────┐         ┌────────────┐         ┌─────────────┐         ┌──────────┐
│  Alexa  │────────>│   Lambda   │────────>│  Queue API  │────────>│ LLM API  │
│         │<────────│            │<────────│             │<────────│          │
└─────────┘         └────────────┘         └─────────────┘         └──────────┘
    │                                             │
    │ "Thinking..."                               │ (async job running)
    │ stays in session                            │
    │                                             │
    │ (auto-re-pings after 5s silence)            │
    │                                             │
    └────────> Lambda ──────> Check status ───> Still running?
              "..." (SSML pause)                  └─> Return partial/wait
              stays in session
```

## How It Works

The system solves Alexa's timeout problem by converting synchronous requests into an async polling pattern:

1. **User asks Alexa a question** → Alexa invokes Lambda
2. **Lambda creates a job** via `POST /ask` → Returns immediately with `job_id`
3. **Lambda responds** with "Let me think about that..." and keeps session open
4. **API processes in background** → Calls Claude/GPT APIs (can take 10-30s)
5. **Alexa auto-reprompts** after silence → Lambda polls `GET /status/{job_id}`
6. **Repeat until complete** → Lambda returns final answer when ready

Each round-trip takes <2 seconds, but the total processing time can be 30+ seconds.

## Project Structure

```
jarvisathome/
├── api/                    # FastAPI middleware
│   ├── __init__.py
│   ├── main.py            # FastAPI app and endpoints
│   ├── job_manager.py     # In-memory job queue
│   ├── llm_client.py      # Anthropic & OpenAI integrations
│   └── config.py          # Configuration management
│
├── lambda/                 # Alexa Lambda function (to be added)
│   └── handler.py         # Lambda handler with polling logic
│
├── tests/                  # Test suite
│
├── docs/                   # Additional documentation
│
├── requirements.txt        # Python dependencies
├── Dockerfile             # Container definition
├── docker-compose.yml     # Local development setup
└── README.md              # This file
```

## Quick Start

### Prerequisites

- Python 3.11+
- Anthropic API key and/or OpenAI API key
- Docker (optional, for containerized deployment)

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd jarvisathome
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

5. **Run the API**
   ```bash
   uvicorn api.main:app --reload
   ```

The API will be available at `http://localhost:8000`

### Using Docker

```bash
# Build and run
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## API Endpoints

### `POST /ask`

Create a new LLM job.

**Request:**
```json
{
  "question": "What is the meaning of life?",
  "session_id": "alexa-session-123",
  "provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022",
  "max_tokens": 1024
}
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2024-01-15T10:30:00",
  "message": "Job created and processing started"
}
```

### `GET /status/{job_id}`

Check job status and retrieve results.

**Response (Pending):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "created_at": "2024-01-15T10:30:00"
}
```

**Response (Complete):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "complete",
  "result": "The meaning of life is...",
  "created_at": "2024-01-15T10:30:00",
  "completed_at": "2024-01-15T10:30:15",
  "processing_time": 15.3
}
```

### `DELETE /job/{job_id}`

Cancel a running job (useful for user interruptions).

### `GET /cleanup`

Manually trigger cleanup of old jobs (>5 minutes).

### `GET /`

Health check endpoint.

## Configuration

Environment variables (`.env` file):

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key | - |
| `OPENAI_API_KEY` | OpenAI API key | - |
| `API_HOST` | API host address | `0.0.0.0` |
| `API_PORT` | API port | `8000` |
| `API_WORKERS` | Number of workers | `4` |
| `MAX_JOB_AGE_MINUTES` | Job cleanup age | `5` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `ALLOWED_ORIGINS` | CORS origins | `*` |

## Supported Models

### Anthropic (Claude)
- `claude-3-5-sonnet-20241022` (default)
- `claude-3-opus-20240229`
- `claude-3-sonnet-20240229`
- `claude-3-haiku-20240307`

### OpenAI
- `gpt-4-turbo-preview` (default)
- `gpt-4`
- `gpt-3.5-turbo`

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black api/
flake8 api/
```

### Type Checking

```bash
mypy api/
```

## Deployment Options

### AWS Lambda + API Gateway
- Deploy as Lambda function with longer timeout (60s)
- Use API Gateway for HTTP endpoints
- Minimal cost, pay per request

### EC2 / Fargate
- Deploy Docker container to EC2 t4g.nano (~$3/month)
- Or use Fargate spot instances (~$5/month)
- Always-on availability

### Production Considerations

1. **Replace in-memory job storage** with Redis or DynamoDB
2. **Add authentication** for API endpoints
3. **Configure CORS** properly (remove `*`)
4. **Set up monitoring** (CloudWatch, DataDog, etc.)
5. **Add rate limiting** to prevent abuse
6. **Implement job timeouts** to prevent infinite processing

## Lambda Integration

The `lambda/` directory will contain the Alexa Skill Lambda function that:
- Receives requests from Alexa
- Calls this API to create/check jobs
- Manages the polling loop
- Returns responses to Alexa with appropriate session management

Example flow in Lambda:
```python
# Initial request
if 'job_id' not in session:
    # Create job via API
    response = requests.post(f"{API_URL}/ask", json={...})
    job_id = response.json()['job_id']
    return alexa_response("Let me think...", keep_session=True)

# Polling request
else:
    # Check status
    status = requests.get(f"{API_URL}/status/{job_id}")
    if status['status'] == 'complete':
        return alexa_response(status['result'], keep_session=False)
    else:
        return alexa_response("<speak><break time='2s'/></speak>", keep_session=True)
```

## Troubleshooting

### Jobs not processing
- Check API logs: `docker-compose logs api`
- Verify API keys are set correctly
- Check network connectivity to LLM APIs

### Timeouts
- Increase `MAX_JOB_AGE_MINUTES` for longer processing
- Check LLM API rate limits
- Monitor API response times

### Memory issues
- Run cleanup endpoint regularly: `GET /cleanup`
- Consider switching to Redis for production
- Monitor job count: `GET /` shows active jobs

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Acknowledgments

Built to solve the fundamental architectural mismatch between Alexa's synchronous model and LLM processing times, inspired by the need for high-quality AI responses through voice interfaces.
