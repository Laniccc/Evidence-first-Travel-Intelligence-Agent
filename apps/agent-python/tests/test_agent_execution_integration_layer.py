from app.execution import EntityResolutionAgent, RetryPolicy, TimeoutPolicy
from app.execution.tool_executor import ActionExecutor, ToolExecutor
from app.execution.tool_registry import TravelToolRegistry
from app.evidence.evidence_model import Evidence
from app.integrations.catalog import PlaceCatalogService
from app.integrations.java_gateway import JavaToolGatewayClient, evidence_list_from_gateway
from app.integrations.llm import LLMClient
from app.integrations.storage import ToolCache


def test_execution_facades_export_current_runtime_surfaces():
    assert ToolExecutor is ActionExecutor
    assert TravelToolRegistry is not None
    assert EntityResolutionAgent is not None


def test_execution_runtime_policies_are_available():
    retry_policy = RetryPolicy(max_attempts=3)
    timeout_policy = TimeoutPolicy(default_seconds=10.0, by_tool={"search_mcp": 4.5})

    assert retry_policy.should_retry("timeout", attempt=2)
    assert not retry_policy.should_retry("timeout", attempt=3)
    assert not retry_policy.should_retry("permanent_error", attempt=1)
    assert timeout_policy.seconds_for("search_mcp") == 4.5
    assert timeout_policy.seconds_for("unknown") == 10.0


def test_integration_facades_export_current_external_surfaces():
    assert JavaToolGatewayClient is not None
    assert LLMClient is not None
    assert PlaceCatalogService is not None
    assert ToolCache is not None


def test_java_gateway_converter_builds_final_evidence_models():
    evidence = evidence_list_from_gateway(
        [
            {
                "source_name": "Official source",
                "source_type": "official",
                "source_url": "https://example.test/source",
                "country": "Japan",
                "claims": [{"claim_type": "opening_hours", "value": "09:00-17:00"}],
            }
        ]
    )

    assert len(evidence) == 1
    assert isinstance(evidence[0], Evidence)
    assert evidence[0].__class__.__module__ == "app.evidence.evidence_model"
