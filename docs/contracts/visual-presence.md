# 桌面精灵视觉呈现合同

> **状态**：`current / V1 contract baseline`；设计依据见
> [桌面精灵可视化](./desktop-visualization.md)，实施与发布状态以
> [仓库 README](../../README.md) 和本仓库 CI 为准。

## Purpose

Provide a stable, action-driven, read-only visual representation of the resident's latest committed state for a pre-authored image, frame-animation, or optional Live2D-capable macOS desktop renderer.

## ADDED Requirements

### Requirement: Committed visual-state projection
The system SHALL expose `VisualStateV1` as a discriminated union derived only from committed ticks. Every state SHALL include the visual-contract schema version and an opaque, non-secret stable `source_id` derived from the committed resident installation id. A ready state SHALL identify the newest committed tick from the existing `state_latest` truth source by monotonic tick id, source commit time, stable motion-instance id, and either one valid action semantic or `action: null`. The revision SHALL be the SQLite `tick.id` assigned when T3 successfully inserts the committed tick; the desktop and Web service MUST NOT synthesize it. The `state_latest` view MUST order by descending tick id so the visual projection, Heart `prev_state`, and other core readers deterministically select the same greatest committed revision. An action semantic SHALL be either a registered atomic action or the framework-reserved `settle` step. An empty state SHALL report only schema version, source id, and `status: empty`. The representation MUST NOT include a per-request observation timestamp.

#### Scenario: Latest committed state is available
- **WHEN** the store contains one or more committed ticks
- **THEN** the visual-state snapshot selects the row with the greatest tick id, reports that id as its revision, and reports the row timestamp as `committed_at`

#### Scenario: Tick commit allocates a revision
- **WHEN** T3 inserts and commits a tick successfully
- **THEN** SQLite assigns its autoincrement tick id, the persistence path returns that `lastrowid`, and later visual snapshots report the same value as revision

#### Scenario: Two commits share one timestamp
- **WHEN** two committed rows have the same second-resolution timestamp
- **THEN** the row with the greater tick id is selected regardless of timestamp ties

#### Scenario: No committed state exists
- **WHEN** the store contains no committed tick
- **THEN** the visual-state snapshot reports its source id and `status: empty` without revision, commit time, motion-instance id, or action

#### Scenario: A tick is still executing
- **WHEN** graph or tool execution has begun but its tick has not committed
- **THEN** the visual-state snapshot remains on the latest committed action and exposes no in-flight execution state

### Requirement: Persisted action semantic is the motion input
The visual-state snapshot SHALL use the persisted current step as its action semantic when that step is a registered atomic action or framework-reserved `settle`. A high-level activity name, decision target, free-text description, or capability name MUST NOT be treated as an implicit animation asset key.

#### Scenario: Activity has an atomic step
- **WHEN** the latest committed activity is `dine_out` with current step `eat`
- **THEN** the visual state reports `eat` as its action semantic and does not use `dine_out` to select the motion

#### Scenario: Activity has no atomic step
- **WHEN** the latest committed activity has no current step
- **THEN** the ready visual state reports `action: null`, retains a stable motion-instance id for that contiguous no-step occurrence, and the renderer uses neutral without inventing a canonical `neutral` action

#### Scenario: Quiet tick preserves an existing action
- **WHEN** `act=false` commits after an existing atomic action
- **THEN** the visual state keeps that existing action rather than treating `act=false` as no action

#### Scenario: Source step is malformed or no longer registered
- **WHEN** the persisted step is neither a registered action nor reserved `settle`
- **THEN** the projection reports `action: null` with a safe diagnostic and does not expose the malformed value as an asset key

#### Scenario: Activity has reached the framework terminal step
- **WHEN** the latest committed activity step is `settle`
- **THEN** the visual state reports the reserved `settle` action semantic even though it is not a registered atomic-action package

### Requirement: Stable motion-instance continuity
The visual state SHALL provide a stable motion-instance identifier for the current contiguous occurrence of an action semantic, reserved `settle`, or a no-action step. The identifier SHALL remain unchanged across committed ticks that continue the same occurrence and SHALL change when the resident enters a different action, returns to the same action after another action, or starts a new activity occurrence. Occurrences SHALL be traversed in descending tick-id order rather than timestamp order.

#### Scenario: Action continues across ticks
- **WHEN** consecutive committed ticks continue the same atomic action occurrence
- **THEN** their revisions advance while their motion-instance identifier remains unchanged

#### Scenario: Action is re-entered
- **WHEN** the resident leaves an action and later enters an action with the same name
- **THEN** the later visual state has a different motion-instance identifier so enter animation can play again

### Requirement: Latest committed action remains current
The renderer SHALL continue presenting the latest committed action, including `settle`, until a newer committed tick replaces it. It MUST NOT expire, fade, relabel, or reinterpret the resident action from tick age alone.

