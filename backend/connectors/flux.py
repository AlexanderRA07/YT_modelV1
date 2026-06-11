# ==============================================================
# backend/connectors/flux.py
# Image generation via Flux running locally in ComfyUI.
# Calls the ComfyUI API over localhost.
# ==============================================================

import random
import os
import uuid
import asyncio
import httpx
import json
from pathlib import Path

COMFYUI_HOST = os.getenv("COMFYUI_HOST", "http://127.0.0.1:8188")
OUTPUT_TIMEOUT = 300   # seconds to wait for ComfyUI to finish a job


# ==============================================================
# Main generation function
# ==============================================================

async def generate_image(prompt: str, asset_id: int,
                          output_dir: str = None) -> dict:
    """
    Generate an image via Flux/ComfyUI.

    Parameters
    ----------
    prompt     : text prompt for the image
    asset_id   : numeric asset id (used to name the output file)
    output_dir : directory to save the image (defaults to current dir)

    Returns
    -------
    { "filename": "image{asset_id}.jpg", "path": "/full/path/to/image.jpg" }
    """
    workflow = _build_workflow(prompt)
    client_id = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=30) as client:
        # Queue the prompt
        response = await client.post(
            f"{COMFYUI_HOST}/prompt",
            json={"prompt": workflow, "client_id": client_id}
        )
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]

    # Poll until the job is complete
    output_images = await _wait_for_output(prompt_id, client_id)

    if not output_images:
        raise RuntimeError(
            f"ComfyUI returned no images for prompt_id={prompt_id}"
        )

    # Download the first output image
    image_data = await _download_image(output_images[0])

    # Save to disk
    filename = f"image{asset_id}.jpg"
    save_path = Path(output_dir) / filename if output_dir else Path(filename)
    save_path.write_bytes(image_data)

    return {
        "filename": filename,
        "path":     str(save_path)
    }


# ==============================================================
# ComfyUI workflow builder
# ==============================================================

def _build_workflow(prompt: str) -> dict:
    """
    Build a minimal Flux workflow dict for ComfyUI.
    This is a basic txt2img workflow using the Flux model.
    Adjust node ids and model names to match your ComfyUI setup.

    To customize: export a workflow from ComfyUI in API format
    (enable dev mode in settings, then 'Save (API Format)') and
    replace this structure with your exported workflow.
    """
    return {
        "6": {
            "inputs": {
                "text": _style_wrap(prompt),
                "clip": ["11", 0]
            },
            "class_type": "CLIPTextEncode"
        },
        "8": {
            "inputs": {
                "samples": ["13", 0],
                "vae": ["10", 0]
            },
            "class_type": "VAEDecode"
        },
        "9": {
            "inputs": {
                "filename_prefix": "flux_output",
                "images": ["8", 0]
            },
            "class_type": "SaveImage"
        },
        "10": {
            "inputs": {
                "vae_name": "ae.safetensors"
            },
            "class_type": "VAELoader"
        },
        "11": {
            "inputs": {
                "clip_name1": "t5xxl_fp8_e4m3fn.safetensors",
                "clip_name2": "clip_l.safetensors",
                "type": "flux"
            },
            "class_type": "DualCLIPLoader"
        },
        "13": {
            "inputs": {
                "noise": ["25", 0],
                "guider": ["22", 0],
                "sampler": ["16", 0],
                "sigmas": ["17", 0],
                "latent_image": ["27", 0]
            },
            "class_type": "SamplerCustomAdvanced"
        },
        "16": {
            "inputs": {
                "sampler_name": "euler"
            },
            "class_type": "KSamplerSelect"
        },
        "17": {
            "inputs": {
                "scheduler": "simple",
                "steps": 28,
                "denoise": 1,
                "model": ["30", 0]
            },
            "class_type": "BasicScheduler"
        },
        "22": {
            "inputs": {
                "model": ["30", 0],
                "conditioning": ["6", 0]
            },
            "class_type": "BasicGuider"
        },
        "25": {
            "inputs": {
                "noise_seed": random.randint(0, 2**32 - 1)
            },
            "class_type": "RandomNoise"
        },
        "27": {
            "inputs": {
                "width": 1280,
                "height": 720,
                "batch_size": 1
            },
            "class_type": "EmptySD3LatentImage"
        },
        "30": {
            "inputs": {
                "unet_name": "flux1-dev/flux1-dev.safetensors",
                "weight_dtype": "fp8_e4m3fn"
            },
            "class_type": "UNETLoader"
        }
    }


def _style_wrap(prompt: str) -> str:
    """
    Wrap the raw prompt with a watercolor/oil paint style directive.
    This is the default aesthetic for this project.
    Modify to match your preferred style.
    """
    return (
        f"watercolor painting of {prompt}, "
        "traditional watercolor illustration, soft wet brushstrokes, "
        "painterly edges, visible paper texture, muted earthy tones, "
        "NOT photorealistic, NOT photograph, NOT 3D render"
    )


# ==============================================================
# ComfyUI polling and download helpers
# ==============================================================

async def _wait_for_output(prompt_id: str,
                            client_id: str) -> list:
    """
    Poll the ComfyUI /history endpoint until the job is complete.
    Returns list of output image references.
    """
    poll_interval = 2  # seconds between polls
    elapsed = 0

    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < OUTPUT_TIMEOUT:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            resp = await client.get(
                f"{COMFYUI_HOST}/history/{prompt_id}"
            )
            resp.raise_for_status()
            history = resp.json()

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                images = []
                for node_output in outputs.values():
                    if "images" in node_output:
                        images.extend(node_output["images"])
                return images

    raise TimeoutError(
        f"ComfyUI job {prompt_id} did not complete within {OUTPUT_TIMEOUT}s"
    )


async def _download_image(image_ref: dict) -> bytes:
    """
    Download an output image from ComfyUI by its reference dict.
    image_ref format: { "filename": "...", "subfolder": "...", "type": "output" }
    """
    params = {
        "filename":  image_ref["filename"],
        "subfolder": image_ref.get("subfolder", ""),
        "type":      image_ref.get("type", "output")
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{COMFYUI_HOST}/view", params=params
        )
        resp.raise_for_status()
        return resp.content


# ==============================================================
# Health check
# ==============================================================

async def is_available() -> bool:
    """Return True if ComfyUI is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{COMFYUI_HOST}/system_stats")
            return resp.status_code == 200
    except Exception:
        return False
