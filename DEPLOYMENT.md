# Jarvis at Home - Deployment Guide

## Overview

This guide covers deploying the Alexa-Claude integration system that uses an async middleware API to bypass Alexa's 8-second timeout constraint. The architecture consists of:

1. **AWS Lambda** - Alexa skill handler (manages sessions, polls for results)
2. **FastAPI Middleware** - Async job queue running on your VPS
3. **Claude/GPT API** - LLM backend for responses

## Architecture

```
┌─────────────────────────────────────────────┐
│              AWS                             │
│  ┌──────────┐         ┌─────────────┐      │
│  │  Alexa   │────────>│   Lambda    │──────┼─────> HTTPS to VPS
│  │ Service  │<────────│  (Skill)    │<─────┼───── 
│  └──────────┘         └─────────────┘      │
└─────────────────────────────────────────────┘
                              │
                              │ HTTPS (public internet)
                              │
                              ▼
                    ┌──────────────────────┐
                    │   Your VPS           │
                    │                      │
                    │  ┌────────────────┐ │
                    │  │  FastAPI App   │ │
                    │  │  (port 8000)   │ │
                    │  └────────────────┘ │
                    │         │            │
                    │         ▼            │
                    │  ┌────────────────┐ │
                    │  │ Claude/GPT API │ │
                    │  │    (outbound)  │ │
                    │  └────────────────┘ │
                    └──────────────────────┘
```

## Prerequisites

- VPS with Ubuntu 22.04+ (DigitalOcean, Linode, Vultr, etc.)
- Domain name with DNS pointing to your VPS
- AWS account with Lambda access
- Claude API key (or OpenAI API key)
- SSH access to your VPS

## Part 1: VPS Setup

### 1.1 Initial Server Configuration

```bash
# SSH into your VPS
ssh root@your-vps-ip

# Update system packages
sudo apt update
sudo apt upgrade -y

# Install required packages
sudo apt install -y python3-pip python3-venv nginx certbot python3-certbot-nginx git
```

### 1.2 Create Application User

```bash
# Create dedicated user for the application
sudo useradd -m -s /bin/bash jarvis
sudo usermod -aG sudo jarvis

# Switch to jarvis user
sudo su - jarvis
```

### 1.3 Clone and Setup Application

```bash
# Clone the repository
cd /home/jarvis
git clone https://github.com/frankbria/jarvisathome.git
cd jarvisathome
git checkout claude/fastapi-job-middleware-011CUWpUrwtFc84XaGv4D5Zg

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install fastapi uvicorn[standard] anthropic openai python-dotenv
```

### 1.4 Configure Environment Variables

```bash
# Create .env file
nano /home/jarvis/jarvisathome/.env
```

Add the following content:

```env
# API Keys
ANTHROPIC_API_KEY=your_anthropic_api_key_here
OPENAI_API_KEY=your_openai_api_key_here  # Optional, if using GPT

# Security
API_KEY=generate_a_random_string_here  # Used for Lambda->API authentication

# Application Settings
MAX_TOKEN_LENGTH=150
JOB_TIMEOUT_SECONDS=60
LOG_LEVEL=INFO
```

To generate a secure API key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 1.5 Create Systemd Service

Exit the jarvis user and return to root, then create the service file:

```bash
exit  # Return to root user
sudo nano /etc/systemd/system/jarvis-api.service
```

Add the following content:

```ini
[Unit]
Description=Jarvis at Home FastAPI Service
After=network.target

[Service]
Type=simple
User=jarvis
Group=jarvis
WorkingDirectory=/home/jarvis/jarvisathome
Environment="PATH=/home/jarvis/jarvisathome/venv/bin"
EnvironmentFile=/home/jarvis/jarvisathome/.env
ExecStart=/home/jarvis/jarvisathome/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable jarvis-api
sudo systemctl start jarvis-api

# Check status
sudo systemctl status jarvis-api

# View logs
sudo journalctl -u jarvis-api -f
```

### 1.6 Configure Nginx Reverse Proxy

```bash
sudo nano /etc/nginx/sites-available/jarvis-api
```

Add the following configuration (replace `api.yourdomain.com` with your actual domain):

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for long-running requests
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /health {
        proxy_pass http://localhost:8000/health;
        access_log off;
    }
}
```

Enable the site:

```bash
# Create symbolic link
sudo ln -s /etc/nginx/sites-available/jarvis-api /etc/nginx/sites-enabled/

# Test nginx configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
```

### 1.7 Setup SSL with Let's Encrypt

```bash
# Obtain SSL certificate
sudo certbot --nginx -d api.yourdomain.com

# Test auto-renewal
sudo certbot renew --dry-run
```

Certbot will automatically modify your nginx configuration to use HTTPS.

### 1.8 Configure Firewall

```bash
# Allow SSH, HTTP, and HTTPS
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable

# Check status
sudo ufw status
```

### 1.9 Test the API

```bash
# Health check
curl https://api.yourdomain.com/health

