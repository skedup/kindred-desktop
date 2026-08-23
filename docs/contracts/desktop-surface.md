# macOS 桌面精灵宿主合同

> **状态**：`current / V1 contract baseline`；设计依据见
> [桌面精灵可视化](./2026-08-16-desktop-spirit-visualization.md)，实施状态只在
> [DSV 计划](../plans/2026-08-16-desktop-spirit-visualization-plan.md)维护。

## Purpose

Host the resident's visual presence as a minimal macOS desktop companion while preserving Kindred's read-only authority boundary across Local or explicitly configured direct-Remote deployment and degrading safely when an overlay capability is unavailable.

## ADDED Requirements

### Requirement: Desktop-only renderer surface
The desktop spirit SHALL host the sole V1 `SpiritStage`, visual-state client, bundled-pack resolver, and renderer implementation. The existing browser Web UI MUST NOT render the spirit or select a visual pack.

#### Scenario: Browser Web UI opens
- **WHEN** the user opens the existing Web observation surface
- **THEN** it retains its existing history and state views without hosting a second resident body or pack preference

### Requirement: Ambient desktop window
The macOS desktop spirit SHALL present the resident in a frameless, transparent companion window when the host supports that behavior. Action-bound props and ambience SHALL remain local to the character rather than filling the window with a complete scene. The user SHALL be able to move the spirit. Always-on-top SHALL default on and SHALL be controllable from Settings and the application/context menu. V1 MUST NOT provide click-through; the companion SHALL retain pointer input for its declared drag and shell-menu behavior. Its hit-testable window SHALL use compact bounds, with a 320×540 logical-pixel baseline, and MUST NOT contain unused transparent gutter beyond the extent required by declared motion, decoration, and drag affordance.

#### Scenario: Transparent overlay is supported
- **WHEN** the desktop compositor supports the required transparent-window features
- **THEN** the spirit appears without ordinary browser or application chrome

#### Scenario: User inspects window controls
- **WHEN** the user opens the shell menu in V1
- **THEN** Keep on Top, Settings, Retry observation now, Open Kindred, and Quit are available, while no click-through control is offered

#### Scenario: User changes the window level
- **WHEN** the user disables or re-enables Keep on Top from Settings or a shell menu
- **THEN** the native window level changes immediately and the shell-only preference is restored on the next launch without changing resident state

#### Scenario: User works beside the resident
- **WHEN** the companion is visible over a grid of underlying controls
- **THEN** controls immediately outside the declared compact stage remain clickable and no unused transparent window region intercepts them

### Requirement: macOS feature degradation
Unsupported transparency on a supported macOS host MUST degrade to a compact ordinary window rather than preventing the resident from being viewed. The host SHALL report unavailable features as safe capability flags and MUST NOT simulate unsupported behavior. Linux and Windows desktop packaging are outside V1; an Ubuntu service host remains supported.

#### Scenario: Compositor rejects overlay behavior
- **WHEN** transparency cannot be enabled on the current desktop session
- **THEN** the host keeps the renderer available in a compact window and identifies the unsupported feature without terminating

### Requirement: Narrow configured read-only transport
The packaged desktop WebView SHALL obtain visual state through a narrow Tauri transport rather than direct browser cross-origin requests. Settings SHALL expose one active source selected from Local and Remote profiles. Local SHALL default to `http://127.0.0.1:8787`; Remote SHALL accept an explicitly configured `http` or `https` origin such as `http://ubuntu-host:8787`. A source URL MUST contain no user-info, query, fragment, or non-root path. The host SHALL append `/api/visual-state` and connect only to the persisted active origin. It SHALL permit only plain `GET`, reject per-request URLs or headers, any other path, redirects, unexpected content types, connect attempts over two seconds, total requests over five seconds, and snapshot bodies over 16 KiB. It SHALL return only validated visual state or bounded error results. It MUST NOT enable broad CORS, read SQLite directly, access graph internals, expose generic HTTP, or expose a command channel to the Heart daemon.

#### Scenario: Default desktop connection starts
- **WHEN** the desktop spirit launches with default configuration
- **THEN** Local is active and it polls `http://127.0.0.1:8787/api/visual-state`

