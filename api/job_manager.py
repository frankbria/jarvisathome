"""
Job Manager for in-memory job queue.

In production, this should be replaced with Redis, DynamoDB, or similar persistent storage.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import threading


class JobManager:
    """
    Manages job storage and retrieval.

    This is an in-memory implementation. For production:
    - Use Redis for distributed access and persistence
    - Use DynamoDB for serverless scalability
    - Add proper locking for concurrent access
    """

    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def create_job(self, job_id: str, job_data: Dict[str, Any]) -> None:
        """Create a new job entry"""
        with self.lock:
            self.jobs[job_id] = job_data

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a job by ID"""
        with self.lock:
            return self.jobs.get(job_id)

    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update a job with new data"""
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(updates)
                return True
            return False

    def update_job_status(self, job_id: str, status: str) -> bool:
        """Update job status"""
        return self.update_job(job_id, {"status": status})

    def delete_job(self, job_id: str) -> bool:
        """Delete a job"""
        with self.lock:
            if job_id in self.jobs:
                del self.jobs[job_id]
                return True
            return False

    def get_active_job_count(self) -> int:
        """Get count of active jobs"""
        with self.lock:
            return len(self.jobs)

    def cleanup_old_jobs(self, max_age_minutes: int = 5) -> int:
        """
        Remove jobs older than specified age.

        Args:
            max_age_minutes: Maximum age in minutes before cleanup

        Returns:
            Number of jobs cleaned up
        """
        with self.lock:
            now = datetime.utcnow()
            cutoff = now - timedelta(minutes=max_age_minutes)

            jobs_to_remove = []

            for job_id, job in self.jobs.items():
                created_at = datetime.fromisoformat(job["created_at"])
                if created_at < cutoff:
                    jobs_to_remove.append(job_id)

            for job_id in jobs_to_remove:
                del self.jobs[job_id]

            return len(jobs_to_remove)

    def get_all_jobs(self) -> Dict[str, Dict[str, Any]]:
        """Get all jobs (for debugging/monitoring)"""
        with self.lock:
            return self.jobs.copy()
