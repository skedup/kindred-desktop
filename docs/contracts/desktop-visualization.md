# 桌面精灵可视化：观察型常驻身体与交互边界

> **状态**：`current / standalone repository baseline`；桌面宿主、视觉渲染与默认视觉包
> 已由本仓库独立维护。
>
> **需求与进度权威**：
> 本文记录背景、取舍与设计结论；当前实施、构建与发布状态以
> [仓库 README](../../README.md) 和本仓库 CI 为准。
>
> **合同基线**：
> [视觉呈现合同](./visual-presence.md)；
> [macOS 桌面宿主合同](./desktop-surface.md)。
>
> **长期渲染方向**：
> 首版继续使用静态图与逐帧动画；Live2D 保持为独立的后续设计方向。

## 0. 结论

Kindred V1 增加一个 macOS 桌面精灵，让 resident 以最新已提交 action 的静态图或帧动画常驻桌面；
浏览器 Web 继续承担历史、指标、关系与作品等完整观察面。桌面端只观察，不写 canonical state，
也不伪造人物已经感知点击的反馈。

桌面端可观察本机或 Ubuntu 上独立部署的 Kindred。远端直接请求现有只读 Web 服务，不由 Kindred
管理 tunnel、应用认证或 TLS；非 loopback 暴露意味着完整只读 Web/API 都可达，operator 负责可信网络
或外部 HTTPS。V1 使用低频普通轮询，不引入 SSE、WebSocket 或 daemon IPC。

首版固定一个无声 resident 身份，为每个内置 action 和 `settle` 提供可区分表现；Live2D、分层视觉语法、
Windows 桌面、浅层输入反馈与 Heart 可观察的深层互动分别后续立项。Linux 不作为 V1 桌面目标，
但 Ubuntu 是支持的服务宿主。V1 没有 click-through、托盘状态项或 launch-at-login；桌面验收后将
窗口基线收紧为 320×540 logical pixels，并把可持久化的 always-on-top 设为默认开启。

## Context

The Heart daemon is the only writer of canonical resident state. It commits tick snapshots to SQLite in WAL mode, while `kindred.web` opens short-lived read-only connections and projects stable JSON contracts. The packaged Vue application consumes those contracts and currently refreshes the `now` view every 30 seconds.

The persisted `activity.step` normally names the current atomic action (`walk`, `eat`, `sleep`, and so on). It also contains the framework-owned `settle` terminal step, which is intentionally not a registered atomic-action package. Atomic actions were shaped around physical animation semantics, but later design clarified that semantically distinct actions may reuse lower-level physical assets. The visual layer therefore needs an explicit mapping instead of treating step names as asset paths, and it must recognize `settle` as a reserved visual semantic.

The V1 desktop host is macOS 14+ on Apple Silicon. Kindred, OpenClaw, and the read-only observation service may run either on that Mac or on a separately managed Ubuntu host. A remote deployment deliberately binds the existing read-only Web service to a network interface and the desktop requests it directly; V1 adds no tunnel management, application authentication, or TLS termination. The repository already has a Vue/TypeScript frontend toolchain, but the persistent spirit is a desktop-only product surface: the existing browser Web UI remains the full textual observation surface and does not select or render a visual pack. Linux desktop packaging is out of V1 scope; Windows desktop may be considered in a separate later change.

## Goals / Non-Goals

**Goals:**

- Establish a minimal, action-only visual-state contract independent of any art format.
- Treat the framework-owned `settle` step as a dedicated quiet closing presentation rather than an unknown action or neutral fallback.
- Notice committed ticks promptly without coupling the Web process to graph execution.
- Reuse the existing TypeScript frontend toolchain for a desktop-only renderer without adding the spirit stage to browser Web routes.
- Preserve action continuity so a looping motion is not restarted by every tick.
- Support small action-bound props and ambience around a transparent resident body.
- Provide a useful static/frame-animation baseline and an extension seam for optional Live2D rendering.
- Give every currently built-in action a dedicated, visually distinguishable default-pack presentation while allowing implementation-level asset reuse.
- Give the resident an ambient desktop body while preserving the read-only observation boundary.

