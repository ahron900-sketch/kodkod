import feedparser
import os
import re
import time
import shutil
from datetime import datetime

# מקורות RSS - ישראל + עולם, ממוינים לקטגוריות
rss_feeds = {
    # חדשות חרדיות / ישראל
    "אמס": ("https://www.emess.co.il/feed/", "חרדים"),
    "כיכר השבת": ("https://www.kikar.co.il/rss", "חרדים"),
    "כל רגע": ("https://93fm.co.il/feed/", "חרדים"),
    "בחדרי חרדים": ("https://www.bhol.co.il/feed", "חרדים"),
    "ynet": ("https://www.ynet.co.il/Integration/StoryRss2.xml", "חדשות"),
    "וואלה חדשות": ("https://rss.walla.co.il/feed/1?type=main", "חדשות"),
    "מאקו": ("https://www.mako.co.il/rss/news-israel.xml", "חדשות"),
    "כאן חדשות": ("https://www.kan.org.il/rss/rss.aspx?FolderName=Web-Israel", "חדשות"),
    "גלובס": ("https://www.globes.co.il/webservice/rss/rssfeeder.asmx/FeederNode?iID=585", "כלכלה"),
    "כלכליסט": ("https://www.calcalist.co.il/GeneralRSS/0,16335,L-8,00.xml", "כלכלה"),
    "ynet ספורט": ("https://www.ynet.co.il/Integration/StoryRss1539.xml", "ספורט"),

    # חדשות עולם (אנגלית)
    "BBC World": ("http://feeds.bbci.co.uk/news/world/rss.xml", "עולם"),
    "CNN World": ("http://rss.cnn.com/rss/edition_world.rss", "עולם"),
    "Reuters World": ("https://feeds.reuters.com/Reuters/worldNews", "עולם"),
    "Al Jazeera": ("https://www.aljazeera.com/xml/rss/all.xml", "עולם"),
    "NY Times World": ("https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "עולם"),
    "The Guardian World": ("https://www.theguardian.com/world/rss", "עולם"),

    # טכנולוגיה
    "TechCrunch": ("https://techcrunch.com/feed/", "טכנולוגיה"),
    "The Verge": ("https://www.theverge.com/rss/index.xml", "טכנולוגיה"),
    "Geektime": ("https://www.geektime.co.il/feed/", "טכנולוגיה"),

    # ספורט עולם
    "BBC Sport": ("http://feeds.bbci.co.uk/sport/rss.xml", "ספורט"),
    "ESPN": ("https://www.espn.com/espn/rss/news", "ספורט"),
}

# ערוצי יוטיוב - נשאבים כווידאו דרך YouTube RSS (אין צורך במפתח API)
youtube_channels = {
    # channel_id: (display name, category)
    "UCeY0bbntWzzVIaj2z3QigXg": ("NBC News", "עולם"),
    "UCknLrEdhRCp1aegoMqRaCZg": ("DW News", "עולם"),
    "UCupvZG-5ko_eiXAupbDfxWw": ("CNN", "עולם"),
}

LIVE_DIR = "content/news"
PENDING_DIR = "content/pending"
ARCHIVE_DIR = "content/archive"

def sanitize_filename(title):
    clean_name = re.sub(r'[\\/*?:"<>|]', "", title).strip()[:50]
    return clean_name if clean_name else "untitled"

def clean_html(raw_html):
    if not raw_html:
        return ""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

def extract_image(entry):
    if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
        return entry.media_thumbnail[0].get('url', "")
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0].get('url', "")
    if 'links' in entry:
        for link in entry.links:
            if 'image' in link.get('type', ''):
                return link.href
    if 'enclosures' in entry and len(entry.enclosures) > 0:
        return entry.enclosures[0].get('url', "")
    # fall back to first <img> found in the description HTML
    desc = entry.get('description', '') or entry.get('summary', '')
    m = re.search(r'<img[^>]+src="([^"]+)"', desc)
    if m:
        return m.group(1)
    return ""

def manage_archive():
    now = time.time()
    for d in [LIVE_DIR, PENDING_DIR]:
        if not os.path.exists(d):
            os.makedirs(d)
        for f in os.listdir(d):
            f_path = os.path.join(d, f)
            if os.path.isfile(f_path) and f != ".gitkeep":
                if os.stat(f_path).st_mtime < now - 3 * 86400:
                    if not os.path.exists(ARCHIVE_DIR):
                        os.makedirs(ARCHIVE_DIR)
                    try:
                        shutil.move(f_path, os.path.join(ARCHIVE_DIR, f))
                    except Exception:
                        pass

def save_article(title, link, content, image_url, source_name, category, video_id=""):
    filename = f"{sanitize_filename(title)}.md"
    exists = any(os.path.exists(os.path.join(d, filename)) for d in [LIVE_DIR, PENDING_DIR, ARCHIVE_DIR])
    if exists:
        return
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    video_line = f'\nvideo_id: "{video_id}"' if video_id else ""
    md_content = f"""---
title: >-
  {title}
date: "{date_str}"
source: "{source_name}"
image: "{image_url}"
link: "{link}"
category: "{category}"{video_line}
---

{content}

[קרא את הכתבה המלאה במקור]({link})
"""
    with open(os.path.join(LIVE_DIR, filename), "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"נשמר: {title}")


def fetch_news():
    manage_archive()

    for source_name, (url, category) in rss_feeds.items():
        print(f"מתחיל שאיבה מ-{source_name}...")
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"שגיאה בשאיבה מ-{source_name}: {e}")
            continue

        for entry in feed.entries[:15]:
            title = entry.get('title', 'ללא כותרת').strip().replace("\n", " ")
            link = entry.get('link', '')
            content = clean_html(entry.get('description', '') or entry.get('summary', ''))
            image_url = extract_image(entry)
            save_article(title, link, content, image_url, source_name, category)

    for channel_id, (source_name, category) in youtube_channels.items():
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        print(f"מתחיל שאיבת וידאו מ-{source_name}...")
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"שגיאה בשאיבת וידאו מ-{source_name}: {e}")
            continue

        for entry in feed.entries[:10]:
            title = entry.get('title', 'ללא כותרת').strip().replace("\n", " ")
            link = entry.get('link', '')
            video_id = entry.get('yt_videoid', '')
            content = clean_html(entry.get('summary', ''))
            image_url = extract_image(entry)
            save_article(title, link, content, image_url, source_name, category, video_id=video_id)


if __name__ == "__main__":
    fetch_news()
