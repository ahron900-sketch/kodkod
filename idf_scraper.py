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
LIVE_DIR = "content/news"      # לאתר מיד (אמס)
PENDING_DIR = "content/pending" # להמתנה (השאר)
ARCHIVE_DIR = "content/archive" # ארכיון לקבצים ישנים

def sanitize_filename(title):
    # ניקוי תווים למערכת הקבצים
    clean_name = re.sub(r'[\\/*?:"<>|]', "", title).strip()[:50]
    return clean_name if clean_name else "untitled"

def clean_for_yml(text):
    # הסרת מירכאות כפולות שמשבשות את ה-CMS
    return text.replace('"', "'").replace("\n", " ")

def clean_html(raw_html):
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
    # העברת קבצים ישנים מ-pending לארכיון כדי לשמור על מהירות האדמין
    now = time.time()
    if not os.path.exists(ARCHIVE_DIR):
        os.makedirs(ARCHIVE_DIR)
    
    for f in os.listdir(PENDING_DIR):
        f_path = os.path.join(PENDING_DIR, f)
        if os.path.isfile(f_path) and f != ".gitkeep":
            # אם הקובץ נוצר לפני יותר מ-3 ימים
            if os.stat(f_path).st_mtime < now - 3 * 86400:
                shutil.move(f_path, os.path.join(ARCHIVE_DIR, f))
                print(f"Archived: {f}")

def fetch_news():
    # יצירת התיקיות
    for d in [LIVE_DIR, PENDING_DIR, ARCHIVE_DIR]:
        if not os.path.exists(d):
            os.makedirs(d)

    # ניקוי ארכיון לפני תחילת העבודה
    manage_archive()

    for source_name, url in rss_feeds.items():
        print(f"Fetching from {source_name}...")
        feed = feedparser.parse(url)
        
        target_dir = LIVE_DIR if source_name == "אמס" else PENDING_DIR
        
        for entry in feed.entries[:10]:
            raw_title = entry.get('title', 'ללא כותרת').strip()
            title = clean_for_yml(raw_title)
            
            link = entry.get('link', '')
            description = entry.get('description', '')
            content = clean_html(description)
            image_url = extract_image(entry)
            
            filename = f"{sanitize_filename(title)}.md"
            filepath = os.path.join(target_dir, filename)
            
            # בדיקה אם הכתבה קיימת בחדשות, בהמתנה או בארכיון
            if not any(os.path.exists(os.path.join(d, filename)) for d in [LIVE_DIR, PENDING_DIR, ARCHIVE_DIR]):
                
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                md_content = f"""---
title: "{title}"
date: "{date_str}"
category: "חדשות"
source: "{source_name}"
image: "{image_url}"
link: "{link}"
---

{content}

[קרא את הכתבה המלאה במקור]({link})
"""
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(md_content)
                print(f"Saved: {title}")

if __name__ == "__main__":
    fetch_news()
