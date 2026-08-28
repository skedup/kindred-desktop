# Kindred Desktop

Kindred Desktop is the read-only macOS desktop presence for
[Kindred](https://github.com/skedup/kindred). It observes the separately running Kindred Web
service through `GET /api/visual-state`; it does not read Kindred's database, manage the service,
or write resident state.

This repository owns the Tauri host, desktop renderer, bundled visual pack, approved visual
sources, and deterministic visual-production tools. The server-side VisualState contract remains
authoritative in Kindred and is vendored here under `contracts/kindred/` with an immutable lock.

## Development

Requirements: Node 22.18.0, pnpm 11.7.0, Rust 1.88.0, and macOS 13 or newer for the app host.

```sh
pnpm --dir app install --frozen-lockfile
pnpm --dir app test
pnpm --dir app typecheck
pnpm --dir app build
cargo test --manifest-path app/src-tauri/Cargo.toml --locked
python3 scripts/validate_visual_pack.py visual-packs/kindred-default
```

Run the development app after starting a compatible Kindred Web service:

```sh
pnpm --dir app tauri:dev
```

Installation, Local/Remote connection, and the unsigned development-app boundary are documented in
[`docs/installation.md`](docs/installation.md).

Build the unsigned Apple Silicon development application:

```sh
pnpm --dir app bundle:macos-arm64
```

The visual production sources and commands are documented in
[`tools/visual_pipeline/README.md`](tools/visual_pipeline/README.md).

Active visual work keeps its reasoning and execution steps separate. The current `eat` redesign is
recorded in the [design discussion](docs/discussions/2026-08-27-eat-frame-animation-design.md) and
[implementation plan](docs/plans/2026-08-27-eat-frame-animation-plan.md).

## Scope

The first release supports Apple Silicon macOS only. It intentionally does not include Live2D,
Windows/Linux desktop builds, automatic updates, authentication tunnels, or semantic interaction.

Licensed under Apache-2.0. Asset-specific provenance is recorded alongside the default visual pack
and application icon.
