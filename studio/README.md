# SpriteSpatial Studio

Minimal local frontend shell for SpriteSpatial Studio.

Phase 9A is mock-only. It does not connect to the Studio API, run reconstruction, launch Godot, or load real SpriteSpatial meshes yet.

## Install

```bash
npm install
```

## Run

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

- Asset browser with mock `hero` and `hero_side_fixture` assets
- Sprite inspector with raw and semantic overlay mock modes
- Preset controls with local state
- Editable embodiment parameter fields
- Mock validation metrics
- Mock parameter diff summary
- Mock run history
- Three.js placeholder mesh viewer with orbit controls, wireframe toggle, and front/side/back camera buttons

## Not Implemented Yet

- Backend API connection
- Real sprite or mesh loading
- Real run execution
- Persistence
- Authentication
- Godot integration
- Production UI polish
