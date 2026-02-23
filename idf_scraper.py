import feedparser
import os
from datetime import datetime
from newspaper import Article
import time

def scrape_news():
    path = 'content/news'
    os.makedirs(path, exist_ok=True)
    
    # מקורות ה-RSS שאתה רוצה
    sources = {
        "ynet": "https://www.ynet.co.il/Integration/StoryRss1854.xml",
        "דובר צהל": "https://www.idf.il/RSS/hebrew/",
        "וואלה": "https://rss.walla.co.il/feed/1"
    }
    
    for name, url in sources.items():
        print(f"סורק את {name}...")
        feed = feedparser.parse(url)
        
        # לוקח את 5 הכתבות הכי חדשות מכל מקור
        for entry in feed.entries[:5]:
            try:
                # שאיבת הכתבה המלאה והתמונה המקורית
                article = Article(entry.link, language='he')
                article.download()
                article.parse()
                
                # יצירת שם קובץ ייחודי
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                safe_title = "".join(x for x in name if x.isalnum())
                filename = f"{timestamp}-{safe_title}-{os.urandom(2).hex()}.md"
                filepath = os.path.join(path, filename)
                
                # בניית התוכן עם התמונה המקורית (article.top_image)
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
                print(f"נשמר בהצלחה: {article.title}")
                
                # הפסקה קצרה כדי לא לחסום את הבוט
                time.sleep(1)
                
            except Exception as e:
                print(f"שגיאה בחילוץ כתבה מ-{name}: {e}")

if __name__ == "__main__":
    scrape_news()
