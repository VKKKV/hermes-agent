"""Local cron outcomes remain available without shared metrics."""
from cron import executions

def test_execution_outcome_remains_durable(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    row=executions.create_execution("fixture", source="builtin")
    executions.mark_execution_running(row["id"])
    executions.finish_execution(row["id"], success=True, delivery_outcome="delivered")
    assert not (tmp_path / "telemetry").exists()
