# ==============================================================
# backend/compiler.py
# Video assembly using MoviePy.
# Takes all approved assets from a project and assembles them
# into a single output.mp4 with voiceover, animations, and
# background music. Also writes the export package.
# ==============================================================

import os
import json
import asyncio
from pathlib import Path
from typing import Optional

# MoviePy imports
from moviepy.editor import (
    VideoFileClip,
    ImageClip,
    AudioFileClip,
    CompositeAudioClip,
    concatenate_videoclips,
    concatenate_audioclips,
)
from moviepy.audio.fx.all import audio_fadeout, volumex

from backend.state import AssetType, AssetState

# Output resolution
OUTPUT_WIDTH  = 1280
OUTPUT_HEIGHT = 720
OUTPUT_FPS    = 24

# Audio mix levels
MUSIC_VOLUME  = 0.12   # background music sits low under voice
VOICE_VOLUME  = 1.0


# ==============================================================
# Main compile function (called by pipeline.py via retry)
# ==============================================================

async def compile_video(project_dir: str, state: dict) -> dict:
    """
    Assemble all approved assets into a single output.mp4.
    Writes the full export package to /export/.
    Returns { "output_path": str } on success.
    Raises on failure (caught by retry wrapper).
    """
    # Run the blocking MoviePy work in a thread pool so we don't
    # block the async event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _compile_sync, project_dir, state
    )
    return result


def _compile_sync(project_dir: str, state: dict) -> dict:
    """Synchronous compilation worker. Runs in thread pool."""
    project_path = Path(project_dir)
    assets_dir   = project_path / "assets"
    export_dir   = project_path / "export"
    export_dir.mkdir(exist_ok=True)

    assets   = state.get("assets", [])
    format_  = state.get("format", "2min")
    title    = state.get("title", "output")

    # ── Gather approved assets by type ───────────────────────
    animations = _get_files(assets, AssetType.ANIMATION,
                            [AssetState.APPROVED, AssetState.DONE],
                            assets_dir)
    images     = _get_files(assets, AssetType.IMAGE,
                            [AssetState.ANIMATING],   # fallback if no animation yet
                            assets_dir)
    voice_files = _get_files(assets, AssetType.VOICE,
                             [AssetState.APPROVED, AssetState.DONE],
                             assets_dir)
    music_files = _get_files(assets, AssetType.MUSIC,
                             [AssetState.APPROVED, AssetState.DONE],
                             assets_dir)
    thumb_files = _get_files(assets, AssetType.THUMBNAIL,
                             [AssetState.THUMBNAIL],
                             assets_dir)

    print(f"[Compiler] Animations: {len(animations)}, "
          f"Images (fallback): {len(images)}, "
          f"Voice: {len(voice_files)}, Music: {len(music_files)}")

    # ── Build video clips ─────────────────────────────────────
    video_clips = []

    # Use shot list order if available, otherwise use file order
    shot_list = state.get("script", {}).get("shot_list", [])

    if shot_list and animations:
        # Map shot numbers to animation files where possible
        anim_map = _map_animations_to_shots(assets, animations)
        for shot in shot_list:
            shot_num = shot.get("shot_number", 0)
            clip_path = anim_map.get(shot_num)
            if clip_path:
                clip = _load_video_clip(clip_path)
            elif images:
                # Fallback: use a still image for this shot
                img_path = images[min(shot_num - 1, len(images) - 1)]
                duration = _estimate_shot_duration(
                    shot.get("narration", ""), format_
                )
                clip = ImageClip(str(img_path)).set_duration(duration)
                clip = clip.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT))
            else:
                continue
            video_clips.append(clip)
    else:
        # No shot list -- just use animations in order
        for path in animations:
            clip = _load_video_clip(path)
            video_clips.append(clip)
        # If still no clips, use static images
        if not video_clips:
            total_duration = _format_duration_seconds(format_)
            per_image = total_duration / max(len(images), 1)
            for path in images:
                clip = ImageClip(str(path)).set_duration(per_image)
                clip = clip.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT))
                video_clips.append(clip)

    if not video_clips:
        raise RuntimeError("No video clips available to compile.")

    # ── Concatenate video ─────────────────────────────────────
    print("[Compiler] Concatenating video clips...")
    final_video = concatenate_videoclips(video_clips, method="compose")

    # ── Build audio ───────────────────────────────────────────
    audio_tracks = []

    # Voiceover
    if voice_files:
        voice_clip = AudioFileClip(str(voice_files[0]))
        voice_clip = voice_clip.fx(volumex, VOICE_VOLUME)
        audio_tracks.append(voice_clip)

        # Trim or extend video to match voiceover length
        voice_duration = voice_clip.duration
        if final_video.duration < voice_duration:
            # Loop last clip to fill
            last_clip = video_clips[-1]
            needed = voice_duration - final_video.duration
            loops = int(needed / last_clip.duration) + 1
            extra = concatenate_videoclips([last_clip] * loops)
            extra = extra.subclip(0, needed)
            final_video = concatenate_videoclips(
                [final_video, extra], method="compose"
            )
        else:
            final_video = final_video.subclip(0, voice_duration)

    # Background music
    if music_files:
        music_clip = AudioFileClip(str(music_files[0]))
        video_dur  = final_video.duration

        # Loop music if shorter than video
        if music_clip.duration < video_dur:
            loops = int(video_dur / music_clip.duration) + 1
            music_clip = concatenate_audioclips([music_clip] * loops)

        music_clip = music_clip.subclip(0, video_dur)
        music_clip = music_clip.fx(volumex, MUSIC_VOLUME)
        # Fade out last 3 seconds
        fade_start = max(0, video_dur - 3)
        music_clip = music_clip.fx(audio_fadeout, 3)
        audio_tracks.append(music_clip)

    # Composite audio
    if audio_tracks:
        composite_audio = CompositeAudioClip(audio_tracks)
        final_video = final_video.set_audio(composite_audio)

    # ── Write output ──────────────────────────────────────────
    output_path = export_dir / "output.mp4"
    print(f"[Compiler] Writing {output_path}...")
    final_video.write_videofile(
        str(output_path),
        fps=OUTPUT_FPS,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile=str(export_dir / "temp_audio.m4a"),
        remove_temp=True,
        logger=None    # suppress verbose MoviePy output
    )

    # ── Copy thumbnail ────────────────────────────────────────
    thumb_path = None
    if thumb_files:
        import shutil
        thumb_src  = thumb_files[0]
        thumb_dest = export_dir / "thumbnail.jpg"
        shutil.copy2(str(thumb_src), str(thumb_dest))
        thumb_path = str(thumb_dest)

    # ── Write metadata ────────────────────────────────────────
    _write_export_metadata(export_dir, state)

    print(f"[Compiler] Done. Output: {output_path}")

    # Clean up MoviePy clips
    final_video.close()
    for c in video_clips:
        try: c.close()
        except: pass

    return {
        "output_path":   str(output_path),
        "thumbnail_path": thumb_path,
        "export_dir":    str(export_dir)
    }


