# Build verification: 0.22.2-3

Artifact: `hermes-agent-0.22.2-3-x86_64.pkg.tar.zst`
Runtime source: `ac8235dce42bc11a7d854161a9fee6e4e6a38d35` on
`https://github.com/VKKKV/hermes-agent/tree/kita/arch-dsml`.
Source baseline: upstream `v0.22.2` / `d923a5eb487a17c0a68801bba9ef0f56c81040a8`.
The recipe is intentionally committed after its runtime source pin.

Verified on Arch Linux x86_64 with system Python 3.14.8, Node.js 26.12.0,
npm 12.2.1 and uv 0.13.4:

- Signed runtime commits verified locally and pushed to the fork.
- Canonical `scripts/run_tests.sh -j 1`: 78 passed, 0 failed across 6 scoped files.
  This is not the entire upstream test suite.
- Six follow-up caller regressions were observed failing before repair; all passed
  afterward. These cover reasoning promotion, stream/prior-housekeeping fallback,
  length-fragment stitching, inline closer prose and non-tag name boundaries.
- Repeated-opener regex probe (2,000 attribute-bearing openers): old ~2.76s,
  repaired ~0.00075s on the test host. The maintained test uses a generous bound.
- `makepkg --noconfirm`: exit 0; source and helper SHA256 checks passed; Web/TUI
  compiled; Python dependencies prepared from `uv.lock`; `check()` passed.
- Final package extracted into an isolated directory. Its four changed runtime
  files were byte-identical to the pinned fork commit; launcher byte-identical
  to the previously installed AUR launcher. The AUR interpreter-preservation
  packaging patch is applied separately and retained in the recipe.
- Extracted venv invoked with `python -S`, bypassing the absolute packaged `.pth`
  so no old `/opt/hermes-agent` could satisfy imports. Seven real conversation-loop
  fixture cases passed, using only synthetic API responses; no leaked text
  executed as a tool. Bundled dependency imports, Web/TUI, sanitizers and stamp
  checks passed.
- Extracted CLI smoke reports `v0.22.2+kita.dsml`, commit `ac8235dc`.
- System package, model/provider configuration and active workers were not changed.

Package SHA256:
`91e2d0caa3fc49e3e1545509c4f5d5937d3e5f915307e1d37124f6b641c2e793`

The hash identifies this built artifact, not a guarantee of bit-for-bit reproducible
future rebuilds: dependency native builds, generated assets and build timestamps
may differ. Source and dependency locks remain pinned.

Known packaging warning: upstream's Web freshness metadata `hermes-build.json`
records the build-time `web/public` input directory under `$srcdir`. This is
provenance metadata, not the application launcher or runtime import path; the
relocated CLI and Web/TUI artifact checks passed. It was retained rather than
rewriting upstream hashes or expanding the runtime patch scope.

Not verified: privileged pacman installation, live provider parsing, incremental
stream filtering, production background review, service restarts, or long-session
compression improvements. No compression or storage rewrite was included. Keep
background review disabled until a separate controlled online acceptance check.
Earlier `0.22.2-2` and binary-repack candidates are superseded; do not install them.
