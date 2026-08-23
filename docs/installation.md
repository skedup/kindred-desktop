# Installation and connection

Kindred Desktop Spirit is an independent, read-only macOS observation surface. It displays the
latest committed Kindred action without reading SQLite or managing the Heart, Mouth host, or
Kindred Web service.

## Supported environment

- Apple Silicon macOS 13 or newer
- Kindred Web on the same Mac or on a separately managed Ubuntu host
- VisualState schema V1
- Static and frame-animation rendering; no Live2D runtime

The application bundle identifier is `dev.kindred.desktop-spirit`.

## Build the development application

Install Node 22.18.0, pnpm 11.7.0, and Rust 1.88.0, then run:

```sh
pnpm --dir app install --frozen-lockfile
pnpm --dir app bundle:macos-arm64
```

The unsigned development application is written to:

```text
app/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Kindred Desktop Spirit.app
```

It is deliberately unsigned and not notarized. On a Mac where you built and reviewed the source,
Control-click the app in Finder and choose Open if Gatekeeper blocks the first launch. Do not
disable Gatekeeper globally.

## Local source

The Local profile requests:

```text
http://127.0.0.1:8787/api/visual-state
```

Start a separately installed, current Kindred Web service before opening the desktop application.
The application remains open and shows a bounded connection error when the service is unavailable.

## Ubuntu source

When Kindred and the Mouth host run on Ubuntu while the desktop application runs on macOS, the
operator may expose the existing Kindred Web service on a reachable interface:

```sh
kindred serve --host 0.0.0.0 --port 8787
```

In the desktop Settings, create and select a Remote profile using the address the Mac can actually
reach, such as `http://ubuntu-host:8787`. Never enter `0.0.0.0` as the client address. You can
check the endpoint from the Mac first:

```sh
curl -i http://ubuntu-host:8787/api/visual-state
```

A non-loopback Kindred Web listener exposes the full read-only Web/API, which may include history,
relationships, narrative, and artifacts. Kindred V1 supplies no application authentication, TLS,
credential storage, or tunnel. Use a trusted network or an operator-managed HTTPS reverse proxy.

## Application controls

The application/context menu provides:

- Settings
- Retry observation now
- Open Kindred
- Keep on Top
- Quit

These controls manage only the desktop shell. They do not change resident state. The window does not
implement click-through or semantic reactions to clicks.

Preferences are stored outside the application at:

```text
~/Library/Application Support/dev.kindred.desktop-spirit/desktop-spirit.json
```

Replacing or removing the `.app` does not delete Kindred data or these preferences.

