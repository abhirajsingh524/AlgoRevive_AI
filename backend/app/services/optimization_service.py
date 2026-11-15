"""Optimization Service and Stage Registry according to Contract G2.

Pipeline stages in order:
generate -> validate -> benchmark -> decide -> completed

Phase 6 registers: generate stage only.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.errors import AppException
from app.core.logging import get_logger
from app.engines.optimizer.llm import (
    LLMDisabledError,
    LLMValidationError,
    get_llm_provider,
)
from app.engines.optimizer.templates import (
    CLASS_TO_TEMPLATE,
    PATTERN_TO_TEMPLATE,
    get_template,
)
from app.models.bottleneck import Bottleneck
from app.models.file import File
from app.models.function import Function
from app.models.optimization import Optimization
from app.models.recommendation import Recommendation
from app.services.progress import publish_progress
from app.services.storage import StorageService

logger = get_logger("optimization_service")


class OptimizationContext:
    """Execution context passed through optimization pipeline stages."""

    def __init__(
        self,
        db: Session,
        storage: StorageService,
        optimization: Optimization,
        recommendation: Recommendation,
        bottleneck: Bottleneck,
        function: Function,
        file: File,
    ):
        self.db = db
        self.storage = storage
        self.optimization = optimization
        self.recommendation = recommendation
        self.bottleneck = bottleneck
        self.function = function
        self.file = file
        self.intermediate: Dict[str, Any] = {}


StageHandler = Callable[[OptimizationContext], None]


class OptimizationStageRegistry:
    """Registry for pluggable optimization pipeline stages (Contract G2)."""

    def __init__(self) -> None:
        self._stages: Dict[str, StageHandler] = {}
        self._stage_order: List[str] = [
            "generate",
            "validate",
            "benchmark",
            "decide",
            "completed",
        ]

    def register(self, stage_name: str, handler: StageHandler) -> None:
        """Register a handler for a named stage."""
        if stage_name not in self._stage_order:
            raise ValueError(f"Unknown stage name '{stage_name}' outside Contract G2")
        self._stages[stage_name] = handler

    def get_registered_stages(self) -> List[str]:
        """Return registered stages in pipeline order."""
        return [s for s in self._stage_order if s in self._stages]

    def get_handler(self, stage_name: str) -> Optional[StageHandler]:
        """Retrieve handler for a registered stage."""
        return self._stages.get(stage_name)


# Global stage registry instance
optimization_registry = OptimizationStageRegistry()


def stage_generate(ctx: OptimizationContext) -> None:
    """Generate optimization candidate (Phase 6).

    Generates candidate via deterministic template (Mode A) or LLM synthesis (Mode B).
    Saves candidate.py and patch.diff under contract section I keys.
    Sets status='generated' on success, or 'failed' with a readable error.
    """
    opt = ctx.optimization
    publish_progress(
        opt.id,
        stage="generate",
        progress=10,
        status="running",
        message=f"Starting candidate generation (mode={opt.mode})",
    )

    # 1. Load source code from object storage
    try:
        source_bytes = ctx.storage.get_file(ctx.file.storage_key)
        source_code = source_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to retrieve source file for {ctx.file.storage_key}: {e}")
        opt.status = "failed"
        opt.error = f"Failed to retrieve source code: {e}"
        publish_progress(opt.id, stage="generate", progress=100, status="failed", error=opt.error)
        return

    # 2. Candidate generation by mode
    if opt.mode == "template":
        template_id = opt.template_id

        # Determine default template if not specified
        if not template_id:
            rec_algo = ctx.recommendation.recommended_algorithm
            if rec_algo == "keep_current":
                opt.status = "failed"
                opt.error = "No optimization needed: recommendation is to keep current implementation."
                publish_progress(opt.id, stage="generate", progress=100, status="failed", error=opt.error)
                return

            template_id = CLASS_TO_TEMPLATE.get(rec_algo)
            if not template_id:
                # Check patterns on function or evidence
                patterns = ctx.function.patterns or []
                for p in patterns:
                    pid = p.get("pattern_id") if isinstance(p, dict) else str(p)
                    if pid in PATTERN_TO_TEMPLATE:
                        template_id = PATTERN_TO_TEMPLATE[pid]
                        break

        if not template_id:
            opt.status = "failed"
            opt.error = (
                f"No applicable deterministic template found for algorithm '{ctx.recommendation.recommended_algorithm}'."
            )
            publish_progress(opt.id, stage="generate", progress=100, status="failed", error=opt.error)
            return

        template = get_template(template_id)
        if not template:
            opt.status = "failed"
            opt.error = f"Template '{template_id}' is not recognized."
            publish_progress(opt.id, stage="generate", progress=100, status="failed", error=opt.error)
            return

        opt.template_id = template_id
        publish_progress(
            opt.id,
            stage="generate",
            progress=40,
            status="running",
            message=f"Applying deterministic template {template_id}",
        )

        try:
            res = template.apply(
                source=source_code,
                function_range=(ctx.function.lineno, ctx.function.end_lineno),
            )
        except Exception as e:
            logger.exception(f"Template {template_id} application failed with error: {e}")
            opt.status = "failed"
            opt.error = f"Template application failed: {e}"
            publish_progress(opt.id, stage="generate", progress=100, status="failed", error=opt.error)
            return

        if res is None:
            opt.status = "failed"
            opt.error = f"Preconditions for template {template_id} were not met for function '{ctx.function.name}'."
            publish_progress(opt.id, stage="generate", progress=100, status="failed", error=opt.error)
            return

        # Template successfully generated candidate
        candidate_code = res.candidate_source
        patch = res.patch

        # Contract Section I keys
        candidate_key = f"optimizations/{opt.id}/candidate.py"
        patch_key = f"optimizations/{opt.id}/patch.diff"
        ctx.storage.put_file(candidate_key, candidate_code.encode("utf-8"))
        ctx.storage.put_file(patch_key, patch.encode("utf-8"))

        opt.candidate_code = candidate_code
        opt.patch = patch
        opt.status = "generated"
        opt.error = None
        opt.decision_reason = {
            "rationale": res.rationale,
            "safety_notes": res.safety_notes,
            "changed_lines": res.changed_lines,
        }
        publish_progress(
            opt.id,
            stage="generate",
            progress=100,
            status="generated",
            message="Deterministic template candidate generated successfully",
        )

    elif opt.mode == "llm":
        publish_progress(
            opt.id,
            stage="generate",
            progress=30,
            status="running",
            message="Querying LLM provider for optimization candidate",
        )
        try:
            provider = get_llm_provider()
            evidence = ctx.bottleneck.evidence or {}
            rec_dict = {
                "current_algorithm": ctx.recommendation.current_algorithm,
                "recommended_algorithm": ctx.recommendation.recommended_algorithm,
                "expected_complexity": ctx.recommendation.expected_complexity,
                "reason": ctx.recommendation.reason,
            }
            res = provider.generate(
                source=source_code,
                function_name=ctx.function.name,
                function_range=(ctx.function.lineno, ctx.function.end_lineno),
                evidence=evidence,
                recommendation=rec_dict,
            )

            # Contract Section I keys
            candidate_key = f"optimizations/{opt.id}/candidate.py"
            patch_key = f"optimizations/{opt.id}/patch.diff"
            ctx.storage.put_file(candidate_key, res.candidate_source.encode("utf-8"))
            ctx.storage.put_file(patch_key, res.patch.encode("utf-8"))

            opt.candidate_code = res.candidate_source
            opt.patch = res.patch
            opt.status = "generated"
            opt.error = None
            opt.decision_reason = {
                "rationale": res.rationale,
                "safety_notes": res.safety_notes,
                "changed_lines": res.changed_lines,
            }
            publish_progress(
                opt.id,
                stage="generate",
                progress=100,
                status="generated",
                message="LLM candidate generated successfully",
            )
        except LLMDisabledError as e:
            opt.status = "failed"
            opt.error = str(e)
            publish_progress(opt.id, stage="generate", progress=100, status="failed", error=str(e))
        except LLMValidationError as e:
            opt.status = "failed"
            opt.error = f"LLM output rejected by guards: {e}"
            publish_progress(opt.id, stage="generate", progress=100, status="failed", error=opt.error)
        except Exception as e:
            logger.warning(f"LLM optimization failed: {e}")
            opt.status = "failed"
            opt.error = f"LLM synthesis failed: {e}"
            publish_progress(opt.id, stage="generate", progress=100, status="failed", error=opt.error)

    else:
        opt.status = "failed"
        opt.error = f"Unknown optimization mode '{opt.mode}'. Expected 'template' or 'llm'."
        publish_progress(opt.id, stage="generate", progress=100, status="failed", error=opt.error)


# Register generate stage only (Phase 6 requirement)
optimization_registry.register("generate", stage_generate)


def execute_optimization(
    db: Session,
    storage: StorageService,
    optimization_id: str,
) -> Optimization:
    """Optimization orchestrator executing registered pipeline stages."""
    opt = db.query(Optimization).filter(Optimization.id == optimization_id).first()
    if not opt:
        raise AppException(status_code=404, detail="Optimization not found", code="NOT_FOUND")

    rec = db.query(Recommendation).filter(Recommendation.id == opt.recommendation_id).first()
    if not rec:
        raise AppException(status_code=404, detail="Recommendation not found", code="NOT_FOUND")

    bn = db.query(Bottleneck).filter(Bottleneck.id == rec.bottleneck_id).first()
    if not bn:
        raise AppException(status_code=404, detail="Bottleneck not found", code="NOT_FOUND")

    fn = db.query(Function).filter(Function.id == bn.function_id).first()
    if not fn:
        raise AppException(status_code=404, detail="Function not found", code="NOT_FOUND")

    fl = db.query(File).filter(File.id == fn.file_id).first()
    if not fl:
        raise AppException(status_code=404, detail="File not found", code="NOT_FOUND")

    ctx = OptimizationContext(
        db=db,
        storage=storage,
        optimization=opt,
        recommendation=rec,
        bottleneck=bn,
        function=fn,
        file=fl,
    )

    for stage_name in optimization_registry.get_registered_stages():
        handler = optimization_registry.get_handler(stage_name)
        if handler:
            handler(ctx)
            db.commit()
            if opt.status == "failed":
                break

    return opt


__all__ = [
    "OptimizationContext",
    "OptimizationStageRegistry",
    "execute_optimization",
    "optimization_registry",
    "stage_generate",
]
