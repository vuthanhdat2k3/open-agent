# OpenAgent Desktop

Native desktop shell (Tauri v2) for OpenAgent. It's a thin client: on first
launch it asks for your OpenAgent server URL (self-hosted or production),
saves it, then loads the existing Next.js web app in a native window — same
backend, same accounts, just no browser chrome. It does **not** bundle the
backend; point it at a running OpenAgent deployment.

## Dev

```bash
npm install
npm run tauri dev
```

## Build installers

```bash
npm run tauri build
```

Outputs platform installers under `src-tauri/target/release/bundle/`.

## Changing server

Use the "Đổi Server URL..." menu item in the app menu, or delete the app's
config file (`config.json` in the OS app-config dir for
`com.openagent.desktop`) to reset to the setup screen.

## Tests

```bash
cd src-tauri && cargo test
```
