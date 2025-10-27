#!/usr/bin/env python3
"""
Manual test script for the Alexa LLM Bridge API.

This script simulates the Alexa Lambda polling pattern:
1. Create a job
2. Poll until complete
3. Display result

Usage:
    python tests/manual_test.py "What is quantum computing?"
"""

import sys
import time
import requests
from typing import Optional


API_BASE_URL = "http://localhost:8000"
POLL_INTERVAL = 2  # seconds
MAX_POLLS = 20


def create_job(question: str, provider: str = "anthropic") -> Optional[str]:
    """Create a new job and return job_id"""
    print(f"\n{'='*60}")
    print(f"Creating job for question: {question}")
    print(f"Provider: {provider}")
    print(f"{'='*60}\n")

    try:
        response = requests.post(
            f"{API_BASE_URL}/ask",
            json={
                "question": question,
                "session_id": "manual-test-session",
                "provider": provider,
                "max_tokens": 1024
            },
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            job_id = data["job_id"]
            print(f"✓ Job created: {job_id}")
            print(f"  Status: {data['status']}")
            print(f"  Created: {data['created_at']}\n")
            return job_id
        else:
            print(f"✗ Error creating job: {response.status_code}")
            print(f"  Response: {response.text}")
            return None

    except requests.RequestException as e:
        print(f"✗ Request failed: {str(e)}")
        return None


def poll_job(job_id: str) -> bool:
    """
    Poll job until complete or failed.
    Returns True if successful, False otherwise.
    """
    print("Polling for completion...")
    print(f"{'─'*60}\n")

    polls = 0
    while polls < MAX_POLLS:
        polls += 1

        try:
            response = requests.get(
                f"{API_BASE_URL}/status/{job_id}",
                timeout=5
            )

            if response.status_code != 200:
                print(f"✗ Error checking status: {response.status_code}")
                return False

            data = response.json()
            status = data["status"]

            if status == "complete":
                print(f"\n{'='*60}")
                print("✓ Job completed!")
                print(f"{'='*60}\n")
                print(f"Result:\n{data['result']}\n")
                print(f"{'─'*60}")
                print(f"Processing time: {data.get('processing_time', 'N/A')} seconds")
                print(f"{'─'*60}\n")
                return True

            elif status == "failed":
                print(f"\n{'='*60}")
                print("✗ Job failed!")
                print(f"{'='*60}\n")
                print(f"Error: {data.get('error', 'Unknown error')}\n")
                return False

            elif status in ["pending", "processing"]:
                # Show progress
                dots = "." * (polls % 4)
                print(f"  [{polls:2d}] Status: {status:12s} {dots:<4s}", end="\r")
                time.sleep(POLL_INTERVAL)

            else:
                print(f"✗ Unknown status: {status}")
                return False

        except requests.RequestException as e:
            print(f"\n✗ Request failed: {str(e)}")
            return False

    print(f"\n✗ Timeout: Job did not complete after {MAX_POLLS * POLL_INTERVAL} seconds")
    return False


def test_health_check():
    """Test API health check"""
    print("Checking API health...")
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✓ API is healthy")
            print(f"  Service: {data['service']}")
            print(f"  Version: {data['version']}")
            print(f"  Active jobs: {data['active_jobs']}\n")
            return True
        else:
            print(f"✗ API returned {response.status_code}")
            return False
    except requests.RequestException as e:
        print(f"✗ Cannot connect to API: {str(e)}")
        print(f"  Make sure the API is running at {API_BASE_URL}")
        return False


def main():
    """Main test function"""
    if len(sys.argv) < 2:
        print("Usage: python manual_test.py <question> [provider]")
        print("\nExamples:")
        print('  python manual_test.py "What is quantum computing?"')
        print('  python manual_test.py "Explain AI" anthropic')
        print('  python manual_test.py "Tell me about Mars" openai')
        sys.exit(1)

    question = sys.argv[1]
    provider = sys.argv[2] if len(sys.argv) > 2 else "anthropic"

    # Health check
    if not test_health_check():
        sys.exit(1)

    # Create job
    job_id = create_job(question, provider)
    if not job_id:
        sys.exit(1)

    # Poll until complete
    success = poll_job(job_id)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
