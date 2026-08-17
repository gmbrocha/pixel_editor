import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

import src.component_pipeline.pipeline as pipeline
from src.component_pipeline.pipeline import (
    PipelineError,
    analyze_candidate,
    build_generation_prompt,
    create_allowed_region_mask,
    create_native_region_mask,
    extract_component_overlay,
    load_component_ideas,
    normalize_generated_image,
    prepare_pipeline,
    promote_candidate,
    validate_canonical_checksums,
)
from src.core.character_forge import (
    CharacterAnimation,
    CharacterCatalog,
    CharacterPart,
    CharacterRecipe,
    create_default_catalog,
    validate_recipe,
)


@pytest.fixture
def isolated_pipeline(tmp_path, monkeypatch) -> Path:
    asset_root = tmp_path / "assets" / "character-forge"
    shutil.copytree(pipeline.ASSET_ROOT, asset_root)
    pipeline_root = tmp_path / "art_pipeline"
    monkeypatch.setattr(pipeline, "ASSET_ROOT", asset_root)
    monkeypatch.setattr(pipeline, "PIPELINE_ROOT", pipeline_root)
    monkeypatch.setattr(pipeline, "CATALOG_PATH", asset_root / "custom_parts" / "components.yaml")
    monkeypatch.setattr(pipeline, "SPEC_PATH", asset_root / "sheet_specs.json")
    return asset_root


def tiny_animation() -> CharacterAnimation:
    return CharacterAnimation(
        id="tiny",
        name="Tiny",
        filename="tiny.png",
        sheet_size=(8, 4),
        frame_size=(4, 4),
        frames_per_direction=2,
        direction_rows={"front": 0},
        fps=8,
        matte_rgb=None,
    )


def test_bootstrap_catalog_has_all_35_compact_records() -> None:
    ideas = load_component_ideas()
    assert len(ideas) == 35
    assert len({idea.id for idea in ideas}) == 35
    assert {idea.slot for idea in ideas} == {
        "headwear",
        "face",
        "neck",
        "waist",
        "outerwear",
        "hands",
        "feet",
    }


def test_generation_prompt_locks_base_and_component_identity() -> None:
    idea = next(idea for idea in load_component_ideas() if idea.id == "short_wool_travel_coat_01")
    animation = CharacterAnimation(
        id="walk",
        name="Walk",
        filename="walk.png",
        sheet_size=(384, 256),
        frame_size=(64, 64),
        frames_per_direction=6,
        direction_rows={"front": 0, "back": 1, "right": 2, "left": 3},
        fps=8,
        matte_rgb=None,
    )

    prompt = build_generation_prompt(idea, animation)

    assert "immutable raster template" in prompt
    assert "Perform additive paper-doll compositing" in prompt
    assert "Every original pixel that remains visible must be identical" in prompt
    assert "row 1 = Front, row 2 = Back, row 3 = Right, row 4 = Left" in prompt
    assert "same construction, material, palette, proportions" in prompt
    assert "When uncertain about a pixel, preserve the original pixel unchanged" in prompt
    assert idea.concept in prompt


def test_checksum_validation_refuses_silent_master_change(isolated_pipeline) -> None:
    validate_canonical_checksums()
    idle_path = isolated_pipeline / "bases" / "human-01" / "idle.png"
    with Image.open(idle_path) as opened:
        changed = opened.convert("RGBA")
    changed.putpixel((0, 0), (254, 255, 255, 255))
    changed.save(idle_path)
    with pytest.raises(PipelineError, match="checksum changed"):
        validate_canonical_checksums()


def test_prepare_builds_exact_generation_geometry_and_api_masks(isolated_pipeline) -> None:
    outputs = prepare_pipeline()
    expected = {
        "idle": (656, 1024),
        "walk": (1536, 1040),
        "run": (1536, 1024),
    }
    for path in outputs["masters"]:
        assert Image.open(path).size == expected[path.stem]
    assert len(outputs["mannequins"]) == 3
    assert len(outputs["ramps"]) == 3
    assert len(outputs["masks"]) == 24
    torso_idle = pipeline.PIPELINE_ROOT / "masks" / "torso" / "idle.png"
    with Image.open(torso_idle) as opened:
        mask = opened.convert("RGBA")
    assert mask.size == expected["idle"]
    assert mask.getchannel("A").getextrema() == (0, 255)


