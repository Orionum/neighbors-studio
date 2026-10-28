"""Agents 1–3: trend analyst, script writer and critic."""
import datetime as dt
import json
import re

from . import gemini


def _extract_json(text):
    """Pull the first JSON object out of a model reply."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    return json.loads(raw)


def analyst(cfg):
    """Agent 1: look up what animal shorts are working right now."""
    today = dt.date.today().isoformat()
    prompt = (
        f"Today is {today}. Search the web for what AI-generated and animated cat and dog "
        "short videos are getting views on YouTube Shorts and TikTok in the last few weeks. "
        "Also note any holidays, seasons or events in the next 7 days that a family-friendly "
        "pet comedy could play on. Reply with 6–10 short bullet points: everyday situations, "
        "formats and seasonal hooks. Only family-friendly ideas, no brands or famous characters."
    )
    resp = gemini.interact({
        "model": cfg["models"]["text"],
        "input": prompt,
        "tools": [{"type": "google_search"}],
    }, timeout=300)
    return gemini.text_of(resp)


SCHEMA = """{
  "branch": "cats" | "dogs" | "crossover",
  "title": "YouTube title, max 90 characters, ends with #shorts",
  "hook_text": "on-screen hook for the first 3 seconds, max 45 characters",
  "description": "2-3 sentence YouTube/TikTok description",
  "tags": ["8-12 short tags"],
  "acts": [
    {
      "characters": ["names from the cast that appear in this act, max 3"],
      "prompt": "Video prompt in English with timecodes like [0-3s] ... [3-6s] ... [6-10s] ... Describe actions, camera, expressions and sounds. No dialogue, no on-screen text."
    }
  ]
}"""


def _cast_line(cfg):
    return ", ".join(f"{n} ({c['family']})" for n, c in cfg["characters"].items())


def writer(cfg, bible, trends, history, feedback=None):
    """Agent 2: write the next episode as structured JSON."""
    past = [f"#{e['number']} [{e.get('branch','?')}] {e['title']}" for e in history[-40:]]
    branches = [e.get("branch") for e in history[-10:]]
    lang = "Russian" if cfg.get("language") == "ru" else "English"
    prompt = f"""You are the head writer of the animated shorts series below.

SERIES BIBLE:
{bible}

CAST (use exactly these names): {_cast_line(cfg)}

WHAT IS WORKING NOW (from the trend analyst):
{trends}

PAST EPISODES (never repeat these plots):
{chr(10).join(past) if past else "none yet - this is episode 1, introduce both families"}

Branches of the last 10 episodes: {branches}. Pick the branch that keeps the 3/3/4 balance.

Write episode #{len(history) + 1}. It has exactly {cfg['acts']} acts. Each act is about 8-10 seconds
and is generated as one video clip; act 2+ continues act 1 seamlessly. The twist lands in the
last act, followed by a short reaction shot. Title, hook_text, description and tags in {lang}.
Video prompts always in English.
{"CRITIC FEEDBACK TO FIX: " + feedback if feedback else ""}

Reply with ONLY a JSON object in this shape:
{SCHEMA}"""
    resp = gemini.interact({"model": cfg["models"]["text"], "input": prompt}, timeout=300)
    ep = _extract_json(gemini.text_of(resp))
    validate(ep, cfg)
    return ep


def critic(cfg, bible, ep):
    """Agent 3: score the script before money is spent on video."""
    prompt = f"""You are a strict short-form video editor. Score this episode script from 1 to 10
for: a strong hook in the first 3 seconds, a clear story with no words, a real surprise twist,
consistency with the bible, and following the hard rules. Any hard-rule violation = score 1.

BIBLE:
{bible}

SCRIPT:
{json.dumps(ep, ensure_ascii=False, indent=2)}

Reply with ONLY JSON: {{"score": <int>, "issues": "<what to fix, one paragraph>"}}"""
    resp = gemini.interact({"model": cfg["models"]["text"], "input": prompt}, timeout=300)
    return _extract_json(gemini.text_of(resp))


def validate(ep, cfg):
    for key in ("branch", "title", "hook_text", "description", "tags", "acts"):
        if key not in ep:
            raise ValueError(f"script is missing '{key}'")
    if len(ep["acts"]) != cfg["acts"]:
        raise ValueError(f"expected {cfg['acts']} acts, got {len(ep['acts'])}")
    for act in ep["acts"]:
        unknown = [c for c in act.get("characters", []) if c not in cfg["characters"]]
        if unknown:
            raise ValueError(f"unknown characters: {unknown}")
        if not act.get("prompt"):
            raise ValueError("an act has an empty prompt")
        act["characters"] = act.get("characters", [])[:3]
    ep["hook_text"] = ep["hook_text"][:60]
    ep["title"] = ep["title"][:100]


def write_episode(cfg, bible, history, log):
    trends = analyst(cfg)
    log(f"Тренды:\n{trends[:1500]}")
    ep = None
    for attempt in range(3):
        try:
            ep = writer(cfg, bible, trends, history)
            break
        except (ValueError, json.JSONDecodeError) as e:
            log(f"Сценарий не прошёл проверку формата ({e}), пишу заново")
    if ep is None:
        raise RuntimeError("writer failed to produce a valid script 3 times")
    if cfg.get("critic_enabled", True):
        review = critic(cfg, bible, ep)
        log(f"Оценка критика: {review.get('score')} — {review.get('issues', '')[:500]}")
        if int(review.get("score", 10)) < int(cfg.get("critic_min_score", 7)):
            try:
                ep = writer(cfg, bible, trends, history, feedback=review.get("issues", ""))
                log("Сценарий переписан по замечаниям критика")
            except (ValueError, json.JSONDecodeError) as e:
                log(f"Переписать не вышло ({e}), оставляю первую версию")
        ep["critic"] = review
    ep["trends"] = trends
    return ep


def fake_episode(cfg, history):
    """Offline script for test runs (no API calls)."""
    return {
        "branch": "crossover",
        "title": f"Neighbors #{len(history) + 1}: Test episode #shorts",
        "hook_text": "When your new neighbors are dogs",
        "description": "Test run of the pipeline.",
        "tags": ["cats", "dogs", "neighbors"],
        "acts": [{"characters": ["Boris", "Rex"], "prompt": "[0-3s] test"} for _ in range(cfg["acts"])],
        "trends": "dry run",
    }