**Non-Goals:**

- Letting the visual surface direct the Heart, invoke capabilities, or mutate resident state.
- Synthesizing local click, pointer, drag, or touch reactions that pretend to be resident responses; true interaction is a future Heart-observed capability.
- Replacing the full Web views for history, metrics, episodes, relationship, or works.
- Adding application authentication, credential storage, TLS termination, tunnel management, or a multi-user authorization model for direct remote observation.
- Driving the first renderer version from appearance, mood, bodily state, weather, location, or other layered visual grammar.
- Generating a new real-time resident body image for each tick or action.
- Building complete room or scene backdrops around the desktop spirit.
- Selecting the final production art direction or production-fidelity animation library; the default pack still provides functional, distinguishable coverage for every built-in action.
- Bundling a proprietary Live2D runtime before license review.
- Playing action audio or ambient audio in the first release.
- Moving the companion window autonomously to simulate locomotion; `walk` remains an in-stage motion.
- Automatically changing the resident's visual identity as an action, mood, or tick effect, or building a skin marketplace.
- Adding motion semantics to capability packages or deriving action from free-form text.
- Building mobile or browser-extension hosts in this change.
- Rendering the spirit inside the browser Web UI or allowing the Web UI to select a visual pack.
- Shipping Linux or Windows desktop support in V1.
- Supporting click-through behavior in V1.

## Decisions

### 1. Separate the ambient body from the full observation surface

The desktop spirit is the resident's ambient current presence. The Web application remains the place to inspect the resident's history and internals, but it does not host `SpiritStage` and does not select a visual pack. A dedicated desktop entry point uses the existing Vue/TypeScript build toolchain and contains only the stage, connection state, minimal shell preferences, and a path to open the Web UI in the user's external browser.

This avoids squeezing timeline and engineering views into a tiny overlay and avoids adding a second character surface to the browser product. A Web-only product was rejected because browser lifecycle and chrome undermine persistent presence. A fully native renderer was rejected because it would duplicate the existing TypeScript contracts and make image, frame, and Live2D support platform-specific.

The first release observes only. Window dragging, Settings/Retry/Open/Quit commands, and opening the Web/conversation surface are shell behaviors; they do not produce scripted smiles, blushes, or other resident reactions. Interaction is split into explicit authority layers in Decision 9 rather than treating all pointer input as equivalent. The renderer never writes canonical state directly.

### 2. Add a semantic `VisualStateV1` contract

The backend projects a deliberately small discriminated union from committed ticks rather than sending the complete `/now` payload to an ambient window. A committed action has this shape:

```json
{
  "schema_version": 1,
  "source_id": "install:6bd3…",
  "status": "ready",
  "revision": 1842,
  "committed_at": "2026-08-16T14:31:04+08:00",
  "motion_instance_id": "tick:1837",
  "action": { "name": "eat" }
}
```

A committed tick whose `activity.step` is `None` is not the same thing as `act=false`. It means the persisted activity has no atomic action yet, which is valid in bootstrap/seed and compatible historical state. `act=false` merely skips T2 and preserves whichever step was already committed. The no-action shape is therefore explicit:

```json
{
  "schema_version": 1,
  "source_id": "install:6bd3…",
  "status": "ready",
  "revision": 3,
  "committed_at": "2026-08-16T14:31:04+08:00",
  "motion_instance_id": "tick:1",
  "action": null
}
```

The renderer presents its neutral fallback for `action: null`, but `neutral` is never fabricated as a canonical action name. The motion-instance id remains stable across a contiguous run of the same `(activity.started_at, activity.step)` signature, including `step=None`, so quiet ticks do not replay neutral entry behavior. A non-empty but unregistered or malformed source step degrades to the same no-action projection with a safe diagnostic; a valid action whose selected pack lacks a mapping remains an action and follows the pack fallback chain.

`schema_version` versions the visual contract, not the SQLite schema. `source_id` is an opaque, non-secret stable identifier derived from the committed resident installation id; it lets the client distinguish two Kindred databases even when one configured endpoint is retargeted.