def test_reserved_blue_mannequin_ramp_is_reversible_and_preserves_neutral_pixels(
    isolated_pipeline,
) -> None:
    prepare_pipeline()
    canonical = Image.open(pipeline.PIPELINE_ROOT / "canonical" / "idle.png").convert("RGBA")
    mannequin = Image.open(pipeline.PIPELINE_ROOT / "mannequins" / "idle.png").convert("RGBA")
    mapping, document = pipeline.load_mannequin_ramp("idle")
    assert len(mapping) == 3
    assert document["reverse_threshold"] == document["leak_threshold"]
    assert all(blue > green > red for red, green, blue in mapping.values())
    assert canonical.getpixel((31, 26)) != mannequin.getpixel((31, 26))
    assert canonical.getpixel((27, 23)) == mannequin.getpixel((27, 23))
    restored = pipeline.reverse_mannequin_ramp(
        mannequin,
        mapping,
        threshold=float(document["reverse_threshold"]),
    )
    assert restored.tobytes() == canonical.tobytes()


def test_reserved_mannequin_color_leak_is_a_hard_qa_failure() -> None:
    animation = tiny_animation()
    base = Image.new("RGBA", animation.sheet_size, (0, 0, 0, 0))
    generated = Image.new("RGBA", animation.sheet_size, (255, 0, 255, 255))
    allowed = create_allowed_region_mask(animation, (1, 1, 3, 3))
    overlay = Image.new("RGBA", animation.sheet_size, (0, 0, 0, 0))
    reserved = (10, 80, 180)
    for frame_left in (0, 4):
        overlay.putpixel((frame_left + 1, 1), (*reserved, 255))
        generated.putpixel((frame_left + 1, 1), (*reserved, 255))
    qa = analyze_candidate(
        base,
        generated,
        overlay,
        allowed,
        animation,
        reserved_colors=(reserved,),
        reserved_color_threshold=1,
    )
    assert qa["status"] == "fail"
    assert "reserved_mannequin_color_leak" in qa["hard_failures"]
    assert qa["metrics"]["reserved_mannequin_leak_pixels"] == 2


def test_normalized_generation_is_canonicalized_outside_slot_region() -> None:
    animation = tiny_animation()
    canonical = Image.new("RGBA", animation.sheet_size, (0, 0, 0, 0))
    canonical.putpixel((0, 0), (20, 30, 40, 255))
    generated = Image.new("RGBA", animation.sheet_size, (5, 200, 240, 255))
    allowed = create_allowed_region_mask(animation, (1, 1, 3, 3))
    clamped = pipeline.clamp_outside_generation_region(
        generated,
        canonical,
        allowed,
        matte_rgb=(255, 0, 255),
    )
    assert clamped.getpixel((0, 0)) == (20, 30, 40, 255)
    assert clamped.getpixel((3, 3)) == (255, 0, 255, 255)
    assert clamped.getpixel((1, 1)) == (5, 200, 240, 255)


def test_position_aware_reversal_restores_exact_canonical_shade() -> None:
    generated = Image.new("RGBA", (2, 1), (0, 96, 210, 255))
    generated.putpixel((1, 0), (255, 0, 255, 255))
    canonical = Image.new("RGBA", (2, 1), (248, 216, 184, 255))
    mapping = {(136, 88, 72): (0, 96, 210)}
    restored = pipeline.reverse_mannequin_ramp(
        generated,
        mapping,
        threshold=64,
        canonical=canonical,
        matte_rgb=(255, 0, 255),
        matte_restore_threshold=64,
    )
    assert restored.getpixel((0, 0)) == (248, 216, 184, 255)
    assert restored.getpixel((1, 0)) == (248, 216, 184, 255)


def test_connected_generated_background_is_restored_without_erasing_component() -> None:
    animation = tiny_animation()
    generated = Image.new("RGBA", animation.sheet_size, (8, 8, 8, 255))
    for frame_left in (0, 4):
        generated.putpixel((frame_left + 2, 2), (120, 70, 35, 255))
    cleaned = pipeline.restore_generation_background(
        generated,
        animation,
        (0, 0, 4, 4),
        matte_rgb=(255, 0, 255),
    )
    assert cleaned.getpixel((0, 0)) == (255, 0, 255, 255)
    assert cleaned.getpixel((2, 2)) == (120, 70, 35, 255)
    assert cleaned.getpixel((6, 2)) == (120, 70, 35, 255)


