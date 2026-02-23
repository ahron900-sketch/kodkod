import feedparser
import os
import time
from datetime import datetime
import re

# הגדרות נתיבים - ודא שהתיקייה הזו קיימת ב-GitHub שלך
NEWS_DIR = "content/news"

# יצירת התיקייה אם היא לא קיימת
if not os.path.exists(NEWS_DIR):
    os.makedirs(NEWS_DIR)

def create_news_file(title, content, image_url, video_url):
    # יצירת שם קובץ ייחודי לפי זמן (מונע כפילויות)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    filename = f"{NEWS_DIR}/{timestamp}.md"
    
    # בניית גוף המבזק - כולל נגן וידאו במידה וקיים קישור
    full_content = content
    if video_url:
        full_content += f'\n\n<video width="100%" controls poster="{image_url}"><source src="{video_url}" type="video/mp4">הדפדפן שלך לא תומך בנגן וידאו.</video>'
    
    # כתיבת הקובץ בפורמט Markdown שמתאים ל-Netlify CMS שלך
    with open(filename, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(f'title: "{title}"\n')
        f.write(f'date: "{datetime.now().isoformat()}"\n')
        f.write(f'category: "ביטחון"\n') # משייך אוטומטית לקטגוריה שביקשת
        f.write(f'image: "{image_url}"\n')
        f.write("---\n\n")
        f.write(full_content)

# משיכת נתונים מערוץ ה-RSS הרשמי של דובר צה"ל
feed = feedparser.parse("https://www.idf.il/RSS")

for entry in feed.entries[:5]: # לוקח את 5 המבזקים האחרונים
    title = entry.title
    content = entry.summary
    
    # חיפוש תמונה או וידאו בתוך הקישורים המצורפים למבזק
    image_url = ""
    video_url = ""
    
    if 'links' in entry:
        for link in entry.links:
            if 'image' in link.get('type', ''):
                image_url = link.get('href', '')
            if 'video' in link.get('type', ''):
                video_url = link.get('href', '')

    create_news_file(title, content, image_url, video_url)