When no committed tick exists, the response is `{"schema_version":1,"source_id":"install:6bd3…","status":"empty"}` and omits `revision`, `committed_at`, `motion_instance_id`, and `action`.

`action.name` normally contains a registered atomic-action name; `settle` is the one framework-reserved action semantic in V1. `revision` is not created by the desktop or Web service: it is the SQLite `tick.id` assigned by the `INTEGER PRIMARY KEY AUTOINCREMENT` column when T3 commits a tick, and the successful insert's `lastrowid` is the canonical value. `committed_at` is the source tick timestamp and may be exposed in Settings or accessibility diagnostics as provenance; it never expires or relabels the action. `VisualStateV1` has no per-request observation timestamp. Request timing and connection health are separate client concerns and never become resident status.

The projection contains no appearance, expression, bodily, location, weather, narrative, relationship, bag, address, intimate, or interior fields. The current activity occurrence may be read internally to derive `motion_instance_id`, but it is not a V1 motion-selection input. Optional source fields degrade through the same typed-projection discipline as the existing Web service. Uncommitted graph execution and tool-running state are deliberately absent: until a new tick commits, the renderer continues the latest committed action.

The longer-term visual grammar remains valuable but is intentionally deferred to a later contract change:

```text
motion     = action semantic (atomic action or reserved settle)
variant    = bodily state such as energy or fatigue
expression = mood and affect
props      = outward or environmental context
```

Keeping those axes out of V1 prevents the first implementation from becoming a combinatorial character-compositing system. Sending the complete `/now` response was rejected because it leaks unrelated personal context to a long-lived overlay and couples render assets to unstable text. Resolving the final motion in the backend was also rejected: motion availability belongs to the selected visual pack, not canonical resident state.

### 3. Harden and reuse the canonical latest-state view

`revision` changes on every tick and therefore cannot be used to trigger enter animation. The visual service reads its current row through the existing `state_latest` view, matching the truth source used by Heart for `prev_state`, the daemon, scheduler, and other readers.

Before the visual endpoint ships, `state_latest` is hardened globally from `ORDER BY ts DESC` to `ORDER BY id DESC`. This is a core correctness repair rather than visualization-specific behavior: timestamps have second resolution, while tick ids are monotonic commit revisions, so equal-timestamp commits can otherwise cause the next Heart tick itself to read an older state. The current schema advances directly to v7 and the existing idempotent migration drops and recreates the view, so the change requires no tick rewrite or presentation bookkeeping. There is no production environment, so V1 supports only the current binary with the current schema: old-binary downgrade and forward/backward schema compatibility are explicitly out of scope. A regression test covers two rows with the same timestamp and different ids through `get_state_latest()`.

Because `kindred-web` is read-only and cannot migrate, the visual endpoint checks for exactly the supported database schema before reading `state_latest`. A missing, older, newer, or mid-migration schema returns `503 Service Unavailable`, never `status: empty`; the desktop treats it as connection failure and preserves any already loaded action. Operators run the current `kindred db migrate` before starting Heart and Web after an upgrade.

Starting from that id, the service walks committed ticks backward in `id DESC` order within the current activity occurrence until the `(activity.started_at, activity.step)` signature changes. The oldest revision in that contiguous run becomes `motion_instance_id = "tick:<revision>"`. This also applies to a contiguous `step=None` run.

This makes identity deterministic across Web-service restarts and same-timestamp commits, distinguishes `walk -> eat -> walk`, and avoids adding presentation bookkeeping to canonical `State`. A narrow history helper starts from the `state_latest` id and stops as soon as it finds the boundary; the result is cached per latest tick revision in the Web process. If historical rows are unavailable or malformed, the latest revision becomes the conservative instance identifier.

Hashing only `(activity.started_at, step)` was rejected because returning to the same step in one activity would collide. Persisting `step_started_at` in canonical state remains a possible future optimization, but the visual feature does not justify a Heart graph and state migration initially.

### 4. Use plain snapshot polling in V1