#### Scenario: No tick arrives for an extended period
- **WHEN** the latest committed action is `walk` and no newer tick commits
- **THEN** the renderer continues the current `walk` motion regardless of elapsed wall-clock time

#### Scenario: Observation connection is interrupted after a snapshot
- **WHEN** a renderer has loaded a committed action and later loses the observation connection
- **THEN** it keeps that action running in memory while reporting connection health separately and attempting recovery

### Requirement: Snapshot polling observation
The system SHALL provide a read-only visual-state snapshot with `Cache-Control: no-store` and no ETag or conditional-request protocol in V1. A revision SHALL be ordered only within the active observation generation and source id, never globally across Local and Remote sources. The endpoint SHALL require exactly the current supported SQLite schema version; a missing, older, newer, or mid-migration schema SHALL return `503 Service Unavailable` rather than an empty resident state. The desktop SHALL permit exactly one request in flight, poll immediately on launch, visibility restoration, resume, source-setting change, and explicit manual retry, and start successive requests every 10–12 seconds while continuously visible, unlocked, and healthy. It SHALL suspend timers and cancel or generation-ignore in-flight results while hidden, locked, asleep, or changing source. Failure retry SHALL use jittered exponential backoff no shorter than ten seconds and capped at five minutes; a successful `200` SHALL reset normal cadence. The endpoint and polling behavior SHALL never grant database or graph write authority.

#### Scenario: Client starts after ticks already exist
- **WHEN** a renderer performs its first snapshot request after at least one tick has committed
- **THEN** it receives the current complete visual-state representation as the baseline for that source

#### Scenario: Representation is unchanged
- **WHEN** a healthy poll returns the same source id and revision as the current representation
- **THEN** the renderer refreshes connection health and keeps the current motion running without replaying enter behavior

#### Scenario: New tick commits
- **WHEN** a newer tick commits before the next visible-state poll
- **THEN** that request returns the complete newer representation and the renderer accepts its greater revision

#### Scenario: User switches from Local to Remote
- **WHEN** the user selects the directly configured Remote profile after observing Local
- **THEN** the client starts a new observation generation, cancels or invalidates old requests, clears the Local source, revision, and action presentation, and accepts only a fresh Remote response as the new baseline

#### Scenario: Selected Remote endpoint is unavailable
- **WHEN** the user has switched from Local to Remote but the selected endpoint has not produced a valid snapshot
- **THEN** the renderer shows the neutral disconnected presentation and neither displays nor falls back to the prior Local action

#### Scenario: User switches back to Local
- **WHEN** the user selects Local after observing Remote
- **THEN** the client starts another observation generation and fetches a fresh Local baseline rather than reviving a cached Local snapshot

#### Scenario: Same endpoint is retargeted
- **WHEN** a response on the unchanged configured origin reports a source id different from the current source
- **THEN** the client resets to that source and accepts its snapshot even when its revision is numerically lower

#### Scenario: Revision regresses within one source
- **WHEN** a response reports the current source id with a lower revision
- **THEN** the client treats it as a source-regression error, preserves the current in-memory action, and does not reverse the resident motion

#### Scenario: Unsupported database schema is observed
- **WHEN** the read-only Web process opens a database whose schema version is not exactly the current supported version or whose migration is incomplete
- **THEN** the endpoint returns `503 Service Unavailable` and does not report `status: empty`

#### Scenario: Client is hidden or locked
- **WHEN** the companion is hidden, the session locks, or the system sleeps
- **THEN** the desktop issues no periodic visual-state requests until an immediate poll on visibility restoration or resume

#### Scenario: Snapshot request fails
- **WHEN** the selected Local or Remote observation service is unavailable
- **THEN** the renderer preserves any in-memory action and retries with jittered exponential backoff capped at five minutes

### Requirement: Explicit action-to-motion resolution
A visual pack SHALL explicitly map action semantics to motion keys. The renderer MUST NOT assume that an action name equals an asset filename, and a pack SHALL be allowed to map multiple semantically distinct actions to the same motion. A resolved motion MAY include small transparent local props or ambience bound to that motion.

#### Scenario: Actions share one physical motion
- **WHEN** a visual pack maps multiple app-specific actions to a shared `use_phone` motion
- **THEN** each action resolves to that motion without collapsing the actions' runtime semantics

#### Scenario: Action has no explicit mapping
- **WHEN** the current action is absent from the bundled visual pack because of a packaging or manifest defect
- **THEN** the renderer selects the pack's declared neutral fallback and keeps the action available as textual context

#### Scenario: Action has local decoration
- **WHEN** an `eat` motion declares a table edge and food as local decoration
- **THEN** the renderer composes those elements around the transparent character without requiring a complete scene backdrop

