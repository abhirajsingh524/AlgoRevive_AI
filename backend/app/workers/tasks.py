from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.analysis_service import execute_analysis
from app.services.optimization_service import execute_optimization
from app.services.storage import get_storage_service
from app.workers.celery_app import celery_app, ping

logger = get_logger("tasks")


@celery_app.task(name="run_analysis", bind=True)
def run_analysis(self, run_id: str) -> dict:
    """Execute repository analysis pipeline orchestrator as a background task."""
    logger.info(f"Starting Celery task run_analysis for run_id={run_id}")
    db = SessionLocal()
    storage = get_storage_service()
    try:
        run = execute_analysis(db=db, storage=storage, run_id=run_id)
        return {
            "run_id": run.id,
            "status": run.status,
            "stage": run.stage,
            "progress": run.progress,
            "error": run.error,
        }
    except Exception as e:
        logger.exception(f"Unexpected error in run_analysis worker task: {e}")
        return {
            "run_id": run_id,
            "status": "failed",
            "error": str(e),
        }
    finally:
        db.close()


@celery_app.task(name="run_optimization", bind=True)
def run_optimization(self, optimization_id: str) -> dict:
    """Execute optimization generation pipeline stage as a background task."""
    logger.info(f"Starting Celery task run_optimization for optimization_id={optimization_id}")
    db = SessionLocal()
    storage = get_storage_service()
    try:
        opt = execute_optimization(db=db, storage=storage, optimization_id=optimization_id)
        return {
            "optimization_id": opt.id,
            "status": opt.status,
            "decision": opt.decision,
            "error": opt.error,
        }
    except Exception as e:
        logger.exception(f"Unexpected error in run_optimization worker task: {e}")
        return {
            "optimization_id": optimization_id,
            "status": "failed",
            "error": str(e),
        }
    finally:
        db.close()


__all__ = ["celery_app", "ping", "run_analysis", "run_optimization"]

