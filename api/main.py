"""
FastAPI Middleware for Alexa-to-LLM Async Bridge
This API acts as a middle layer between Alexa Skills and AI APIs (Anthropic/OpenAI),
enabling asynchronous LLM calls that exceed Alexa's 8-second timeout limit.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal
from contextlib import asynccontextmanager
import uuid
import asyncio
from datetime import datetime, timedelta
import logging

from .llm_client import LLMClient
from .job_manager import JobManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle (startup and shutdown)"""
    # Startup
    logger.info("Alexa LLM Bridge API starting up")
    yield
    # Shutdown
    logger.info("Alexa LLM Bridge API shutting down")


app = FastAPI(
    title="Alexa LLM Bridge API",
    description="Async middleware for connecting Alexa Skills to LLM APIs",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize job manager (in-memory for now)
job_manager = JobManager()

# Initialize LLM client
llm_client = LLMClient()


# Request/Response Models
class AskRequest(BaseModel):
    """Request to create a new LLM job"""
    question: str = Field(..., description="The question/prompt for the LLM")
    session_id: str = Field(..., description="Alexa session ID for tracking")
    provider: Literal["anthropic", "openai"] = Field(
        default="anthropic",
        description="LLM provider to use"
    )
    model: Optional[str] = Field(
        None,
        description="Specific model to use (defaults to provider's best model)"
    )
    max_tokens: Optional[int] = Field(
        default=1024,
        description="Maximum tokens in response"
    )
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional context for the conversation"
    )


class JobResponse(BaseModel):
    """Response containing job information"""
    job_id: str
    status: Literal["pending", "processing", "complete", "failed"]
    created_at: str
    message: Optional[str] = None


class StatusResponse(BaseModel):
    """Response for job status check"""
    job_id: str
    status: Literal["pending", "processing", "complete", "failed", "not_found"]
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    processing_time: Optional[float] = None
    partial_result: Optional[str] = None


# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Alexa LLM Bridge API",
        "status": "healthy",
        "version": "1.0.0",
        "active_jobs": job_manager.get_active_job_count()
    }


@app.get("/health")
async def health():
    """Health check endpoint (alias for /)"""
    return {
        "service": "Alexa LLM Bridge API",
        "status": "healthy",
        "version": "1.0.0",
        "active_jobs": job_manager.get_active_job_count()
    }


@app.post("/ask", response_model=JobResponse)
async def create_job(request: AskRequest, background_tasks: BackgroundTasks):
    """
    Create a new LLM job and start processing it asynchronously.

    This endpoint:
    1. Creates a job with a unique ID
    2. Returns immediately with job_id
    3. Processes the LLM request in the background

    The Lambda function can then poll /status/{job_id} to check completion.
    """
    try:
        # Generate unique job ID
        job_id = str(uuid.uuid4())

        # Create job entry
        job_data = {
            "job_id": job_id,
            "status": "pending",
            "question": request.question,
            "session_id": request.session_id,
            "provider": request.provider,
            "model": request.model,
            "max_tokens": request.max_tokens,
            "context": request.context,
            "created_at": datetime.utcnow().isoformat(),
            "result": None,
            "error": None
        }

        job_manager.create_job(job_id, job_data)

        logger.info(f"Created job {job_id} for session {request.session_id}")

        # Start processing in background
        background_tasks.add_task(
            process_llm_job,
            job_id,
            request.question,
            request.provider,
            request.model,
            request.max_tokens,
            request.context
        )

        return JobResponse(
            job_id=job_id,
            status="pending",
            created_at=job_data["created_at"],
            message="Job created and processing started"
        )

    except Exception as e:
        logger.error(f"Error creating job: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


@app.get("/status/{job_id}", response_model=StatusResponse)
async def check_status(job_id: str):
    """
    Check the status of a job.

    Returns:
    - pending: Job created but not yet processing
    - processing: LLM is actively working on the request
    - complete: Job finished successfully, result available
    - failed: Job failed, error message available
    - not_found: Job ID not recognized
    """
    job = job_manager.get_job(job_id)

    if not job:
        return StatusResponse(
            job_id=job_id,
            status="not_found"
        )

    response = StatusResponse(
        job_id=job_id,
        status=job["status"],
        created_at=job.get("created_at"),
        completed_at=job.get("completed_at")
    )

    if job["status"] == "complete":
        response.result = job.get("result")
        # Calculate processing time if available
        if job.get("created_at") and job.get("completed_at"):
            created = datetime.fromisoformat(job["created_at"])
            completed = datetime.fromisoformat(job["completed_at"])
            response.processing_time = (completed - created).total_seconds()

    elif job["status"] == "failed":
        response.error = job.get("error")

    elif job["status"] == "processing":
        # Include partial results if available (for streaming scenarios)
        response.partial_result = job.get("partial_result")

    return response


@app.delete("/job/{job_id}")
async def cancel_job(job_id: str):
    """
    Cancel a job and clean up its resources.

    Useful when user says "stop" or "cancel" mid-processing.
    """
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_manager.delete_job(job_id)

    logger.info(f"Cancelled job {job_id}")

    return {
        "job_id": job_id,
        "message": "Job cancelled successfully"
    }


@app.get("/cleanup")
async def cleanup_old_jobs():
    """
    Clean up jobs older than 5 minutes.

    This helps prevent memory bloat in the in-memory job store.
    Can be called periodically or by a scheduled task.
    """
    count = job_manager.cleanup_old_jobs(max_age_minutes=5)

    logger.info(f"Cleaned up {count} old jobs")

    return {
        "cleaned": count,
        "remaining": job_manager.get_active_job_count()
    }


# Background task for processing LLM requests
async def process_llm_job(
    job_id: str,
    question: str,
    provider: str,
    model: Optional[str],
    max_tokens: int,
    context: Optional[Dict[str, Any]]
):
    """
    Process an LLM request asynchronously.

    This function:
    1. Updates job status to 'processing'
    2. Calls the appropriate LLM API
    3. Updates job with result or error
    4. Sets status to 'complete' or 'failed'
    """
    try:
        logger.info(f"Starting processing for job {job_id}")

        # Update status to processing
        job_manager.update_job_status(job_id, "processing")

        # Call the LLM API
        result = await llm_client.generate(
            question=question,
            provider=provider,
            model=model,
            max_tokens=max_tokens,
            context=context
        )

        # Update job with result
        job_manager.update_job(job_id, {
            "status": "complete",
            "result": result,
            "completed_at": datetime.utcnow().isoformat()
        })

        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Error processing job {job_id}: {str(e)}")

        # Update job with error
        job_manager.update_job(job_id, {
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.utcnow().isoformat()
        })
