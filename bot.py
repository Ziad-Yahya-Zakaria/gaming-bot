#!/usr/bin/env python3
"""
🎮 Gaming News & YouTube Telegram Bot — Railway Edition
"""

import feedparser
import json
import asyncio
import logging
import os
from pathlib import Path
from telegram import Bot
from telegram.error import TelegramError
from telegram.constants import ParseMode

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

SEEN_FILE = "seen_items.json"

# ─── Config من Environment Variables ────────────────────────────────────────

def get_config():
    return {
        "telegram_token":        os.environ.get("TELEGRAM_TOKEN", ""),
        "channel_id":            os.environ.get("CHANNEL_ID", ""),
        "check_interval_minutes": int(os.environ.get("CHECK_INTERVAL", "15")),
        "news_feeds": [
            {"name": "IGN",      "url": "https://feeds.feedburner.com/ign/all",        "emoji": "🎮"},
            {"name": "GameSpot", "url": "https://www.gamespot.com/feeds/mashup/",       "emoji": "🕹️"},
            {"name": "Kotaku",   "url": "https://kotaku.com/rss",                       "emoji": "🎯"},
            {"name": "PCGamer",  "url": "https://www.pcgamer.com/rss/",                 "emoji": "🖥️"},
            {"name": "Polygon",  "url": "https://www.polygon.com/rss/index.xml",        "emoji": "📰"},
        ],
        "youtube_channels": json.loads(os.environ.get("YOUTUBE_CHANNELS", "[]"))
    }

# ─── Seen Items ──────────────────────────────────────────────────────────────

def load_seen():
    if Path(SEEN_FILE).exists():
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen)[-2000:], f)

# ─── Fetchers ────────────────────────────────────────────────────────────────

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

# ─── Formatter ───────────────────────────────────────────────────────────────

def format_message(item):
    def esc(t):
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    title  = esc(item["title"])
    source = esc(item["source"])
    link   = item["link"]

    if item["type"] == "youtube":
        return f"{item['emoji']} <b>فيديو جديد!</b>\n📺 <b>القناة:</b> {source}\n🎬 {title}\n\n🔗 {link}"
    else:
        return f"{item['emoji']} <b>خبر جديد!</b>\n📰 <b>المصدر:</b> {source}\n📝 {title}\n\n🔗 {link}"

# ─── Main Loop ───────────────────────────────────────────────────────────────

async def check_and_post(bot, config, seen):
    new_seen  = set(seen)
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
                    parse_mode=ParseMode.HTML,
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

async def run_bot():
    config = get_config()

    if not config["telegram_token"]:
        log.error("❌ TELEGRAM_TOKEN مش موجود!")
        return
    if not config["channel_id"]:
        log.error("❌ CHANNEL_ID مش موجود!")
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

if __name__ == "__main__":
    asyncio.run(run_bot())
