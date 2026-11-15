"""Analysis Service and Stage Registry according to Contract G1.

Pipeline stages in order:
queued -> static -> structure -> profile -> bottleneck -> workload -> recommend -> completed

Currently registered: static, structure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.errors import AppException
from app.core.logging import get_logger
from app.engines.complexity import ComplexityEstimator
from app.engines.static_analyzer import PatternDetector, StaticAnalyzer
from app.engines.structure import CallGraphBuilder, save_call_graph
from app.models.analysis_run import AnalysisRun
from app.models.file import File
from app.models.function import Function
from app.models.repository import Repository
from app.services.progress import publish_progress
from app.services.storage import StorageService

logger = get_logger("analysis_service")


class AnalysisContext:
    """Execution context passed through analysis pipeline stages."""

    def __init__(
        self,
        db: Session,
        storage: StorageService,
        run: AnalysisRun,
        repository: Repository,
    ):
        self.db = db
        self.storage = storage
        self.run = run
        self.repository = repository
        self.intermediate: Dict[str, Any] = {
            "file_imports": {},
            "parsed_functions": [],
        }


StageHandler = Callable[[AnalysisContext], None]


class StageRegistry:
    """Registry for pluggable analysis pipeline stages."""

    def __init__(self):
        self._stages: Dict[str, StageHandler] = {}
        self._stage_order: List[str] = [
            "queued",
            "static",
            "structure",
            "profile",
            "bottleneck",
            "workload",
            "recommend",
            "completed",
        ]

    def register(self, stage_name: str, handler: StageHandler) -> None:
        """Register a handler for a named stage."""
        if stage_name not in self._stage_order:
            raise ValueError(f"Unknown stage name '{stage_name}' outside contract G1")
        self._stages[stage_name] = handler

    def get_registered_stages(self) -> List[str]:
        """Return registered stages in pipeline order."""
        return [s for s in self._stage_order if s in self._stages]

    def get_handler(self, stage_name: str) -> Optional[StageHandler]:
        """Retrieve handler for a registered stage."""
        return self._stages.get(stage_name)


# Global stage registry instance
registry = StageRegistry()


def stage_static(ctx: AnalysisContext) -> None:
    """Execute static AST analysis, complexity estimation, and pattern detection."""
    logger.info(f"Running static analysis stage for repo {ctx.repository.id}")
    ctx.run.stage = "static"
    ctx.run.progress = 25
    ctx.db.commit()
    publish_progress(ctx.run.id, stage="static", progress=25, status="running")

    # 1. Fetch Python files for repository
    python_files = (
        ctx.db.query(File)
        .filter(File.repository_id == ctx.repository.id, File.language == "python")
        .all()
    )

    static_analyzer = StaticAnalyzer()
    complexity_estimator = ComplexityEstimator()
    pattern_detector = PatternDetector()

    new_functions: List[Function] = []
    file_imports: Dict[str, List[Dict[str, Any]]] = {}

    for file_record in python_files:
        try:
            content_bytes = ctx.storage.get_file(file_record.storage_key)
            try:
                content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = content_bytes.decode("latin1", errors="replace")
        except Exception as e:
            logger.warning(f"Could not read file {file_record.path}: {e}")
            continue

        analysis_res = static_analyzer.analyze_source(content, file_path=file_record.path)
        file_imports[file_record.path] = [i.to_dict() for i in analysis_res.imports]

        for fn_info in analysis_res.functions:
            est = complexity_estimator.estimate(fn_info)
            detected_patterns = pattern_detector.detect_patterns(fn_info)

            # Build enriched metrics
            metrics_dict = dict(fn_info.metrics)
            metrics_dict["complexity_reason"] = est.reason

            func_obj = Function(
                id=str(uuid.uuid4()),
                file_id=file_record.id,
                repository_id=ctx.repository.id,
                qualified_name=fn_info.qualified_name,
                name=fn_info.name,
                lineno=fn_info.lineno,
                end_lineno=fn_info.end_lineno,
                params=fn_info.params,
                complexity_class=est.complexity_class,
                complexity_rank=est.complexity_rank,
                loop_depth=fn_info.loop_depth,
                has_recursion=fn_info.has_recursion,
                patterns=[p.to_dict() for p in detected_patterns],
                severity=est.severity,
                metrics=metrics_dict,
            )
            new_functions.append(func_obj)

    # Idempotent replacement: delete existing functions for this repository
    ctx.db.query(Function).filter(Function.repository_id == ctx.repository.id).delete(
        synchronize_session=False
    )
    if new_functions:
        ctx.db.add_all(new_functions)
    ctx.db.commit()

    ctx.intermediate["file_imports"] = file_imports
    ctx.run.progress = 50
    ctx.db.commit()
    publish_progress(ctx.run.id, stage="static", progress=50, status="running")


def stage_structure(ctx: AnalysisContext) -> None:
    """Build cross-file function call graph and store in object storage."""
    logger.info(f"Running structure stage for repo {ctx.repository.id}")
    ctx.run.stage = "structure"
    ctx.run.progress = 75
    ctx.db.commit()
    publish_progress(ctx.run.id, stage="structure", progress=75, status="running")

    # Fetch fresh function records from DB
    functions = (
        ctx.db.query(Function)
        .filter(Function.repository_id == ctx.repository.id)
        .all()
    )

    # Build function dictionary list with file_path resolved
    file_map = {f.id: f.path for f in ctx.db.query(File).filter(File.repository_id == ctx.repository.id).all()}

    funcs_data: List[Dict[str, Any]] = []
    for fn in functions:
        fpath = file_map.get(fn.file_id, "")
        calls = (fn.metrics or {}).get("calls", [])
        funcs_data.append(
            {
                "id": fn.id,
                "name": fn.name,
                "qualified_name": fn.qualified_name,
                "file_id": fn.file_id,
                "file_path": fpath,
                "lineno": fn.lineno,
                "end_lineno": fn.end_lineno,
                "severity": fn.severity,
                "complexity_class": fn.complexity_class,
                "complexity_rank": fn.complexity_rank,
                "calls": calls,
            }
        )

    file_imports = ctx.intermediate.get("file_imports", {})

    call_graph_builder = CallGraphBuilder()
    graph_res = call_graph_builder.build_graph(
        repository_id=ctx.repository.id,
        functions_data=funcs_data,
        file_imports=file_imports,
    )

    save_call_graph(ctx.storage, graph_res)

    ctx.run.progress = 90
    ctx.db.commit()
    publish_progress(ctx.run.id, stage="structure", progress=90, status="running")


# Register Phase 2 stages
registry.register("static", stage_static)
registry.register("structure", stage_structure)


def execute_analysis(db: Session, storage: StorageService, run_id: str) -> AnalysisRun:
    """Execute analysis pipeline orchestrator over all registered stages."""
    run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
    if not run:
        raise AppException(status_code=404, detail="Analysis run not found", code="NOT_FOUND")

    repo = db.query(Repository).filter(Repository.id == run.repository_id).first()
    if not repo:
        raise AppException(status_code=404, detail="Repository not found", code="NOT_FOUND")

    run.status = "running"
    run.stage = "queued"
    run.progress = 5
    run.started_at = datetime.now(timezone.utc)
    db.commit()
    publish_progress(run.id, stage="queued", progress=5, status="running")

    ctx = AnalysisContext(db=db, storage=storage, run=run, repository=repo)

    try:
        registered_stages = registry.get_registered_stages()
        for stage_name in registered_stages:
            handler = registry.get_handler(stage_name)
            if handler:
                handler(ctx)

        # Pipeline complete
        run.status = "completed"
        run.stage = "completed"
        run.progress = 100
        run.finished_at = datetime.now(timezone.utc)
        run.error = None
        db.commit()
        publish_progress(run.id, stage="completed", progress=100, status="completed")
        logger.info(f"Analysis run {run.id} completed successfully")

    except Exception as e:
        logger.exception(f"Analysis run {run.id} failed: {e}")
        run.status = "failed"
        run.error = str(e)
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        publish_progress(run.id, stage=run.stage, progress=run.progress, status="failed", error=str(e))

    return run
