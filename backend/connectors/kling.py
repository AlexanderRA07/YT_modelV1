# ==============================================================
# backend/connectors/kling.py
# Animation generation via the Kling API.
# Takes an approved image and animates it.
# ==============================================================

import os
import asyncio
import httpx
from pathlib import Path

KLING_API_KEY = os.getenv("KLING_API_KEY")
KLING_BASE_URL = "https://api.klingai.com/v1"

POLL_INTERVAL = 10    # seconds between status checks
JOB_TIMEOUT   = 600   # 10 minutes max wait for a video job


# ==============================================================
# Main generation function
# ==============================================================

async def generate_animation(prompt: str, asset_id: int,
                              output_dir: str = None,
                              image_path: str = None) -> dict:
    """
    Animate an image using Kling's image-to-video API.

    Parameters
    ----------
    prompt      : motion/animation prompt describing how the image should move
    asset_id    : numeric asset id (used to name the output file)
    output_dir  : directory to save the video
    image_path  : path to the source image file to animate

    Returns
    -------
    { "filename": "animation{asset_id}.mp4", "path": "/full/path/..." }
    """
    if not KLING_API_KEY:
        raise EnvironmentError("KLING_API_KEY is not set in .env")

    headers = {
        "Authorization": f"Bearer {KLING_API_KEY}",
        "Content-Type":  "application/json"
    }

    # Build request body
    body = {
        "prompt":   _motion_wrap(prompt),
        "duration": "5",       # seconds, adjust as needed
        "mode":     "standard" # "standard" or "pro"
    }

    # Attach image as base64 if provided
    if image_path and Path(image_path).exists():
        import base64
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        body["image"] = image_b64

    async with httpx.AsyncClient(timeout=30) as client:
        # Submit job
        resp = await client.post(
            f"{KLING_BASE_URL}/videos/image2video",
            headers=headers,
            json=body
        )
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("data", {}).get("task_id") or data.get("task_id")

        if not task_id:
            raise RuntimeError(f"Kling did not return a task_id. Response: {data}")

    # Poll for completion
    video_url = await _poll_for_completion(task_id, headers)

    # Download video
    video_bytes = await _download_video(video_url)

    # Save to disk
    filename = f"animation{asset_id}.mp4"
    save_path = Path(output_dir) / filename if output_dir else Path(filename)
    save_path.write_bytes(video_bytes)

    return {
        "filename": filename,
        "path":     str(save_path)
    }


# ==============================================================
# Prompt wrapper
# ==============================================================

def _motion_wrap(prompt: str) -> str:
    """
    Add motion guidance to the animation prompt.
    Keeps motion subtle to match the painterly aesthetic.
    """
    return (
        f"{prompt}. "
        "Gentle, slow motion. Subtle camera drift. "
        "Painterly style preserved. Cinematic and calm."
    )


# ==============================================================
# Polling helper
# ==============================================================

async def _poll_for_completion(task_id: str, headers: dict) -> str:
    """
    Poll Kling's task status endpoint until the video is ready.
    Returns the download URL of the completed video.
    """
    elapsed = 0

    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < JOB_TIMEOUT:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

            resp = await client.get(
                f"{KLING_BASE_URL}/videos/image2video/{task_id}",
                headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

            task_data = data.get("data", data)
            status = task_data.get("task_status") or task_data.get("status")

            if status in ("succeed", "completed", "done"):
                # Extract video URL from response
                works = task_data.get("task_result", {}).get("videos", [])
                if works:
                    return works[0].get("url")
                # Fallback key names
                url = (task_data.get("video_url")
                       or task_data.get("result", {}).get("url"))
                if url:
                    return url
                raise RuntimeError(
                    f"Kling job {task_id} completed but no video URL found. "
                    f"Response: {data}"
                )

            elif status in ("failed", "error"):
                raise RuntimeError(
                    f"Kling job {task_id} failed. Response: {data}"
                )

            # Still processing -- continue polling

    raise TimeoutError(
        f"Kling job {task_id} did not complete within {JOB_TIMEOUT}s"
    )


# ==============================================================
# Download helper
# ==============================================================

async def _download_video(url: str) -> bytes:
    """Download a video file from a URL and return raw bytes."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


# ==============================================================
# Health check
# ==============================================================

async def is_available() -> bool:
    """Return True if the Kling API key is set and the endpoint is reachable."""
    if not KLING_API_KEY:
        return False
    try:
        headers = {"Authorization": f"Bearer {KLING_API_KEY}"}
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{KLING_BASE_URL}/videos/image2video",
                headers=headers
            )
            return resp.status_code in (200, 401, 403, 404)
    except Exception:
        return False
