---
title: "Gateway Monitoring"
description: "Local gateway health and diagnostics in this privacy fork"
---

# Gateway Monitoring (local only)

This fork removes the OTLP exporter and its optional SDK extra. Legacy
`monitoring.export.otlp` and `monitoring.gateway_health_export` settings do not
start an exporter. `hermes monitoring status` reads local gateway state only.

Local status, gateway logs, redacted diagnostics, process watchdogs and durable
cron execution outcomes remain. Session history and token/cost accounting are
also local features, not an upload queue. Use `hermes status`, `hermes logs`
and `hermes doctor` to diagnose the local installation.

Generic observer hooks and NeMo Relay execution scopes remain for execution and
explicitly installed plugins. A user-provided plugin or Relay exporter may still
perform network I/O; removing built-in telemetry is not a plugin network sandbox.
See [observer hooks](observer-hooks.md) and [middleware](middleware.md).
