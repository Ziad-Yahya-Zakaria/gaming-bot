#!/usr/bin/env python3
"""
🎮 Gaming News & YouTube Telegram Bot
يشتغل على Render مع web server صغير عشان ميناموش
"""

import feedparser
import json
import asyncio
import logging
import os
from pathlib import Path
from threading import Thread
from flask import Flask
from telegram import Bot
from telegram.error import TelegramError
from telegram.constants import ParseMode

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ─── Flask App (عشان Render ميناموش) ────────────────────────────────────────
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "🎮 Gaming Bot is running!", 200

@flask_app.route("/health")
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# ─── Config من Environment Variables أو config.json ─────────────────────────
SEEN_FILE = "seen_items.json"

def get_config():
    """بياخد الإعدادات من Environment Variables (الأأمن على Render)"""
    return {
        "telegram_token": os.environ.get("TELEGRAM_TOKEN", ""),
        "channel_id":     os.environ.get("CHANNEL_ID", ""),
        "check_interval_minutes": int(os.environ.get("CHECK_INTERVAL", "15")),
        "news_feeds": [
            {"name": "IGN",      "url": "https://feeds.feedburner.com/ign/all",          "emoji": "🎮"},
            {"name": "GameSpot", "url": "https://www.gamespot.com/feeds/mashup/",         "emoji": "🕹️"},
            {"name": "Kotaku",   "url": "https://kotaku.com/rss",                         "emoji": "🎯"},
            {"name": "PCGamer",  "url": "https://www.pcgamer.com/rss/",                   "emoji": "🖥️"},
            {"name": "Polygon",  "url": "https://www.polygon.com/rss/index.xml",          "emoji": "📰"},
        ],
        "youtube_channels": json.loads(os.environ.get("YOUTUBE_CHANNELS", "[]"))
    }

# ─── Helpers ────────────────────────────────────────────────────────────────

def load_seen():
    if Path(SEEN_FILE).exists():
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    trimmed = list(seen)[-2000:]
    with open(SEEN_FILE, "w") as f:
        json.dump(trimmed, f)

# ─── Feed Fetchers ───────────────────────────────────────────────────────────

def fetch_news(feed):
    try:
        parsed = feedparser.parse(feed["url"])
        return [
            {
                "id":     e.get("id") or e.get("link"),
                "title":  e.get("title", "بدون عنوان"),
                "link":   e.get("link", ""),
                "source": feed["name"],
                "emoji":  feed.get("emoji", "📰"),
                "type":   "news"
            }
            for e in parsed.entries[:5]
        ]
    except Exception as ex:
        log.error(f"خطأ في {feed['name']}: {ex}")
        return []

def fetch_youtube(channel):
    try:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['channel_id']}"
        parsed = feedparser.parse(url)
        return [
            {
                "id":     e.get("yt_videoid") or e.get("id"),
                "title":  e.get("title", "بدون عنوان"),
                "link":   e.get("link", ""),
                "source": channel["name"],
                "emoji":  channel.get("emoji", "▶️"),
                "type":   "youtube"
            }
            for e in parsed.entries[:5]
        ]
    except Exception as ex:
        log.error(f"خطأ في قناة {channel['name']}: {ex}")
        return []

# ─── Message Formatter ───────────────────────────────────────────────────────

def escape_md(text):
    """Escape special chars for MarkdownV2"""
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text

def format_message(item):
    title = escape_md(item["title"])
    source = escape_md(item["source"])
    link = item["link"]
    if item["type"] == "youtube":
        return f"{item['emoji']} *فيديو جديد\\!*\n📺 *القناة:* {source}\n🎬 {title}\n\n🔗 {link}"
    else:
        return f"{item['emoji']} *خبر جديد\\!*\n📰 *المصدر:* {source}\n📝 {title}\n\n🔗 {link}"

# ─── Main Bot Loop ───────────────────────────────────────────────────────────

async def check_and_post(bot, config, seen):
    new_seen = set(seen)
    all_items = []

    for feed in config["news_feeds"]:
        all_items.extend(fetch_news(feed))
    for ch in config["youtube_channels"]:
        all_items.extend(fetch_youtube(ch))

    posted = 0
    for item in all_items:
        iid = item["id"]
        if iid and iid not in seen:
            try:
                await bot.send_message(
                    chat_id=config["channel_id"],
                    text=format_message(item),
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=False
                )
                new_seen.add(iid)
                posted += 1
                log.info(f"✅ [{item['source']}] {item['title'][:60]}")
                await asyncio.sleep(2)
            except TelegramError as e:
                log.error(f"خطأ تيليجرام: {e}")

    log.info(f"📤 {posted} جديد." if posted else "🔍 مفيش جديد.")
    return new_seen

async def bot_loop():
    config = get_config()

    if not config["telegram_token"]:
        log.error("❌ TELEGRAM_TOKEN مش موجود في Environment Variables!")
        return
    if not config["channel_id"]:
        log.error("❌ CHANNEL_ID مش موجود في Environment Variables!")
        return

    bot      = Bot(token=config["telegram_token"])
    interval = config["check_interval_minutes"] * 60
    seen     = load_seen()

    me = await bot.get_me()
    log.info(f"🚀 البوت شغّال! @{me.username}")

    while True:
        log.info("⏰ بيتشيك...")
        seen = await check_and_post(bot, config, seen)
        save_seen(seen)
        log.info(f"😴 هيستنى {config['check_interval_minutes']} دقيقة...")
        await asyncio.sleep(interval)

# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # شغّل Flask في thread منفصل
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    log.info("🌐 Web server شغّال...")

    # شغّل البوت
    asyncio.run(bot_loop())
