import feedparser
import os
from datetime import datetime
from newspaper import Article
import time

# הגדרת קטגוריות ומילים מנחות
CATEGORIES = {
    'ביטחון': ['צה"ל', 'ביטחוני', 'צבא', 'חמאס', 'חיזבאללה', 'תקיפה', 'עזה', 'לבנון', 'חייל', 'כוחות'],
    'כלכלה': ['בורסה', 'דולר', 'ריבית', 'כספים', 'נדל"ן', 'אוצר', 'מניות'],
    'פוליטיקה': ['נתניהו', 'כנסת', 'ממשלה', 'בחירות', 'שר', 'קואליציה', 'אופוזיציה'],
    'עולם': ['ארה"ב', 'ביידן', 'אירופה', 'אוקראינה', 'רוסיה', 'סין']
}

FORBIDDEN_KEYWORDS = ['רצח', 'אונס', 'גרפי', 'גופה', 'נרצחה', 'דקירה', 'אלימות']

def get_category(title, text):
    combined = (title + " " + text).lower()
    for cat, keywords in CATEGORIES.items():
        if any(word in combined for word in keywords):
            return cat
    return "כללי"

def scrape_news():
    path = 'content/news'
    os.makedirs(path, exist_ok=True)
    sources = {
        "וואלה": "https://rss.walla.co.il/feed/1",
        "ynet": "https://www.ynet.co.il/Integration/StoryRss1854.xml",
        "דובר צהל": "https://www.idf.il/RSS/hebrew/"
    }
    
    for name, url in sources.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:10]:
            try:
                if any(word in entry.title for word in FORBIDDEN_KEYWORDS): continue
                
                article = Article(entry.link, language='he')
                article.download()
                article.parse()
                
                cat = get_category(article.title, article.text)
                if cat == "כללי": continue # סינון כתבות שלא מתאימות לקטגוריות שלך
                
                image_url = article.top_image
                # הגנה בסיסית: אם יש מילים שקשורות לנשים בכתבה, נחליף תמונה ליתר ביטחון
                if any(w in article.text for w in ['אישה', 'נשים', 'בחורה', 'דוגמנית']):
                    image_url = "https://kodkodnews.co.il/logo_placeholder.png"

                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{timestamp}.md"
                filepath = os.path.join(path, filename)
                
                content = f"""---
title: "{article.title}"
category: "{cat}"
source: "{name}"
image: "{image_url}"
date: "{datetime.now().isoformat()}"
---

{article.text}"""
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
            except: continue

if __name__ == "__main__":
    scrape_news()
