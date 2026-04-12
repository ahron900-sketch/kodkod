import feedparser
import os
import re
import time
import shutil
from datetime import datetime

# מקורות ה-RSS הממוקדים - מוגדרים לשאיבה ישירה לאתר
rss_feeds = {
    "אמס": "https://www.emess.co.il/feed/",
    "כיכר השבת": "https://www.kikar.co.il/rss",
    "כל רגע": "https://93fm.co.il/feed/"
}

# תיקיות יעד (נתיבים בתוך ה-Repository שלך)
LIVE_DIR = "content/news"
PENDING_DIR = "content/pending"
ARCHIVE_DIR = "content/archive"

def sanitize_filename(title):
    # ניקוי שם הקובץ מתווים אסורים ושמירה על אורך תקני
    clean_name = re.sub(r'[\\/*?:"<>|]', "", title).strip()[:50]
    return clean_name if clean_name else "untitled"

def clean_html(raw_html):
    if not raw_html: return ""
    # הסרת תגיות HTML כדי להשאיר טקסט נקי בלבד
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html).strip()

def extract_image(entry):
    # ניסיון לשלוף תמונה ממספר מקורות אפשריים ב-RSS (Media, Enclosure, Links)
    if 'media_content' in entry and len(entry.media_content) > 0:
        return entry.media_content[0]['url']
    if 'links' in entry:
        for link in entry.links:
            if 'image' in link.get('type', ''):
                return link.href
    if 'enclosures' in entry and len(entry.enclosures) > 0:
        return entry.enclosures[0].get('url', "")
    return ""

def manage_archive():
    # העברת קבצים ישנים לארכיון כדי לשמור על ביצועי האתר
    now = time.time()
    for d in [LIVE_DIR, PENDING_DIR]:
        if not os.path.exists(d): os.makedirs(d)
        for f in os.listdir(d):
            f_path = os.path.join(d, f)
            if os.path.isfile(f_path) and f != ".gitkeep":
                # אם הקובץ ישן מ-3 ימים, הוא עובר לארכיון
                if os.stat(f_path).st_mtime < now - 3 * 86400:
                    if not os.path.exists(ARCHIVE_DIR): os.makedirs(ARCHIVE_DIR)
                    try:
                        shutil.move(f_path, os.path.join(ARCHIVE_DIR, f))
                    except: pass

def fetch_news():
    # ראשית, ננקה קבצים ישנים
    manage_archive()

    for source_name, url in rss_feeds.items():
        print(f"מתחיל שאיבה מ-{source_name}...")
        feed = feedparser.parse(url)
        
        # הגדרה שכל המקורות האלו הולכים ישירות לתיקיית החדשות הפעילה
        target_dir = LIVE_DIR
        
        # שואב את 15 הידיעות האחרונות מכל אתר
        for entry in feed.entries[:15]:
            title = entry.get('title', 'ללא כותרת').strip().replace("\n", " ")
            link = entry.get('link', '')
            content = clean_html(entry.get('description', ''))
            image_url = extract_image(entry)
            
            filename = f"{sanitize_filename(title)}.md"
            
            # בדיקה אם הידיעה כבר קיימת (בחדשות, בהמתנה או בארכיון) כדי למנוע כפילויות
            exists = any(os.path.exists(os.path.join(d, filename)) for d in [LIVE_DIR, PENDING_DIR, ARCHIVE_DIR])
            
            if not exists:
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # יצירת קובץ המארקדאון בפורמט שהאתר שלך מכיר (Frontmatter)
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
                # כתיבת הקובץ
                with open(os.path.join(target_dir, filename), "w", encoding="utf-8") as f:
                    f.write(md_content)
                print(f"נשמר: {title}")

if __name__ == "__main__":
    fetch_news()
