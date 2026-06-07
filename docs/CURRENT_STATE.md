# Current State

Last updated: 2026-06-07

## Summary
PixelForge is a PySide6 desktop pixel-art and tileset utility. Source-grounded tools include image import and preview extraction, palette handling, pixel editing, animation editing, tile layout, tileset processing, tileset template generation, and procedural texture generation.

## Current Status
Active development is indicated by recent commits on `main`, including selection copy workflows, transparency keying, palette sampling, and texture generator updates. The `active-lab` category and `active` status are reviewable classifications for Command Center setup.

## Blockers
None.

## Current Decisions
Use `.project-command/project.json` as provisional Command Center V1 project metadata.

Use `docs/CURRENT_STATE.md` as the project pulse for Command Center re-entry.

## Assumptions
The repository should be registered in Command Center as `pixel-forge` / `PixelForge`.

The project is an active personal/lab project unless the owner reclassifies it.

## Known Gaps
Command Center's final manifest schema is not implemented yet, so `.project-command/project.json` is provisional.

No formal task-source file was found during this setup pass.

Palette PNG assets are now tracked under `palettes/`; their color contents were not reviewed during this setup pass.

## Next Actions
Review the `category`, `status`, and `priorityRank` values when registering the project in Command Center.

Update this document after commits or other git state changes made during agent sessions.

## Recent Activity
2026-06-07: Prepared all Command Center setup files and `palettes/` PNG assets for commit and remote push.

2026-06-07: Metadata-only Command Center setup added provisional project manifest, current-state document, and AI-agent guidance.

Recent git history includes selection copy workflows, transparency keying, palette sampling, and texture generator updates.

## Service Notes
No long-running services, backend processes, health URLs, or service suites were found. The source-grounded app launch command is `python main.py`.
