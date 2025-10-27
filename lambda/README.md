# Lambda Function for Alexa Skill

This directory contains the AWS Lambda function that handles Alexa Skill requests and integrates with the FastAPI middleware.

## Overview

The Lambda function acts as the interface between Alexa and the async API:

1. Receives requests from Alexa
2. Creates jobs via the API
3. Manages polling loop
4. Returns responses to Alexa with session management

## Files

- `handler.py` - Main Lambda handler with polling logic
- `requirements.txt` - Python dependencies
- `skill.json` - Example Alexa Skill schema (to be created)

## Deployment

### Option 1: AWS Console

1. Create a new Lambda function in AWS Console
2. Choose Python 3.11 runtime
3. Upload handler.py and dependencies as a ZIP file
4. Set environment variables
5. Configure Alexa Skills trigger

### Option 2: AWS CLI

```bash
# Install dependencies locally
cd lambda
pip install -r requirements.txt -t .

# Create deployment package
zip -r function.zip handler.py requests/

# Create/update Lambda function
aws lambda create-function \
  --function-name alexa-jarvis-handler \
  --runtime python3.11 \
  --role arn:aws:iam::YOUR_ACCOUNT:role/lambda-execution-role \
  --handler handler.lambda_handler \
  --zip-file fileb://function.zip \
  --timeout 8 \
  --environment Variables="{API_BASE_URL=https://your-api-url.com}"
```

### Option 3: Serverless Framework

Create `serverless.yml`:

```yaml
service: alexa-jarvis

provider:
  name: aws
  runtime: python3.11
  stage: prod
  region: us-east-1
  timeout: 8
  environment:
    API_BASE_URL: https://your-api-url.com

functions:
  alexaSkill:
    handler: handler.lambda_handler
    events:
      - alexaSkill: amzn1.ask.skill.YOUR-SKILL-ID
```

Deploy:
```bash
serverless deploy
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `API_BASE_URL` | URL of the FastAPI middleware | Yes |

## Lambda Configuration

- **Runtime**: Python 3.11
- **Timeout**: 8 seconds (Alexa's max)
- **Memory**: 128 MB (sufficient for simple HTTP calls)
- **Trigger**: Alexa Skills Kit

## Testing

### Test Event (LaunchRequest)

```json
{
  "version": "1.0",
  "session": {
    "new": true,
    "sessionId": "amzn1.echo-api.session.test",
    "application": {
      "applicationId": "amzn1.ask.skill.test"
    },
    "attributes": {},
    "user": {
      "userId": "amzn1.ask.account.test"
    }
  },
  "request": {
    "type": "LaunchRequest",
    "requestId": "amzn1.echo-api.request.test",
    "timestamp": "2024-01-15T10:30:00Z",
    "locale": "en-US"
  }
}
```

### Test Event (Question Intent)

```json
{
  "version": "1.0",
  "session": {
    "new": false,
    "sessionId": "amzn1.echo-api.session.test",
    "application": {
      "applicationId": "amzn1.ask.skill.test"
    },
    "attributes": {},
    "user": {
      "userId": "amzn1.ask.account.test"
    }
  },
  "request": {
    "type": "IntentRequest",
    "requestId": "amzn1.echo-api.request.test",
    "timestamp": "2024-01-15T10:30:00Z",
    "locale": "en-US",
    "intent": {
      "name": "AskQuestionIntent",
      "slots": {
        "Question": {
          "name": "Question",
          "value": "What is the meaning of life?"
        }
      }
    }
  }
}
```

## Alexa Skill Setup

### 1. Create Skill in Alexa Developer Console

1. Go to https://developer.amazon.com/alexa/console/ask
2. Click "Create Skill"
3. Choose "Custom" model
4. Choose "Provision your own" backend

### 2. Configure Invocation Name

Set invocation name (e.g., "jarvis")

### 3. Add Intents

**AskQuestionIntent:**
```json
{
  "name": "AskQuestionIntent",
  "slots": [
    {
      "name": "Question",
      "type": "AMAZON.SearchQuery"
    }
  ],
  "samples": [
    "ask {Question}",
    "tell me about {Question}",
    "explain {Question}",
    "what is {Question}",
    "{Question}"
  ]
}
```

### 4. Configure Endpoint

- Choose AWS Lambda ARN
- Enter your Lambda function ARN
- Example: `arn:aws:lambda:us-east-1:123456789012:function:alexa-jarvis-handler`

### 5. Enable Session Persistence

In the skill settings, ensure "Session Persistence" is enabled so the skill can maintain state across multiple requests.

## How the Polling Works

```
User: "Alexa, ask Jarvis what is quantum computing?"

[Request 1 - t=0s]
Alexa → Lambda: IntentRequest (new session)
Lambda → API: POST /ask (create job)
API → Lambda: job_id
Lambda → Alexa: "Let me think about that..." (keep session open)

[Request 2 - t=5s] (auto-reprompt)
Alexa → Lambda: IntentRequest (with job_id in session)
Lambda → API: GET /status/{job_id}
API → Lambda: status="processing"
Lambda → Alexa: "<break time='2s'/>" (keep session open)

[Request 3 - t=10s] (auto-reprompt)
Alexa → Lambda: IntentRequest (with job_id in session)
Lambda → API: GET /status/{job_id}
API → Lambda: status="processing"
Lambda → Alexa: "Still working on it... <break time='2s'/>" (keep session open)

[Request 4 - t=15s] (auto-reprompt)
Alexa → Lambda: IntentRequest (with job_id in session)
Lambda → API: GET /status/{job_id}
API → Lambda: status="complete", result="..."
Lambda → Alexa: "Quantum computing is..." (end session)

User hears: "Let me think about that... Still working on it... Quantum computing is..."
```

## Troubleshooting

### Lambda Timeout

If Lambda times out before returning, check:
- API_BASE_URL is correct and reachable
- API responds within timeout (3 seconds)
- Network connectivity from Lambda to API

### Session Not Persisting

- Ensure `shouldEndSession: false` in responses
- Check session attributes are being passed correctly
- Verify Alexa Skill has session persistence enabled

### No Auto-Reprompt

Alexa should auto-reprompt after ~5-8 seconds of silence if session is open. If not:
- Ensure SSML includes `<break>` tag
- Verify `shouldEndSession: false`
- Check skill configuration

## Monitoring

Use CloudWatch Logs to monitor:
- Lambda invocations
- API call success/failure
- Job status transitions
- Error messages

Example CloudWatch Insights query:
```
fields @timestamp, @message
| filter @message like /job_id/
| sort @timestamp desc
| limit 100
```

## Cost Estimation

With 1000 questions per month:
- Lambda invocations: ~5000 (1 initial + 4 polls average)
- Lambda compute: ~0.5 seconds * 5000 = 2500 seconds
- Cost: ~$0.01/month (free tier covers this)

## Next Steps

1. Deploy Lambda function
2. Create Alexa Skill in developer console
3. Configure skill with Lambda ARN
4. Test with Alexa simulator
5. Test on physical device
6. Submit for certification (optional)
