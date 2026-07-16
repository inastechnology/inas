#!/usr/bin/env python3
"""Generate the canonical plant-action illustrations with the local Krea 2 workflow."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "data" / "plant_action_image_jobs.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "src" / "ina_device_hub" / "static" / "plant-actions"
DEFAULT_SERVERS = ("http://127.0.0.1:8188", "http://host.docker.internal:8188")


def main():
    parser = argparse.ArgumentParser(description="Generate plant action illustrations through ComfyUI Krea 2.")
    parser.add_argument("--server", help="ComfyUI base URL. Auto-detected when omitted.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--only", action="append", default=[], help="Generate only this job name. Repeatable.")
    args = parser.parse_args()

    server = args.server.rstrip("/") if args.server else detect_server()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    style = str(manifest.get("style") or "").strip()
    jobs = [job for job in manifest.get("jobs", []) if isinstance(job, dict)]
    if args.only:
        selected = set(args.only)
        jobs = [job for job in jobs if job.get("name") in selected]
    if not jobs:
        raise SystemExit("No plant action image jobs were selected.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for job in jobs:
        generate_job(server, style, job, output_dir)


def detect_server():
    for server in DEFAULT_SERVERS:
        try:
            request_json(f"{server}/system_stats", timeout=3)
            return server
        except (OSError, ValueError):
            continue
    raise SystemExit("ComfyUI is not reachable on 127.0.0.1:8188 or host.docker.internal:8188.")


def generate_job(server: str, style: str, job: dict, output_dir: Path):
    name = required_string(job, "name")
    subject = required_string(job, "prompt")
    prompt = f"{style} {subject}".strip()
    workflow = krea2_workflow(prompt, int(job.get("seed", 0)), name)
    response = request_json(
        f"{server}/prompt",
        data=json.dumps({"client_id": str(uuid.uuid4()), "prompt": workflow}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    prompt_id = str(response.get("prompt_id") or "")
    if not prompt_id:
        raise SystemExit(f"ComfyUI did not return a prompt id for {name}: {response}")
    print(f"[krea2-image] queued {name}: {prompt_id}", flush=True)
    output = wait_for_output(server, prompt_id)
    image_bytes = request_bytes(f"{server}/view?{urllib.parse.urlencode(output)}", timeout=60)

    png_path = output_dir / f"{name}.png"
    webp_path = output_dir / f"{name}.webp"
    png_path.write_bytes(image_bytes)
    if shutil.which("ffmpeg"):
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(png_path), "-c:v", "libwebp", "-quality", "82", "-compression_level", "6", str(webp_path)],
            check=True,
        )
        png_path.unlink()
        final_path = webp_path
    else:
        final_path = png_path
    print(f"[krea2-image] wrote {final_path}", flush=True)


def krea2_workflow(prompt: str, seed: int, name: str):
    return {
        "10": {"class_type": "UNETLoader", "inputs": {"unet_name": "krea2_turbo_fp8_scaled.safetensors", "weight_dtype": "default"}},
        "11": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors", "type": "krea2", "device": "default"}},
        "12": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["11", 0], "text": prompt}},
        "13": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 768, "batch_size": 1}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["10", 0],
                "positive": ["6", 0],
                "negative": ["13", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": 8,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["12", 0]}},
        "29": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": f"inas/plant-actions/{name}"}},
    }


def wait_for_output(server: str, prompt_id: str):
    for _ in range(180):
        history = request_json(f"{server}/history/{prompt_id}", timeout=20)
        record = history.get(prompt_id) if isinstance(history, dict) else None
        if isinstance(record, dict):
            status = record.get("status") if isinstance(record.get("status"), dict) else {}
            if status.get("status_str") == "error":
                raise SystemExit(f"ComfyUI generation failed for {prompt_id}: {status.get('messages')}")
            images = ((record.get("outputs") or {}).get("29") or {}).get("images") or []
            if images:
                image = images[0]
                return {"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")}
        time.sleep(2)
    raise SystemExit(f"Timed out waiting for ComfyUI prompt {prompt_id}.")


def required_string(value: dict, key: str):
    text = str(value.get(key) or "").strip()
    if not text:
        raise SystemExit(f"Manifest job is missing {key}.")
    return text


def request_json(url: str, *, data=None, headers=None, timeout=20):
    payload = request_bytes(url, data=data, headers=headers, timeout=timeout)
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object from {url}")
    return value


def request_bytes(url: str, *, data=None, headers=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


if __name__ == "__main__":
    main()
