# Pip & Pyre component factory

The factory turns the ideas in
`assets/character-forge/custom_parts/components.yaml` into reviewed, transparent,
sheet-aligned Character Forge overlays. Canonical body art is never edited by a
generation job.

## Setup and folders

Install `requirements.txt` and set `OPENAI_API_KEY` in the environment or an ignored
`.env.local`/`.env` file. Keys are never copied into job metadata.

`art_pipeline/` is an ignored working tree containing canonical working copies,
reserved-blue mannequin references, reversible ramp metadata, 4x generation
masters, API masks, resumable jobs, previews, and the review queue.
Production assets live only under `assets/character-forge/parts/`.

## Commands

```powershell
python component_pipeline.py validate
python component_pipeline.py prepare
python component_pipeline.py generate --component weathered_captains_cap_01
python component_pipeline.py generate --component weathered_captains_cap_01 --animation walk --candidates 3
python component_pipeline.py generate --bootstrap
python component_pipeline.py normalize --job <job-id>
python component_pipeline.py extract --job <job-id>
python component_pipeline.py qa --job <job-id>
python component_pipeline.py review
python component_pipeline.py promote --job <job-id> --candidate candidate-001
python component_pipeline.py rebaseline --confirm human-01
python component_pipeline.py smoke-api --component weathered_captains_cap_01 --animation idle
```

Identical generation commands resume queued/incomplete candidates. Use `--new` only
when another independent job is wanted. Bootstrap queues all 35 ideas across Idle,
Walk, and Run; with an API key it processes the seven-component pilot first. Pass
`--remaining` only after reviewing and tuning that pilot.

If the key is missing, jobs remain `queued`, no fake images are created, and the CLI
prints the exact resume command.

## Processing and review

The Image API edits an opaque 4x generation-only copy through a same-size RGBA slot
mask. Preparation derives a warm authored ramp independently for Idle, Walk, and
Run, maps it to the reserved saturated-blue mannequin ramp, and records the exact
mapping plus hashes. Canonical PNGs are never recolored. After normalization,
border-connected generated background is restored to the recorded magenta matte.
Blue mannequin pixels and generated matte holes snap to the exact canonical pixel
at the same coordinate before extraction against the pristine base. This avoids
shade drift being mistaken for component art. Generated components are instructed
not to use the reserved ramp, and QA hard-fails if a reserved blue leaks into an
overlay.

Successful candidates automatically receive center, dominant, and palette-aware
normalization, tolerant difference extraction, reconstruction QA, and PNG/WebP
previews. Raw and background-cleaned pre-reversal comparisons are retained as
`*-mannequin-raw.png` and `*-mannequin.png`; dominant block sampling is the
production default.

Open review from the Pixel Forge **Component Factory** action or the `review`
command. APPROVE and REJECT record human decisions; REGENERATE preserves the prior
candidate; EDIT/CLEANUP opens the extracted native overlay in Pixel Editor. In
cleanup mode, erase/paint/eyedropper/undo/redo work normally and **Restore Source
Selection** restores selected pixels from the original extraction. **To Tray** saves
the corrected candidate back into its job and reruns QA.

Promotion is separate from approval. It refuses failing QA, revalidates canonical
checksums and geometry, writes the overlay and manifest, records provenance, and
marks partial animation sets `incomplete`. Use `--replace` explicitly to version and
replace an existing animation.

## Runtime composition

Character recipes select one component per primary slot. `occupiesSlots` and
`reservedSlots` prevent multi-slot collisions. The renderer inserts the canonical
body at the `body` layer and applies manifests in the declarative layer order from
`sheet_specs.json`; missing component animations or directions fall back to the
unchanged base.

For API errors, inspect the job's sanitized request and candidate metadata. Retry
queued jobs after authentication, quota, rate-limit, or server issues are resolved.
Permanent moderation and validation errors are recorded against only the affected
candidate and are never retried. Other independent candidates and jobs continue.
A changed prompt, canonical input, generation master, or slot mask produces a new
request fingerprint and sibling job. Post-processing revisions reuse persisted raw
candidates when those generation inputs are identical and record their own version
and ramp hash in candidate metadata.
