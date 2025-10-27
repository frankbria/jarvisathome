"""
Test script for the Alexa LLM Bridge API.

Run with: python -m pytest tests/test_api.py -v
"""

import pytest
import time
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock

# Import the app
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from api.main import app
from api.job_manager import JobManager


@pytest.fixture
def client():
    """Create a test client"""
    return TestClient(app)


@pytest.fixture
def job_manager():
    """Create a fresh job manager for each test"""
    return JobManager()


def test_health_check(client):
    """Test the health check endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Alexa LLM Bridge API"
    assert data["status"] == "healthy"
    assert "active_jobs" in data


def test_create_job(client):
    """Test creating a job"""
    with patch('api.main.llm_client.generate', new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = "Test response"

        response = client.post("/ask", json={
            "question": "What is 2+2?",
            "session_id": "test-session-123",
            "provider": "anthropic"
        })

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert "created_at" in data


def test_check_status_not_found(client):
    """Test checking status of non-existent job"""
    response = client.get("/status/nonexistent-job-id")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_found"


def test_job_lifecycle(client):
    """Test complete job lifecycle: create -> poll -> complete"""
    with patch('api.main.llm_client.generate', new_callable=AsyncMock) as mock_generate:
        # Mock LLM to return quickly
        mock_generate.return_value = "The answer is 42"

        # Create job
        create_response = client.post("/ask", json={
            "question": "What is the meaning of life?",
            "session_id": "test-session-456",
            "provider": "anthropic"
        })
        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]

        # Poll status (may need to wait a moment for background task)
        time.sleep(0.5)

        status_response = client.get(f"/status/{job_id}")
        assert status_response.status_code == 200
        data = status_response.json()
        assert data["job_id"] == job_id
        assert data["status"] in ["pending", "processing", "complete"]


def test_cancel_job(client):
    """Test canceling a job"""
    with patch('api.main.llm_client.generate', new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = "Test response"

        # Create job
        create_response = client.post("/ask", json={
            "question": "Long running question",
            "session_id": "test-session-789",
            "provider": "anthropic"
        })
        job_id = create_response.json()["job_id"]

        # Cancel job
        cancel_response = client.delete(f"/job/{job_id}")
        assert cancel_response.status_code == 200
        assert cancel_response.json()["message"] == "Job cancelled successfully"

        # Verify job is gone
        status_response = client.get(f"/status/{job_id}")
        assert status_response.json()["status"] == "not_found"


def test_cleanup_old_jobs(client):
    """Test cleanup endpoint"""
    response = client.get("/cleanup")
    assert response.status_code == 200
    data = response.json()
    assert "cleaned" in data
    assert "remaining" in data


def test_job_manager_create_and_get():
    """Test JobManager create and get"""
    manager = JobManager()

    job_data = {
        "status": "pending",
        "question": "Test?",
        "created_at": "2024-01-15T10:00:00"
    }

    manager.create_job("test-job-1", job_data)
    retrieved = manager.get_job("test-job-1")

    assert retrieved is not None
    assert retrieved["question"] == "Test?"
    assert retrieved["status"] == "pending"


def test_job_manager_update():
    """Test JobManager update"""
    manager = JobManager()

    job_data = {"status": "pending"}
    manager.create_job("test-job-2", job_data)

    manager.update_job("test-job-2", {"status": "complete", "result": "Done"})
    updated = manager.get_job("test-job-2")

    assert updated["status"] == "complete"
    assert updated["result"] == "Done"


def test_job_manager_delete():
    """Test JobManager delete"""
    manager = JobManager()

    manager.create_job("test-job-3", {"status": "pending"})
    assert manager.get_job("test-job-3") is not None

    manager.delete_job("test-job-3")
    assert manager.get_job("test-job-3") is None


def test_job_manager_cleanup(job_manager):
    """Test JobManager cleanup of old jobs"""
    from datetime import datetime, timedelta

    # Create an old job (10 minutes ago)
    old_time = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
    job_manager.create_job("old-job", {
        "status": "complete",
        "created_at": old_time
    })

    # Create a recent job
    recent_time = datetime.utcnow().isoformat()
    job_manager.create_job("recent-job", {
        "status": "pending",
        "created_at": recent_time
    })

    # Cleanup jobs older than 5 minutes
    cleaned = job_manager.cleanup_old_jobs(max_age_minutes=5)

    assert cleaned == 1
    assert job_manager.get_job("old-job") is None
    assert job_manager.get_job("recent-job") is not None


def test_invalid_provider(client):
    """Test creating job with invalid provider"""
    with patch('api.main.llm_client.generate', new_callable=AsyncMock) as mock_generate:
        mock_generate.side_effect = ValueError("Unknown provider: invalid")

        response = client.post("/ask", json={
            "question": "Test question",
            "session_id": "test-session",
            "provider": "invalid"
        })

        # Job is created but will fail during processing
        assert response.status_code == 200


def test_openai_provider(client):
    """Test creating job with OpenAI provider"""
    with patch('api.main.llm_client.generate', new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = "GPT response"

        response = client.post("/ask", json={
            "question": "Test question",
            "session_id": "test-session",
            "provider": "openai",
            "model": "gpt-4"
        })

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