The observation service adds one read-only endpoint: `GET /api/visual-state`. Every successful request returns one complete `VisualStateV1` snapshot with `Cache-Control: no-store`. V1 deliberately omits ETag and conditional `304` behavior: the payload is tiny, while maintaining both an HTTP representation fingerprint and a resident revision creates two change identities without meaningful benefit at a ten-second cadence. A conditional validator would also need a separate cache for every selectable source and MUST NOT survive a source switch. `revision` therefore remains the committed-data sequence number within one active observation generation and `source_id`; it is never compared globally across Local and Remote.

The desktop permits exactly one snapshot request in flight. It polls immediately on launch, operating-system visibility restoration, resume, source-setting change, and the explicit `Retry observation now` shell action. While continuously visible, unlocked, healthy, and not already requesting, successive request starts occur every 10–12 seconds; this makes the accepted roughly-ten-second latency testable without polling faster than once per ten seconds. Operating-system hide, lock, sleep, or source-setting change cancels or generation-invalidates an in-flight result and clears its timer. A failure starts exponential retry with jitter, never sooner than ten seconds and capped at five minutes; a successful `200` resets the normal cadence.

Settings has one explicitly active observation source selected from a Local profile and a Remote profile. Each profile contains a non-authoritative display label and a validated base URL. Local defaults to `http://127.0.0.1:8787`; Remote is configured explicitly, for example `http://ubuntu-host:8787`. The URL is an origin only: V1 accepts `http` or `https`, rejects user-info, query, fragment, and non-root paths, and the host transport always appends the one fixed visual path itself. No resident snapshot or credential is stored in a profile.

The client scopes ordering to an observation generation and `source_id`. Switching the active profile, or changing that profile's base URL, always creates a new generation even if the next endpoint reports the same `source_id` or revision. The transition cancels or invalidates old requests, clears the previous source, revision, and action presentation, and accepts the first valid snapshot as a fresh baseline. It does not display, cache for reuse, or fall back to the Local snapshot while Remote is selected; an unavailable Remote endpoint produces the neutral disconnected presentation until Remote supplies a valid baseline. Switching back to Local also fetches a fresh Local baseline instead of reviving its earlier snapshot. If an unchanged active endpoint is silently retargeted and returns a different `source_id`, the client performs the same reset. Within one generation and source, a greater revision replaces the snapshot; an equal revision refreshes connection health without replaying motion; a lower revision is a source-regression error and leaves the current snapshot intact. Conflicting payloads for one `(schema_version, source_id, revision)` are invalid; a projection change that alters that identity requires a visual-contract schema bump.

The latest committed action remains current until another commit replaces it, regardless of elapsed time. If snapshot reads fail after a renderer has loaded a snapshot, the renderer continues the in-memory action, exposes connection health only through a subtle shell/diagnostic indication, and retries. A fresh client with no snapshot uses a neutral disconnected presentation. No resident snapshot is persisted to disk or HTTP cache.

SSE remains a reasonable future choice when true interaction or sub-second state makes push latency important: it is one-way, keeps one connection open, reconnects automatically, and can resume from an event id. It was rejected for V1 because `kindred-web` is a separate process from Heart and would still have to poll SQLite or gain a new daemon IPC path before it could emit an event. That adds a broker, subscription-race handling, keepalive, bounded queues, stream parsing, and proxy idle-timeout behavior without eliminating database polling. Plain polling is stateless, recovers naturally from ordinary endpoint interruption, and matches the low frequency of action changes; its accepted trade-off is roughly ten seconds of update latency and one small latest-row query per visible interval.

WebSocket was rejected because the V1 data flow is strictly server-to-client and a bidirectional channel would suggest control authority that the surface must not have. Direct daemon-to-Web IPC was rejected because it creates lifecycle coupling and would miss commits made before the Web process starts.

### 5. Resolve actions through a validated visual-pack manifest

The renderer consumes a versioned, local visual pack. A conceptual manifest is:

```yaml
schema_version: 1
id: kindred-default
fallback_motion: neutral
action_motions:
  walk: walk
  eat: eat
  compose: compose
  send: send
  settle: settle
motions:
  neutral:
    renderer: static
    source: neutral.webp
  walk:
    renderer: frames
    source: walk/manifest.json
    backdrop:
      renderer: static
      source: walk/night-street.png
    playback: {enter: once, loop: repeat}
  eat:
    renderer: frames
    source: eat/manifest.json
    decoration:
      renderer: frames
      source: eat/table-and-food.json
  compose:
    renderer: frames
    source: compose/writing.json
  send:
    renderer: frames
    source: send/phone-and-envelope.json
  settle:
    renderer: frames
    source: settle/reflect.json
```

All asset paths are pack-relative, validated against traversal and symlink escape, and loaded only from packaged desktop resources. Runtime network URLs are forbidden. The V1 pack is limited to 2,048 files, 256 MiB total unpacked bytes, 16 MiB per file, 4,096 x 4,096 pixels per raster, 600 frames per motion, and 30 frames per second. Every pack declares a neutral static fallback, and every non-static motion may declare a closer fallback before reaching neutral. The manifest format may support multiple actions resolving to one motion for future packs, but V1 loads exactly one bundled `kindred-default` pack and exposes no selection, installation, discovery, or third-party pack path. The bundled pack gives every currently built-in action and `settle` a dedicated, visually distinguishable motion/decor composition and must not reach neutral during normal operation. Lower-level rigs, poses, cycles, and frame material may still be reused. A motion may declare one static transparent backdrop behind the body plus small transparent local props or ambience above it, such as a table edge, food, rain, footsteps, or a pillow. Backdrops remain bounded to the compact stage and preserve substantial transparency rather than turning the companion into a complete room or poster. Keeping a backdrop static also prevents scenery drift and avoids duplicating it into every body frame.

`settle` resolves to a quiet closing or reflective loop, distinct from neutral. Because latest committed state remains authoritative, this loop may continue indefinitely until a later tick replaces it; the renderer does not invent an automatic transition to idle.

The persistent resident body and its action motions use pre-authored assets. Image generation is never invoked to redraw the real-time body per tick; generated works and episode illustrations remain separate artifacts. The initial in-repository pack provides the one stable V1 resident identity, static fallbacks, and deterministic, distinguishable frame-animation coverage for all current built-in actions plus `settle`. Live2D support is an optional dynamically loaded adapter and is not part of the default critical path. This allows the contract and product experience to be validated before paying the modeling, runtime-size, and licensing cost of a full Live2D character.

Visual-pack V1 contains no audio descriptors and the renderer does not play action or ambient sound.

Embedding renderer type or asset path in each atomic-action manifest was rejected because life assets are semantic runtime inputs while visual packs are replaceable presentation assets with separate licensing and completeness.

### 6. Implement one renderer state machine with pluggable adapters

`SpiritStage` owns connection health, backdrop/body/decoration resolution, transition identity, accessibility settings, and adapter lifecycle. Format adapters implement a narrow lifecycle such as `load`, `enter`, `suspend`, and `dispose`; a later layered-visual change may add context updates.

On a new revision:

1. If `motion_instance_id` is unchanged, keep the current action motion and its backdrop/local decoration running without replaying enter motion.
2. If it changed, resolve the action and its optional static backdrop and local decoration through the pack, cross-fade from the previous adapter, play optional enter motion once, then loop.
3. If loading or playback fails, walk the declared fallback chain and finally render the bundled neutral static asset.

Connection interruption does not run this transition algorithm and does not replace the current adapter. It only changes the orthogonal connection indicator and retry behavior.

The renderer respects `prefers-reduced-motion`, page visibility, desktop lock/sleep signals, and a 30 FPS V1 ceiling. On a release-build Apple Silicon acceptance machine, visible steady-state frame playback is accepted at no more than 5% process CPU averaged over 60 seconds and 250 MiB resident memory; hidden or locked state schedules no animation frames, performs no visual-state polling, and averages no more than 0.5% process CPU over 60 seconds. While continuously visible and healthy, successive request starts remain within the 10–12-second cadence. Renderer diagnostics expose only safe shapes such as adapter name, pack id, source label, missing motion key, and error class; they do not contain resident narrative or local filesystem paths.

