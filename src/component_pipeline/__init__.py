"""Pip & Pyre modular character-component production pipeline."""

from .pipeline import (
    PipelineError,
    analyze_candidate,
    create_native_region_mask,
    extract_component_overlay,
    load_component_ideas,
    normalize_generated_image,
    prepare_pipeline,
    promote_candidate,
    queue_component_jobs,
    validate_pipeline,
)

__all__ = [
    "PipelineError",
    "analyze_candidate",
    "create_native_region_mask",
    "extract_component_overlay",
    "load_component_ideas",
    "normalize_generated_image",
    "prepare_pipeline",
    "promote_candidate",
    "queue_component_jobs",
    "validate_pipeline",
]