# Should return: {"status":"ok","timestamp":1234567890.123}
```

## Part 2: AWS Lambda Setup

### 2.1 Create Lambda Function

1. Log into AWS Console
2. Navigate to Lambda service
3. Click "Create function"
4. Choose "Author from scratch"
5. Function name: `jarvis-alexa-skill`
6. Runtime: `Python 3.11`
7. Architecture: `x86_64`
8. Click "Create function"

### 2.2 Configure Lambda

#### Set Environment Variables

In the Lambda console, go to Configuration → Environment variables:

```
API_URL = https://api.yourdomain.com
API_KEY = your_generated_api_key_from_vps
```

#### Adjust Timeout and Memory

Configuration → General configuration:
- Timeout: `8 seconds` (max for Alexa)
- Memory: `256 MB` (sufficient for this use case)

### 2.3 Deploy Lambda Code

Create a deployment package locally:

```bash
# On your local machine
mkdir lambda-package
cd lambda-package

# Copy the Lambda handler code
# (You'll create this file based on the code structure in the repo)
cp /path/to/lambda_handler.py .

# Install dependencies
pip install requests -t .

# Create zip file
zip -r lambda-function.zip .
```

Upload to Lambda:
1. In Lambda console, go to "Code" tab
2. Click "Upload from" → ".zip file"
3. Upload your `lambda-function.zip`

Alternatively, use AWS CLI:

```bash
aws lambda update-function-code \
    --function-name jarvis-alexa-skill \
    --zip-file fileb://lambda-function.zip
```

### 2.4 Create Alexa Skill

1. Go to [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask)
2. Click "Create Skill"
3. Skill name: `Jarvis` (or your preferred name)
4. Choose model: "Custom"
5. Choose method: "Provision your own"
6. Click "Create skill"

#### Configure Invocation

1. In the skill builder, set Invocation name: `jarvis` or `claude`
2. This allows: "Alexa, ask Jarvis..." or "Alexa, open Jarvis"

#### Create Intent Schema

Go to JSON Editor and paste:

```json
{
  "interactionModel": {
    "languageModel": {
      "invocationName": "jarvis",
      "intents": [
        {
          "name": "AskQuestionIntent",
          "slots": [
            {
              "name": "question",
              "type": "AMAZON.SearchQuery"
            }
          ],
          "samples": [
            "{question}",
            "ask {question}",
            "tell me {question}",
            "what is {question}",
            "explain {question}"
          ]
        },
        {
          "name": "AMAZON.CancelIntent",
          "samples": []
        },
        {
          "name": "AMAZON.StopIntent",
          "samples": []
        },
        {
          "name": "AMAZON.HelpIntent",
          "samples": []
        }
      ],
      "types": []
    }
  }
}
```

Click "Save Model" then "Build Model"

#### Configure Endpoint

1. Go to "Endpoint" in the left sidebar
2. Select "AWS Lambda ARN"
3. Default Region: Enter your Lambda function ARN
   - Find this in Lambda console under Function ARN
   - Format: `arn:aws:lambda:us-east-1:123456789:function:jarvis-alexa-skill`
4. Click "Save Endpoints"

#### Add Lambda Trigger

1. In Lambda console, click "Add trigger"
2. Select "Alexa Skills Kit"
3. Skill ID: Copy from Alexa Developer Console (under "Endpoint" section)
4. Click "Add"

### 2.5 Test the Integration

In Alexa Developer Console:
1. Go to "Test" tab
2. Enable testing: "Development"
3. Type or speak: "ask jarvis what is quantum computing"
4. Check the JSON input/output to debug

## Part 3: Monitoring and Maintenance

### 3.1 VPS Logging

```bash
# View application logs
sudo journalctl -u jarvis-api -f

# View nginx access logs
sudo tail -f /var/log/nginx/access.log

# View nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### 3.2 Lambda Logging

View logs in AWS CloudWatch:
1. Lambda console → Monitor tab
2. Click "View CloudWatch logs"
3. Select latest log stream

### 3.3 Health Monitoring

Setup a simple uptime monitor (optional):

