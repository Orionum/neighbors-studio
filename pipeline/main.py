"""Entry point: python -m pipeline.main --mode daily|refs|test"""
import argparse
import datetime as dt
import json
import sys
import traceback
from pathlib import Path

import yaml

from . import assemble, refs, telegram, video, writer, youtube

ROOT = Path(".")
HISTORY = ROOT / "data" / "history.json"
EPISODES = ROOT / "data" / "episodes"
OUTPUT = ROOT / "output"


def log(msg):
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def load_history():
    if HISTORY.exists():
        return json.loads(HISTORY.read_text(encoding="utf-8")).get("episodes", [])
    return []


def save_history(episodes):
    HISTORY.parent.mkdir(exist_ok=True)
    HISTORY.write_text(json.dumps({"episodes": episodes}, ensure_ascii=False, indent=2), encoding="utf-8")


def run_refs(cfg, regenerate=False):
    names = list(cfg["characters"]) if regenerate else refs.missing(cfg)
    if not names:
        log("Все эталоны персонажей уже есть")
        return
    made = refs.generate(cfg, names, log)
    for p in made:
        telegram.send_photo(p, f"Эталон персонажа: {p.stem}")
    telegram.send_message(
        "Эталоны персонажей готовы. Если кто-то не нравится — удалите его файл в папке "
        "characters на GitHub и запустите режим refs ещё раз.")


def run_daily(cfg, dry_run=False):
    if not cfg.get("enabled", True):
        log("Конвейер на паузе (enabled: false)")
        return
    history = load_history()
    number = len(history) + 1
    work = OUTPUT / f"work_{number:03d}"
    work.mkdir(parents=True, exist_ok=True)
    bible = (ROOT / "bible.md").read_text(encoding="utf-8")

    if not dry_run and refs.missing(cfg):
        log("Нет эталонов персонажей — создаю")
        run_refs(cfg)

    log(f"Пишу серию #{number}")
    ep = writer.fake_episode(cfg, history) if dry_run else writer.write_episode(cfg, bible, history, log)
    ep["number"] = number
    ep["date"] = dt.date.today().isoformat()
    log(f"Сценарий: {ep['title']}")

    clips = video.fake_clips(cfg, work) if dry_run else video.generate(cfg, ep, work, log)
    final = OUTPUT / f"episode_{number:03d}.mp4"
    assemble.assemble(clips, ep["hook_text"], final, work)
    log(f"Монтаж готов: {final} ({video.duration(final):.1f} с)")

    yt = None
    if youtube.configured() and not dry_run:
        yt = youtube.upload(cfg, ep, final)
        ep["youtube"] = yt
        log(f"Загружено на YouTube: {yt['url']}")

    if not dry_run:
        EPISODES.mkdir(parents=True, exist_ok=True)
        (EPISODES / f"{number:03d}.json").write_text(json.dumps(ep, ensure_ascii=False, indent=2), encoding="utf-8")
        history.append({"number": number, "date": ep["date"], "branch": ep["branch"], "title": ep["title"],
                        "youtube": (yt or {}).get("url")})
        save_history(history)

    lines = [f"Серия #{number} готова: {ep['title']}"]
    if yt:
        lines.append(f"YouTube: загружена ({cfg.get('youtube_privacy')}). "
                     f"Опубликовать: {yt['studio']}")
    lines.append("Для TikTok: сохраните видео и опубликуйте с пометкой «Создано ИИ».")
    lines.append(f"Описание:\n{ep['description']}\n" + " ".join("#" + t.replace(" ", "") for t in ep["tags"][:6]))
    telegram.send_video(final, "\n\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="daily", choices=["daily", "refs", "refs-all", "test"])
    args = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    try:
        if args.mode == "daily":
            run_daily(cfg)
        elif args.mode == "refs":
            run_refs(cfg)
        elif args.mode == "refs-all":
            run_refs(cfg, regenerate=True)
        else:
            run_daily(cfg, dry_run=True)
    except Exception as e:  # report every failure to the owner
        traceback.print_exc()
        telegram.send_message(f"Конвейер «Соседи»: ошибка в режиме {args.mode}.\n{type(e).__name__}: {str(e)[:1500]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