def test_region_mask_is_frame_relative_and_api_alpha_is_inverted() -> None:
    animation = tiny_animation()
    allowed = create_allowed_region_mask(animation, (1, 1, 3, 3))
    api_mask = create_native_region_mask(animation, (1, 1, 3, 3))
    assert allowed.getpixel((1, 1)) == 255
    assert allowed.getpixel((5, 1)) == 255
    assert allowed.getpixel((0, 0)) == 0
    assert api_mask.getpixel((1, 1))[3] == 0
    assert api_mask.getpixel((0, 0))[3] == 255


def test_normalization_methods_preserve_geometry_and_choose_dominant_block() -> None:
    source = Image.new("RGBA", (16, 8), (0, 0, 0, 255))
    pixels = source.load()
    for y in range(4):
        for x in range(4):
            pixels[x + 4, y + 2] = (200, 10, 20, 255)
    pixels[4, 2] = (2, 2, 2, 255)
    dominant = normalize_generated_image(source, (2, 1), (4, 2, 4, 2), method="dominant")
    center = normalize_generated_image(source, (2, 1), (4, 2, 4, 2), method="center")
    palette = normalize_generated_image(
        source,
        (2, 1),
        (4, 2, 4, 2),
        method="palette",
        canonical_palette=((195, 10, 20, 255),),
    )
    assert dominant.size == center.size == palette.size == (2, 1)
    assert dominant.getpixel((0, 0)) == (200, 10, 20, 255)
    assert palette.getpixel((0, 0)) == (195, 10, 20, 255)


def test_tolerant_extraction_preserves_alpha_and_reconstruction_qa() -> None:
    animation = tiny_animation()
    base = Image.new("RGBA", animation.sheet_size, (0, 0, 0, 0))
    generated = Image.new("RGBA", animation.sheet_size, (255, 0, 255, 255))
    for frame_left in (0, 4):
        generated.putpixel((frame_left + 1, 1), (100, 50, 25, 128))
        generated.putpixel((frame_left + 2, 1), (100, 50, 25, 255))
    allowed = create_allowed_region_mask(animation, (1, 1, 3, 3))
    overlay = extract_component_overlay(base, generated, allowed)
    assert overlay.getpixel((1, 1)) == (100, 50, 25, 128)
    assert overlay.getpixel((0, 0))[3] == 0
    qa = analyze_candidate(base, generated, overlay, allowed, animation)
    assert qa["metrics"]["missing_frames"] == []
    assert qa["metrics"]["unique_colors"] == 2
    assert qa["status"] in ("pass", "warn")


def test_manifest_slot_exclusivity_and_legacy_recipe_migration() -> None:
    catalog = create_default_catalog()
    migrated = CharacterRecipe.from_dict(
        {
            "schema_version": 1,
            "base": "human-01",
            "parts": {"top": "walking-shirt-test"},
        }
    )
    assert migrated.parts["torso"] == "walking-shirt-test"
    validate_recipe(catalog, migrated)

    shirt = catalog.part("walking-shirt-test")
    conflict = CharacterPart(
        id="conflict",
        name="Conflict",
        slot="outerwear",
        layer="outerwear",
        animations={},
        occupies_slots=("outerwear",),
        reserved_slots=("torso",),
    )
    conflicting_catalog = CharacterCatalog(catalog.bases, (shirt, conflict))
    migrated.parts["outerwear"] = "conflict"
    with pytest.raises(Exception, match="both claim slot"):
        validate_recipe(conflicting_catalog, migrated)


