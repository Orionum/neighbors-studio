"""Notifications to the owner's Telegram (video file + links)."""
import os

import requests


def _url(method):
    return f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/{method}"


def configured():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN"))


def chat_id():
    cid = os.environ.get("TELEGRAM_CHAT_ID")
    if cid:
        return cid
    # Fallback: the last chat that messaged the bot (send /start to it once).
    r = requests.get(_url("getUpdates"), timeout=30).json()
    for upd in reversed(r.get("result", [])):
        msg = upd.get("message") or upd.get("channel_post")
        if msg:
            return str(msg["chat"]["id"])
    raise RuntimeError("Send /start to your bot in Telegram, then run again")


def send_message(text):
    if not configured():
        print(text)
        return
    requests.post(_url("sendMessage"), timeout=30, data={
        "chat_id": chat_id(), "text": text[:4000], "disable_web_page_preview": True})


def send_video(path, caption):
    if not configured():
        print(caption)
        return
    with open(path, "rb") as f:
        r = requests.post(_url("sendVideo"), timeout=600,
                          data={"chat_id": chat_id(), "caption": caption[:1000], "supports_streaming": True},
                          files={"video": f})
    if r.status_code != 200:  # files over 50 MB or other issue: send a note instead
        send_message(caption + "\n\n(Видео не отправилось в Telegram, скачайте его в GitHub → Actions.)")


def send_photo(path, caption):
    if not configured():
        print(caption)
        return
    with open(path, "rb") as f:
        requests.post(_url("sendPhoto"), timeout=120,
                      data={"chat_id": chat_id(), "caption": caption[:1000]}, files={"photo": f})
