import json
import logging
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.conversation_compression import _emit_aborted_attempt_telemetry, compress_context
from agent.context_compressor import ContextCompressor


class _TodoStore:
    def format_for_injection(self):
        return ""


class _Agent:
    def __init__(self, compressor):
        self.context_compressor = compressor
        self.session_id = "session-telemetry-test"
        self.platform = "cli"
        self.model = "test/main-model"
        self.provider = "test-provider"
        self.tools = []
        self._compression_feasibility_checked = True
        self.compression_in_place = False
        self._memory_manager = None
        self._session_db = None
        self._todo_store = _TodoStore()
        self._cached_system_prompt = None

    def _emit_status(self, _message):
        pass

    def _emit_warning(self, _message):
        pass

    def _invalidate_system_prompt(self):
        self._cached_system_prompt = None

    def _build_system_prompt(self, system_message):
        return system_message

    def commit_memory_session(self, _messages):
        pass


def _messages(secret_text="TOPSECRET_TRANSCRIPT_TEXT"):
    msgs = [{"role": "system", "content": "system prompt"}]
    for idx in range(10):
        msgs.append({"role": "user", "content": f"user message {idx} {secret_text}"})
        msgs.append({"role": "assistant", "content": f"assistant reply {idx} {secret_text}"})
    return msgs


def _extract_telemetry(caplog):
    records = [
        record.getMessage()
        for record in caplog.records
        if "context compression attempt telemetry:" in record.getMessage()
    ]
    assert len(records) == 1
    return json.loads(records[0].split("context compression attempt telemetry: ", 1)[1])


def test_compression_attempt_telemetry_is_metadata_only(caplog):
    with patch("agent.context_compressor.get_model_context_length", return_value=100_000):
        compressor = ContextCompressor(
            model="test/main-model",
            provider="test-provider",
            threshold_percent=0.50,
            quiet_mode=True,
            config_context_length=100_000,
        )
    compressor.tail_token_budget = 10
    agent = _Agent(compressor)

    with patch.object(compressor, "_generate_summary", return_value="SANITIZED SUMMARY"):
        with caplog.at_level(logging.INFO, logger="agent.conversation_compression"):
            compressed, system_prompt = compress_context(
                agent,
                _messages(),
                "system prompt",
                approx_tokens=75_000,
                force=True,
            )

    assert system_prompt == "system prompt"
    assert compressed is not None
    payload = _extract_telemetry(caplog)

    assert payload["event"] == "compression_attempt"
    assert payload["attempt_id"]
    assert payload["session_id"] == "session-telemetry-test"
    assert payload["trigger_source"] == "manual"
    assert payload["main_model"] == "test/main-model"
    assert payload["main_context_limit"] == 100_000
    assert payload["current_estimated_tokens"] == 75_000
    assert payload["effective_threshold"] == compressor.threshold_tokens
    assert payload["protected_head_tokens"] is not None
    assert payload["protected_tail_tokens"] is not None
    assert payload["middle_window_tokens"] is not None
    assert payload["chunking"] is False
    assert payload["chunk_count"] in {0, 1}
    assert payload["commit_status"] == "committed"
    assert payload["split_status"] == "not_applicable"
    assert payload["fallback_used"] is False
    assert isinstance(payload["total_duration_ms"], int)
    assert isinstance(payload["commit_ms"], int)
    assert payload["queue_wait_ms"] is None
    assert payload["prompt_build_ms"] is None
    assert payload["time_to_first_progress_ms"] is None
    assert payload["summary_generation_ms"] is None

    raw_log = json.dumps(payload)
    assert "TOPSECRET_TRANSCRIPT_TEXT" not in raw_log
    assert "SANITIZED SUMMARY" not in raw_log
    assert "user message" not in raw_log
    assert "assistant reply" not in raw_log


def test_aux_call_telemetry_records_durations_without_content(caplog):
    with patch("agent.context_compressor.get_model_context_length", return_value=100_000):
        compressor = ContextCompressor(
            model="test/main-model",
            provider="test-provider",
            threshold_percent=0.50,
            quiet_mode=True,
            config_context_length=100_000,
        )
    compressor.tail_token_budget = 10
    agent = _Agent(compressor)
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="SANITIZED SUMMARY"))]
    )

    with patch("agent.context_compressor.call_llm", return_value=response):
        with caplog.at_level(logging.INFO, logger="agent.conversation_compression"):
            compress_context(
                agent,
                _messages(),
                "system prompt",
                approx_tokens=75_000,
            )

    payload = _extract_telemetry(caplog)
    assert payload["aux_prompt_tokens"] is not None
    # Current main intentionally omits max_tokens from the aux summary call
    # (the summary budget is prompt-level guidance only), so no output
    # reservation is recorded.
    assert payload["aux_output_reservation"] is None
    assert isinstance(payload["aux_call_duration_ms"], int)
    assert payload["aux_provider"]
    assert payload["aux_model"]

    raw_log = json.dumps(payload)
    assert "TOPSECRET_TRANSCRIPT_TEXT" not in raw_log
    assert "SANITIZED SUMMARY" not in raw_log


