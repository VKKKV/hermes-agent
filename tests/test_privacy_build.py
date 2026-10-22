"""No built-in collection/export survives legacy opt-ins; local execution still works."""
from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest

pytest_plugins = ['tests.agent.test_dsml_recovery']


@pytest.fixture()
def opted_in_home(tmp_path, monkeypatch):
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    (tmp_path / 'config.yaml').write_text(
        'telemetry:\n  shared_metrics:\n    enabled: true\n    send: true\n'
        'monitoring:\n  gateway_health_export:\n    enabled: true\n  export:\n'
        '    otlp:\n      enabled: true\n      endpoint: https://invalid.example.test/v1/traces\n'
        'computer_use:\n  cua_telemetry: true\n',
    )
    yield tmp_path
    assert not (tmp_path / 'telemetry').exists()


def test_old_config_cannot_restore_collection_or_export(opted_in_home):
    from hermes_cli.config_defaults import DEFAULT_CONFIG
    from tui_gateway.contracts.registry import METHODS
    import tui_gateway.contracts  # registers the authoritative method contracts

    for module in ('hermes_cli.main', 'hermes_cli.setup', 'hermes_cli.web_server',
                   'tui_gateway.server', 'gateway.run'):
        importlib.import_module(module)
    assert 'telemetry' not in DEFAULT_CONFIG
    assert 'monitoring' not in DEFAULT_CONFIG
    assert not any(name.startswith('shared_metrics.') for name in METHODS)
    from hermes_cli.web_server import app
    assert not any('/shared-metrics' in getattr(route, 'path', '') for route in app.routes)


def test_retired_builtin_modules_are_not_shipped():
    for name in ('hermes_cli.observability.relay_shared_metrics',
                 'agent.monitoring.otlp_exporter', 'agent.monitoring.gateway_health_export'):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(name)


def test_provider_and_connector_requests_have_no_opt_in_correlation(opted_in_home):
    from tools.managed_gateway_identity import CallRef, connector_headers

    headers = connector_headers(CallRef(turn_id='private-turn', tool_call_id='private-tool'))
    assert headers.keys() == {'User-Agent'}
    assert 'private-' not in str(headers)


def test_third_party_child_env_forces_telemetry_off(opted_in_home, monkeypatch):
    from tools.computer_use.cua_backend import cua_driver_child_env
    from tools.browser_use_cli import _base_subprocess_env
    from tools.environments.vercel_sandbox import _ensure_vercel_sdk

    monkeypatch.setenv('CUA_DRIVER_RS_TELEMETRY_ENABLED', '1')
    monkeypatch.setenv('ANONYMIZED_TELEMETRY', 'true')
    assert cua_driver_child_env()['CUA_DRIVER_RS_TELEMETRY_ENABLED'] == '0'
    assert _base_subprocess_env()['ANONYMIZED_TELEMETRY'] == 'false'
    monkeypatch.setenv('VERCEL_TELEMETRY_DISABLED', '0')
    def ensure_with_disabled_telemetry(name):
        assert os.environ['VERCEL_TELEMETRY_DISABLED'] == '1'

    with patch('pm.ensure_import', side_effect=ensure_with_disabled_telemetry) as ensure:
        _ensure_vercel_sdk()
    ensure.assert_called_once_with('vercel')
    assert os.environ['VERCEL_TELEMETRY_DISABLED'] == '1'


def test_real_turn_retains_answer_and_local_history_without_metrics(opted_in_home, loop_agent, monkeypatch):
    from tests.agent.test_dsml_recovery import _run
    from tests.agent.test_run_agent import _mock_response

    import socket

    attempts = []

    def record_connect(sock, address):
        attempts.append(address)
        raise AssertionError('Unexpected network connection during synthetic turn')

    monkeypatch.setattr(socket.socket, 'connect', record_connect)
    old_data = opted_in_home / 'old-telemetry-sentinel'
    old_data.write_text('keep historical data')
    result = _run(loop_agent, [_mock_response(content='Privacy-preserving answer.')])
    assert result['final_response'] == 'Privacy-preserving answer.'
    assert result['completed']
    assert any(m.get('role') == 'assistant' for m in result['messages'])
    assert old_data.read_text() == 'keep historical data'
    assert attempts == []


def test_general_lifecycle_hooks_still_run(opted_in_home):
    from hermes_cli import lifecycle

    with patch('hermes_cli.plugins.invoke_hook', return_value=['local-result']) as callback:
        assert lifecycle.invoke_hook('on_session_start', session_id='synthetic') == ['local-result']
    callback.assert_called_once_with('on_session_start', session_id='synthetic')
