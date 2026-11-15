"""Analysis Service and Stage Registry according to Contract G1.

Pipeline stages in order:
queued -> static -> structure -> profile -> bottleneck -> workload -> recommend -> completed

Currently registered: static, structure.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Callable, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from app.core.errors import AppException
from app.core.logging import get_logger
from app.engines.bottleneck import BottleneckDetector
from app.engines.complexity import ComplexityEstimator
from app.engines.profiler import ProfilerEngine, collect_environment_metadata
from app.engines.static_analyzer import PatternDetector, StaticAnalyzer
from app.engines.structure import CallGraphBuilder, save_call_graph
from app.engines.workload import WorkloadSpec
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

    ctx.run.progress = 50
    ctx.db.commit()
    publish_progress(ctx.run.id, stage="structure", progress=50, status="running")


def stage_profile(ctx: AnalysisContext) -> None:
    """Execute dynamic profiling inside sandbox container under specified workload."""
    logger.info(f"Running profile stage for repo {ctx.repository.id} run {ctx.run.id}")
    ctx.run.stage = "profile"
    ctx.run.progress = 55
    ctx.db.commit()
    publish_progress(
        ctx.run.id,
        stage="profile",
        progress=55,
        status="running",
        message="Preparing runtime profiling",
    )

    # 1. Locate workload spec: from run.workload_spec, config, or repo root algorevive.workload.json
    workload_data: Optional[Dict[str, Any]] = None
    if ctx.run.workload_spec:
        workload_data = ctx.run.workload_spec
    elif ctx.run.config and isinstance(ctx.run.config, dict) and ctx.run.config.get("workload_spec"):
        workload_data = ctx.run.config.get("workload_spec")
    else:
        repo_files = ctx.db.query(File).filter(File.repository_id == ctx.repository.id).all()
        for f in repo_files:
            clean = f.path.lstrip("/\\")
            if clean in ("algorevive.workload.json", "workload.json"):
                try:
                    raw_bytes = ctx.storage.get_file(f.storage_key)
                    workload_data = json.loads(raw_bytes.decode("utf-8"))
                    break
                except Exception as e:
                    logger.warning(f"Failed to read workload spec from {f.path}: {e}")

    # 2. If no workload spec found, skip with clear warning (static-only mode)
    if not workload_data:
        warning_msg = "No workload spec found (static-only mode); skipping profiling stage"
        logger.warning(warning_msg)
        ctx.run.progress = 80
        ctx.db.commit()
        publish_progress(
            ctx.run.id,
            stage="profile",
            progress=80,
            status="running",
            message=warning_msg,
        )
        return

    # 3. Validate workload spec with Pydantic
    try:
        spec = WorkloadSpec.model_validate(workload_data)
    except Exception as val_err:
        warning_msg = f"Invalid workload spec: {val_err}; skipping profiling stage"
        logger.warning(warning_msg)
        ctx.run.progress = 80
        ctx.db.commit()
        publish_progress(
            ctx.run.id,
            stage="profile",
            progress=80,
            status="running",
            message=warning_msg,
        )
        return

    # 4. Save validated spec and hash on the run
    spec_dict = spec.model_dump()
    ctx.run.workload_spec = spec_dict
    ctx.run.workload_hash = hashlib.sha256(
        json.dumps(spec_dict, sort_keys=True).encode("utf-8")
    ).hexdigest()

    # 5. Record environment metadata (Contract G10)
    env_meta = collect_environment_metadata(seed=spec.seed)
    ctx.run.environment = env_meta
    ctx.db.commit()

    # 6. Fetch all repository files into memory dict
    repo_files = ctx.db.query(File).filter(File.repository_id == ctx.repository.id).all()
    files_dict: Dict[str, bytes] = {}
    for f in repo_files:
        try:
            files_dict[f.path] = ctx.storage.get_file(f.storage_key)
        except Exception as e:
            logger.warning(f"Could not load file {f.path} for sandbox: {e}")

    publish_progress(
        ctx.run.id,
        stage="profile",
        progress=60,
        status="running",
        message="Running profiling inside sandbox container...",
    )

    # 7. Run profiler engine
    profiler = ProfilerEngine()
    try:
        profile_result = profiler.profile(run_id=ctx.run.id, files=files_dict, spec=spec)
    except Exception as prof_err:
        logger.error(f"Profiling failed: {prof_err}")
        publish_progress(
            ctx.run.id,
            stage="profile",
            progress=80,
            status="running",
            message=f"Profiling warning: {prof_err}",
        )
        return

    # 8. Save profile to storage: runs/{run_id}/profile.json (Contract I)
    storage_key = f"runs/{ctx.run.id}/profile.json"
    profile_bytes = profile_result.model_dump_json(indent=2).encode("utf-8")
    ctx.storage.put_file(storage_key, profile_bytes)

    ctx.run.progress = 80
    ctx.db.commit()
    publish_progress(
        ctx.run.id,
        stage="profile",
        progress=80,
        status="running",
        message="Runtime profiling completed successfully",
    )


def stage_bottleneck(ctx: AnalysisContext) -> None:
    """Detect and score performance bottlenecks combining static and runtime evidence."""
    logger.info(f"Running bottleneck stage for repo {ctx.repository.id} run {ctx.run.id}")
    ctx.run.stage = "bottleneck"
    ctx.run.progress = 85
    ctx.db.commit()
    publish_progress(
        ctx.run.id,
        stage="bottleneck",
        progress=85,
        status="running",
        message="Evaluating impact scores and ranking bottlenecks...",
    )

    detector = BottleneckDetector(db=ctx.db, storage=ctx.storage)
    bottlenecks = detector.detect_and_save(
        analysis_run_id=ctx.run.id,
        repository_id=ctx.repository.id,
    )

    ctx.run.progress = 90
    ctx.db.commit()
    publish_progress(
        ctx.run.id,
        stage="bottleneck",
        progress=90,
        status="running",
        message=f"Identified {len(bottlenecks)} candidate bottlenecks",
    )


# Register pipeline stages
registry.register("static", stage_static)
registry.register("structure", stage_structure)
registry.register("profile", stage_profile)
registry.register("bottleneck", stage_bottleneck)


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
