"""cua-driver cannot opt back in via inherited env or legacy config."""
from unittest.mock import patch

import pytest

from tools.computer_use import cua_backend


@pytest.mark.parametrize("config", [
    {}, {"computer_use": {"cua_telemetry": False}}, {"computer_use": {"cua_telemetry": True}},
])
def test_child_forces_off_preserving_other_env(config):
    with patch("hermes_cli.config.load_config", return_value=config):
        base = {"PATH": "/usr/bin", "CUA_DRIVER_RS_TELEMETRY_ENABLED": "1"}
        child = cua_backend.cua_driver_child_env(base)
    assert child["CUA_DRIVER_RS_TELEMETRY_ENABLED"] == "0"
    assert child["PATH"] == base["PATH"]
    assert base["CUA_DRIVER_RS_TELEMETRY_ENABLED"] == "1"
