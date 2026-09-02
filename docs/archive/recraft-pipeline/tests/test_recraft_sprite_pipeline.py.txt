from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import numpy as np
import pytest
from PIL import Image

from src.core.recraft_sprite_pipeline import (
    RecraftAmbiguousSubmissionError,
    RecraftClient,
    RecraftPipelineError,
    calibrate_validation_profile,
    check_candidate,
    ingest_candidate,
    load_job,
    prepare_job,
    promote_recraft_component,
    record_review,
    submit_job_candidates,
)

COMPONENT = {
    "id": "horn-friendly-guard-helm",
    "display_name": "Horn-Friendly Guard Helm",
    "description": "A fitted steel helmet with openings around the existing horns",
    "slot": "headwear",
    "material": "steel",
    "colors": ["#252A31", "#66717D", "#AEB8C2"],
    "mirror_safe": True,
    "expected_pieces": 1,
}


def _prepare(tmp_path: Path, *, animation: str = "run", frames=None) -> Path:
    return prepare_job(
        base="tiefling-female-01",
        camera="low",
        animation=animation,
        direction="front",
        component=COMPONENT,
        selected_frames=frames,
        job_id=f"test-{animation}-{len(frames) if frames else 'all'}",
        work_root=tmp_path,
    )


def _rearranged_board(job_root: Path, order: list[int], layout: str = "4x2") -> Path:
    source = Image.open(job_root / "source" / "request_board.png").convert("RGBA")
    source_layout = load_job(job_root)["layout"]
    source_columns = int(source_layout["columns"])
    source_rows = int(source_layout["rows"])
    cell_width = source.width // source_columns
    cell_height = source.height // source_rows
    cells = [
        source.crop(
            (
                (index % source_columns) * cell_width,
                (index // source_columns) * cell_height,
                (index % source_columns + 1) * cell_width,
                (index // source_columns + 1) * cell_height,
            )
        )
        for index in range(source_columns * source_rows)
    ]
    columns, rows = (int(value) for value in layout.split("x"))
    output = Image.new("RGBA", (columns * cell_width, rows * cell_height), (0, 0, 0, 0))
    for target, origin in enumerate(order):
        output.alpha_composite(
            cells[origin],
            ((target % columns) * cell_width, (target // columns) * cell_height),
        )
    path = job_root / "manual_candidate.png"
    output.save(path)
    return path


def test_prepare_run_creates_locked_4x2_request_without_secrets(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path)
    job = load_job(job_root)
    assert job["layout"] == {
        "name": "4x2",
        "columns": 4,
        "rows": 2,
        "width": 1536,
        "height": 768,
    }
    assert job["selected_frame_indices"] == list(range(8))
    assert "not a collage to rearrange" in job["provider"]["prompt"]
    assert "which arm and leg is forward" in job["provider"]["prompt"]
    assert len(job["provider"]["palette_colors"]) <= 10
    with Image.open(job_root / "source" / "request_board.png") as board:
        assert board.size == (1536, 768)
    text = (job_root / "job.json").read_text(encoding="utf-8")
    assert "RECRAFT_API_TOKEN" not in text
    assert "Authorization" not in text


def test_prepare_idle_uses_full_loop_and_two_sentinels(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path, animation="idle")
    job = load_job(job_root)
    assert job["layout"]["name"] == "4x4"
    assert job["selected_frame_indices"] == list(range(14))
    assert job["board_frame_indices"] == [*range(14), 0, 13]
    with Image.open(job_root / "source" / "request_board.png") as board:
        assert board.size == (1024, 1024)


def test_idle_sentinel_pose_change_is_rejected(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path, animation="idle")
    source = job_root / "source" / "request_board.png"
    with Image.open(source) as opened:
        board = opened.convert("RGBA")
    board.paste((0, 0, 0, 0), (512, 768, 768, 1024))
    changed = tmp_path / "changed-sentinel.png"
    board.save(changed)
    candidate = ingest_candidate(
        job_root, changed, layout="4x4", candidate_id="changed-sentinel"
    )
    validation = json.loads(
        (job_root / "candidates" / candidate / "validation.json").read_text()
    )
    assert "sentinel_pose_mismatch_cell_15" in validation["errors"]


def test_identity_ingest_is_structurally_exact_and_deterministic(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path)
    candidate = ingest_candidate(
        job_root,
        job_root / "source" / "request_board.png",
        layout="4x2",
        candidate_id="identity",
        strict_layout=True,
    )
    validation = json.loads(
        (job_root / "candidates" / candidate / "validation.json").read_text()
    )
    assert not validation["errors"]
    assert all(frame["silhouette_iou"] == 1.0 for frame in validation["frames"])
    assert all(frame["best_pose_frame"] == frame["source_frame"] for frame in validation["frames"])
    assert all(value == 0 for value in validation["illegal_excursion_pixels"])
    assert check_candidate(job_root, candidate) == []


def test_job_rejects_authoritative_source_snapshot_drift(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path)
    frame = job_root / "source" / "frames" / "frame_00.png"
    frame.write_bytes(frame.read_bytes() + b"tampered")
    with pytest.raises(RecraftPipelineError, match="source frame hash drift"):
        load_job(job_root)


def test_swapped_source_cells_are_flagged_as_wrong_pose(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path)
    swapped = _rearranged_board(job_root, [0, 1, 3, 2, 4, 5, 6, 7])
    candidate = ingest_candidate(
        job_root,
        swapped,
        layout="4x2",
        candidate_id="swapped",
        strict_layout=True,
    )
    validation = json.loads(
        (job_root / "candidates" / candidate / "validation.json").read_text()
    )
    assert validation["status"] == "reject"
    assert "unexpected_pose_match" in validation["errors"]
    assert validation["frames"][2]["best_pose_frame"] == 3
    assert validation["frames"][3]["best_pose_frame"] == 2


def test_explicit_legacy_2x2_layout_can_be_reviewed(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path, frames=[0, 2, 4, 6])
    legacy = _rearranged_board(job_root, [0, 1, 2, 3], layout="2x2")
    candidate = ingest_candidate(
        job_root, legacy, layout="2x2", candidate_id="legacy", strict_layout=False
    )
    validation = json.loads(
        (job_root / "candidates" / candidate / "validation.json").read_text()
    )
    assert len(validation["frames"]) == 4
    assert (job_root / "candidates" / candidate / "review" / "normalized.gif").is_file()


def test_component_extraction_discards_illegal_detached_addition(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path)
    source = Image.open(job_root / "source" / "request_board.png").convert("RGBA")
    raw = np.asarray(source, dtype=np.uint8).copy()
    # A large detached addition in every 384px cell is deliberately outside the body.
    for row in range(2):
        for column in range(4):
            raw[row * 384 + 24 : row * 384 + 42, column * 384 + 24 : column * 384 + 42] = (
                230,
                40,
                40,
                255,
            )
    candidate_path = job_root / "illegal.png"
    Image.fromarray(raw, "RGBA").save(candidate_path)
    candidate = ingest_candidate(
        job_root, candidate_path, layout="4x2", candidate_id="illegal", strict_layout=True
    )
    validation = json.loads(
        (job_root / "candidates" / candidate / "validation.json").read_text()
    )
    assert any(value > 0 for value in validation["illegal_excursion_pixels"])
    assert "illegal_candidate_excursions_discarded" in validation["warnings"]
    with Image.open(job_root / "candidates" / candidate / "extracted" / "frame_00.png") as image:
        assert image.getpixel((10, 10))[3] == 0


def test_review_decision_is_separate_from_automatic_validation(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path)
    candidate = ingest_candidate(
        job_root,
        job_root / "source" / "request_board.png",
        layout="4x2",
        candidate_id="reviewed",
    )
    decision = record_review(
        job_root, candidate, status="approved", notes="Complete loop manually checked"
    )
    assert decision["status"] == "approved"
    assert decision["validation_status"] in {"pass", "warn"}
    assert load_job(job_root)["state"] == "reviewed"


def test_calibration_only_promotes_perfectly_separating_metrics(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path)
    identity = ingest_candidate(
        job_root,
        job_root / "source" / "request_board.png",
        layout="4x2",
        candidate_id="good",
    )
    record_review(job_root, identity, status="approved")
    swapped_path = _rearranged_board(job_root, [0, 1, 3, 2, 4, 5, 6, 7])
    swapped = ingest_candidate(
        job_root, swapped_path, layout="4x2", candidate_id="bad"
    )
    record_review(job_root, swapped, status="rejected")
    output = tmp_path / "calibrated.json"
    profile = calibrate_validation_profile([job_root], output_path=output)
    assert profile["status"] == "calibrated"
    assert output.is_file()
    assert set(profile["hard_metrics"]).isdisjoint(profile["warning_metrics"])


def test_recraft_client_uses_direct_json_and_redacts_base64_response(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGBA", (256, 256), (10, 20, 30, 255)).save(source)
    output_bytes = source.read_bytes()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/users/me"):
            return httpx.Response(200, json={"id": "u1", "credits": 1000})
        body = json.loads(request.content)
        assert body["response_format"] == "b64_json"
        assert body["n"] == 1
        assert body["image_url"].startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "image-1", "b64_json": base64.b64encode(output_bytes).decode()}
                ]
            },
        )

    with RecraftClient(
        "secret-token",
        base_url="https://example.test/v1",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.doctor()["credits"] == 1000
        result, metadata = client.image_to_image(
            image=source,
            prompt="locked",
            negative_prompt="changed pose",
            model="recraftv4_1",
            strength=0.25,
            seed=17011,
            colors=((1, 2, 3),),
        )
    assert result == output_bytes
    assert metadata == {"response": {}, "image": {"id": "image-1"}}
    assert all(request.headers["Authorization"] == "Bearer secret-token" for request in requests)


def test_paid_submit_requires_acknowledgement_and_enforces_output_cap(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path)
    with pytest.raises(RecraftPipelineError, match="explicit --submit"):
        submit_job_candidates(
            job_root, strengths=[0.25], seeds=[1], max_outputs=1, submit=False
        )
    with pytest.raises(RecraftPipelineError, match="exceeds --max-outputs"):
        submit_job_candidates(
            job_root,
            strengths=[0.15, 0.25, 0.35],
            seeds=[1, 2, 3, 4],
            max_outputs=4,
            submit=True,
        )


def test_ambiguous_transport_failure_is_recorded_without_retry(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path)

    class AmbiguousClient:
        calls = 0

        def doctor(self) -> dict[str, object]:
            return {"credits": 100}

        def image_to_image(self, **_kwargs: object) -> tuple[bytes, dict[str, object]]:
            self.calls += 1
            raise RecraftAmbiguousSubmissionError("ambiguous")

    client = AmbiguousClient()
    with pytest.raises(RecraftAmbiguousSubmissionError):
        submit_job_candidates(
            job_root,
            strengths=[0.25],
            seeds=[17],
            max_outputs=1,
            submit=True,
            client=client,  # type: ignore[arg-type]
        )
    assert client.calls == 1
    records = load_job(job_root)["candidates"]
    assert len(records) == 1
    assert records[0]["state"] == "unknown_submission"


def test_promotion_refuses_an_incomplete_matrix(tmp_path: Path) -> None:
    job_root = _prepare(tmp_path)
    candidate = ingest_candidate(
        job_root,
        job_root / "source" / "request_board.png",
        layout="4x2",
        candidate_id="only-one",
    )
    record_review(job_root, candidate, status="approved")
    with pytest.raises(RecraftPipelineError, match="Incomplete promotion matrix"):
        promote_recraft_component([job_root], asset_root=tmp_path / "assets")
