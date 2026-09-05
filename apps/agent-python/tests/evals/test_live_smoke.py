import json
from evals import live_smoke


def test_live_smoke_needs_explicit_consent_before_loading_credentials(tmp_path, monkeypatch):
    def forbidden():
        raise AssertionError("must not inspect credentials without live consent")
    monkeypatch.setattr(live_smoke, "load_settings", forbidden)
    report = tmp_path / "smoke.json"
    assert live_smoke.main(["--report", str(report)]) == 2
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["status"] == "not_run" and result["reason"] == "live_consent_required"
    assert result["tool_calls"] == result["llm_calls"] == 0


def test_live_smoke_requires_retention_consent_and_credentials(tmp_path, monkeypatch):
    from app.config import Settings
    monkeypatch.setattr(live_smoke, "load_settings", lambda: Settings(_env_file=None,
        anthropic_api_key=None, deepseek_api_key=None, baidu_map_ak=None))
    report = tmp_path / "missing.json"
    assert live_smoke.main(["--allow-live", "--report", str(report)]) == 2
    assert json.loads(report.read_text())["reason"] == "data_retention_consent_required"
    assert live_smoke.main(["--allow-live", "--allow-data-retention", "--report", str(report)]) == 2
    assert json.loads(report.read_text())["status"] == "blocked"


async def test_call_budget_prevents_invocation_not_just_records_it():
    import pytest
    calls = []
    async def target(*args, **kwargs):
        calls.append(1)
        return "ok"
    bounded = live_smoke.BoundedCall(target, limit=1)
    assert await bounded() == "ok"
    with pytest.raises(RuntimeError, match="smoke_call_budget_exhausted"):
        await bounded()
    assert bounded.count == len(calls) == 1


def test_missing_embedding_records_blocked_not_fake_metrics(tmp_path, monkeypatch):
    from evals import runner
    def unavailable(**kwargs):
        raise RuntimeError("private-provider-error")
    monkeypatch.setattr(runner, "_environment", unavailable)
    target = tmp_path / "semantic.json"
    assert runner.main(["--suite", "retrieval", "--profile", "real-embedding", "--report", str(target)]) == 2
    data = json.loads(target.read_text())
    assert data["status"] == "blocked" and data["profile"] == "real-embedding"
    assert "metrics" not in data and "private" not in json.dumps(data)


async def test_smoke_exercises_real_runtime_with_fake_transports_and_retains_no_payload(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app import main as composition
    from evals.closure_runtime import fixture_settings, fixture_transport, parameters
    factory = composition.build_runtime
    calls = []
    monkeypatch.setattr(composition, "build_runtime", lambda config: factory(config,
        llm_http_client=fixture_transport(calls), mcp_parameters=parameters()))
    report = {}
    await live_smoke.run_smoke(fixture_settings(tmp_path), SimpleNamespace(max_llm_calls=4, max_tool_calls=4), report)
    assert report["status"] == "passed" and all(report["checks"].values())
    assert report["llm_calls"] == 3 and report["tool_calls"] == 2
    assert "新建宫门" not in json.dumps(report, ensure_ascii=False)
    assert "fixture-only" not in json.dumps(report)
