from __future__ import annotations

import pytest

def _metric(snapshot, name):
    return next(metric for metric in snapshot.metrics if metric.name == name)

def test_execution_projection_is_opaque_bounded_and_content_free():
    from agent.monitoring.cron_health import project_execution_event

    event = project_execution_event(
        {
            "id": "execution-private-id",
            "job_id": "Payroll for alice@example.com and token top-secret-token",
            "source": "builtin",
            "status": "failed",
            "claimed_at": "2026-07-24T12:00:00+00:00",
            "started_at": "2026-07-24T12:00:01+00:00",
            "finished_at": "2026-07-24T12:00:03.250000+00:00",
            "error": "Bearer top-secret-token rejected for alice@example.com",
        },
        delivery_outcome="failed",
    ).to_dict()

    assert event["event"] == "cron_execution"
    assert event["status"] == "failed"
    assert event["job_key"].startswith("sha256:")
    assert len(event["job_key"]) == len("sha256:") + 24
    assert event["duration_ms"] == 2250
    assert event["delivery_outcome"] == "failed"
    assert event["error_class"] == "auth_failed"
    assert "job_id" not in event
    assert "error" not in event
    assert "alice@example.com" not in str(event)
    assert "top-secret-token" not in str(event)

def test_cron_store_writability_is_exported(monkeypatch, tmp_path):
    """A degraded store exports writable=0 with its skipped runs, a cleared one writable=1."""
    import errno
    from agent.monitoring.cron_health import build_cron_health_snapshot
    from cron import store_health
    monkeypatch.setattr(store_health, "_degraded", {})
    monkeypatch.setattr(store_health, "_listener", None)
    monkeypatch.setattr(store_health, "_recovered", {})
    from cron import scheduler_ownership
    monkeypatch.setattr(scheduler_ownership, "_ticked_homes", {})
    store_health.note_unwritable(OSError(errno.ENOSPC, "full"), "x", "advance",
                                 [{"id": "job", "next_run_at": "2026-06-22T12:00:00+00:00"}])
    degraded = build_cron_health_snapshot()
    assert (_metric(degraded, "hermes.cron.store.writable").value,
            _metric(degraded, "hermes.cron.store.skipped_runs").value) == (0, 1)
    store_health._degraded.clear()
    assert _metric(build_cron_health_snapshot(), "hermes.cron.store.writable").value == 1
    # A secondary profile's store (not the exporter's scope) must not read as healthy.
    from cron.scheduler_ownership import register_ticked_homes
    register_ticked_homes([tmp_path / "other"])
    store_health.note_unwritable(OSError(errno.ENOSPC, "full"), "x", "scan", cron_dir=tmp_path / "other" / "cron")
    assert _metric(build_cron_health_snapshot(), "hermes.cron.store.writable").value == 0
    register_ticked_homes([])  # the profile left this gateway: its store no longer counts
    assert _metric(build_cron_health_snapshot(), "hermes.cron.store.writable").value == 1

@pytest.mark.parametrize("message", ["oauth refresh failed", "tokenizer crashed", "HTTP 4015"])
def test_error_classification_avoids_auth_substring_false_positives(message):
    from agent.monitoring.cron_health import classify_cron_error

    assert classify_cron_error(message) == "unknown"

def test_terminal_execution_emission_flushes_and_failures_are_fail_open(monkeypatch):
    from agent.monitoring import cron_health, emitter

    calls = []

    class FakeEmitter:
        def emit(self, event):
            calls.append(("emit", event.to_dict()["status"]))

        def flush(self, timeout):
            calls.append(("flush", timeout))
            raise RuntimeError("collector unavailable")

    monkeypatch.setattr(emitter, "get_emitter", lambda: FakeEmitter())

    cron_health.emit_execution_state(
        {"job_id": "private", "source": "builtin", "status": "completed"}
    )

    assert calls == [("emit", "completed"), ("flush", 1.0)]
