# ==============================================================
# backend/asset_targets.py
# Format-driven asset generation targets.
# Single source of truth for minimum counts and generation
# targets per video format. Edit here to adjust ratios.
# ==============================================================

import math


# --------------------------------------------------------------
# Minimum image counts per format
# --------------------------------------------------------------
IMAGE_MINIMUMS = {
    "1min":  2,
    "2min":  3,
    "10min": 10,
    "15min": 15,
}

# Images overgenerates at 150% of minimum, rounded up
IMAGE_OVERAGE_RATIO = 1.5

# --------------------------------------------------------------
# Hardcoded targets for all other asset types
# (same regardless of format)
# --------------------------------------------------------------
FIXED_TARGETS = {
    "animation":  None,   # 1 per approved image, on-demand only
    "voice":      1,
    "music":      1,
    "thumbnail":  3,
}


# ==============================================================
# Public interface
# ==============================================================

def get_image_minimum(format: str) -> int:
    """Return the minimum number of approved images required for a format."""
    if format not in IMAGE_MINIMUMS:
        raise ValueError(
            f"Unknown format '{format}'. "
            f"Valid formats: {list(IMAGE_MINIMUMS.keys())}"
        )
    return IMAGE_MINIMUMS[format]


def get_image_target(format: str) -> int:
    """
    Return how many images to generate initially (150% of minimum, rounded up).
    Example: 2min minimum=3 -> target=ceil(3 * 1.5) = 5
    """
    minimum = get_image_minimum(format)
    return math.ceil(minimum * IMAGE_OVERAGE_RATIO)


def get_all_targets(format: str) -> dict:
    """
    Return the full generation target table for a given format.
    Used by the pipeline to know how many of each asset type to dispatch.

    Returns:
        {
            "image":     5,     <- initial dispatch count
            "animation": None,  <- on-demand, not pre-dispatched
            "voice":     1,
            "music":     1,
            "thumbnail": 3,
            "image_minimum": 3  <- minimum needed to unlock compile
        }
    """
    return {
        "image":         get_image_target(format),
        "animation":     FIXED_TARGETS["animation"],
        "voice":         FIXED_TARGETS["voice"],
        "music":         FIXED_TARGETS["music"],
        "thumbnail":     FIXED_TARGETS["thumbnail"],
        "image_minimum": get_image_minimum(format),
    }


def get_compile_minimums(format: str) -> dict:
    """
    Return the minimum approved counts required in each category
    before compilation is unlocked.
    Passed to ProjectState.check_compile_ready().

    Returns:
        {
            "image":     3,
            "animation": 3,   <- must match image minimum
            "voice":     1,
            "music":     1,
            "thumbnail": 1    <- at least 1 thumbnail selected
        }
    """
    image_min = get_image_minimum(format)
    return {
        "image":     image_min,
        "animation": image_min,   # one animation per approved image
        "voice":     1,
        "music":     1,
        "thumbnail": 1,
    }


# --------------------------------------------------------------
# Quick reference table (for logging / UI display)
# --------------------------------------------------------------
def describe_targets(format: str) -> str:
    targets = get_all_targets(format)
    minimums = get_compile_minimums(format)
    lines = [
        f"Format: {format}",
        f"  Images:     generate {targets['image']}, need {minimums['image']} approved",
        f"  Animations: 1 per approved image (on-demand)",
        f"  Voice:      {targets['voice']} (1 required)",
        f"  Music:      {targets['music']} (1 required)",
        f"  Thumbnails: {targets['thumbnail']} generated (1 required)",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    # Quick sanity check
    for fmt in IMAGE_MINIMUMS:
        print(describe_targets(fmt))
        print()
