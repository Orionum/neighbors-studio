"""Agent 5: director — turns acts into video clips with Gemini Omni Flash."""
import subprocess
from pathlib import Path

from . import gemini, refs

AUDIO_RULES = (
    "Sound design: cartoon animal vocalizations (meows, purrs, barks, whines), "
    "comedic sound effects and light playful background music. No human speech, "
    "no dialogue, no narration, no on-screen text, no subtitles, no logos."
)
REF_RULE = ("Use the given images as references for the characters' appearance. "
            "The images should not be used as literal initial frames.")


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip() or 0)


def _inputs(cfg, act, extend):
    names = act["characters"]
    parts = [gemini.image_part(refs.ref_path(n)) for n in names]
    cast = ", ".join(f"{n} is shown in <IMAGE_REF_{i}>" for i, n in enumerate(names))
    head = ("Extend this video: the scene continues seamlessly with the same characters, "
            "same location and same style. " if extend else "")
    text = (f"{head}{cfg['style']} Vertical 9:16 cartoon short. "
            f"{('Characters: ' + cast + '. ') if names else ''}"
            f"{act['prompt']} {AUDIO_RULES} {REF_RULE if names else ''}")
    return parts + [{"type": "text", "text": text}]


def generate(cfg, ep, workdir, log):
    """Returns a list of clip paths to concatenate in order."""
    workdir = Path(workdir)
    fmt = {"type": "video", "aspect_ratio": "9:16",
           "resolution": cfg.get("video_resolution", "720p"), "delivery": "uri"}
    clips, prev_id, prev_dur = [], None, 0.0
    for i, act in enumerate(ep["acts"]):
        body = {"model": cfg["models"]["video"], "input": _inputs(cfg, act, extend=i > 0),
                "response_format": fmt}
        if prev_id:
            body["previous_interaction_id"] = prev_id
        log(f"Генерирую акт {i + 1}/{len(ep['acts'])}…")
        resp = gemini.interact(body, timeout=1200)
        blocks = gemini.outputs(resp, "video")
        if not blocks:
            raise gemini.GeminiError(f"no video returned for act {i + 1}: {str(resp)[:300]}")
        path = workdir / f"act{i + 1}.mp4"
        gemini.save_media(blocks[-1], path)
        dur = duration(path)
        log(f"Акт {i + 1}: {dur:.1f} с")
        # An extension may come back as the whole video (longer than before)
        # or only as the new part. Keep whichever makes a continuous episode.
        if i > 0 and dur >= prev_dur + 2:
            clips = [path]
        else:
            clips.append(path)
        prev_id = resp.get("id")
        prev_dur = sum(duration(c) for c in clips)
    return clips


def fake_clips(cfg, workdir):
    """Offline colored test clips with a tone (for test runs)."""
    clips = []
    for i, color in zip(range(cfg["acts"]), ["orange", "skyblue", "pink", "khaki"]):
        p = Path(workdir) / f"act{i + 1}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=720x1280:d=4:r=24",
            "-f", "lavfi", "-i", f"sine=frequency={440 + 110 * i}:duration=4",
            "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", str(p)],
            check=True)
        clips.append(p)
    return clips
