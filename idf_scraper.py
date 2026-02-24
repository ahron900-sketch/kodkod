import feedparser
import os
import re
from datetime import datetime

# מקורות ה-RSS (כולל אמס ללא שום סינון)
rss_feeds = {
    "ynet": "https://www.ynet.co.il/Integration/StoryRss1854.xml",
    "וואלה": "https://rss.walla.co.il/feed/1",
    "דובר צהל": "https://www.idf.il/RSS/hebrew/",
    "אמס": "https://www.emess.co.il/feed/"
}

# תיקיית היעד לכתבות הממתינות לאישור
OUTPUT_DIR = "content/pending"

def sanitize_filename(title):
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
    return "None"

def fetch_news():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    for source_name, url in rss_feeds.items():
        print(f"Fetching from {source_name}...")
        feed = feedparser.parse(url)
        
        for entry in feed.entries[:10]:
            title = entry.get('title', 'ללא כותרת').strip()
            title = title.replace('"', "'")
            
            link = entry.get('link', '')
            description = entry.get('description', '')
            content = clean_html(description)
            
            image_url = extract_image(entry)
            
            # ללא סינון! פשוט שומרים את הקובץ
            filename = f"{sanitize_filename(title)}.md"
            filepath = os.path.join(OUTPUT_DIR, filename)
            
            if not os.path.exists(filepath):
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
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
                print(f"Saved: {title}")

if __name__ == "__main__":
    fetch_news()
