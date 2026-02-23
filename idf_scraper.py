import feedparser
import os
from datetime import datetime

def scrape_news():
    # יצירת נתיב התיקייה
    path = 'content/news'
    os.makedirs(path, exist_ok=True)
    
    # קובץ בדיקה כדי לוודא שהבוט כותב לתיקייה
    with open(os.path.join(path, 'bot-status.md'), 'w', encoding='utf-8') as f:
        f.write(f"---\ntitle: \"סטטוס בוט\"\n---\nעודכן לאחרונה: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    # מקורות ה-RSS
    sources = {
        "ynet": "https://www.ynet.co.il/Integration/StoryRss1854.xml",
        "דובר צהל": "https://www.idf.il/RSS/hebrew/"
    }
    
    for name, url in sources.items():
        print(f"סורק את {name}...")
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                # יצירת שם קובץ ייחודי ובטוח
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                clean_title = "".join(x for x in entry.title if x.isalnum() or x == ' ')[:30]
                filename = f"{timestamp}-{name.replace(' ', '_')}.md"
                filepath = os.path.join(path, filename)
                
                content = f"""---
title: "{entry.title}"
date: "{datetime.now().isoformat()}"
source: "{name}"
link: "{entry.link}"
---

{entry.get('summary', 'לחצו על הקישור לקריאת הידיעה המלאה.')}

[לכתבה המלאה ב-{name}]({entry.link})
"""
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"נשמר בהצלחה: {filename}")
        except Exception as e:
            print(f"שגיאה בסריקת {name}: {e}")

if __name__ == "__main__":
    scrape_news()