def test_promotion_writes_incomplete_manifest_and_keeps_normal_catalog_clean(
    isolated_pipeline,
) -> None:
    prepare_pipeline()
    job_dir = pipeline.PIPELINE_ROOT / "jobs" / "test-promotion-job"
    (job_dir / "extracted").mkdir(parents=True)
    overlay = Image.new("RGBA", (64, 256), (0, 0, 0, 0))
    overlay.putpixel((30, 10), (20, 30, 40, 255))
    overlay.save(job_dir / "extracted" / "candidate-001.png")
    (job_dir / "prompt.txt").write_text("test prompt\n", encoding="utf-8")
    metadata = {
        "schema_version": 1,
        "job_id": job_dir.name,
        "component_id": "weathered_captains_cap_01",
        "animation_id": "idle",
        "slot": "headwear",
        "layer": "headwear",
        "status": "review",
        "candidates": {
            "candidate-001": {
                "status": "review",
                "review": {"decision": "approved"},
                "qa": {"status": "warn", "score": 80},
            }
        },
    }
    (job_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    target = promote_candidate(job_dir, "candidate-001")
    manifest_path = target.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert target == isolated_pipeline / "parts" / "headwear" / "weathered_captains_cap_01" / "idle.png"
    assert manifest["status"] == "incomplete"
    assert manifest["animations"] == {"idle": "idle.png"}
    development = create_default_catalog(isolated_pipeline, include_incomplete=True)
    production = create_default_catalog(isolated_pipeline, include_incomplete=False)
    assert development.part("weathered_captains_cap_01").status == "incomplete"
    assert all(part.id != "weathered_captains_cap_01" for part in production.parts)


def test_mocked_generation_runs_normalize_extract_qa_and_preview(
    isolated_pipeline,
    monkeypatch,
) -> None:
    jobs = pipeline.queue_component_jobs(
        "weathered_captains_cap_01",
        animation_id="idle",
        candidates=1,
        force_new=True,
    )
    master_path = pipeline.PIPELINE_ROOT / "generation_masters" / "idle.png"
    with Image.open(master_path) as opened:
        generated = opened.convert("RGBA")
    pixels = generated.load()
    for row in range(4):
        native_x, native_y = 30, row * 64 + 10
        for dy in range(4):
            for dx in range(4):
                pixels[200 + native_x * 4 + dx, native_y * 4 + dy] = (40, 60, 80, 255)
    buffer = pipeline.BytesIO()
    generated.save(buffer, format="PNG")
    monkeypatch.setattr(
        pipeline,
        "_openai_edit_candidate",
        lambda _job, _metadata: (
            buffer.getvalue(),
            {"request_id": "req_test", "attempt": 1, "usage": None},
        ),
    )
    metadata = pipeline.generate_job(jobs[0])
    candidate = metadata["candidates"]["candidate-001"]
    assert metadata["status"] == "review"
    assert candidate["api"]["request_id"] == "req_test"
    assert candidate["qa"]["metrics"]["missing_frames"] == []
    assert (jobs[0] / "extracted" / "candidate-001.png").is_file()
    assert (jobs[0] / "previews" / "candidate-001" / "front.webp").is_file()
    decided = pipeline.set_candidate_review(
        jobs[0], "candidate-001", "rejected", note="Silhouette needs cleanup"
    )
    assert decided["candidates"]["candidate-001"]["review"]["note"] == (
        "Silhouette needs cleanup"
    )


def test_permanent_api_rejection_is_recorded_once_per_candidate_and_queue_continues(
    isolated_pipeline,
    monkeypatch,
) -> None:
    jobs = pipeline.queue_component_jobs(
        "weathered_captains_cap_01",
        animation_id="idle",
        candidates=2,
        force_new=True,
    )
    calls = []

    def reject(_job, _metadata):
        calls.append(True)
        raise pipeline.PermanentAPIError(
            "moderation blocked",
            code="moderation_blocked",
            request_id=f"req_{len(calls)}",
        )

    monkeypatch.setattr(pipeline, "_openai_edit_candidate", reject)
    metadata = pipeline.generate_job(jobs[0])
    assert len(calls) == 2
    assert metadata["status"] == "failed"
    assert {
        candidate["status"] for candidate in metadata["candidates"].values()
    } == {"failed"}
    assert metadata["candidates"]["candidate-001"]["attempts"] == 1
    assert metadata["candidates"]["candidate-001"]["error"]["request_id"] == "req_1"


def test_resumption_does_not_reuse_a_smoke_job_with_the_wrong_candidate_count(
    isolated_pipeline,
) -> None:
    smoke = pipeline.queue_component_jobs(
        "weathered_captains_cap_01",
        animation_id="idle",
        candidates=1,
        force_new=True,
    )[0]
    production = pipeline.queue_component_jobs(
        "weathered_captains_cap_01",
        animation_id="idle",
        candidates=3,
    )[0]
    assert production != smoke
    _path, metadata = pipeline.load_job(production)
    assert metadata["candidate_count"] == 3


def test_resumption_accepts_same_generation_inputs_after_processing_revision(
    isolated_pipeline,
) -> None:
    original = pipeline.queue_component_jobs(
        "weathered_captains_cap_01",
        animation_id="idle",
        candidates=3,
        force_new=True,
    )[0]
    _path, metadata = pipeline.load_job(original)
    metadata["fingerprint"] = "legacy-processing-fingerprint"
    pipeline.save_job(original, metadata)
    resumed = pipeline.queue_component_jobs(
        "weathered_captains_cap_01",
        animation_id="idle",
        candidates=3,
    )[0]
    assert resumed == original