### 7. Host the shared entry point in Tauri

The desktop surface uses a small Tauri shell because the Vue/WebGL renderer can be packaged as a local desktop entry point. The browser Web UI does not import or host `SpiritStage`.

The packaged WebView and the observation service have different origins: a Tauri asset origin such as `tauri://localhost` is not the same origin as either a Local or Remote HTTP service. A frontend CSP can permit an attempted request, but it cannot grant server-side CORS permission. V1 therefore does not use browser `fetch` and does not enable broad CORS on the observation service.

Instead, the TypeScript visual client depends on a narrow `getSnapshot()` transport interface. The Tauri side reads the active profile's validated base URL from host-owned Settings, appends `/api/visual-state`, and returns only a validated `VisualStateV1` value or a bounded error shape to the WebView. The renderer cannot supply a per-request URL or header. Changing the persisted Local/Remote base URL goes through the host validator and atomically creates a new observation generation. The display label is non-authoritative, and V1 does not authenticate the configured Remote host.

The transport is not a generic HTTP proxy: it accepts no per-request URL or header, permits only `GET /api/visual-state` on the persisted active origin, rejects redirects and unexpected content types, and exposes no other Web or Heart endpoint to the privileged WebView. Snapshot bodies are limited to 16 KiB; connect timeout is two seconds and total request timeout is five seconds.

For an all-local deployment, the separately installed `kindred-web` service listens at `127.0.0.1:8787`. The existing Web configuration gains `host` and `port` with those defaults; explicit `kindred serve --host/--port` flags override configuration, while the existing systemd/launchd command can inherit configuration without a second service-template path. For split deployment, Kindred and OpenClaw run on Ubuntu and the operator deliberately sets `web.host: 0.0.0.0` (or uses the CLI override); the desktop selects a usable address such as `http://ubuntu-host:8787`, never the wildcard listener address itself. Selecting Remote makes that configured origin the sole active observation source and never reads Local as a fallback. The desktop reports distinct connection-refused/timeout, unexpected-service/content-type, invalid-payload, schema-mismatch, and source-regression diagnostics. `Retry observation now` resets only observation backoff. "Open Kindred" atomically uses the current observation generation's base URL in the external browser.

Direct remote access intentionally reuses the existing full read-only FastAPI service instead of splitting a visual-only listener. This is the smallest V1 deployment: non-loopback `kindred serve --host` remains explicit opt-in and prints an informational notice that the full Web/API is reachable without application authentication or TLS, including relationship, narrative, history, artifact, and revealable intimate surfaces. The project is open source, but runtime resident data is a separate operator choice; V1 accepts that choice rather than adding a security subsystem. Operators who need confidentiality or server authentication supply a trusted network or external HTTPS reverse proxy. Native credentials, Keychain storage, certificate handling, revocation, and tunnel ownership are deferred.

The minimal V1 shell owns only desktop concerns:

- transparent/frameless window configuration;
- always-on-top defaults on and remains a persisted shell-only preference;
- drag regions, saved position, monitor clamping, and scale-factor changes;
- an ordinary Dock presence plus Keep on Top, Settings, Retry observation now, Open Kindred, and Quit through the application/context menu;
- lock, sleep, and resume signals;
- a minimal Tauri v2 capability/ACL, strict content-security policy, and navigation policy for packaged content only.

V1 has no menu-bar status item, close-to-hide lifecycle, launch-at-login control, or custom Show/Hide command. Keep on Top is available from Settings and the application/context menu; a decorated-window fallback treats Close as Quit rather than leaving a hidden background process.

Action locomotion remains inside the renderer stage. In particular, `walk` loops in place and may use local footsteps or slight character displacement, but it never changes the operating-system window position. Only an explicit user drag, saved-geometry restoration, or monitor clamping moves that window.

