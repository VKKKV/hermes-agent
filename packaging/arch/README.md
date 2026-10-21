# Arch Linux package for the VKKKV Hermes fork

This recipe builds Hermes from a checksum-pinned source commit in
[VKKKV/hermes-agent](https://github.com/VKKKV/hermes-agent), not by modifying or
repacking an installed pacman payload. The maintenance branch is `kita/arch-dsml`;
upstream `main` remains separate. The initial baseline is upstream `v0.22.2`.

## Build and install

Build as an ordinary user on an up-to-date Arch Linux x86_64 host. The declared
runtime dependencies must already be installed, including the AUR `agent-browser`
(or a package providing it). Building also needs Arch's `base-devel`, Python 3.14,
Node.js >=22.22, npm, uv and cmake. The dependency versions in upstream's
`uv.lock` and `package-lock.json` are retained. Network access is needed for the
source archive, npm and Python dependencies; Python runtime downloads are disabled.
The venv is built using Arch's system Python and is relocatable.

```sh
cd packaging/arch
makepkg --noconfirm
```

`makepkg` does not install the resulting package. In a separately authorized
privileged terminal, install the exact generated file:

```sh
pacman -U /absolute/path/to/hermes-agent-0.22.2-3-x86_64.pkg.tar.zst
pacman -Q hermes-agent
hermes --version
```

The package retains the name `hermes-agent`, `/usr/bin/hermes` launcher,
`/opt/hermes-agent` application tree, system-browser preference, and a read-only
PM tool store pointing to Arch binaries. It replaces the AUR package via pacman;
it does not add an alternative launcher to PATH or modify user configuration.
The displayed version is `0.22.2+kita.dsml`, with the exact source commit recorded
in `/opt/hermes-agent/install-stamp.json`. It does not enable background review.

Allow old workers to finish and exit their processes before replacing the package,
then start a fresh process. `/new` alone does not reload Python modules. No service
or worker is automatically stopped or restarted by this recipe.

For rollback, retain the previously installed package archive and install it with
`pacman -U /absolute/path/to/the/old.pkg.tar.zst`, then start fresh processes.
A later AUR/upstream update may replace this fork package; no automatic pin or
system-wide pacman configuration is installed.

For an offline smoke test of the extracted package without accidentally using
an existing `/opt/hermes-agent`, run the bundled venv with `-S` and the validator:

```sh
check=$(mktemp -d "$TMPDIR/hermes-package-check.XXXXXX")
bsdtar -xf hermes-agent-0.22.2-3-x86_64.pkg.tar.zst -C "$check"
"$check/opt/hermes-agent/venv/bin/python" -S validate-package.py "$check/opt/hermes-agent"
```

`-S` avoids evaluating the packaged absolute `hermes.pth`; the validator adds
only the extracted application and bundled dependency paths. This exercises the
real conversation entry with synthetic responses and does not contact an LLM.

## Scope and verification

The fork adds conservative handling of complete-message DSML leaks: fullwidth or
ASCII pipes, doubled pipes, spaces and orphan `calls`/`invoke`/`parameter` closers.
A no-tool DSML attempt is discarded and goes through existing bounded recovery,
not converted into executable tool calls. Alternate reasoning/stream/housekeeping
sources are guarded before promotion; malformed length fragments are not replayed
or stitched into a later answer. Inline closer mentions and hyphenated non-tags
remain ordinary prose. Repeated unclosed openers do not rescan every suffix.
CLI/history sanitization shares the patterns. Existing provider fallback policy
is unchanged.

This is not a provider parser repair or an incremental streaming filter. A live
stream may transiently display a fragment before the complete response is handled.
Explicit DSML examples may also be stripped. Do not infer live background-review
availability from offline response fixtures; keep it disabled until separately
validated against the intended provider in a controlled new process.

No compression branch or database persistence behavior is changed: on this
baseline the healthy post-tool prune path is reachable, while its persistence
still archives/reinserts rows. The in-place rewrite merged upstream is not part
of this baseline.

Run scoped source regressions with the canonical runner and a prepared test
interpreter containing the locked runtime/test dependencies:

```sh
HERMES_PYTHON=/absolute/path/to/test-env/bin/python scripts/run_tests.sh -j 1 \
  tests/agent/test_dsml_recovery.py \
  tests/agent/test_empty_response_guard.py \
  tests/agent/test_empty_response_recovery_persistence.py \
  tests/agent/test_proactive_prune_loop_wiring.py \
  tests/agent/test_anthropic_truncation_continuation.py \
  tests/agent/test_truncated_tool_call_boost.py -q --tb=short
```

The scoped canonical runner passed 78 tests across six files on the pinned runtime
source, including the two adjacent truncation suites. Six added caller regressions
failed before the follow-up repair and passed afterward. The recipe's `check()`
also validates the bundled Web/TUI and representative optional dependency imports
under an isolated `HERMES_HOME`. Test fixtures in the
fork are synthetic: no production conversations, credentials, profiles or state
database are distributed.

## Maintaining the pin

1. Commit and push the reviewed runtime changes with tests to the fork first.
2. Set `_commit` and `_commit_date` to that immutable source commit and increment
   `pkgrel` (or rebase and update `pkgver` for an explicitly chosen new release).
3. Download the exact fork commit archive; update its SHA256 in `sha256sums`.
   Never use `SKIP` or a moving branch URL for the source.
4. Rebuild in a new `BUILDDIR` and validate the extracted package, not merely the
   developer checkout. Verify its source files and stamp against the pinned
   commit, imports against its bundled venv, and Web/TUI entry artifacts.
5. Commit the recipe separately. Its source pin intentionally points to the prior
   runtime commit rather than to the recipe's own commit (no self-referential SHA).

This packaging is adapted from AUR `hermes-agent` 0.22.2, AUR revision
`3c5a6413fc61cca3178e135caf5111413b77b197`, by Youcef and Evert. The PM store
helper and interpreter preservation patch retain the AUR attribution to jabla's
`hermes-agent-bin`. Hermes and these adaptations are distributed under MIT.