def test_aux_call_telemetry_records_content_free_phase_timings():
    with patch("agent.context_compressor.get_model_context_length", return_value=100_000):
        compressor = ContextCompressor(
            model="test/main-model",
            provider="test-provider",
            threshold_percent=0.50,
            quiet_mode=True,
            config_context_length=100_000,
        )
    compressor._begin_compression_telemetry(current_tokens=75_000)

    compressor._record_aux_compression_call(
        prompt_messages=[{"role": "user", "content": "TOPSECRET_TRANSCRIPT_TEXT"}],
        max_tokens=1400,
        duration_ms=22,
        aux_provider="ollama",
        aux_model="qwen3:8b",
        phase_timings={
            "queue_wait_ms": 3,
            "prompt_build_ms": 5,
            "time_to_first_progress_ms": 7,
            "summary_generation_ms": 19,
            "commit_ms": 11,
        },
    )

    payload = compressor._last_compression_telemetry
    assert payload is not None
    assert {key: payload[key] for key in (
        "queue_wait_ms",
        "prompt_build_ms",
        "time_to_first_progress_ms",
        "summary_generation_ms",
        "commit_ms",
    )} == {
        "queue_wait_ms": 3,
        "prompt_build_ms": 5,
        "time_to_first_progress_ms": 7,
        "summary_generation_ms": 19,
        "commit_ms": 11,
    }
    assert "TOPSECRET_TRANSCRIPT_TEXT" not in json.dumps(payload)








def test_in_place_commit_preserves_seeded_telemetry_fields(caplog):
    """#118580: the memory-flush session-end inside the commit must not wipe attempt telemetry."""
    import contextlib
    import os
    import tempfile
    from pathlib import Path

    from agent.conversation_compression import CompressionCommitFence, run_compress_context_with_progress_timeout

    with tempfile.TemporaryDirectory() as tmp:
        from hermes_state import SessionDB
        from run_agent import AIAgent

        db = SessionDB(db_path=Path(tmp) / "t.db")
        sid = "20260920_234956_0c74e527"
        db.create_session(sid, "cli", model="test/model")
        for idx in range(8):
            db.append_message(
                session_id=sid, role="user" if idx % 2 == 0 else "assistant", content=f"msg {idx}",
            )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            agent = AIAgent(
                api_key="test-key", base_url="https://openrouter.ai/api/v1", model="test/model",
                quiet_mode=True, session_db=db, session_id=sid,
                skip_context_files=True, skip_memory=True,
            )
        agent.compression_in_place = True
        agent._compression_feasibility_checked = True
        messages = [
            {"role": "user" if idx % 2 == 0 else "assistant",
             "content": f"turn message {idx} padding " * 20}
            for idx in range(30)
        ]

        def worker(fence):
            return compress_context(
                agent, messages, "system prompt",
                approx_tokens=75_000, force=True, commit_fence=fence,
            )

        with patch.object(agent.context_compressor, "_generate_summary", return_value="SUMMARY"):
            with caplog.at_level(logging.INFO, logger="agent.conversation_compression"):
                run_compress_context_with_progress_timeout(
                    worker=worker, messages=messages, system_prompt_fallback="system prompt",
                    idle_timeout_seconds=30, total_ceiling_seconds=120, fence=CompressionCommitFence(),
                    telemetry_agent=agent, stall_fallback=False,
                )
        with contextlib.suppress(Exception):
            db.close()
    payload = _extract_telemetry(caplog)
    assert payload["commit_status"] == "committed"
    assert payload["split_status"] == "in_place_committed"
    for key in (
        "trigger_source", "main_model", "middle_window_tokens",
        "protected_head_tokens", "protected_tail_tokens",
    ):
        assert key in payload, f"seeded field lost: {key}"
    assert payload["middle_window_tokens"] is not None


def test_an_overlapping_blocked_call_keeps_the_running_attempts_telemetry():
    """A call that stops at the automatic gate must not erase the record of an attempt still summarizing: the
    previous-attempt clear (#118580) happens only once an attempt owns the lease and dispatches its summary."""
    with patch("agent.context_compressor.get_model_context_length", return_value=100_000):
        compressor = ContextCompressor(
            model="test/main-model", provider="test-provider", threshold_percent=0.50, quiet_mode=True,
            config_context_length=100_000,
        )
    running = {"event": "compression_attempt", "attempt_id": "running-attempt", "method": "llm_summary"}
    compressor._last_compression_telemetry = compressor._active_compression_telemetry = running
    compressor._compression_telemetry_seed = {"attempt_id": "running-attempt"}
    compressor._summary_failure_cooldown_until = time.monotonic() + 600
    agent = _Agent(compressor)

    from agent.conversation_compression import compress_context

    with patch.object(type(compressor), "_refresh_durable_guards"):
        compress_context(agent, [{"role": "user", "content": "hi"}] * 4, "sys", approx_tokens=80_000)

    assert compressor._last_compression_telemetry is running
    assert compressor._active_compression_telemetry is running
    assert compressor._compression_telemetry_seed == {"attempt_id": "running-attempt"}


