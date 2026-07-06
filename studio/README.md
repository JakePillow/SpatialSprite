# SpriteSpatial Studio

Local frontend for SpriteSpatial authoring and inspection workflows.

The Studio runs in LIVE mode when `studio_api` is reachable and falls back to MOCK mode when the backend is unavailable. LIVE mode can browse real sample assets, upload raw sheets, extract view candidates, create assets, apply embodiment presets, start local reconstruction builds, inspect build artifacts, and load renderable mesh JSON outputs.

## Install

```bash
npm install
```

## Run

Start the local API from the repository root:

```bash
python tools/run_studio_api.py
```

Then start the frontend:

```bash
npm run dev
```

Vite serves the app on a local URL, usually:

```text
http://127.0.0.1:5173
```

## Test

```bash
npm run test
```

## Current Scope

- Asset browser backed by `assets/samples` in LIVE mode with MOCK fallback assets
- Source sheet upload, browsing, candidate extraction, and candidate-to-view assignment
- Asset creation from selected front, side, and back candidates
- Embodiment preset application and parameter-diff summaries from the Studio API
- Build-job launch, polling, validation summaries, artifact links, mesh preview, and depth diagnostics
- Three.js mesh viewer with orbit controls, wireframe toggle, and front/side/back camera buttons

## Not Implemented Yet

- Authentication beyond local Studio request headers
- Production persistence or multi-user coordination
- Godot integration
- Production packaging/polish
