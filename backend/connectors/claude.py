# ==============================================================
# backend/connectors/claude.py
# Script generation via the Anthropic Claude API.
# ==============================================================

import os
import re
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL = "claude-sonnet-4-20250514"

# --------------------------------------------------------------
# Format guidance injected into the prompt
# --------------------------------------------------------------
FORMAT_GUIDANCE = {
    "1min":  "The script should be very short -- approximately 150 words of spoken dialogue. Aim for 1-2 scenes.",
    "2min":  "The script should be approximately 300 words of spoken dialogue. Aim for 3-4 scenes.",
    "10min": "The script should be approximately 1400 words of spoken dialogue. Aim for 10-12 scenes.",
    "15min": "The script should be approximately 2000 words of spoken dialogue. Aim for 14-16 scenes.",
}


# ==============================================================
# Main generation function
# ==============================================================

async def generate_script(title: str, description: str, niche: str,
                           format: str, style_guide: str = "") -> dict:
    """
    Generate a full video script using Claude.

    Returns:
        {
            "script": str,     <- full script text with visual cue markers
            "tags":   list     <- list of tag strings extracted from end of script
        }
    """
    format_note = FORMAT_GUIDANCE.get(format, "")
    style_section = f"\n\nCHANNEL STYLE GUIDE:\n{style_guide}" if style_guide.strip() else ""

    prompt = f"""You are writing a script for a {niche} YouTube video.

TITLE: {title}
DESCRIPTION: {description}
FORMAT: {format} video. {format_note}
{style_section}

INSTRUCTIONS:
Write a complete video script following these rules exactly:

1. STRUCTURE: Write the script as a series of scenes. Each scene must begin
   with a visual cue marker on its own line in this exact format:
   [VISUAL: brief description of the image/scene to generate]
   Followed immediately by the spoken narration for that scene.

2. TONE: Informative, engaging, and conversational. Write as if speaking
   directly to a curious viewer. Avoid filler phrases, excessive adjectives,
   and any construction like "this is not X, it is Y."

3. HOOK: The first 15 seconds must immediately hook the viewer. Open with
   the most interesting or surprising aspect of the topic. Do not open with
   "In this video" or "Today we're going to."

4. PACING: Write to be spoken aloud. Short sentences. Vary rhythm.
   Read it back mentally -- if it sounds like an essay, rewrite it.

5. TAGS: At the very end of the script, after a line containing only
   "---TAGS---", list 15-20 relevant YouTube search tags separated by commas.

EXAMPLE FORMAT:
[VISUAL: wide shot of a dark forest at night, watercolor style]
Deep in the oldest forests on Earth, something is watching. Not an animal.
Not a person. Something much older.

[VISUAL: close-up of ancient tree roots tangling underground]
These trees are communicating right now -- through a network of fungal threads
stretching for miles beneath your feet.

---TAGS---
forest communication, mycorrhizal network, trees talk, plant intelligence, nature documentary

Now write the full script for: {title}"""

    message = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text
    script_text, tags = _parse_script(raw)

    return {
        "script": script_text,
        "tags":   tags
    }


# ==============================================================
# Shot list extraction
# ==============================================================

async def extract_shot_list(script: str) -> list:
    """
    Parse a finalized script and return a structured shot list.
    Each shot contains the visual cue and the spoken text for that scene.

    Returns:
        [
            {
                "shot_number":    1,
                "image_prompt":   "wide shot of a dark forest...",
                "narration":      "Deep in the oldest forests..."
            },
            ...
        ]
    """
    shots = []
    # Split on [VISUAL: ...] markers
    pattern = r'\[VISUAL:\s*(.*?)\]'
    parts = re.split(pattern, script, flags=re.IGNORECASE)

    # parts alternates: [pre-text, visual1, narration1, visual2, narration2, ...]
    shot_number = 1
    i = 1  # start after any pre-marker text
    while i < len(parts) - 1:
        visual = parts[i].strip()
        narration = parts[i + 1].strip() if i + 1 < len(parts) else ""
        # Strip the tags section if it leaked into the last narration
        narration = narration.split("---TAGS---")[0].strip()
        if visual:
            shots.append({
                "shot_number":  shot_number,
                "image_prompt": visual,
                "narration":    narration
            })
            shot_number += 1
        i += 2

    return shots


# ==============================================================
# Save style diff
# ==============================================================

def save_style_diff(channel_dir: str, project_id: str,
                    draft: str, final: str):
    """
    Save a diff between AI draft and user-edited final script.
    Used periodically to update the channel style guide.
    """
    import difflib
    from pathlib import Path
    from datetime import datetime

    diff = list(difflib.unified_diff(
        draft.splitlines(keepends=True),
        final.splitlines(keepends=True),
        fromfile="draft",
        tofile="final"
    ))

    if not diff:
        return  # No changes, nothing to record

    diff_dir = Path(channel_dir) / "style_diffs"
    diff_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    diff_path = diff_dir / f"diff_{project_id}_{timestamp}.txt"

    with open(diff_path, "w", encoding="utf-8") as f:
        f.writelines(diff)


# ==============================================================
# Internal helpers
# ==============================================================

def _parse_script(raw: str) -> tuple[str, list]:
    """Split raw Claude output into script text and tags list."""
    if "---TAGS---" in raw:
        parts = raw.split("---TAGS---", 1)
        script_text = parts[0].strip()
        tags_raw = parts[1].strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    else:
        script_text = raw.strip()
        tags = []

    return script_text, tags
