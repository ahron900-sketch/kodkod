import feedparser
import os
from datetime import datetime
from newspaper import Article

def scrape_news():
    path = 'content/news'
    os.makedirs(path, exist_ok=True)
    
    sources = {
        "ynet": "https://www.ynet.co.il/Integration/StoryRss1854.xml",
        "דובר צהל": "https://www.idf.il/RSS/hebrew/",
        "וואלה": "https://rss.walla.co.il/feed/1"
    }
    
    for name, url in sources.items():
        print(f"סורק את {name}...")
        feed = feedparser.parse(url)
        
        for entry in feed.entries[:5]: # 5 כתבות אחרונות מכל מקור
            try:
                # שימוש ב-newspaper3k כדי להביא את הכתבה המלאה
                article = Article(entry.link, language='he')
                article.download()
                article.parse()
                
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{timestamp}-{name.replace(' ', '_')}.md"
                filepath = os.path.join(path, filename)
                
                # בניית התוכן עם קרדיט ותמונה מקורית
                content = f"""---
title: "{article.title}"
date: "{datetime.now().isoformat()}"
source: "{name}"
image: "{article.top_image}"
link: "{entry.link}"
---

{article.text}

---
**קרדיט:** פורסם במקור ב-{name}. [לכתבה המלאה לחצו כאן]({entry.link})
"""
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"נשמר: {article.title}")
                
            except Exception as e:
                print(f"שגיאה בחילוץ כתבה מ-{name}: {e}")

if __name__ == "__main__":
    scrape_news()