def test_a_lock_contended_call_keeps_the_running_attempts_telemetry(tmp_path):
    """The lock sit-out shares the gate's rule: the holder's record on a shared compressor must survive, and the
    contender logs its own ``lock_contended`` record from its seed."""
    import os

    from hermes_state import SessionDB

    db = SessionDB(db_path=tmp_path / "state.db")
    db.create_session("S", source="cli")
    assert db.try_acquire_compression_lock("S", "winner", ttl_seconds=60)
    with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
        from run_agent import AIAgent

        agent = AIAgent(
            api_key="test-key", base_url="https://openrouter.ai/api/v1", model="test/model", quiet_mode=True,
            session_db=db, session_id="S", skip_context_files=True, skip_memory=True,
        )
    compressor = agent.context_compressor
    running = {"event": "compression_attempt", "attempt_id": "running-attempt", "method": "llm_summary"}
    compressor._last_compression_telemetry = compressor._active_compression_telemetry = running
    try:
        agent._compress_context([{"role": "user", "content": f"m{i}"} for i in range(20)], "sys", force=True)
        assert agent._compression_skipped_due_to_lock
        assert compressor._last_compression_telemetry is running
        assert compressor._active_compression_telemetry is running
    finally:
        agent.close()


def test_pool_saturation_emit_does_not_inherit_previous_attempt_telemetry(caplog):
    """The pool-refusal emit fires before any attempt begins: no previous attempt's numbers ride along."""
    with patch("agent.context_compressor.get_model_context_length", return_value=100_000):
        compressor = ContextCompressor(
            model="test/main-model", provider="test-provider", threshold_percent=0.50, quiet_mode=True,
            config_context_length=100_000,
        )
    compressor.tail_token_budget = 10
    compressor._last_compression_telemetry = {
        "event": "compression_attempt", "attempt_id": "prior-attempt", "session_id": "prior-session",
        "commit_ms": 73, "middle_window_tokens": 2407,
    }
    compressor._active_compression_telemetry = compressor._last_compression_telemetry
    agent = _Agent(compressor)

    from agent.conversation_compression import CompressionCommitFence, run_compress_context_with_progress_timeout

    with patch("agent.conversation_compression._try_admit_compression_job", return_value=False):
        with caplog.at_level(logging.INFO, logger="agent.conversation_compression"):
            run_compress_context_with_progress_timeout(
                worker=lambda fence: ([], "system prompt"), messages=[], system_prompt_fallback="system prompt",
                idle_timeout_seconds=30, total_ceiling_seconds=120, fence=CompressionCommitFence(),
                telemetry_agent=agent, stall_fallback=False,
            )

    payload = _extract_telemetry(caplog)
    assert payload["failure_class"] == "pool_saturated"
    assert payload["session_id"] == "session-telemetry-test"
    assert payload.get("commit_ms") is None
    assert payload.get("middle_window_tokens") is None


def test_late_unwinding_attempt_keeps_its_own_identity_after_a_newer_attempt_starts(caplog):
    """A stalled attempt that unwinds after its stall fallback began must log its own attempt id, session
    and trigger, not the newer attempt's (they overwrite the agent's current-attempt fields)."""
    import threading

    with patch("agent.context_compressor.get_model_context_length", return_value=100_000):
        compressor = ContextCompressor(
            model="test/main-model", provider="test-provider", threshold_percent=0.50, quiet_mode=True,
            config_context_length=100_000,
        )
    compressor.tail_token_budget = 10
    agent = _Agent(compressor)
    agent.session_id = "session-A"
    stalled, release = threading.Event(), threading.Event()
    calls = []

    def _summary(*_args, **_kwargs):
        calls.append(None)
        if len(calls) == 1:
            stalled.set()
            release.wait(10)
        return "SANITIZED SUMMARY"

    with patch.object(compressor, "_generate_summary", side_effect=_summary):
        with caplog.at_level(logging.INFO, logger="agent.conversation_compression"):
            first = threading.Thread(
                target=compress_context, args=(agent, _messages(), "system prompt"),
                kwargs={"approx_tokens": 80_000, "trigger": "pre_api"},
            )
            first.start()
            assert stalled.wait(10)
            agent.session_id = "session-B"
            compress_context(agent, _messages(), "system prompt", approx_tokens=80_000, trigger="post_tool")
            release.set()
            first.join(10)

    records = [
        json.loads(record.getMessage().split("context compression attempt telemetry: ", 1)[1])
        for record in caplog.records
        if "context compression attempt telemetry:" in record.getMessage()
    ]
    by_trigger = {payload["trigger_source"]: payload for payload in records}
    assert len(records) == 2 and set(by_trigger) == {"pre_api", "post_tool"}
    assert by_trigger["pre_api"]["session_id"] == "session-A"
    assert by_trigger["post_tool"]["session_id"] == "session-B"
    assert by_trigger["pre_api"]["attempt_id"] != by_trigger["post_tool"]["attempt_id"]