The shell does not read SQLite and does not spawn, install, start, or stop the Heart daemon or `kindred-web`. Both services are independently deployed and managed on their own host. With an in-memory snapshot, an endpoint interruption leaves the current resident action running and changes only a subtle connection indicator while retrying; without a snapshot, the shell shows neutral disconnected. Changing source settings is different from an interruption: it clears the old resident presentation until the new source supplies a valid baseline. Quitting the shell leaves both Heart and Web services under their existing platform-service lifecycle.

The Tauri bridge exposes only the narrow read-only visual transport and minimal shell commands. It exposes no generic request primitive and no synthetic resident-interaction command in V1. "Open Kindred" launches the active Local or Remote observation UI in the user's external browser; the privileged desktop WebView never navigates to the full application. A future true-interaction change must introduce an explicit approved input event path to the Heart instead of adding renderer-local reactions.

Bundling a Python sidecar inside Tauri was rejected because Kindred already owns service installation and logs, remote deployments cannot be managed as a local sidecar, and a second owner creates duplicate server and upgrade races. Reading SQLite in Rust was rejected because it duplicates projection/privacy logic, cannot cover remote data, and weakens the established Web contract boundary.

### 8. Ship macOS V1 with capability dependencies

macOS 14+ on Apple Silicon is the only V1 desktop acceptance target. Linux desktop support is removed; an Ubuntu service host remains supported, and Windows desktop is a possible later platform change with its own packaging and window-behavior review. The desktop bridge reports actual support for transparency and its ordinary Dock/application-menu lifecycle so failures on a supported Mac degrade safely rather than blocking startup.

Click-through is removed from V1 rather than merely defaulted off. The companion window always receives pointer input for explicit drag and shell-menu behavior. This keeps the observation-only input boundary understandable; a later interaction/window-management change may reconsider it. Post-acceptance desktop use showed that an ordinary window level made the resident disappear behind normal work, so always-on-top now defaults on while remaining user-controllable. The 320×540 logical-pixel stage keeps the interactive footprint narrow, contains no unused transparent gutter beyond declared motion and decoration, and leaves underlying controls immediately outside the stage bounds clickable.

V1 keeps an ordinary Dock icon and application menu but does not implement a menu-bar status item or background hide/recovery state machine. Settings and Quit remain reachable from the application/context menu; a decorated fallback's Close exits the desktop surface. Relaunching the application performs a fresh snapshot request.

Saved geometry is clamped to an available display work area before the window is shown. Preferences store only shell settings such as geometry, active source selection, labels, and Local/Remote base URLs; visual-state payloads are kept in memory and reloaded from the selected endpoint after restart.

### 9. Separate shell control, input feedback, and semantic interaction

The feature boundary has three layers:

```text
shell control        -> changes window/preferences only
input feedback       -> future non-character surface effect only
semantic interaction -> future Heart event -> committed tick -> canonical state
```

The observation-only first release implements only shell control. Primary-button drag on the declared drag region moves the window; primary click, double-click, and hover produce no resident response; and secondary click opens the minimal Settings/Retry/Open/Quit shell menu. The window does not support click-through in V1. Cursor treatment may identify the drag region but must not imply an unavailable character interaction. Opening the full Web surface remains a deliberate application/context-menu command rather than a character gesture.

A later shallow-interaction increment may add deterministic input feedback. It is restricted to non-character presentation such as a pointer ripple, brief light point, or window-outline cue. It must remain silent, must not use gaze, facial expression, body response, emotion symbols, or language, must not replace or restart the committed action motion, is not persisted, and cannot change action, needs, affect, memory, relationship, inventory, or any other resident state. It proves only that the surface received input, not that the resident interpreted it.

Deeper interaction begins only when the surface submits an approved, bounded event to the Heart. Submission itself does not mutate resident state. The Heart may observe or ignore the event, interpret it in context, and affect canonical state only through the same graph validation and committed-tick path used by other life events. This later design must define consent, event vocabulary, wake-up latency, rate limiting, ordering, and privacy before adding a writable ingress.

Direct commands that overwrite a resident's action or interior state, and renderer-local emotional reactions presented as canonical responses, are outside this boundary.

## Risks / Trade-offs