#### Scenario: Framework settle step is resolved
- **WHEN** the current action semantic is `settle`
- **THEN** the default pack resolves it to a dedicated quiet closing presentation rather than treating it as unknown or neutral

### Requirement: Default pack distinguishes every built-in action
The bundled default visual pack SHALL be the only pack loaded or selectable in V1 and SHALL provide a dedicated, visually distinguishable motion and local-decoration composition for every built-in registered action and the framework-reserved `settle` step. V1 MUST NOT discover, install, or load a third-party pack. The pack MUST remain within 2,048 files, 256 MiB total unpacked bytes, 16 MiB per file, 4,096 x 4,096 pixels per raster, 600 frames per motion, and 30 frames per second. Implementations MAY reuse lower-level rigs, poses, cycles, or frame material, but normal built-in action resolution MUST NOT silently collapse to the neutral fallback.

#### Scenario: Every built-in action is validated
- **WHEN** the default pack is checked against the registered action inventory plus `settle`
- **THEN** every semantic resolves successfully and each has a distinguishable declared presentation

#### Scenario: Pack internals reuse material
- **WHEN** two built-in action presentations share lower-level animation material
- **THEN** their final motion or local-decoration compositions remain visually distinguishable

### Requirement: Format-independent desktop renderer
The desktop renderer SHALL consume the visual-state and bundled visual-pack contracts behind a transport-independent TypeScript client. It SHALL support a static-image baseline and a frame-animation adapter, SHALL permit an optional Live2D adapter, and SHALL remain usable when the Live2D runtime or model assets are absent. The browser Web UI SHALL NOT host this renderer in V1.

#### Scenario: Static-only pack is selected
- **WHEN** the bundled pack contains only declared static fallback images
- **THEN** the desktop surface renders a valid resident presence without loading an animation runtime

#### Scenario: Optional animation adapter is unavailable
- **WHEN** a pack references an animation format whose adapter cannot initialize
- **THEN** the renderer falls back deterministically to a declared static asset and reports a non-fatal diagnostic shape

### Requirement: Motion playback does not restart on every tick
The renderer SHALL use the motion-instance identifier rather than the tick revision to decide whether to replay enter motion.

#### Scenario: Revision changes during the same action
- **WHEN** a new tick advances the revision while continuing the same motion instance
- **THEN** the renderer keeps the current action loop and does not replay the action's enter sequence

### Requirement: Safe and accessible fallback behavior
Every visual pack SHALL declare a neutral fallback. The renderer SHALL honor reduced-motion preference, SHALL tolerate malformed or missing optional assets without a blank surface, and SHALL avoid fetching undeclared remote assets at runtime.

#### Scenario: Reduced motion is enabled
- **WHEN** the operating environment requests reduced motion
- **THEN** the renderer uses an action-specific static or low-motion pose or prop so every built-in action remains visually distinguishable without relying only on hidden metadata

#### Scenario: Referenced asset is invalid
- **WHEN** the selected motion asset cannot be decoded or validated
- **THEN** the renderer displays the neutral fallback and does not crash the surrounding observation surface

### Requirement: Resident body uses pre-authored assets
The persistent real-time resident body SHALL use pre-authored static, frame-animation, or distribution-approved model assets. The renderer MUST NOT generate a new resident body image for each tick or action update.

#### Scenario: A new action tick commits
- **WHEN** the resident moves to a new action
- **THEN** the renderer selects pre-authored assets from the active visual pack instead of invoking an image-generation provider

#### Scenario: Generated artwork exists elsewhere
- **WHEN** Kindred produces a generated work or episode illustration
- **THEN** that artifact remains outside the real-time resident body pipeline

### Requirement: Stable silent resident identity
The renderer SHALL use the one bundled default visual-pack identity across action, tick, and restart boundaries. The first visual release MUST NOT expose pack selection, select identity from resident state, or play action audio or ambient audio.

#### Scenario: Action changes
- **WHEN** the resident moves from one committed action to another
- **THEN** the same configured resident identity performs the new motion without an automatic skin or body change

#### Scenario: Motion plays
- **WHEN** any built-in action or `settle` presentation is active
- **THEN** the first-release renderer produces no action or ambient sound

### Requirement: Ambient projection is action-only
The action-only ambient visual-state contract MUST omit appearance, expression, scene, intimate clothing, narrative, relationship, and other fields not required to select and continue the current action motion, regardless of whether a separate Web request is authorized to reveal those details.

#### Scenario: Source tick contains layered state
- **WHEN** the latest committed tick contains appearance, mood, bodily, location, weather, narrative, relationship, and bag data
- **THEN** the V1 visual-presence snapshot omits those fields and projects only the action and continuity contract

#### Scenario: Web intimate reveal is enabled
- **WHEN** the current Web configuration or request permits intimate text details
- **THEN** the visual-presence snapshot still excludes those intimate fields from ambient render inputs
