"""Agent 6: editor — joins clips, adds the hook caption, normalizes sound."""
import subprocess
import textwrap
from pathlib import Path

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _font():
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    raise FileNotFoundError("No bold font found; install fonts-dejavu-core")


def _has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                          "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    return bool(out.stdout.strip())


def _run(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def normalize(src, dst):
    """1080x1920, 30 fps, stereo AAC; adds silence if the clip has no sound."""
    vf = ("scale=1080:1920:force_original_aspect_ratio=decrease,"
          "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,format=yuv420p")
    if _has_audio(src):
        _run(["-i", str(src), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-c:a", "aac", "-ar", "44100", "-ac", "2", str(dst)])
    else:
        _run(["-i", str(src), "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest",
              "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-c:a", "aac", "-ar", "44100", "-ac", "2", str(dst)])


def assemble(clips, hook_text, out_path, workdir):
    workdir = Path(workdir)
    norm = []
    for i, c in enumerate(clips):
        n = workdir / f"norm{i}.mp4"
        normalize(c, n)
        norm.append(n)
    listfile = workdir / "list.txt"
    listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in norm))
    joined = workdir / "joined.mp4"
    _run(["-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(joined)])

    caption = workdir / "hook.txt"
    caption.write_text("\n".join(textwrap.wrap(hook_text, width=20)) or " ", encoding="utf-8")
    draw = (f"drawtext=fontfile='{_font()}':textfile='{caption}':fontsize=68:fontcolor=white:"
            "line_spacing=12:box=1:boxcolor=black@0.55:boxborderw=28:"
            "x=(w-text_w)/2:y=h*0.14:enable='between(t,0,3.2)'")
    _run(["-i", str(joined), "-vf", draw, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
          "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out_path)])
    return out_path
