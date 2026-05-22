# ==============================================================
# backend/connectors/elevenlabs.py
# Voiceover generation via the ElevenLabs API.
# ==============================================================

import os
import httpx
from pathlib import Path

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"

# Voice settings -- adjust to taste
VOICE_SETTINGS = {
    "stability":        0.5,   # 0.0-1.0: lower = more expressive
    "similarity_boost": 0.8,   # 0.0-1.0: higher = closer to original voice
    "style":            0.2,   # 0.0-1.0: speaking style exaggeration
    "use_speaker_boost": True
}

MODEL_ID = "eleven_multilingual_v2"


# ==============================================================
# Main generation function
# ==============================================================

async def generate_voice(prompt: str, asset_id: int,
                          output_dir: str = None) -> dict:
    """
    Generate voiceover audio from script text using ElevenLabs.

    Parameters
    ----------
    prompt     : the full script text to convert to speech
    asset_id   : numeric asset id (used to name the output file)
    output_dir : directory to save the audio file

    Returns
    -------
    { "filename": "voice{asset_id}.mp3", "path": "/full/path/..." }
    """
    if not ELEVENLABS_API_KEY:
        raise EnvironmentError("ELEVENLABS_API_KEY is not set in .env")
    if not ELEVENLABS_VOICE_ID:
        raise EnvironmentError("ELEVENLABS_VOICE_ID is not set in .env")

    headers = {
        "xi-api-key":   ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept":       "audio/mpeg"
    }

    body = {
        "text":           _clean_script(prompt),
        "model_id":       MODEL_ID,
        "voice_settings": VOICE_SETTINGS
    }

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{ELEVENLABS_BASE_URL}/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers=headers,
            json=body
        )
        resp.raise_for_status()
        audio_bytes = resp.content

    # Save to disk
    filename = f"voice{asset_id}.mp3"
    save_path = Path(output_dir) / filename if output_dir else Path(filename)
    save_path.write_bytes(audio_bytes)

    return {
        "filename": filename,
        "path":     str(save_path)
    }


# ==============================================================
# Script cleaner
# ==============================================================

def _clean_script(script: str) -> str:
    """
    Strip visual cue markers and tags section before sending to TTS.
    ElevenLabs should only receive the spoken narration text.
    """
    import re
    # Remove [VISUAL: ...] markers
    cleaned = re.sub(r'\[VISUAL:.*?\]', '', script, flags=re.IGNORECASE)
    # Remove tags section
    cleaned = cleaned.split("---TAGS---")[0]
    # Collapse excessive whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


# ==============================================================
# List available voices (utility)
# ==============================================================

async def list_voices() -> list:
    """
    Return list of available voices on this ElevenLabs account.
    Useful for finding the right ELEVENLABS_VOICE_ID to put in .env.
    """
    if not ELEVENLABS_API_KEY:
        raise EnvironmentError("ELEVENLABS_API_KEY is not set in .env")

    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{ELEVENLABS_BASE_URL}/voices",
            headers=headers
        )
        resp.raise_for_status()
        voices = resp.json().get("voices", [])

    return [
        {
            "voice_id": v["voice_id"],
            "name":     v["name"],
            "category": v.get("category", "")
        }
        for v in voices
    ]


# ==============================================================
# Health check
# ==============================================================

async def is_available() -> bool:
    """Return True if ElevenLabs API key is set and the endpoint responds."""
    if not ELEVENLABS_API_KEY:
        return False
    try:
        headers = {"xi-api-key": ELEVENLABS_API_KEY}
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{ELEVENLABS_BASE_URL}/voices",
                headers=headers
            )
            return resp.status_code == 200
    except Exception:
        return False