1. Sign up for [UptimeRobot](https://uptimerobot.com) (free tier)
2. Add monitor:
   - Type: HTTPS
   - URL: `https://api.yourdomain.com/health`
   - Interval: 5 minutes
3. Configure email alerts

### 3.4 Restart Services

```bash
# Restart FastAPI application
sudo systemctl restart jarvis-api

# Restart Nginx
sudo systemctl restart nginx

# View service status
sudo systemctl status jarvis-api
```

### 3.5 Update Application

```bash
# SSH into VPS
ssh jarvis@your-vps-ip

# Pull latest changes
cd /home/jarvis/jarvisathome
git pull origin claude/fastapi-job-middleware-011CUWpUrwtFc84XaGv4D5Zg

# Restart service
sudo systemctl restart jarvis-api

# Check logs
sudo journalctl -u jarvis-api -f
```

## Part 4: Troubleshooting

### Common Issues

#### Issue: API returns 401 Unauthorized

**Cause**: API key mismatch between Lambda and VPS

**Solution**:
```bash
# On VPS, check .env file
cat /home/jarvis/jarvisathome/.env | grep API_KEY

# In Lambda, verify environment variable matches
# AWS Console → Lambda → Configuration → Environment variables
```

#### Issue: Alexa says "There was a problem with the requested skill's response"

**Cause**: Lambda timeout or incorrect response format

**Solution**:
1. Check Lambda CloudWatch logs for errors
2. Verify Lambda has correct API_URL environment variable
3. Test API endpoint manually:
```bash
curl -X POST https://api.yourdomain.com/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_api_key" \
  -d '{"question":"test","session_id":"test123"}'
```

#### Issue: API not responding

**Cause**: Service crashed or not running

**Solution**:
```bash
# Check service status
sudo systemctl status jarvis-api

# Restart service
sudo systemctl restart jarvis-api

# Check for Python errors
sudo journalctl -u jarvis-api -n 50
```

#### Issue: SSL certificate expired

**Cause**: Certbot auto-renewal failed

**Solution**:
```bash
# Manually renew
sudo certbot renew

# Restart nginx
sudo systemctl restart nginx

# Check renewal timer
sudo systemctl status certbot.timer
```

## Part 5: Cost Estimates

### VPS Costs
- **DigitalOcean Droplet** (1 GB RAM, 1 vCPU): $6/month
- **Linode Nanode**: $5/month
- **Vultr**: $5/month

### AWS Costs
- **Lambda**: ~$0.20/month (assuming 1000 invocations/month)
- **CloudWatch Logs**: ~$0.50/month

### API Costs
- **Claude API** (Sonnet 4): ~$3-15/month (depends on usage)
  - Input: $3 per million tokens
  - Output: $15 per million tokens
- **OpenAI API** (GPT-4): Similar pricing

**Total estimated monthly cost**: $15-30/month

## Part 6: Security Best Practices

### 6.1 API Key Rotation

Rotate your API keys periodically:

```bash
# Generate new API key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Update .env on VPS
nano /home/jarvis/jarvisathome/.env

# Update Lambda environment variable in AWS Console

# Restart VPS service
sudo systemctl restart jarvis-api
```

### 6.2 Rate Limiting

The FastAPI middleware should include rate limiting (already in code):

```python
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter

@app.post("/ask", dependencies=[Depends(RateLimiter(times=10, seconds=60))])
```

### 6.3 Firewall Rules

Ensure only necessary ports are open:

```bash
sudo ufw status verbose
```

### 6.4 Regular Updates

Keep system updated:

```bash
# Update system packages monthly
sudo apt update && sudo apt upgrade -y

# Update Python dependencies quarterly
source /home/jarvis/jarvisathome/venv/bin/activate
pip list --outdated
pip install --upgrade package_name
```

## Part 7: Advanced Configuration

### 7.1 Using Redis for Job State (Optional)

For more robust state management:

```bash
# Install Redis
sudo apt install redis-server

# Configure Redis
sudo nano /etc/redis/redis.conf
# Set: supervised systemd

# Restart Redis
sudo systemctl restart redis

# Update Python code to use Redis
pip install redis
```

### 7.2 Multiple Workers

For higher concurrency:

```bash
# Edit systemd service
sudo nano /etc/systemd/system/jarvis-api.service

# Change ExecStart line to:
ExecStart=/home/jarvis/jarvisathome/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2

# Restart
sudo systemctl daemon-reload
sudo systemctl restart jarvis-api
```

### 7.3 Database Logging

Track all queries for analysis:

```bash
# Install SQLite (usually pre-installed)
sudo apt install sqlite3

# Create database directory
sudo mkdir -p /var/lib/jarvis-api
sudo chown jarvis:jarvis /var/lib/jarvis-api
```

Update code to log to SQLite at `/var/lib/jarvis-api/queries.db`

## Part 8: Usage Examples

### Basic Usage

```
You: "Alexa, open Jarvis"
Alexa: "Welcome to Jarvis. What would you like to know?"
You: "What is quantum entanglement?"
Alexa: "Let me think about that..." [2-3 second pause]
Alexa: [Provides detailed answer from Claude]
```

### Follow-up Questions

```
You: "Alexa, ask Jarvis about machine learning"
Alexa: "Let me think about that..." [pause]
Alexa: [Provides answer]
You: "Can you give me an example?"
Alexa: "Still working on it..." [pause]
Alexa: [Provides example]
```

### Canceling

```
You: "Alexa, ask Jarvis a complex question"
Alexa: "Let me think about that..."
You: "Alexa, stop"
Alexa: "Okay, cancelled."
```

## Support and Contributing

For issues or questions:
- GitHub Issues: https://github.com/frankbria/jarvisathome/issues
- Check logs: `sudo journalctl -u jarvis-api -f`
- Check Lambda logs in CloudWatch

## License

[Add your license information here]

## Acknowledgments

Built with:
- FastAPI
- Anthropic Claude API
- AWS Lambda
- Alexa Skills Kit

---

*Last updated: October 2025*