#### Scenario: Renderer requests an arbitrary URL
- **WHEN** renderer content attempts to use the transport for a non-visual path, redirect, per-request origin, or caller-selected header
- **THEN** the bridge rejects the request without issuing it

#### Scenario: Snapshot exceeds its bound
- **WHEN** the selected endpoint sends an oversized body, unexpected content type, redirect, or exceeds its timeout
- **THEN** the bridge rejects the response, releases its buffer, and enters bounded retry backoff

#### Scenario: Renderer attempts a mutation
- **WHEN** renderer content attempts to write resident state or invoke a Heart action
- **THEN** the desktop integration provides no such operation and the resident state remains unchanged

### Requirement: Direct Remote observation is explicit operator opt-in
Kindred, OpenClaw, and `kindred-web` MAY run on a separately managed Ubuntu host while the desktop spirit runs on macOS. Web configuration SHALL provide `host` and `port` with loopback `127.0.0.1:8787` defaults; explicit `kindred serve --host/--port` options SHALL override configuration, and managed systemd/launchd Web services SHALL inherit the configured values. The operator MAY bind the existing read-only Web service to a reachable interface and configure that origin directly in the Remote profile. V1 SHALL add no application authentication, credential storage, TLS termination, tunnel management, or OpenClaw-token reuse. A non-loopback bind SHALL print an informational notice that the full read-only Web/API, including relationship, narrative, history, artifact, and revealable intimate surfaces, is reachable without application authentication or transport confidentiality. The operator SHALL own network reachability and MAY provide a trusted network or external HTTPS reverse proxy.

#### Scenario: Remote Ubuntu deployment is connected
- **WHEN** Ubuntu configures `web.host: 0.0.0.0` and `web.port: 8787`, its managed Web service starts, and Settings selects a reachable origin such as `http://ubuntu-host:8787`
- **THEN** the desktop polls the fixed visual path directly without a tunnel or application credential

#### Scenario: Remote endpoint is absent
- **WHEN** Remote is selected but its configured service is unavailable
- **THEN** the desktop reports a bounded connection diagnostic, offers `Retry observation now`, and retries without consulting Local

#### Scenario: Non-loopback Web service starts
- **WHEN** configuration or an explicit CLI override starts `kindred serve` on a non-loopback host
- **THEN** startup identifies the unauthenticated full-Web exposure while continuing to serve

#### Scenario: Remote URL is malformed
- **WHEN** Settings receives an unsupported scheme, user-info, query, fragment, or non-root path
- **THEN** the host rejects the source setting and keeps the prior generation unchanged

### Requirement: First release is observation-only
The first desktop spirit release MUST NOT synthesize resident reactions to clicks, pointer proximity, dragging, or similar shell input. Shell interactions MAY manage the window or open the existing observation/conversation surface, but true resident interaction SHALL require a future Heart-observed event path.

#### Scenario: User clicks or drags the spirit
- **WHEN** the user interacts with the desktop window in the first release
- **THEN** the host performs only its declared shell behavior and does not play a scripted resident reaction or change resident state

### Requirement: V1 pointer behavior is explicit
Primary-button drag on the declared drag region SHALL move the companion window, secondary click SHALL open the shell menu, and primary click, double-click, and hover SHALL produce no resident reaction. V1 MUST NOT pass pointer input through to underlying applications. Cursor styling MUST NOT imply an unavailable resident interaction.

#### Scenario: User single-clicks the resident
- **WHEN** the user clicks without dragging
- **THEN** the character does not react and the committed action motion continues unchanged

#### Scenario: User opens the shell menu
- **WHEN** the user secondary-clicks the declared surface
- **THEN** the host opens shell controls without changing resident state

### Requirement: Locomotion stays inside the companion stage
Action animation MUST NOT autonomously move the operating-system companion window. The `walk` action SHALL animate within the transparent stage; window position SHALL change only through explicit shell behavior such as user dragging or display-topology recovery.

#### Scenario: Resident keeps walking
- **WHEN** the latest committed action remains `walk` across an extended quiet period
- **THEN** the character keeps walking inside the stage while the companion window remains at its configured desktop position

