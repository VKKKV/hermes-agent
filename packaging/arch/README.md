# Arch source package

This recipe pins upstream v0.22.4 to an immutable commit. It builds source, not
an existing installation, with separate logging, DSML repair, selective stable
maintenance, no-telemetry and new-session model-retention layers.

## Fork behavior

In the classic CLI, `/new` clears the conversation while retaining the active
model, provider and explicit endpoint/credential overrides, without changing
`config.yaml`. Pending `/model --once` selections are cancelled back to their
previous route. Reasoning and `/fast` overrides still reset. The gateway-backed
CLI sends this active route on `session.create`, leaving the ended session alone.
The separate Node TUI, Desktop and messaging gateway commands are unchanged.

Upstream introduced the default-model reset in commit
`47fb20c0bd09c0c1575a635a34145225e8af707d` (PR #67979), first included in
v0.19.0. `new-session-model.patch` intentionally restores route retention.

Built-in Shared Metrics collection, consent, upload queues, sender and UI/RPC
are removed, along with the built-in OTLP exporter and its optional dependency.
Legacy opt-in settings cannot restore deleted code. cua-driver, browser-use,
the Vercel Sandbox SDK and the bundled Photon/Spectrum adapter force their own
telemetry off.

Local token/cost accounting, session history, error logs, watchdogs and gateway
health remain. `hermes monitoring status` reads local state only. NeMo Relay
execution scopes, middleware and explicit plugin hooks remain: user-installed
plugins or exporters are not a network sandbox. Existing user data is untouched.

Stable maintenance is selected from upstream commit
`85d57d956454914a97bcf24b4c8c6e463267ef1e`: dependency updates, sandbox background
startup/workdir and damaged-checkout update recovery. This is not a main merge;
`hermes mcp serve` stays available without the main branch's plugin migration.

The DSML guard never executes serialized tool text. It rejects protocol outside
Markdown code, preserves code in lists and quotes, and classifies continuation
fragments with their prefix. Private reasoning is inspected only when the live
route allows it to become the answer. A truncated raw tool attempt ends as a
retryable incomplete turn rather than requesting an unknown argument tail.
This is a final/replay guard, not a guarantee that no text was already streamed.

## Verify and build

With the project's test environment prepared (see `tests/AGENTS.md`), run from
the repository root:

```sh
scripts/run_tests.sh tests/agent/test_dsml_recovery.py tests/test_privacy_build.py
scripts/run_tests.sh tests/hermes_cli/test_reasoning_command.py tests/hermes_cli/test_gateway_model_switch_cli.py tests/hermes_cli/test_gateway_session_store.py tests/hermes_cli/test_gateway_resume_launch_key.py tests/hermes_cli/test_model_switch_reasoning_reresolve.py
python scripts/check --base HEAD --only health
```

These tests exercise the real conversation loop, storage/replay, legacy opt-ins,
removed exporter entry points and forced third-party settings using synthetic
provider replies. They do not certify an online provider or an installed package.

After a source change, regenerate only the affected patch against its preceding
layer from raw Git diff output; include new files, update SHA256 and bump
`pkgrel`. Keep deletions in `no-telemetry-files.txt` rather than embedding entire
removed collectors in the patches. `prepare()` validates every listed regular
file before removing exactly those source files, never user data.

In a fresh source tree, run `prepare()` in recipe order with `--fuzz=0`. Compare
all maintained source bytes against the intended checkout, accounting only for
the package-only interpreter patch and Git archive line-ending attributes.
Then build without installing from this directory with `makepkg`; `check()`
verifies bundled entry points and selected optional SDK imports. Source checks
are not acceptance of the generated package: independently check its relocated
interpreter, module origins, launchers, Web/TUI assets and runtime fixtures before
installation. Keep the previous package for rollback.
