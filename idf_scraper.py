import feedparser
import os
import re
import time
import shutil
from datetime import datetime

# מקורות ה-RSS
rss_feeds = {
    "ynet": "https://www.ynet.co.il/Integration/StoryRss1854.xml",
    "וואלה": "https://rss.walla.co.il/feed/1",
    "דובר צהל": "https://www.idf.il/RSS/hebrew/",
    "אמס": "https://www.emess.co.il/feed/",
    "קורי": "https://www.kore.co.il/rss"
}

# תיקיות יעד
LIVE_DIR = "content/news"
PENDING_DIR = "content/pending"
ARCHIVE_DIR = "content/archive"

def sanitize_filename(title):
    clean_name = re.sub(r'[\\/*?:"<>|]', "", title).strip()[:50]
    return clean_name if clean_name else "untitled"

def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

def extract_image(entry):
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0]['url']
    if 'links' in entry:
        for link in entry.links:
            if 'image' in link.get('type', ''):
                return link.href
    return ""

def manage_archive():
    # שומר על ה-CMS מהיר - מעביר ישנים לארכיון
    now = time.time()
    for d in [LIVE_DIR, PENDING_DIR]:
        if not os.path.exists(d): os.makedirs(d)
        for f in os.listdir(d):
            f_path = os.path.join(d, f)
            if os.path.isfile(f_path) and f != ".gitkeep":
                # מעביר לארכיון אחרי 3 ימים
                if os.stat(f_path).st_mtime < now - 3 * 86400:
                    if not os.path.exists(ARCHIVE_DIR): os.makedirs(ARCHIVE_DIR)
                    shutil.move(f_path, os.path.join(ARCHIVE_DIR, f))

def fetch_news():
    manage_archive()

    for source_name, url in rss_feeds.items():
        print(f"מושך מ-{source_name}...")
        feed = feedparser.parse(url)
        target_dir = LIVE_DIR if source_name == "אמס" else PENDING_DIR
        
        for entry in feed.entries[:10]:
            title = entry.get('title', 'ללא כותרת').strip().replace("\n", " ")
            link = entry.get('link', '')
            content = clean_html(entry.get('description', ''))
            image_url = extract_image(entry)
            
            filename = f"{sanitize_filename(title)}.md"
            
            # בדיקה אם קיים כבר
            exists = any(os.path.exists(os.path.join(d, filename)) for d in [LIVE_DIR, PENDING_DIR, ARCHIVE_DIR])
            
            if not exists:
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # פורמט חסין שגיאות (YAML Block Scalar)
                md_content = f"""---
title: >-
  {title}
date: "{date_str}"
source: "{source_name}"
image: "{image_url}"
link: "{link}"
category: "חדשות"
---

{content}

[קרא את הכתבה המלאה במקור]({link})
"""
                with open(os.path.join(target_dir, filename), "w", encoding="utf-8") as f:
                    f.write(md_content)
                print(f"נשמר: {title}")

if __name__ == "__main__":
    fetch_news()