- **[Long-lived atomic action makes continuity-boundary lookup expensive]** -> Cache by latest revision, stop at the first signature change, measure query depth, and only consider canonical `step_started_at` if evidence shows the read-only derivation is insufficient.
- **[Snapshot polling delays a new action]** -> Use a testable 10–12-second healthy cadence, poll immediately on visibility restoration/resume/manual retry, deduplicate within one source generation, and revisit server push when sub-second interaction becomes a product need.
- **[A Remote endpoint is unavailable]** -> Keep the last Remote action in memory after a baseline exists, expose connection health separately, and retry the selected origin with bounded backoff without falling back to Local.
- **[Direct HTTP exposes resident data]** -> Make non-loopback binding explicit, print the unauthenticated/full-Web exposure notice, document trusted-network or external-HTTPS options, and do not imply confidentiality in V1.
- **[Ambient windows expose personal context]** -> Minimize `VisualStateV1`, permanently exclude intimate fields and narrative, avoid on-disk snapshot caches, and suspend on session lock.
- **[Input feedback is mistaken for a real resident response]** -> Keep it outside the character layer and reserve gaze, expression, body response, language, and other semantic reactions for a Heart-observed event followed by a committed tick.
- **[A long-running action looks surprising after a quiet period]** -> Treat the latest commit as authoritative by design; do not invent a second freshness state machine in the renderer, and keep operator connection health separate.
- **[Animation restarts or freezes after reconnect]** -> Separate revision from motion-instance identity, fetch complete idempotent snapshots, and test reconnect across unchanged and changed actions.
- **[Broken or incomplete visual packs blank the UI]** -> Validate manifests and asset paths before activation and require a bundled neutral static fallback.
- **[Live2D runtime size, license, and GPU cost dominate the feature]** -> Keep it optional and dynamically loaded; ship static/frame rendering first and gate distribution on license review.
- **[Desktop overlay capability fails on a supported Mac]** -> Expose capability flags and use a compact-window fallback.
- **[Privileged WebView is exposed to full Web content]** -> Keep packaged navigation local, expose only the fixed visual path on the selected origin, reject redirects, and open the full Web UI in the external browser.

## Migration Plan

1. Directly advance the only supported schema to v7, harden `state_latest` to monotonic tick-id order, update the authoritative state documentation, and require the normal database migration before starting the observation service; then add the projection, schema gate, snapshot endpoint, continuity tests, and privacy tests. Existing `/now` and 30-second refresh behavior remain unchanged.
2. Add the desktop-only TypeScript renderer, validated bundled default pack with local action decoration, and deterministic visual fixtures. Existing browser Web routes remain unchanged.
3. Add the narrow snapshot-polling Tauri transport and minimal macOS desktop host while collecting Local and direct-Remote performance evidence.
4. Update macOS install/release assembly and document both all-local and direct Ubuntu-service-host deployment. Desktop installation does not install or manage Heart or Web services.
5. Leave the Live2D adapter to a separate future change after the hybrid-renderer research gates for runtime licensing,
   model packaging, session lifecycle, three-action quality, and resource ceilings pass review.

The view-definition repair is applied by the existing idempotent schema migration and rewrites no tick data; all server/API changes are additive. Because no production environment exists, only the current v7 binary/schema combination is supported and binary downgrade compatibility is not implemented. Removing or disabling the desktop application leaves canonical resident data and the existing Web observation pages readable under the current binary.

## Open Questions

- Which minimal original character assets will seed the default static/frame visual pack? The pack contract and fallback requirements do not depend on the final art direction.
- What future input vocabulary and wake-up latency should qualify as semantic interaction rather than non-character input feedback? This does not block the observation-only release.
- Will Live2D confirm in writing that Kindred's fixed single-model, no-import AI desktop application is not an
  Expandable Application, and which D-plan notice / Logo / Showcase terms apply? The current free-plan working
  assumption remains provisional, and the optional adapter stays out of the default critical path until this release
  gate is resolved.
- Should a later remote-access change add native authenticated HTTPS or continue treating confidentiality and server authentication as deployment infrastructure? V1 deliberately uses direct operator-configured HTTP/HTTPS without application credentials.
