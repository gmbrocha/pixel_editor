# Recraft Sprite Pipeline

Pixel Forge uses Recraft as a constrained component renderer for the `Heroic`
Character Forge style. Heroic base sheets and semantic region maps remain the
sole authority for pose, anatomy, proportions, camera, direction, framing,
frame order, and timing. Generative output is always a review candidate.

The pipeline has two entry points:

- `tools/recraft_sprite_lab.py` prepares jobs, imports manual downloads, serves
  the local reviewer, records decisions, and calibrates validation thresholds.
- `tools/run_recraft_sprite_jobs.py` performs guarded API submission, local
  resumption and validation, deterministic checks, and full-matrix promotion.

All job state lives under ignored `working/recraft/<job-id>/`. Secrets never
enter a job manifest. The only supported credential source is the
`RECRAFT_API_TOKEN` environment variable.

## Offline review lab

Preparing a complete eight-frame Tiefling Low Run Front helmet request does not
require a token:

```powershell
python tools/recraft_sprite_lab.py prepare `
  --base tiefling-female-01 --camera low --animation run --direction front `
  --component-id simple-guard-helm --component-name "Simple Guard Helm" `
  --description "Add a compact steel guard helmet with cheek guards." `
  --slot headwear --layer headwear --material steel `
  --color "#25233A" --color "#69647F" --color "#B6AEC7"
```

The command prints the job directory. Its `source/request_board.png` is the
provider input and `request/prompt.txt` is the versioned prompt contract. Run
and Walk use a 4x2 board. Idle uses a 4x4 board with frames 1 and 14 repeated as
cells 15 and 16; those consistency sentinels are discarded after validation.

Import a manually downloaded result with an explicit layout:

```powershell
python tools/recraft_sprite_lab.py ingest `
  --job working/recraft/<job-id> --input F:\path\result.png `
  --layout 4x2 --candidate-id manual-01
python tools/recraft_sprite_lab.py review `
  --job working/recraft/<job-id> --candidate manual-01
```

Legacy examples may use `4x1`, `2x2`, or another explicit rectangular mapping.
Use `--frames 1,2,3,4` during preparation for a partial historical example.
Partial jobs are regression/review evidence and cannot be promoted.

This workstation's two supplied historical examples are preserved under
`working/recraft/legacy-armored-layout-tiefling-run-front/` and
`working/recraft/legacy-wrong-leg-tiefling-run-front/`. The first is explicitly
labeled as layout/extraction evidence only. The second is a rejected mandatory
negative whose third supplied pose structurally matches the wrong canonical Run
frame. Both reproduce under deterministic `check` without an API call.

The loopback-only reviewer displays authoritative and raw boards, normalized
and extracted animations, nearest-neighbor frame inspection, differences,
structural scores, and semantic violations. Approval or rejection is stored in
the candidate's `review.json`.

## Paid calibration

Install dependencies, set the token in the current shell, and verify identity
and positive API-unit balance:

```powershell
python -m pip install -r requirements.txt
$env:RECRAFT_API_TOKEN = "..."
python tools/run_recraft_sprite_jobs.py doctor
```

The first calibration job must be Tiefling Female, Heroic Low, Run Front, with
all eight frames. Submission is impossible without the paid-action flag:

```powershell
python tools/run_recraft_sprite_jobs.py submit `
  --job working/recraft/<job-id> --calibration --max-outputs 12 --submit
```

This produces twelve independent `n=1` requests: strengths 0.15, 0.25, and 0.35
crossed with four fixed seeds. Concurrency is one. Balance before and after is
recorded without the token or authorization header. An ambiguous POST timeout
is marked `unknown_submission` and is never retried automatically.

After reviewing all calibration candidates, generate the tracked profile:

```powershell
python tools/recraft_sprite_lab.py calibrate `
  --job working/recraft/<job-id> `
  --output animation_images_models/recraft_validation_profile_v1.json
```

A measured metric becomes a hard gate only when it rejects every labeled bad
example without rejecting an approved example. Inconclusive metrics remain
warnings. The known wrong-leg frame must remain a rejected regression case
before production batching is enabled.

If calibration shows that Standard preserves structure but consistently loses
small equipment detail, prepare a new otherwise-identical job with
`--model recraftv4_1_pro`. Do not change model, prompt, strength, and board
layout in the same experiment.

## Production jobs and promotion

Production uses one direction, camera, and animation per job. Front, Back, and
Right are authored independently. A mirror-safe component derives Left from the
complete approved Right composite and extracts the overlay against the canonical
Left base. Asymmetric components require an explicit Left job.

Every candidate passes through these deterministic stages:

1. Decode and split the declared board without provider-side recentering.
2. Reduce all cells with one shared palette and binary alpha.
3. Compare each cell against every canonical pose, allowing at most two final
   pixels of integer registration for measurement only.
4. Check alpha, contour, core retention, centroid and bounds, semantic anchors,
   duplicate/swapped poses, margins, and complete-loop continuity.
5. Extract changes only inside declared semantic slots and their style-guide
   silhouette envelope, subtract protected foreground anatomy, split declared
   render layers/body-hide masks, and expose uncertain pixels for review.
6. Build exact-timing normalized and extracted GIFs and a reproducible report.

Local processing never spends API units:

```powershell
python tools/run_recraft_sprite_jobs.py resume --job working/recraft/<job-id>
python tools/run_recraft_sprite_jobs.py check `
  --job working/recraft/<job-id> --candidate <candidate-id>
```

`component` jobs may be promoted. `full_style_experiment` jobs can be prepared,
submitted, validated, and reviewed but cannot be promoted in pipeline v1.

Promotion requires exactly one approved, non-hard-rejected candidate for every
required cell of the matrix: three cameras times Idle/Walk/Run times
Front/Back/Right, plus explicit Left for asymmetric components. Pass each job
directory with a separate `--job` argument. The full command needs 27
mirror-safe jobs or 36 asymmetric jobs.

Promotion writes only Heroic camera variants, a shared recolor ramp, slot/layer
metadata, mirror policy, hashes, and provider provenance. It validates the
public Character Forge catalog and rolls back the newly created component if
catalog verification fails. Standard and JRPG assets are never modified.

## Job contents and deterministic checks

Each job records source sheet and semantic-map hashes, exact frame mapping,
prompt, model, strength, seed, palette controls, request and pipeline hashes,
candidate state, response metadata, normalized frames, extracted layers,
uncertain pixels, validation, GIFs, review decision, and promotion provenance.
Raw base64 is decoded and saved immediately; temporary public result URLs are
not used.

`check` rebuilds normalized images, reports, GIFs, and extracted layers in a
temporary directory without an API call and byte-compares them with the stored
candidate. Source or semantic hash drift invalidates the job before reuse.
