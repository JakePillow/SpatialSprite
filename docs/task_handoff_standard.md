# SpriteSpatial Task Handoff Standard

Every completed implementation task should produce a Markdown handoff file for the next AI agent or engineer.

## Required Location

Write the handoff into the primary output folder for the task:

```text
outputs/<asset>/<task_output>/AI_AGENT_HANDOFF.md
```

If a task does not produce an asset output folder, write it to:

```text
docs/handoffs/<task_name>_handoff.md
```

## Required Sections

Each handoff must include:

- task name and phase
- current status
- exact output folder
- commands run
- commands deliberately not run
- files added or changed
- primary reports and debug outputs
- key validation metrics
- pass/fail result
- warnings and known caveats
- diagnosis if quality did not improve
- recommended next engineering step
- handoff checklist

## Constraints

The handoff should be factual and should not inflate visual quality. If a task passes structurally but does not improve the image, say that clearly and separate the likely issue by layer:

- semantic issue
- SDF issue
- meshing issue
- render issue

Godot preview commands should be listed only if they were actually run. If Godot was skipped because it was unstable or explicitly avoided, record that directly.
