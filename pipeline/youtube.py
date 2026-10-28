"""Agent 7: publisher — uploads the finished episode to YouTube."""
import json
import os
from pathlib import Path

import requests


def _access_token():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"],
        "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"YouTube token refresh failed: {r.text[:300]}")
    return r.json()["access_token"]


def configured():
    return all(os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def upload(cfg, ep, video_path):
    token = _access_token()
    status = {
        "privacyStatus": cfg.get("youtube_privacy", "private"),
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
    }
    meta = {
        "snippet": {
            "title": ep["title"],
            "description": ep["description"] + "\n\n" + " ".join(f"#{t.replace(' ', '')}" for t in ep["tags"][:8]),
            "tags": ep["tags"][:15],
            "categoryId": str(cfg.get("youtube_category", "15")),
        },
        "status": status,
    }
    size = Path(video_path).stat().st_size
    url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
               "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)}
    r = requests.post(url, headers=headers, data=json.dumps(meta), timeout=60)
    if r.status_code == 400 and "containsSyntheticMedia" in r.text:
        status.pop("containsSyntheticMedia")
        r = requests.post(url, headers=headers, data=json.dumps(meta), timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"YouTube upload init failed: HTTP {r.status_code} {r.text[:300]}")
    with open(video_path, "rb") as f:
        up = requests.put(r.headers["Location"], data=f, timeout=1800,
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"})
    if up.status_code not in (200, 201):
        raise RuntimeError(f"YouTube upload failed: HTTP {up.status_code} {up.text[:300]}")
    vid = up.json()["id"]
    return {"id": vid, "url": f"https://youtube.com/shorts/{vid}",
            "studio": f"https://studio.youtube.com/video/{vid}/edit"}
