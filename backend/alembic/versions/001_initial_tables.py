"""initial tables

Revision ID: 001_initial_tables
Revises: 
Create Date: 2026-11-15 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_initial_tables"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # 2. projects
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"], unique=False)

    # 3. repositories
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_label", sa.String(length=100), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="uploaded"),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_loc", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_repositories_project_id"), "repositories", ["project_id"], unique=False)

    # 4. files
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("repository_id", sa.String(length=36), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=False, server_default="python"),
        sa.Column("loc", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_files_repository_id"), "files", ["repository_id"], unique=False)

    # 5. functions
    op.create_table(
        "functions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("file_id", sa.String(length=36), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository_id", sa.String(length=36), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("qualified_name", sa.String(length=500), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("lineno", sa.Integer(), nullable=False),
        sa.Column("end_lineno", sa.Integer(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("complexity_class", sa.String(length=50), nullable=True),
        sa.Column("complexity_rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loop_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_recursion", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("patterns", sa.JSON(), nullable=True),
        sa.Column("severity", sa.String(length=50), nullable=False, server_default="LOW"),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_functions_file_id"), "functions", ["file_id"], unique=False)
    op.create_index(op.f("ix_functions_repository_id"), "functions", ["repository_id"], unique=False)

    # 6. analysis_runs
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("repository_id", sa.String(length=36), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("workload_spec", sa.JSON(), nullable=True),
        sa.Column("workload_hash", sa.String(length=64), nullable=True),
        sa.Column("environment", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_analysis_runs_repository_id"), "analysis_runs", ["repository_id"], unique=False)
    op.create_index(op.f("ix_analysis_runs_requested_by"), "analysis_runs", ["requested_by"], unique=False)

    # 7. bottlenecks
    op.create_table(
        "bottlenecks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("analysis_run_id", sa.String(length=36), sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("function_id", sa.String(length=36), sa.ForeignKey("functions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("static_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("runtime_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("runtime_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("memory_peak_kb", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("impact_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_bottlenecks_analysis_run_id"), "bottlenecks", ["analysis_run_id"], unique=False)
    op.create_index(op.f("ix_bottlenecks_function_id"), "bottlenecks", ["function_id"], unique=False)

    # 8. recommendations
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("bottleneck_id", sa.String(length=36), sa.ForeignKey("bottlenecks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("current_algorithm", sa.String(length=100), nullable=False),
        sa.Column("recommended_algorithm", sa.String(length=100), nullable=False),
        sa.Column("alternatives", sa.JSON(), nullable=True),
        sa.Column("expected_complexity", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("feature_importance", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="rules"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_recommendations_bottleneck_id"), "recommendations", ["bottleneck_id"], unique=True)

    # 9. optimizations
    op.create_table(
        "optimizations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("recommendation_id", sa.String(length=36), sa.ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False, server_default="template"),
        sa.Column("template_id", sa.String(length=100), nullable=True),
        sa.Column("candidate_code", sa.Text(), nullable=True),
        sa.Column("patch", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="generated"),
        sa.Column("decision", sa.String(length=50), nullable=True),
        sa.Column("decision_reason", sa.JSON(), nullable=True),
        sa.Column("human_review", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_optimizations_recommendation_id"), "optimizations", ["recommendation_id"], unique=False)

    # 10. benchmark_runs
    op.create_table(
        "benchmark_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("optimization_id", sa.String(length=36), sa.ForeignKey("optimizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("workload", sa.JSON(), nullable=True),
        sa.Column("environment", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_benchmark_runs_optimization_id"), "benchmark_runs", ["optimization_id"], unique=False)

    # 11. benchmark_results
    op.create_table(
        "benchmark_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("benchmark_run_id", sa.String(length=36), sa.ForeignKey("benchmark_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant", sa.String(length=50), nullable=False),
        sa.Column("size_n", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_benchmark_results_benchmark_run_id"), "benchmark_results", ["benchmark_run_id"], unique=False)

    # 12. test_results
    op.create_table(
        "test_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("benchmark_run_id", sa.String(length=36), sa.ForeignKey("benchmark_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_test_results_benchmark_run_id"), "test_results", ["benchmark_run_id"], unique=False)

    # 13. audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("test_results")
    op.drop_table("benchmark_results")
    op.drop_table("benchmark_runs")
    op.drop_table("optimizations")
    op.drop_table("recommendations")
    op.drop_table("bottlenecks")
    op.drop_table("analysis_runs")
    op.drop_table("functions")
    op.drop_table("files")
    op.drop_table("repositories")
    op.drop_table("projects")
    op.drop_table("users")
