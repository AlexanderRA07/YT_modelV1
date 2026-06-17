# ==============================================================
# backend/connectors/claude.py
# Script generation via the Anthropic Claude API.
# ==============================================================

import os
import re
from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL = "claude-sonnet-4-6"

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
                           format: str, style_guide: str = "",
                           references: str = "", concepts: str = "") -> dict:
    """
    Generate a full video script using Claude.

    Returns:
        {
            "script":   str,   <- full script text with episode + visual markers
            "episodes": list,  <- structured [{number, title, scenes: [{image_prompt, narration}]}]
            "tags":     list,
            "description": str,
            "credits":  str
        }
    """
    format_note = FORMAT_GUIDANCE.get(format, "")
    style_section = f"\n\nCHANNEL STYLE GUIDE:\n{style_guide}" if style_guide.strip() else ""

    ref_urls = [r.strip() for r in references.split(";") if r.strip()] if references.strip() else []
    refs_section = (
        "\n\nREFERENCE SOURCES (draw from these and credit them):\n"
        + "\n".join(f"- {r}" for r in ref_urls)
    ) if ref_urls else ""
    ref_count = len(ref_urls)

    concepts_section = (
        f"\n\nCREATIVE CONCEPTS & ANGLES:\n{concepts.strip()}\n"
        "Incorporate these ideas, angles, or structural notes into the script."
    ) if concepts.strip() else ""

    prompt = f"""You are writing a script for a {niche} YouTube video.

TITLE: {title}
DESCRIPTION: {description}
FORMAT: {format} video. {format_note}
{style_section}{refs_section}{concepts_section}

INSTRUCTIONS:
Write a complete video script following these rules exactly:

1. STRUCTURE: Divide the script into exactly 4 episodes, each marked with:
   [EPISODE N: Short Title]

   Episode 1 — Opening Narrative: A character-driven anecdote or vignette that
     draws the viewer into the world of the topic. Sets tone and atmosphere.
     Does NOT explain the topic directly — it creates intrigue.
   Episode 2 — Core Information: Informative coverage of the main topic.
     Facts, explanations, the substance of the video.
   Episode 3 — Lore & History: Deeper real-world context — historical background,
     lore, trivia, behind-the-scenes detail that rewards curious viewers.
   Episode 4 — Closing Narrative: Return to the character or image from Episode 1.
     Close the loop. Leave the viewer with a final thought or lingering question.

   Within each episode, each scene begins with a visual cue on its own line:
   [VISUAL: concrete description of exactly what is visible in the frame]
   Followed immediately by the spoken narration for that scene.

   Each VISUAL description must be concrete: subject, setting, lighting, camera angle.
   Never use abstract or emotional language.
   If the image depicts a named character, name them and describe their appearance
   (especially if obscure — include hair, clothing, build rather than relying on the name).
   Bad:  "a tense confrontation between two enemies"
   Good: "two cloaked figures facing each other in a torchlit stone corridor, low camera angle, deep shadows"
   Bad: "an unlikely hero sneaks up on a dragon"
   Good: "Bilbo Baggins, small and wide-eyed in his travelling cloak, creeping along a ledge above Smaug the golden dragon coiled on a vast treasure pile, warm firelight from below, high angle shot"

2. TONE: Informative, engaging, and conversational. Write as if speaking
   directly to a curious viewer. Avoid filler phrases, excessive adjectives,
   and any construction like "this is not X, it is Y."

3. HOOK: The first 15 seconds must immediately hook the viewer. Open with
   the most interesting or surprising aspect of the topic. Do not open with
   "In this video" or "Today we're going to."

4. PACING: Write to be spoken aloud. Short sentences. Vary rhythm.
   Read it back mentally — if it sounds like an essay, rewrite it.

5. TAGS: After the script, after a line containing only \"---TAGS---\",
   list 15-20 YouTube search tags separated by commas.
   Mix broad category terms (e.g. \"star wars\", \"space facts\") with
   mid-level topic terms (e.g. \"darth vader lore\") and specific detail
   terms (e.g. \"mustafar duel\"). Always include the broadest 3-5 terms
   a casual viewer would search, not just deep-dive specifics.

6. DESCRIPTION: After the tags, after a line containing only \"---DESCRIPTION---\",
   write a 3-4 sentence YouTube video description. Engaging, informative,
   ends with a call to action. No hashtags — those come from the tags.

7. CREDITS: After the description, after a line containing only "---CREDITS---",
   list every source that informed this script.
   Format each as: Label | URL
   Every URL must start with https://.

   Sourcing rules:
   - ALWAYS list the REFERENCE SOURCES provided above first (if any were given) —
     you drew from those, so credit them. Use the site or author name as the label.
   - Then use web_search to find ADDITIONAL sources. If {ref_count} reference(s) were
     provided, find at least {max(ref_count, 3)} more via search. If none were provided,
     aim for at least 5 credible sources.
   - Useful searches: the topic directly, "[topic] wiki", "[topic] history",
     "[topic] fandom" — fan wikis (fandom.com, wikia.com) are valid and often
     the best source for game/fictional lore topics.
   - Include any URL that meaningfully informed the content: Wikipedia, fan wikis,
     academic summaries, news articles, official sites.
   - If truly nothing credible can be found via search, write: ¯\_(ツ)_/¯

EXAMPLE FORMAT:
[EPISODE 1: Opening Narrative]
[VISUAL: wide shot of a moonlit forest floor, gnarled roots and faint bioluminescent fungi, atmospheric watercolor style]
Deep in the oldest forests on Earth, something ancient is listening.

[VISUAL: extreme close-up of a fungal thread network beneath dark soil, cross-section view, soft amber lighting]
Not with ears. Not with eyes. But with a web of filaments older than memory.

[EPISODE 2: Core Information]
[VISUAL: illustrated diagram of a mycorrhizal network connecting three oak trees, roots intertwined underground, clean educational style]
Scientists call it the mycorrhizal network. Most people call it the Wood Wide Web.

---TAGS---
nature documentary, forest facts, mycorrhizal network, trees communicate, plant intelligence, fungi network, forest science, biology explained, nature science, how forests work

---DESCRIPTION---
Beneath every forest floor lies a hidden internet — a vast network of fungal threads connecting trees across miles. In this video, we explore how trees communicate, share resources, and even warn each other of danger. The science is stranger than fiction. Like and subscribe for more nature deep-dives.

---CREDITS---
Wikipedia — Mycorrhizal network | https://en.wikipedia.org/wiki/Mycorrhizal_network
Simard, S. — Finding the Mother Tree | https://www.hachettebooks.com/titles/suzanne-simard/finding-the-mother-tree/9780525656098/

Now write the full script for: {title}"""

    message = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
        messages=[{"role": "user", "content": prompt}]
    )

    raw = ""
    for block in message.content:
        if hasattr(block, "text"):
            raw += block.text

    script_text, episodes, tags, description, credits = _parse_script(raw)

    return {
        "script":      script_text,
        "episodes":    episodes,
        "tags":        tags,
        "description": description,
        "credits":     credits
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
    pattern = r'\[VISUAL:\s*(.*?)\]'
    parts = re.split(pattern, script, flags=re.IGNORECASE)

    shot_number = 1
    i = 1
    while i < len(parts) - 1:
        visual = parts[i].strip()
        narration = parts[i + 1].strip() if i + 1 < len(parts) else ""
        narration = narration.split("---TAGS---")[0].strip()
        # Strip any episode markers that leaked into the narration tail
        narration = re.sub(r'\[EPISODE\s+\d+:[^\]]*\]', '', narration, flags=re.IGNORECASE).strip()
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

def _parse_script(raw: str) -> tuple[str, list, list, str, str]:
    """Split raw Claude output into script, episodes, tags, description, credits."""
    script_text = raw.strip()
    tags        = []
    description = ""
    credits     = ""

    if "---TAGS---" in script_text:
        script_text, remainder = script_text.split("---TAGS---", 1)
        script_text = script_text.strip()
    else:
        remainder = ""

    if "---DESCRIPTION---" in remainder:
        tags_raw, remainder = remainder.split("---DESCRIPTION---", 1)
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    else:
        tags = [t.strip() for t in remainder.split(",") if t.strip()]
        remainder = ""

    if "---CREDITS---" in remainder:
        description, credits = remainder.split("---CREDITS---", 1)
        description = description.strip()
        credits     = credits.strip()
    else:
        description = remainder.strip()

    episodes = _parse_episodes(script_text)
    return script_text, episodes, tags, description, credits


def _parse_episodes(script_text: str) -> list:
    """Parse [EPISODE N: Title] sections and their nested scenes."""
    episode_pattern = re.compile(r'\[EPISODE\s+(\d+):\s*([^\]]+)\]', re.IGNORECASE)
    parts = episode_pattern.split(script_text)

    episodes = []
    # After split: [pre, num1, title1, body1, num2, title2, body2, ...]
    i = 1
    while i + 2 <= len(parts):
        number = int(parts[i])
        title  = parts[i + 1].strip()
        body   = parts[i + 2]
        episodes.append({
            "number": number,
            "title":  title,
            "scenes": _parse_scenes(body)
        })
        i += 3

    return episodes


def _parse_scenes(episode_body: str) -> list:
    """Extract [VISUAL: ...] scenes from an episode body."""
    visual_pattern = re.compile(r'\[VISUAL:\s*(.*?)\]', re.IGNORECASE)
    parts = visual_pattern.split(episode_body)

    scenes = []
    i = 1
    while i < len(parts):
        image_prompt = parts[i].strip()
        narration = parts[i + 1].strip() if i + 1 < len(parts) else ""
        # Stop at the next episode marker or tags section
        narration = re.split(r'\[EPISODE', narration)[0].strip()
        narration = narration.split("---TAGS---")[0].strip()
        if image_prompt:
            scenes.append({"image_prompt": image_prompt, "narration": narration})
        i += 2

    return scenes
