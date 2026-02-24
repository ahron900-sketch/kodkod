import feedparser
import os
from datetime import datetime
from newspaper import Article
import time

# רשימת מילים שחייבות להופיע (אחת מהן לפחות)
ALLOWED_KEYWORDS = ['ביטחון', 'צה"ל', 'כלכלה', 'פוליטי', 'ממשלה', 'כספים', 'צבא', 'ביטחוני', 'נתניהו', 'כנסת']

# רשימת מילים אסורות (אלימות או תכנים לא הולמים)
FORBIDDEN_KEYWORDS = ['רצח', 'אונס', 'גרפי', 'גופה', 'נרצחה', 'דקירה']

def contains_allowed_topics(text):
    return any(word in text for word in ALLOWED_KEYWORDS)

def contains_violence(text):
    return any(word in text for word in FORBIDDEN_KEYWORDS)

def scrape_news():
    path = 'content/news'
    os.makedirs(path, exist_ok=True)
    
    sources = {
        "וואלה": "https://rss.walla.co.il/feed/1",
        "ynet": "https://www.ynet.co.il/Integration/StoryRss1854.xml",
        "דובר צהל": "https://www.idf.il/RSS/hebrew/"
    }
    
    for name, url in sources.items():
        print(f"סורק את {name}...")
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            try:
                # סינון לפי כותרת עוד לפני ההורדה
                if not contains_allowed_topics(entry.title) or contains_violence(entry.title):
                    continue

                article = Article(entry.link, language='he')
                article.download()
                article.parse()
                
                # בדיקה נוספת בתוך הטקסט המלא
                if contains_violence(article.text):
                    continue

                # --- סינון תמונות נשים (גישת הזהירות) ---
                # אם הכתבה היא מוואלה או ynet, ואין לנו בוט זיהוי פנים פעיל כרגע, 
                # הדרך הכי בטוחה היא להשתמש בתמונת לוגו של קודקוד במקום תמונה שעלולה להיות בעייתית
                image_url = article.top_image
                
                # הגנה: אם הכתבה עוסקת בנושאים כלליים, נשים תמונה ניטרלית
                if "ביטחון" not in article.title and "צבא" not in article.title:
                    image_url = "https://kodkodnews.co.il/logo_placeholder.png"

                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{timestamp}-{os.urandom(2).hex()}.md"
                filepath = os.path.join(path, filename)
                
                content = f"""---
title: "{article.title}"
date: "{datetime.now().isoformat()}"
source: "{name}"
image: "{image_url}"
link: "{entry.link}"
---

{article.text}
"""
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"נשמר: {article.title}")
                time.sleep(1)
            except Exception as e:
                print(f"שגיאה: {e}")

if __name__ == "__main__":
    scrape_news()
