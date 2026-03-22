import feedparser
import os
import re
from datetime import datetime

# מקורות ה-RSS
rss_feeds = {
    "ynet": "https://www.ynet.co.il/Integration/StoryRss1854.xml",
    "וואלה": "https://rss.walla.co.il/feed/1",
    "דובר צהל": "https://www.idf.il/RSS/hebrew/",
    "אמס": "https://www.emess.co.il/feed/",
    "קורי": "https://www.kore.co.il/rss" # המקור החדש שביקשת
}

# תיקיות יעד
LIVE_DIR = "content/news"      # לאתר מיד (אמס)
PENDING_DIR = "content/pending" # להמתנה (השאר)

def sanitize_filename(title):
    # ניקוי תווים בעייתיים ושמירה על עברית
    return re.sub(r'[\\/*?:"<>|]', "", title).strip()[:50]

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

def fetch_news():
    # יצירת התיקיות אם הן לא קיימות
    for d in [LIVE_DIR, PENDING_DIR]:
        if not os.path.exists(d):
            os.makedirs(d)

    for source_name, url in rss_feeds.items():
        print(f"Fetching from {source_name}...")
        feed = feedparser.parse(url)
        
        # בחירת תיקיית יעד לפי המקור
        target_dir = LIVE_DIR if source_name == "אמס" else PENDING_DIR
        
        for entry in feed.entries[:10]:
            title = entry.get('title', 'ללא כותרת').strip().replace('"', "'")
            link = entry.get('link', '')
            description = entry.get('description', '')
            content = clean_html(description)
            image_url = extract_image(entry)
            
            filename = f"{sanitize_filename(title)}.md"
            filepath = os.path.join(target_dir, filename)
            
            # בדיקה אם הכתבה כבר קיימת באחת מהתיקיות (כדי למנוע כפילויות)
            if not os.path.exists(os.path.join(LIVE_DIR, filename)) and \
               not os.path.exists(os.path.join(PENDING_DIR, filename)):
                
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # פורמט שמתאים בול ל-Decap CMS
                md_content = f"""---
title: "{title}"
date: {date_str}
category: "חדשות"
source: "{source_name}"
image: "{image_url}"
---

{content}

[קרא את הכתבה המלאה במקור]({link})
"""
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(md_content)
                print(f"Saved to {target_dir}: {title}")

if __name__ == "__main__":
    fetch_news()
