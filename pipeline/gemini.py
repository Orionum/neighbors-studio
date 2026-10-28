"""Thin REST client for the Gemini Interactions API (text, image, video)."""
import base64
import os
import re
import time

import requests

API = "https://generativelanguage.googleapis.com/v1beta"


class GeminiError(Exception):
    pass


def _headers():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set")
    return {"x-goog-api-key": key, "Content-Type": "application/json"}


def interact(body, timeout=900, retries=3):
    """POST /interactions with retries on transient errors."""
    err = "unknown error"
    for attempt in range(retries):
        try:
            r = requests.post(f"{API}/interactions", headers=_headers(), json=body, timeout=timeout)
        except requests.RequestException as e:
            err = f"network error: {e}"
        else:
            if r.status_code == 200:
                return r.json()
            err = f"HTTP {r.status_code}: {r.text[:800]}"
            if r.status_code in (400, 401, 403, 404):
                raise GeminiError(err)
        time.sleep(30 * (attempt + 1))
    raise GeminiError(err)


def outputs(resp, kind):
    """Collect model_output content blocks of a given type (text/image/video)."""
    items = []
    for step in resp.get("steps", []) or []:
        if step.get("type") == "model_output":
            for block in step.get("content", []) or []:
                if block.get("type") == kind:
                    items.append(block)
    if not items:
        conv = resp.get({"text": "output_text", "image": "output_image", "video": "output_video"}[kind])
        if isinstance(conv, dict):
            items.append(conv)
        elif isinstance(conv, str) and kind == "text":
            items.append({"type": "text", "text": conv})
    return items


def text_of(resp):
    return "\n".join(b.get("text", "") for b in outputs(resp, "text")).strip()


def image_part(path):
    mime = "image/png" if str(path).lower().endswith(".png") else "image/jpeg"
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return {"type": "image", "data": data, "mime_type": mime}


def _file_state(fid):
    r = requests.get(f"{API}/files/{fid}", headers=_headers(), timeout=60)
    r.raise_for_status()
    state = r.json().get("state")
    if isinstance(state, dict):
        state = state.get("name")
    return str(state or "")


def save_media(block, path):
    """Write an image/video block to disk (inline base64 or Files API uri)."""
    if block.get("data"):
        with open(path, "wb") as f:
            f.write(base64.b64decode(block["data"]))
        return path
    uri = block.get("uri")
    if not uri:
        raise GeminiError("media block has neither data nor uri")
    m = re.search(r"files/([^/:?]+)", uri)
    if not m:
        raise GeminiError(f"cannot parse file id from {uri}")
    fid = m.group(1)
    for _ in range(180):  # up to 15 minutes
        state = _file_state(fid)
        if state == "ACTIVE":
            break
        if state == "FAILED":
            raise GeminiError("generation failed while processing the file")
        time.sleep(5)
    else:
        raise GeminiError("timed out waiting for the video file")
    r = requests.get(f"{API}/files/{fid}:download", params={"alt": "media"},
                     headers=_headers(), timeout=900, stream=True)
    r.raise_for_status()
    with open(path, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    return path
