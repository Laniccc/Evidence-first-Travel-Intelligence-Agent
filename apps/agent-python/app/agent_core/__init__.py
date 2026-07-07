"""Agent Core — state-space driven research agent runtime.

Run → Topics → Phases → Artifacts → Evidence → Quality Checks → Jobs
"""

from app.agent_core.state.models import (
    AdoptedFact,
    ArtifactRecord,
    BlockedTool,
    CrossReferenceResult,
    EvidenceGap,
    EvidenceRecord,
    JobRecord,
    PhaseCard,
    PhaseState,
    PhaseToolResult,
    QualityCheckRecord,
    RejectedFact,
    ResearchPlanArtifact,
    ResearchReportArtifact,
    ResearchSubQuestion,
    RunProjection,
    RunState,
    SourceRating,
    ToolVisibility,
    TopicCard,
    TopicDraft,
    TopicState,
    utc_now_iso,
)
from app.agent_core.state.ids import (
    generate_artifact_id,
    generate_check_id,
    generate_evidence_id,
    generate_job_id,
    generate_phase_id,
    generate_run_id,
    generate_topic_id,
)
from app.agent_core.state.lifecycle import (
    ALL_STATUSES,
    FULL_PHASE_ORDER,
    RUN_PHASE_ORDER,
    TRANSITION_MAP,
    validate_transition,
    validate_transition_strict,
    phases_after,
)
from app.agent_core.store import AgentCoreStore
from app.agent_core.memory_store import MemoryAgentStore
from app.agent_core.sqlite_store import SQLiteAgentStore
from app.agent_core.projection import build_run_projection
from app.agent_core.control_tools import (
    ControlToolResult,
    approve_phase,
    reject_artifact,
    rollback_to_phase,
    retry_phase,
    skip_phase,
    mark_phase_failed,
    reconcile_job,
)
from app.agent_core.gate import PipelineGate

__all__ = [
    # Models
    "RunState", "TopicState", "PhaseState", "ArtifactRecord",
    "EvidenceRecord", "QualityCheckRecord", "JobRecord",
    "TopicDraft", "ResearchSubQuestion", "ResearchPlanArtifact",
    "ResearchReportArtifact", "SourceRating", "CrossReferenceResult",
    "PhaseToolResult", "ToolVisibility", "BlockedTool",
    "RunProjection", "TopicCard", "PhaseCard",
    "AdoptedFact", "RejectedFact", "EvidenceGap", "utc_now_iso",
    # IDs
    "generate_run_id", "generate_topic_id", "generate_phase_id",
    "generate_artifact_id", "generate_evidence_id",
    "generate_check_id", "generate_job_id",
    # Lifecycle
    "ALL_STATUSES", "FULL_PHASE_ORDER", "RUN_PHASE_ORDER",
    "TRANSITION_MAP", "validate_transition", "validate_transition_strict",
    "phases_after",
    # Store
    "AgentCoreStore", "MemoryAgentStore", "SQLiteAgentStore",
    # Projection
    "build_run_projection",
    # Control tools
    "ControlToolResult", "approve_phase", "reject_artifact",
    "rollback_to_phase", "retry_phase", "skip_phase",
    "mark_phase_failed", "reconcile_job",
    # Gate
    "PipelineGate",
]
