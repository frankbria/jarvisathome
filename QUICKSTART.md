# Quick Start Guide

Get up and running with the Alexa LLM Bridge in 5 minutes.

## Prerequisites

- Python 3.11 or higher
- An Anthropic API key OR OpenAI API key
- Terminal/command line access

## Installation Steps

### 1. Clone and Setup

```bash
# Navigate to project directory
cd jarvisathome

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your API key(s)
# You need at least one of these:
nano .env  # or use your preferred editor
```

Add your key(s):
```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
# OR
OPENAI_API_KEY=sk-your-key-here
```

### 3. Start the API

```bash
uvicorn api.main:app --reload
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

### 4. Test the API

In a new terminal:

```bash
# Activate the virtual environment again
source venv/bin/activate

# Run test script
python tests/manual_test.py "What is quantum computing?"
```

You should see the job being created, polled, and completed with an answer!

## Using Docker (Alternative)

If you prefer Docker:

```bash
# Make sure .env file is configured with your API keys
cp .env.example .env
# Edit .env with your keys

# Start with Docker Compose
docker-compose up --build

# Test (in another terminal)
python tests/manual_test.py "Hello world"
```

## API Endpoints

Once running, you can access:

- **Health Check**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs (interactive Swagger UI)
- **ReDoc**: http://localhost:8000/redoc (alternative documentation)

## Testing with curl

Create a job:
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the meaning of life?",
    "session_id": "test-123",
    "provider": "anthropic"
  }'
```

Check status (replace JOB_ID with the returned job_id):
```bash
curl http://localhost:8000/status/JOB_ID
```

## Next Steps

1. **Deploy the API** to a server (EC2, Fargate, etc.)
2. **Create Alexa Skill** in Amazon Developer Console
3. **Deploy Lambda function** (see `lambda/README.md`)
4. **Connect everything** and test with your Alexa device!

## Troubleshooting

### "Module not found" errors
Make sure virtual environment is activated and dependencies are installed:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### API key errors
- Check your `.env` file has the correct key
- Make sure there are no extra spaces or quotes
- Verify the key is valid by testing in the provider's playground

### "Connection refused" errors
- Make sure the API is running (`uvicorn api.main:app --reload`)
- Check it's running on the correct port (8000)
- Try accessing http://localhost:8000 in your browser

## Getting Help

- Check the main [README.md](README.md) for detailed documentation
- Review [lambda/README.md](lambda/README.md) for Lambda setup
- Look at test examples in `tests/` directory

## Architecture Reminder

```
Alexa → Lambda → This API → Anthropic/OpenAI
         ↑         ↓
         └─(polls)─┘
```

The API handles the long-running LLM calls while Lambda quickly polls for results, working around Alexa's 8-second timeout!
