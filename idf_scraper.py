import feedparser
import os
from datetime import datetime, timedelta
from newspaper import Article
import time

def cleanup_old_files(path, days=3):
    """מוחק קבצים שנוצרו לפני יותר מ-X ימים"""
    now = datetime.now()
    for filename in os.listdir(path):
        if filename.endswith(".md"):
            file_path = os.path.join(path, filename)
            file_time = datetime.fromtimestamp(os.path.getctime(file_path))
            if now - file_time > timedelta(days=days):
                os.remove(file_path)
                print(f"ניקוי: הקובץ {filename} הוסר כי הוא ישן.")

def scrape_news():
    path = 'content/news'
    os.makedirs(path, exist_ok=True)
    
    # ניקוי קבצים ישנים לפני שמתחילים
    cleanup_old_files(path)
    
    sources = {
        "וואלה": "https://rss.walla.co.il/feed/1",
        "ynet": "https://www.ynet.co.il/Integration/StoryRss1854.xml",
        "דובר צהל": "https://www.idf.il/RSS/hebrew/"
    }
    
    for name, url in sources.items():
        print(f"סורק את {name}...")
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            try:
                article = Article(entry.link, language='he')
                article.download()
                article.parse()
                
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{timestamp}-{os.urandom(2).hex()}.md"
                filepath = os.path.join(path, filename)
                
                content = f"""---
title: "{article.title}"
date: "{datetime.now().isoformat()}"
source: "{name}"
image: "{article.top_image}"
link: "{entry.link}"
---

{article.text}

---
**קרדיט:** התוכן פורסם במקור ב-{name}. [לכתבה המלאה]({entry.link})
"""
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"נשמר: {article.title}")
                time.sleep(1)
            except Exception as e:
                print(f"שגיאה: {e}")

if __name__ == "__main__":
    scrape_news()
