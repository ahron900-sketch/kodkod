import os
import re
import json
import glob
import html
import shutil
from datetime import datetime

CONTENT_DIR = "content/news"
OUTPUT_DIR = "public_site"
SITE_NAME = "קודקוד חדשות"
SITE_URL = "https://kodkodnews.co.il"
TIP_FORM_ACTION = "https://formspree.io/f/xeelpjwg"


def slugify(text, fallback):
    text = re.sub(r'[^\w\-א-ת]+', '-', text, flags=re.UNICODE).strip('-')
    return text[:60] if text else fallback


def parse_frontmatter(raw):
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', raw, re.DOTALL)
    if not m:
        return None, raw
    fm_text, body = m.group(1), m.group(2)
    data = {}
    lines = fm_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        kv = re.match(r'^(\w+):\s*(.*)$', line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            if val == ">-":
                i += 1
                collected = []
                while i < len(lines) and lines[i].startswith("  "):
                    collected.append(lines[i].strip())
                    i += 1
                data[key] = " ".join(collected)
                continue
            else:
                data[key] = val.strip('"')
        i += 1
    return data, body.strip()


def load_articles():
    articles = []
    for path in glob.glob(os.path.join(CONTENT_DIR, "*.md")):
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            continue
        data, body = parse_frontmatter(raw)
        if not data:
            continue
        title = data.get("title", "ללא כותרת")
        date_str = data.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            dt = datetime.min
        slug = slugify(title, os.path.splitext(os.path.basename(path))[0])
        articles.append({
            "title": title,
            "date": date_str,
            "dt": dt,
            "source": data.get("source", ""),
            "image": data.get("image", ""),
            "link": data.get("link", ""),
            "category": data.get("category", "חדשות"),
            "body": body,
            "slug": slug,
        })
    articles.sort(key=lambda a: a["dt"], reverse=True)
    seen = {}
    for a in articles:
        base = a["slug"]
        if base in seen:
            seen[base] += 1
            a["slug"] = f"{base}-{seen[base]}"
        else:
            seen[base] = 0
    return articles


PAGE_HEAD = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="icon" href="/favicon.png">
<link href="https://fonts.googleapis.com/css2?family=Assistant:wght@200;400;700;800&family=Orbitron:wght@700;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css">
<script>
if (localStorage.getItem('theme') === 'dark') document.documentElement.classList.add('dark-mode');
</script>
</head>
<body>
<div class="ticker"><div class="ticker-move">{ticker_text}</div></div>
<header class="site-header">
  <a href="/" class="logo">KOD<span>KOD</span></a>
  <form class="search-form" action="/search.html" method="get">
    <input type="text" name="q" placeholder="חיפוש חדשות..." autocomplete="off">
    <button type="submit">חיפוש</button>
  </form>
  <button class="theme-toggle" onclick="document.documentElement.classList.toggle('dark-mode'); localStorage.setItem('theme', document.documentElement.classList.contains('dark-mode') ? 'dark' : 'light');" title="מצב כהה/בהיר">🌓</button>
  <nav class="categories">{cat_links}</nav>
</header>
"""

PAGE_FOOT = """
<footer class="site-footer">
  <nav class="footer-nav">
    <a href="/about.html">אודות</a>
    <a href="/tip-line.html">המייל האדום - שלחו סקופ</a>
    <a href="/advertise.html">פרסמו אצלנו</a>
  </nav>
  <p>© {year} קודקוד חדשות — כל הזכויות שמורות</p>
</footer>
<script src="/assets/search.js"></script>
</body>
</html>
"""


def render_card(a, featured=False):
    img = a["image"] or "/favicon.png"
    cls = "card featured" if featured else "card"
    return f"""
    <a class="{cls}" href="/article/{a['slug']}.html">
      <div class="card-img" style="background-image:url('{html.escape(img)}')"></div>
      <div class="card-body">
        <span class="card-cat">{html.escape(a['category'])}</span>
        <h3>{html.escape(a['title'])}</h3>
        <span class="card-meta">{html.escape(a['source'])} · {html.escape(a['date'][:10])}</span>
      </div>
    </a>"""


def cat_nav(categories, active=None):
    links = ['<a href="/" class="{}">כל החדשות</a>'.format("active" if active is None else "")]
    for c in categories:
        cls = "active" if c == active else ""
        links.append(f'<a href="/category/{slugify(c, c)}.html" class="{cls}">{html.escape(c)}</a>')
    return "".join(links)


MD_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\s)]+)\)')
WP_BOILERPLATE_RE = re.compile(r'^The post .* appeared first on .*\.?$')


def render_body(body_text):
    paragraphs = []
    for line in body_text.split("\n"):
        line = line.strip()
        if not line or WP_BOILERPLATE_RE.match(line):
            continue
        escaped = html.escape(line)

        def repl(m):
            return f'<a href="{html.escape(m.group(2))}" target="_blank" rel="noopener">{m.group(1)}</a>'

        linked = MD_LINK_RE.sub(repl, escaped)
        paragraphs.append(f"<p>{linked}</p>")
    return "".join(paragraphs)


def write_page(path, title, description, categories, active_cat, body_html, ticker_text):
    full = PAGE_HEAD.format(
        title=html.escape(title),
        description=html.escape(description),
        cat_links=cat_nav(categories, active_cat),
        ticker_text=html.escape(ticker_text),
    ) + body_html + PAGE_FOOT.format(year=datetime.now().year)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(full)


ABOUT_BODY = """
<main class="static-page">
  <h1>קודקוד <span>–</span> הלב הפועם של עולם החדשות</h1>
  <p class="lead">ברוכים הבאים ל"קודקוד", מרכז חדשותי המנגיש את אירועי היום במהירות ובאמינות, עם סיקור רחב של חדשות ישראל והעולם, כלכלה, טכנולוגיה, ספורט וחצרות הקודש.</p>
  <h2>החזון שלנו</h2>
  <p>לרכז במקום אחד מבזקים ממיטב המקורות בישראל ובעולם, בעברית קריאה, בלי רעש ובלי פרסום פולשני.</p>
  <h2>למה קודקוד?</h2>
  <ul>
    <li><strong>מהירות:</strong> עדכון אוטומטי לאורך היממה ממגוון מקורות.</li>
    <li><strong>מגוון:</strong> חדשות, עולם, כלכלה, טכנולוגיה, ספורט וחרדים — הכול תחת קורת גג אחת.</li>
    <li><strong>נקי:</strong> ממשק פשוט, ללא רעש מיותר.</li>
  </ul>
</main>"""

ADVERTISE_BODY = f"""
<main class="static-page">
  <h1>פרסמו <span>אצלנו</span></h1>
  <p class="lead">קודקוד חדשות מגיע לקהל קוראים רחב ומגוון. מעוניינים לפרסם? צרו קשר ונחזור אליכם בהקדם.</p>
  <form class="contact-form" action="{TIP_FORM_ACTION}" method="POST">
    <input type="text" name="name" placeholder="שם מלא / חברה" required>
    <input type="email" name="email" placeholder="אימייל לחזרה" required>
    <textarea name="message" rows="5" placeholder="ספרו לנו על הקמפיין שלכם..." required></textarea>
    <button type="submit">שלח בקשה</button>
  </form>
</main>"""

TIP_LINE_BODY = f"""
<main class="static-page">
  <h1>המייל <span>האדום</span></h1>
  <p class="lead">ראיתם משהו חריג? יש לכם תיעוד בלעדי מהשטח? שלחו לנו עכשיו — בסודיות מלאה.</p>
  <form class="contact-form" action="{TIP_FORM_ACTION}" method="POST">
    <input type="text" name="name" placeholder="שם (או 'אנונימי')" required>
    <input type="text" name="location" placeholder="מיקום האירוע" required>
    <input type="text" name="media_link" placeholder="קישור לתמונה או סרטון">
    <textarea name="content" rows="6" placeholder="מה קרה שם? ספרו לנו הכל..." required></textarea>
    <button type="submit">שגר דיווח לחדר המבזקים</button>
  </form>
</main>"""


def build():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
    os.makedirs(os.path.join(OUTPUT_DIR, "assets"))
    os.makedirs(os.path.join(OUTPUT_DIR, "article"))
    os.makedirs(os.path.join(OUTPUT_DIR, "category"))

    articles = load_articles()
    categories = sorted({a["category"] for a in articles})
    ticker_text = "   •   ".join(a["title"] for a in articles[:12]) or "מערכת קודקוד - חדשות ומבזקים מהארץ ומהעולם"

    # Homepage (hero + grid)
    hero_html = ""
    rest = articles
    if articles:
        hero = articles[0]
        hero_img = hero["image"] or "/favicon.png"
        hero_html = f"""
        <a class="hero" href="/article/{hero['slug']}.html">
          <img src="{html.escape(hero_img)}" class="hero-img" onerror="this.style.display='none'">
          <div class="hero-overlay"><span class="card-cat">{html.escape(hero['category'])}</span><h1>{html.escape(hero['title'])}</h1></div>
        </a>"""
        rest = articles[1:]
    cards = "".join(render_card(a) for a in rest[:60])
    body = f'<main class="grid">{hero_html}<div class="grid-inner">{cards}</div></main>'
    write_page(os.path.join(OUTPUT_DIR, "index.html"), SITE_NAME, "האתר החדשותי המהיר בישראל ובעולם", categories, None, body, ticker_text)

    # Category pages
    for c in categories:
        c_articles = [a for a in articles if a["category"] == c]
        cards = "".join(render_card(a) for a in c_articles[:100])
        body = f'<main class="grid"><h1 class="page-title">{html.escape(c)}</h1><div class="grid-inner">{cards}</div></main>'
        write_page(os.path.join(OUTPUT_DIR, "category", f"{slugify(c, c)}.html"), f"{c} - {SITE_NAME}", f"חדשות {c}", categories, c, body, ticker_text)

    # Article pages
    for a in articles:
        img_html = f'<img src="{html.escape(a["image"])}" class="article-img" onerror="this.style.display=\'none\'">' if a["image"] else ""
        body_paragraphs = render_body(a["body"])
        body = f"""
        <main class="article">
          <span class="card-cat">{html.escape(a['category'])}</span>
          <h1>{html.escape(a['title'])}</h1>
          <div class="article-meta">{html.escape(a['source'])} · {html.escape(a['date'])}</div>
          {img_html}
          <div class="article-body">{body_paragraphs}</div>
          <a class="source-link" href="{html.escape(a['link'])}" target="_blank" rel="noopener">קרא את הכתבה המלאה במקור</a>
        </main>"""
        write_page(os.path.join(OUTPUT_DIR, "article", f"{a['slug']}.html"), a["title"], a["title"], categories, a["category"], body, ticker_text)

    # Search page
    body = '<main class="grid"><h1 class="page-title">תוצאות חיפוש</h1><div id="search-results" class="grid-inner"></div></main>'
    write_page(os.path.join(OUTPUT_DIR, "search.html"), f"חיפוש - {SITE_NAME}", "חיפוש חדשות", categories, None, body, ticker_text)

    # Static pages
    write_page(os.path.join(OUTPUT_DIR, "about.html"), f"אודות - {SITE_NAME}", "אודות קודקוד חדשות", categories, None, ABOUT_BODY, ticker_text)
    write_page(os.path.join(OUTPUT_DIR, "advertise.html"), f"פרסום - {SITE_NAME}", "פרסמו בקודקוד חדשות", categories, None, ADVERTISE_BODY, ticker_text)
    write_page(os.path.join(OUTPUT_DIR, "tip-line.html"), f"המייל האדום - {SITE_NAME}", "שלחו סקופ לקודקוד", categories, None, TIP_LINE_BODY, ticker_text)

    # Search index JSON (client-side search, no server/API needed)
    search_index = [
        {
            "title": a["title"],
            "slug": a["slug"],
            "category": a["category"],
            "source": a["source"],
            "date": a["date"],
            "image": a["image"],
        }
        for a in articles
    ]
    with open(os.path.join(OUTPUT_DIR, "assets", "search-index.json"), "w", encoding="utf-8") as f:
        json.dump(search_index, f, ensure_ascii=False)

    # sitemap.xml
    urls = (
        [f"{SITE_URL}/", f"{SITE_URL}/about.html", f"{SITE_URL}/advertise.html", f"{SITE_URL}/tip-line.html"]
        + [f"{SITE_URL}/category/{slugify(c, c)}.html" for c in categories]
        + [f"{SITE_URL}/article/{a['slug']}.html" for a in articles]
    )
    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    sitemap += "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
    sitemap += "</urlset>\n"
    with open(os.path.join(OUTPUT_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap)

    print(f"נבנה אתר עם {len(articles)} כתבות ב-{len(categories)} קטגוריות.")


if __name__ == "__main__":
    build()