# ==============================================================
# Export metadata writer
# ==============================================================

def _write_export_metadata(export_dir: Path, state: dict):
    """
    Write description.txt, tags.txt, and metadata.json
    to the export directory.
    """
    title       = state.get("title", "")
    description = state.get("description", "")
    tags        = state.get("script", {}).get("tags", [])
    sources     = state.get("sources", [])

    # Build description with credits block
    full_description = description.strip()
    if sources:
        full_description += "\n\n── Sources & Credits ──\n"
        for s in sources:
            line = f"{s['title']}: {s['url']}" if s.get("title") else s["url"]
            full_description += line + "\n"

    # description.txt
    with open(export_dir / "description.txt", "w", encoding="utf-8") as f:
        f.write(full_description)

    # tags.txt
    with open(export_dir / "tags.txt", "w", encoding="utf-8") as f:
        f.write(", ".join(tags))

    # metadata.json
    metadata = {
        "title":       title,
        "description": full_description,
        "tags":        tags,
        "sources":     sources
    }
    with open(export_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


# ==============================================================
# Internal helpers
# ==============================================================

def _get_files(assets: list, asset_type: str,
               states: list, assets_dir: Path) -> list:
    """Return sorted list of file paths for approved assets of a given type."""
    files = []
    for a in assets:
        if a.get("type") == asset_type and a.get("state") in states:
            filename = a.get("filename")
            if filename:
                path = assets_dir / filename
                if path.exists():
                    files.append(path)
    return sorted(files)


def _load_video_clip(path: Path):
    """Load a video clip and normalize resolution."""
    clip = VideoFileClip(str(path))
    if clip.size != [OUTPUT_WIDTH, OUTPUT_HEIGHT]:
        clip = clip.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT))
    return clip


def _map_animations_to_shots(assets: list,
                              animation_paths: list) -> dict:
    """
    Build a dict mapping shot_number -> animation file path.
    Uses the linked_image_id on animation assets to determine order.
    """
    mapping = {}
    anim_assets = [a for a in assets if a.get("type") == AssetType.ANIMATION
                   and a.get("state") in (AssetState.APPROVED, AssetState.DONE)]

    # Sort by asset_id as a proxy for shot order
    anim_assets.sort(key=lambda a: a.get("asset_id", 0))

    for i, asset in enumerate(anim_assets):
        shot_num = i + 1
        filename = asset.get("filename")
        if filename:
            # Find the matching path
            for p in animation_paths:
                if p.name == filename:
                    mapping[shot_num] = p
                    break

    return mapping


def _estimate_shot_duration(narration: str, format_: str) -> float:
    """
    Estimate duration for a still-image shot based on narration length.
    Assumes ~2.5 words per second of speech.
    Clamps between 3 and 30 seconds.
    """
    words = len(narration.split()) if narration.strip() else 0
    duration = words / 2.5
    return max(3.0, min(30.0, duration))


def _format_duration_seconds(format_: str) -> float:
    """Return total video duration in seconds for a given format."""
    return {
        "1min":  60.0,
        "2min":  120.0,
        "10min": 600.0,
        "15min": 900.0,
    }.get(format_, 120.0)
