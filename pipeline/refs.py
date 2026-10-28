"""Agent 4 (one-off): character designer — reference images for each hero."""
from pathlib import Path

from . import gemini

CHAR_DIR = Path("characters")


def ref_path(name):
    return CHAR_DIR / f"{name}.png"


def missing(cfg):
    return [n for n in cfg["characters"] if not ref_path(n).exists()]


def generate(cfg, names, log):
    CHAR_DIR.mkdir(exist_ok=True)
    made = []
    for name in names:
        c = cfg["characters"][name]
        prompt = (
            f"{cfg['style']} Character reference sheet for an animated series: {c['prompt']}. "
            f"The character's name is {name}. A single character, full body, three-quarter "
            "front view, friendly neutral pose, centered, plain soft light background, "
            "no text, no other characters."
        )
        resp = gemini.interact({
            "model": cfg["models"]["image"],
            "input": prompt,
            "response_format": {"type": "image", "aspect_ratio": "1:1", "image_size": "1K"},
        }, timeout=300)
        blocks = gemini.outputs(resp, "image")
        if not blocks:
            raise gemini.GeminiError(f"no image returned for {name}")
        gemini.save_media(blocks[-1], ref_path(name))
        log(f"Эталон готов: {name}")
        made.append(ref_path(name))
    return made
