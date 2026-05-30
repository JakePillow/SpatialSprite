# SpriteSpatial Phase 9B Lovable Inspection

## Source

Downloaded zip:

```text
C:\Users\jakep\Downloads\spritespatial-src.zip
```

Extracted safely into:

```text
tmp/lovable_spritespatial_src/
```

The live `studio/` folder was not overwritten.

## Detected Framework

The Lovable project is a TanStack Start app:

```text
package name: tanstack_start_ts
runtime: @tanstack/react-start
router: @tanstack/react-router
build config: @lovable.dev/vite-tanstack-config
server entry: src/server.ts
routes: src/routes/
```

It is not a plain Vite SPA.

## Package Manager Expected

The zip includes:

```text
bun.lock
package.json
```

This suggests Bun was the package manager used by Lovable. The local SpriteSpatial Studio currently uses npm with Vite.

## Major Components

Useful SpriteSpatial-specific components were found under:

```text
src/components/spritespatial/
```

Detected components:

```text
AssetBrowser.tsx
Badge.tsx
DiffSummary.tsx
MeshViewer.tsx
Panel.tsx
PresetControls.tsx
RunHistory.tsx
SpriteViewer.tsx
ValidationPanel.tsx
```

The app route is:

```text
src/routes/index.tsx
```

It contains a desktop-style shell with:

```text
top chrome/title bar
mock/live style status badge
three-row editor grid
bottom CRT/status ticker
scanline/vignette overlays
```

## Styling System

Lovable uses Tailwind 4 with CSS-first tokens in:

```text
src/styles.css
```

Visual identity:

```text
dark arcade/Y2K palette
chrome bevels
neon cyan/magenta/lime accents
scanlines
HUD-like typography classes
dense docked panels
compact badges and readouts
```

It also includes a full shadcn/Radix-style component set under:

```text
src/components/ui/
```

## TanStack Start / Cloudflare Notes

The Vite config imports:

```ts
@lovable.dev/vite-tanstack-config
```

The comments state that this config includes:

```text
tanstackStart
viteReact
tailwindcss
tsConfigPaths
nitro build-only using cloudflare as default target
Lovable dev plugins
sandbox detection
```

Because of this, the Lovable runtime should not be adopted wholesale for Phase 9B.

## Merge Strategy

Decision: keep the existing `studio/` Vite SPA runtime and extract only selected visual/design ideas from Lovable.

Kept from Codex Phase 9A:

```text
Vite runtime
React 18
TypeScript setup
Vitest tests
Three.js viewer infrastructure
existing component structure
mock fallback flow
```

Extracted from Lovable:

```text
Y2K/arcade/chrome visual direction
compact title/status bar concept
panel bevel/chrome language
badge styling direction
dense docked layout treatment
scanline/HUD CSS ideas softened for readability
```

Not adopted:

```text
TanStack Start runtime
Cloudflare/Nitro assumptions
React 19 upgrade
Tailwind 4 migration
full shadcn/Radix component stack
Lovable dev plugins
server wrapper/error reporter
```

## Compatibility Assessment

Compatible enough for visual extraction.

Not compatible enough to replace the local Studio runtime without creating unnecessary risk and package churn.

## Risks

- The Lovable dependency tree is much heavier than the current Studio app.
- TanStack Start and Cloudflare/Nitro assumptions do not match the requested local Vite editor shell.
- Tailwind 4 CSS-first setup would require a broader style migration.
- React 19 upgrade is unnecessary for this phase.
- The Lovable look is visually loud; it must be softened so the editor remains readable as an internal tool.

## Conclusion

Use Lovable as a design source, not as the final runtime. The consolidated Phase 9B app should remain a single local Vite frontend under `studio/`, wired to the existing Phase 8D FastAPI backend with mock fallback.