### Requirement: Minimal macOS shell lifecycle
Installing, starting, or quitting the desktop spirit MUST NOT install, start, stop, or restart the Heart daemon or `kindred-web`. V1 SHALL retain an ordinary Dock presence and provide Keep on Top, Settings, Retry observation now, Open Kindred, and Quit through its application/context menu. It SHALL NOT implement a menu-bar status item, custom Show/Hide lifecycle, close-to-hide behavior, or launch-at-login control. Quitting the surface SHALL leave the resident and observation runtimes unchanged on their Local or Remote host.

#### Scenario: User quits the desktop spirit
- **WHEN** the user selects Quit from the application/context menu
- **THEN** the desktop surface exits while Heart and `kindred-web` continue according to their existing service lifecycle

#### Scenario: Decorated fallback is closed
- **WHEN** the user closes a compact decorated fallback window
- **THEN** the desktop surface exits instead of remaining hidden in the background

### Requirement: Connection health does not redefine resident state
The desktop spirit SHALL keep observation connection health separate from the latest committed resident action. After a snapshot has loaded, a connection interruption SHALL NOT expire or replace that action; the host SHALL continue it in memory, expose only a subtle connection-health indication, retry automatically, and MUST NOT persist the snapshot to disk.

#### Scenario: Observation endpoint becomes unavailable
- **WHEN** the selected snapshot endpoint becomes unavailable after a baseline loaded
- **THEN** the surface continues that source's latest in-memory action, indicates the connection problem separately, periodically retries the selected endpoint, and offers `Retry observation now`

#### Scenario: First launch has no snapshot
- **WHEN** the desktop spirit starts while the selected observation endpoint is unavailable and no snapshot has loaded
- **THEN** the surface shows a neutral disconnected presentation without inventing a resident action

#### Scenario: Local observation service recovers
- **WHEN** the service becomes available after a disconnection
- **THEN** the surface obtains a fresh complete snapshot and resumes from its reported motion instance

#### Scenario: User retries the selected endpoint
- **WHEN** the user repairs network or service reachability and selects `Retry observation now`
- **THEN** the host clears only observation backoff and performs one immediate request to the persisted active origin

#### Scenario: Observation source changes
- **WHEN** Settings switches between Local and Remote, changes the active profile's base URL, or the unchanged endpoint reports a different source id
- **THEN** the host starts a new observation generation, clears the old resident presentation without caching it for fallback, and accepts the new source baseline regardless of its numeric revision

### Requirement: Display topology recovery
The desktop host SHALL persist only shell preferences such as position, active source selection, labels, and validated Local/Remote base URLs, and SHALL clamp a restored window to a currently available display after monitor topology changes. It MUST NOT persist a snapshot or credential for either source.

#### Scenario: Saved display is absent
- **WHEN** the spirit launches after the display containing its saved position has been removed
- **THEN** the spirit is placed fully within the work area of an available display

### Requirement: Privacy and resource-aware lifecycle
The desktop host SHALL stop animation-frame scheduling and visual-state polling when hidden by the operating system, the session is locked, or the system is sleeping. On release-build Apple Silicon acceptance hardware, visible steady-state playback SHALL average at most 5% process CPU over 60 seconds and use at most 250 MiB resident memory; hidden or locked operation SHALL average at most 0.5% process CPU over 60 seconds. While continuously visible and healthy, the host SHALL keep successive request starts within 10–12 seconds and permit only one in-flight request; visibility restoration, resume, source change, or manual retry SHALL atomically cancel/reset the previous timer or generation before one immediate request. The host MUST NOT persist visual-state payloads, intimate state, resident narrative, or source credentials to desktop preference storage.

#### Scenario: Session locks
- **WHEN** the operating-system session becomes locked
- **THEN** the host suspends active rendering and polling and does not display resident details over the lock transition

#### Scenario: Host restarts
- **WHEN** the desktop spirit restarts
- **THEN** it restores only shell preferences and reloads resident state from the selected Local or Remote endpoint without consulting the inactive source

### Requirement: Full observation remains available
The application/context menu and Settings SHALL provide a deliberate action to open Kindred's existing full Web observation surface from the current observation generation's base URL in the user's external browser. The privileged desktop WebView MUST NOT navigate to the full Web application. The desktop spirit itself SHALL remain focused on current presence instead of duplicating history, metrics, episodes, and works views.

#### Scenario: User opens the full observation surface
- **WHEN** the user selects the corresponding shell action
- **THEN** the existing local Web UI opens without changing the current resident state
