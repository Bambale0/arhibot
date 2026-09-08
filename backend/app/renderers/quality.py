from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageFilter, ImageStat


@dataclass(frozen=True, slots=True)
class RenderQualityResult:
    score: float
    report: dict[str, float | bool]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_render_quality(data: bytes) -> RenderQualityResult:
    """Score technical image quality without changing or interpreting architecture geometry."""
    with Image.open(BytesIO(data)) as image:
        rgb = image.convert("RGB")
        grayscale = rgb.convert("L")
        histogram = grayscale.histogram()
        pixels = max(1, grayscale.width * grayscale.height)
        stats = ImageStat.Stat(grayscale)
        mean = float(stats.mean[0]) / 255.0
        contrast = float(stats.stddev[0]) / 255.0
        entropy = float(grayscale.entropy()) / 8.0

        black_clip = sum(histogram[:6]) / pixels
        white_clip = sum(histogram[250:]) / pixels

        edges = grayscale.filter(ImageFilter.FIND_EDGES)
        edge_stats = ImageStat.Stat(edges)
        sharpness = float(edge_stats.stddev[0]) / 255.0

    exposure_score = _clamp01(1.0 - abs(mean - 0.52) / 0.52)
    contrast_score = _clamp01(contrast / 0.24)
    entropy_score = _clamp01(entropy)
    sharpness_score = _clamp01(sharpness / 0.20)
    clipping_penalty = _clamp01((black_clip + white_clip) / 0.18)

    score = (
        exposure_score * 0.30
        + contrast_score * 0.25
        + entropy_score * 0.20
        + sharpness_score * 0.25
        - clipping_penalty * 0.20
    )
    score = round(_clamp01(score), 6)
    technically_usable = (
        0.12 <= mean <= 0.92
        and black_clip <= 0.25
        and white_clip <= 0.25
        and contrast >= 0.035
    )
    if not technically_usable:
        score = round(score * 0.45, 6)

    return RenderQualityResult(
        score=score,
        report={
            "mean_luminance": round(mean, 6),
            "contrast": round(contrast, 6),
            "entropy": round(entropy, 6),
            "sharpness": round(sharpness, 6),
            "black_clip_ratio": round(black_clip, 6),
            "white_clip_ratio": round(white_clip, 6),
            "technically_usable": technically_usable,
        },
    )
