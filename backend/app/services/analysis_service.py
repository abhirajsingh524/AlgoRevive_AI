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
from sqlalchemy.orm.attributes import flag_modified

from app.core.errors import AppException
from app.core.logging import get_logger
from app.engines.bottleneck import BottleneckDetector
from app.engines.complexity import ComplexityEstimator
from app.engines.explain import build_why_flagged
from app.engines.profiler import ProfilerEngine, collect_environment_metadata
from app.engines.recommender import RecommendationEngine
from app.engines.static_analyzer import PatternDetector, StaticAnalyzer
from app.engines.structure import CallGraphBuilder, save_call_graph
from app.engines.workload import (
    WorkloadSpec,
    build_feature_vector,
    build_workload_profile,
)
from app.models.analysis_run import AnalysisRun
from app.models.bottleneck import Bottleneck
from app.models.file import File
from app.models.function import Function
from app.models.recommendation import Recommendation
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

    # If no workload spec found, auto-synthesize from detected functions so profiling can run
    if not workload_data:
        funcs = (
            ctx.db.query(Function)
            .filter(Function.repository_id == ctx.repository.id)
            .all()
        )
        if funcs:
            from pathlib import Path
            file_map = {f.id: f.path for f in ctx.db.query(File).filter(File.repository_id == ctx.repository.id).all()}
            entrypoint_specs = []
            for fn in funcs[:5]:
                fpath = file_map.get(fn.file_id, "")
                mod_name = Path(fpath).stem if fpath else "main"
                if fn.name != "<module>" and not fn.name.startswith("__"):
                    arg_specs = []
                    for param in (fn.params or []):
                        pname = param.get("name", "")
                        if pname in ("self", "cls"):
                            continue
                        arg_specs.append({"kind": "int_list", "size_factor": 1.0})
                    entrypoint_specs.append({
                        "function": f"{mod_name}:{fn.name}",
                        "args": arg_specs,
                    })
            if entrypoint_specs:
                workload_data = {
                    "sizes": [100, 500, 1000],
                    "entrypoints": entrypoint_specs,
                    "operation_mix": {"lookup": 0.9, "insert": 0.05, "delete": 0.05},
                    "memory_constraint": "medium",
                    "seed": 42,
                }
                ctx.run.workload_spec = workload_data
                ctx.db.commit()

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
        workload_spec=ctx.run.workload_spec,
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


def stage_workload(ctx: AnalysisContext) -> None:
    """Characterize workload profiles for all identified bottlenecks."""
    logger.info(f"Running workload stage for repo {ctx.repository.id} run {ctx.run.id}")
    ctx.run.stage = "workload"
    ctx.run.progress = 92
    ctx.db.commit()
    publish_progress(
        ctx.run.id,
        stage="workload",
        progress=92,
        status="running",
        message="Deriving workload profiles for bottlenecks...",
    )

    bottlenecks = (
        ctx.db.query(Bottleneck)
        .filter(Bottleneck.analysis_run_id == ctx.run.id)
        .all()
    )

    spec = ctx.run.workload_spec

    for b in bottlenecks:
        fn = ctx.db.query(Function).filter(Function.id == b.function_id).first()
        workload_prof = build_workload_profile(spec=spec, bottleneck=b, function=fn)
        evidence = dict(b.evidence or {})
        evidence["workload"] = workload_prof.to_dict()
        b.evidence = evidence
        fv = build_feature_vector(b, function=fn)
        evidence["features"] = fv.model_dump()
        evidence["features_array"] = fv.to_array()
        why_tree = build_why_flagged(b, function=fn)
        evidence["why_flagged"] = why_tree
        b.evidence = evidence
        flag_modified(b, "evidence")

    ctx.db.commit()
    publish_progress(
        ctx.run.id,
        stage="workload",
        progress=95,
        status="running",
        message=f"Characterized workload for {len(bottlenecks)} bottlenecks",
    )


def stage_recommend(ctx: AnalysisContext) -> None:
    """Execute recommendation engine for detected bottlenecks.

    Generates algorithmic & data structure recommendations, per-feature importances,
    and plain-English explanations. Persists results to recommendations table.
    """
    logger.info(f"Running recommend stage for repo {ctx.repository.id} run {ctx.run.id}")
    ctx.run.stage = "recommend"
    ctx.run.progress = 96
    ctx.db.commit()
    publish_progress(
        ctx.run.id,
        stage="recommend",
        progress=96,
        status="running",
        message="Generating algorithm & data structure recommendations...",
    )

    bottlenecks = (
        ctx.db.query(Bottleneck)
        .filter(Bottleneck.analysis_run_id == ctx.run.id)
        .all()
    )

    for b in bottlenecks:
        fn = ctx.db.query(Function).filter(Function.id == b.function_id).first()
        evidence = dict(b.evidence or {})
        fv = build_feature_vector(b, function=fn)

        # Generate combined recommendation
        comb_rec = RecommendationEngine.recommend(bottleneck=b, features=fv, function=fn)

        # Upsert recommendation in recommendations table
        rec_obj = ctx.db.query(Recommendation).filter(Recommendation.bottleneck_id == b.id).first()
        if not rec_obj:
            rec_obj = Recommendation(
                id=str(uuid.uuid4()),
                bottleneck_id=b.id,
                current_algorithm=comb_rec.current_algorithm,
                recommended_algorithm=comb_rec.recommended_algorithm,
                alternatives=comb_rec.alternatives,
                expected_complexity=comb_rec.expected_complexity,
                confidence=comb_rec.confidence,
                reason=comb_rec.reason,
                feature_importance=comb_rec.feature_importance,
                source=comb_rec.source,
            )
            ctx.db.add(rec_obj)
        else:
            rec_obj.current_algorithm = comb_rec.current_algorithm
            rec_obj.recommended_algorithm = comb_rec.recommended_algorithm
            rec_obj.alternatives = comb_rec.alternatives
            rec_obj.expected_complexity = comb_rec.expected_complexity
            rec_obj.confidence = comb_rec.confidence
            rec_obj.reason = comb_rec.reason
            rec_obj.feature_importance = comb_rec.feature_importance
            rec_obj.source = comb_rec.source

        # Store in bottleneck evidence as well for frontend convenience
        evidence["recommendation"] = {
            "current_algorithm": comb_rec.current_algorithm,
            "recommended_algorithm": comb_rec.recommended_algorithm,
            "expected_complexity": comb_rec.expected_complexity,
            "confidence": comb_rec.confidence,
            "alternatives": comb_rec.alternatives,
            "reason": comb_rec.reason,
            "source": comb_rec.source,
            "data_structure": comb_rec.data_structure.model_dump(),
            "feature_importance": comb_rec.feature_importance,
            "class_probabilities": comb_rec.class_probabilities,
        }
        b.evidence = evidence
        flag_modified(b, "evidence")

    ctx.db.commit()
    publish_progress(
        ctx.run.id,
        stage="recommend",
        progress=98,
        status="running",
        message=f"Generated recommendations for {len(bottlenecks)} bottlenecks",
    )


# Register pipeline stages
registry.register("static", stage_static)
registry.register("structure", stage_structure)
registry.register("profile", stage_profile)
registry.register("bottleneck", stage_bottleneck)
registry.register("workload", stage_workload)
registry.register("recommend", stage_recommend)


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
