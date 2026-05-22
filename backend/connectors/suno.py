# ==============================================================
# backend/connectors/suno.py
# Background music generation via the Suno API.
#
# NOTE: Suno's API is in beta and details may change.
# This connector targets the unofficial/community Suno API pattern.
# If the official API becomes available, update the endpoint and
# auth pattern here -- the rest of the pipeline is unaffected.
# ==============================================================

import os
import asyncio
import httpx
from pathlib import Path

SUNO_API_KEY   = os.getenv("SUNO_API_KEY")
SUNO_BASE_URL  = "https://studio-api.suno.ai/api"

POLL_INTERVAL  = 10   # seconds between status polls
JOB_TIMEOUT    = 300  # 5 minutes max wait


# ==============================================================
# Main generation function
# ==============================================================

async def generate_music(prompt: str, asset_id: int,
                          output_dir: str = None) -> dict:
    """
    Generate background music from a text prompt using Suno.

    Parameters
    ----------
    prompt     : description of the desired music mood/style
    asset_id   : numeric asset id (used to name the output file)
    output_dir : directory to save the audio file

    Returns
    -------
    { "filename": "music{asset_id}.mp3", "path": "/full/path/..." }
    """
    if not SUNO_API_KEY:
        raise EnvironmentError("SUNO_API_KEY is not set in .env")

    headers = {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type":  "application/json"
    }

    body = {
        "prompt":           _music_wrap(prompt),
        "make_instrumental": True,   # no vocals -- background music only
        "wait_audio":        False   # async job
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{SUNO_BASE_URL}/generate",
            headers=headers,
            json=body
        )
        resp.raise_for_status()
        data = resp.json()

    # Extract job id -- Suno returns a list of clip objects
    clips = data if isinstance(data, list) else data.get("clips", [data])
    if not clips:
        raise RuntimeError(f"Suno returned no clips. Response: {data}")

    clip_id = clips[0].get("id")
    if not clip_id:
        raise RuntimeError(f"Suno clip has no id. Response: {clips[0]}")

    # Poll for audio URL
    audio_url = await _poll_for_audio(clip_id, headers)

    # Download
    audio_bytes = await _download_audio(audio_url)

    # Save to disk
    filename = f"music{asset_id}.mp3"
    save_path = Path(output_dir) / filename if output_dir else Path(filename)
    save_path.write_bytes(audio_bytes)

    return {
        "filename": filename,
        "path":     str(save_path)
    }


# ==============================================================
# Prompt wrapper
# ==============================================================

def _music_wrap(prompt: str) -> str:
    """
    Ensure the music prompt targets ambient/background style.
    """
    return (
        f"{prompt}. "
        "Instrumental only. Ambient, atmospheric background music. "
        "No lyrics. Subtle and unobtrusive. Cinematic mood."
    )


# ==============================================================
# Polling helper
# ==============================================================

async def _poll_for_audio(clip_id: str, headers: dict) -> str:
    """
    Poll Suno's clip status until audio is ready.
    Returns the audio URL.
    """
    elapsed = 0

    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < JOB_TIMEOUT:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            resp = await client.get(
                f"{SUNO_BASE_URL}/feed/?ids={clip_id}",
                headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

            clips = data if isinstance(data, list) else [data]
            clip = next((c for c in clips if c.get("id") == clip_id), None)

            if not clip:
                continue

            status = clip.get("status")

            if status == "complete":
                url = clip.get("audio_url")
                if url:
                    return url
                raise RuntimeError(
                    f"Suno clip {clip_id} complete but no audio_url. "
                    f"Response: {clip}"
                )
            elif status in ("error", "failed"):
                raise RuntimeError(
                    f"Suno clip {clip_id} failed. Response: {clip}"
                )

    raise TimeoutError(
        f"Suno clip {clip_id} did not complete within {JOB_TIMEOUT}s"
    )


# ==============================================================
# Download helper
# ==============================================================

async def _download_audio(url: str) -> bytes:
    """Download audio from a URL and return raw bytes."""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


# ==============================================================
# Health check
# ==============================================================

async def is_available() -> bool:
    """Return True if Suno API key is set."""
    # Suno doesn't have a lightweight ping endpoint in beta
    # so we just verify the key is configured
    return bool(SUNO_API_KEY)
