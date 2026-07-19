import os
import re
import json
import glob
import html
import shutil
from datetime import datetime

CONTENT_DIR = "content/news"
MAGAZINE_DIR = "content/magazine"
OUTPUT_DIR = "public_site"
SITE_NAME = "קודקוד חדשות"
SITE_URL = "https://kodkodnews.co.il"
TIP_FORM_ACTION = "https://formspree.io/f/xeelpjwg"
ARTICLE_PREVIEW_CHARS = 900
WP_BOILERPLATE_RE = re.compile(r'^The post .* appeared first on .*\.?$')
RECIPE_CATEGORY = "בישול ומתכונים"
TV_CATEGORY = "טלוויזיה ושידורים חיים"


def extract_dek(body_text, max_len=180):
    """First real sentence of the body, used as a subtitle under the headline."""
    for line in body_text.split("\n"):
        line = line.strip()
        if not line or WP_BOILERPLATE_RE.match(line):
            continue
        clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)  # unwrap markdown links
        clean = html.unescape(clean).strip()
        if len(clean) < 15:
            continue
        if len(clean) > max_len:
            clean = clean[:max_len].rsplit(" ", 1)[0] + "…"
        return clean
    return ""


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
            "video_id": data.get("video_id", ""),
            "body": body,
            "slug": slug,
            "dek": extract_dek(body),
            "is_quick": len(body) < 500 and not data.get("video_id"),
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


def load_magazine_issues():
    """Weekly magazine issues, generated separately by generate_magazine.py
    (runs on its own schedule) and committed as JSON snapshots. Returns them
    newest-first; a missing/empty directory just means no issue yet."""
    issues = []
    if not os.path.isdir(MAGAZINE_DIR):
        return issues
    for path in sorted(glob.glob(os.path.join(MAGAZINE_DIR, "*.json")), reverse=True):
        try:
            with open(path, encoding="utf-8") as f:
                issues.append(json.load(f))
        except Exception:
            continue
    issues.sort(key=lambda i: i.get("week_id", ""), reverse=True)
    return issues


PAGE_HEAD = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="{site_name}">
{og_image_tag}
<meta name="twitter:card" content="summary_large_image">
<meta name="robots" content="index, follow">
<link rel="icon" href="/favicon.png">
<link rel="sitemap" type="application/xml" href="/sitemap.xml">
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css">
{structured_data}
</head>
<body>
<header class="site-header">
  <a href="/" class="logo">קודקוד <span>חדשות</span></a>
  <nav class="categories">{cat_links}</nav>
  <button class="search-toggle" id="search-toggle" aria-label="חיפוש" aria-expanded="false">
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
  </button>
</header>
<div class="search-drawer" id="search-drawer">
  <form class="search-form" action="/search.html" method="get">
    <input type="text" name="q" placeholder="חיפוש חדשות..." autocomplete="off" id="search-drawer-input">
    <button type="submit">חיפוש</button>
  </form>
</div>
"""

PAGE_FOOT = """
<footer class="site-footer">
  <nav class="footer-nav">
    <a href="/about.html">אודות</a>
    <a href="/tip-line.html">שלחו לנו סקופ</a>
    <a href="/advertise.html">פרסמו אצלנו</a>
  </nav>
  <p>© {year} קודקוד חדשות — כל הזכויות שמורות</p>
</footer>
<script src="/assets/search.js"></script>
</body>
</html>
"""


def render_card(a):
    img = a["image"] or PLACEHOLDER_IMG
    is_recipe = a["category"] == RECIPE_CATEGORY
    video_badge = '<span class="badge badge-video">וידאו</span>' if a.get("video_id") else ""
    quick_badge = '<span class="badge badge-quick">בקצרה</span>' if a.get("is_quick") and not a.get("video_id") and not is_recipe else ""
    recipe_badge = '<span class="badge badge-recipe">מתכון</span>' if is_recipe else ""
    card_cls = "card card-recipe" if is_recipe else "card"
    return f"""
    <a class="{card_cls}" href="/article/{a['slug']}.html" data-slug="{html.escape(a['slug'])}" data-title="{html.escape(a['title'])}" data-img="{html.escape(img)}" data-cat="{html.escape(a['category'])}">
      <div class="card-img-wrap">
        <img class="card-img" src="{html.escape(img)}" alt="{html.escape(a['title'])}" loading="lazy" onerror="this.src='{PLACEHOLDER_IMG}'">
        {video_badge}{quick_badge}{recipe_badge}
      </div>
      <div class="card-body">
        <span class="card-cat">{html.escape(a['category'])}</span>
        <h3>{html.escape(a['title'])}</h3>
        <span class="card-meta">{html.escape(a['source'])} · {html.escape(a['date'][:10])}</span>
      </div>
    </a>"""


def render_quick_card(a):
    return f"""
    <a class="quick-card" href="/article/{a['slug']}.html">
      <span class="card-cat">{html.escape(a['category'])}</span>
      <h4>{html.escape(a['title'])}</h4>
      <span class="card-meta">{html.escape(a['source'])} · {html.escape(a['date'][:10])}</span>
    </a>"""


PLACEHOLDER_IMG = "/assets/placeholder.svg"

# Mock ad creatives - purely visual placeholders (no real network/tracking) so
# the layout demos like a live site rather than empty dashed boxes.
MOCK_ADS = [
    {
        "cls": "ad-fin",
        "img": "https://images.unsplash.com/photo-1526304640581-d334cdbbf45e?w=900&q=70",
        "eyebrow": "מומלץ עבורך",
        "title": "תיק השקעות חכם ב-90 שניות",
        "body": "השוואת קרנות מדד בעמלות הנמוכות בישראל",
        "cta": "להשוואה חינם",
    },
    {
        "cls": "ad-travel",
        "img": "https://images.unsplash.com/photo-1436491865332-7a61a109cc05?w=900&q=70",
        "eyebrow": "דיל השבוע",
        "title": "טיסות ישירות לאירופה",
        "body": "החל מ-₪899 בכרטיס הלוך ושוב, מקומות אחרונים",
        "cta": "לצפייה בדילים",
    },
    {
        "cls": "ad-tech",
        "img": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=900&q=70",
        "eyebrow": "חדש בישראל",
        "title": "אוזניות ביטול רעשים דור חדש",
        "body": "עד 40 שעות סוללה, משלוח חינם עד הבית",
        "cta": "לרכישה עכשיו",
    },
    {
        "cls": "ad-food",
        "img": "https://images.unsplash.com/photo-1490474418585-ba9bad8fd0ea?w=900&q=70",
        "eyebrow": "פינוק לשבת",
        "title": "ארגז ירקות טרי מהחקלאי",
        "body": "מגיע ישר מהשדה עד הדלת, ללא תיווך",
        "cta": "להזמנה השבוע",
    },
]

_ad_counter = {"i": 0}


def ad_slot_html(compact=False):
    ad = MOCK_ADS[_ad_counter["i"] % len(MOCK_ADS)]
    _ad_counter["i"] += 1
    size_cls = "ad-slot-compact" if compact else ""
    return f"""<div class="ad-slot {ad['cls']} {size_cls}">
      <div class="ad-slot-bg" style="background-image:url('{html.escape(ad['img'])}')"></div>
      <div class="ad-slot-shine"></div>
      <span class="ad-tag">פרסומת</span>
      <div class="ad-creative">
        <span class="ad-eyebrow">{html.escape(ad['eyebrow'])}</span>
        <h4 class="ad-title">{html.escape(ad['title'])}</h4>
        <p class="ad-body">{html.escape(ad['body'])}</p>
        <span class="ad-cta">{html.escape(ad['cta'])}</span>
      </div>
    </div>"""




VIDEO_ICON_SVG = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>'
MAGAZINE_ICON_SVG = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>'


def cat_nav(categories, active=None):
    links = ['<a href="/" class="{}">כל החדשות</a>'.format("active" if active is None else "")]
    for c in categories:
        if c == TV_CATEGORY:
            continue
        cls = "active" if c == active else ""
        links.append(f'<a href="/category/{slugify(c, c)}.html" class="{cls}">{html.escape(c)}</a>')
    video_cls = "active" if active == "וידאו" else ""
    links.append(f'<a href="/video.html" class="nav-video {video_cls}">{VIDEO_ICON_SVG}<span>וידאו</span></a>')
    tv_cls = "active" if active == TV_CATEGORY else ""
    links.append(f'<a href="/tv.html" class="nav-video {tv_cls}">{VIDEO_ICON_SVG}<span>טלוויזיה</span></a>')
    magazine_cls = "active" if active == "מגזין" else ""
    links.append(f'<a href="/magazine.html" class="nav-video {magazine_cls}">{MAGAZINE_ICON_SVG}<span>מגזין</span></a>')
    return "".join(links)


MD_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\s)]+)\)')


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


def write_page(path, title, description, categories, active_cat, body_html,
               ticker_text, canonical=None, og_type="website", og_image="", structured_data=""):
    canonical = canonical or SITE_URL + "/"
    og_image_tag = f'<meta property="og:image" content="{html.escape(og_image)}">' if og_image else ""
    full = PAGE_HEAD.format(
        title=html.escape(title),
        description=html.escape(description),
        canonical=html.escape(canonical),
        og_type=og_type,
        site_name=SITE_NAME,
        og_image_tag=og_image_tag,
        cat_links=cat_nav(categories, active_cat),
        structured_data=structured_data,
    )
    full = full.replace("<header class=\"site-header\">",
                         f'<div class="ticker"><div class="ticker-move">{html.escape(ticker_text)}</div></div>\n<header class="site-header">')
    page_shell = f"""
<div class="page-shell">
  <aside class="side-rail side-rail-right">{ad_slot_html(compact=True)}</aside>
  <div class="page-shell-content">{body_html}</div>
  <aside class="side-rail side-rail-left">{ad_slot_html(compact=True)}</aside>
</div>"""
    full += page_shell + PAGE_FOOT.format(year=datetime.now().year)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(full)


ABOUT_BODY = """
<main class="static-page about-page">
  <h1>קודקוד <span>–</span> הלב הפועם של עולם החדשות</h1>
  <p class="lead">קודקוד הוא מרכז חדשותי דיגיטלי המנגיש בזמן אמת את האירועים החשובים בישראל ובעולם - חדשות, ביטחון, כלכלה, טכנולוגיה, עולם החרדים ובישול - הכול במקום אחד, בעברית קריאה ובעיצוב נקי וממוקד.</p>

  <h2>מי אנחנו</h2>
  <p>קודקוד הוקם מתוך רצון לפתור בעיה פשוטה: קוראים ישראלים שרוצים להישאר מעודכנים נאלצים לדלג בין עשרות אתרי חדשות שונים. קודקוד מרכז את המבזקים החשובים ביותר ממיטב המקורות בישראל למקום אחד, עם ממשק מהיר, נקי, וללא רעש פרסומי מציק.</p>

  <h2>איך אנחנו עובדים</h2>
  <p>המערכת שלנו פועלת כאגרגטור חדשות אוטומטי: בוט ייעודי סורק מדי 15 דקות את פידי ה-RSS הרשמיים של מקורות החדשות המובילים בישראל, ומעלה את המבזקים החדשים לאתר באופן מיידי. אנו <strong>לא</strong> כותבים או עורכים את תוכן הכתבות עצמו - כל כתבה מוצגת עם ייחוס ברור למקור המקורי שלה, ובסיום כל כתבה מופיע קישור ישיר לכתבה המלאה באתר המקור. קודקוד אינו טוען לבעלות על תוכן הכתבות המקוריות.</p>

  <h2>תחומי סיקור</h2>
  <ul>
    <li><strong>חדשות:</strong> אירועים מרכזיים בישראל ובעולם, פוליטיקה, ביטחון וחברה.</li>
    <li><strong>חרדים:</strong> עדכונים מעולם היהדות החרדית והדתית בישראל ובעולם.</li>
    <li><strong>כלכלה:</strong> שוק ההון, עסקים ומגמות כלכליות.</li>
    <li><strong>טכנולוגיה:</strong> חדשנות, סטארטאפים והייטק ישראלי ועולמי.</li>
    <li><strong>בישול ומתכונים:</strong> תוכן אוכל ולייף-סטייל ממיטב אתרי הבישול בישראל.</li>
    <li><strong>וידאו:</strong> קטעי חדשות מצולמים מערוצי החדשות המובילים, מוצגים בנגן הווידאו הייעודי של קודקוד.</li>
  </ul>

  <h2>למה קודקוד?</h2>
  <ul>
    <li><strong>מהירות:</strong> עדכון אוטומטי לאורך היממה, כל 15 דקות, ממגוון רחב של מקורות.</li>
    <li><strong>מגוון:</strong> חדשות, כלכלה, טכנולוגיה, חרדים ובישול - הכול תחת קורת גג אחת.</li>
    <li><strong>נקי:</strong> ממשק מהיר וקריא, ללא רעש מיותר, עם גופן גדול ונוח לקריאה.</li>
    <li><strong>מקור מכובד:</strong> כל כתבה מקושרת בבירור למקור המקורי שלה, ומיוחסת לכתב ולערוץ שפרסם אותה.</li>
    <li><strong>חינמי ופתוח:</strong> קודקוד נגיש לכולם ללא צורך בהרשמה או תשלום.</li>
  </ul>

  <h2>שאלות נפוצות</h2>
  <h3>האם קודקוד כותב את הכתבות בעצמו?</h3>
  <p>לא. קודקוד הוא אגרגטור - אנו אוספים ומציגים מבזקים ממקורות חדשות קיימים, עם ייחוס וקישור מלא למקור המקורי.</p>
  <h3>באיזו תדירות האתר מתעדכן?</h3>
  <p>מערכת האיסוף האוטומטית שלנו רצה כל 15 דקות, מסביב לשעון.</p>
  <h3>איך אפשר לדווח על טעות או לשלוח משוב?</h3>
  <p>אפשר לפנות אלינו בכל עת דרך <a href="/tip-line.html">עמוד יצירת הקשר</a>.</p>

  <h2>יצירת קשר</h2>
  <p>יש לכם משוב, תיקון, סקופ, או שאלה? אתם מוזמנים <a href="/tip-line.html">לשלוח לנו הודעה</a>. מעוניינים לפרסם אצלנו? מוזמנים לבקר ב<a href="/advertise.html">עמוד הפרסום</a>.</p>
</main>"""

ADVERTISE_BODY = f"""
<main class="static-page">
  <h1>פרסמו <span>אצלנו</span></h1>
  <p class="lead">קודקוד חדשות מגיע לקהל קוראים רחב ומגוון. מעוניינים לפרסם באתר? צרו קשר ונחזור אליכם בהקדם עם פרטים על מיקומי הפרסום וההיקפים הזמינים.</p>

  <h2>מיקומי פרסום באתר</h2>
  <ul>
    <li><strong>באנר עמוד הבית:</strong> מתחת לכתבה הראשית, נצפה על ידי כל מבקר.</li>
    <li><strong>בין קטגוריות:</strong> באנרים בין מקטעי הקטגוריות השונות בעמוד הבית.</li>
    <li><strong>בתוך הכתבה:</strong> מיקום פרסומת בסיום כל כתבה, לפני אזור "עוד בנושא".</li>
  </ul>

  <h2>השאירו פרטים</h2>
  <form class="contact-form" action="{TIP_FORM_ACTION}" method="POST">
    <input type="text" name="name" placeholder="שם מלא / חברה" required>
    <input type="email" name="email" placeholder="אימייל לחזרה" required>
    <textarea name="message" rows="5" placeholder="ספרו לנו על הקמפיין שלכם..." required></textarea>
    <button type="submit">שלח בקשה</button>
  </form>
</main>"""

TIP_LINE_BODY = f"""
<main class="static-page">
  <h1>שלחו לנו <span>סקופ</span></h1>
  <p class="lead">ראיתם משהו חריג? יש לכם תיעוד בלעדי מהשטח? שלחו לנו עכשיו — בסודיות מלאה.</p>
  <form class="contact-form" action="{TIP_FORM_ACTION}" method="POST">
    <input type="text" name="name" placeholder="שם (או 'אנונימי')" required>
    <input type="text" name="location" placeholder="מיקום האירוע" required>
    <input type="text" name="media_link" placeholder="קישור לתמונה או סרטון">
    <textarea name="content" rows="6" placeholder="מה קרה שם? ספרו לנו הכל..." required></textarea>
    <button type="submit">שגר דיווח לחדר המבזקים</button>
  </form>
</main>"""


def json_ld_script(data):
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'


def article_structured_data(a, canonical):
    published = a["dt"].isoformat() if a["dt"] != datetime.min else ""
    data = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": a["title"],
        "description": a.get("dek", "") or a["title"],
        "datePublished": published,
        "dateModified": published,
        "articleSection": a["category"],
        "inLanguage": "he",
        "author": {"@type": "Organization", "name": a["source"] or SITE_NAME},
        "publisher": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": SITE_URL + "/",
        },
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
    }
    if a["image"]:
        data["image"] = [a["image"]]
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": SITE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": a["category"], "item": f"{SITE_URL}/category/{slugify(a['category'], a['category'])}.html"},
            {"@type": "ListItem", "position": 3, "name": a["title"], "item": canonical},
        ],
    }
    return json_ld_script(data) + json_ld_script(breadcrumb)


def category_structured_data(category_name, canonical):
    data = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{category_name} - {SITE_NAME}",
        "url": canonical,
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": SITE_URL + "/"},
    }
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": SITE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": category_name, "item": canonical},
        ],
    }
    return json_ld_script(data) + json_ld_script(breadcrumb)


def homepage_structured_data():
    data = {
        "@context": "https://schema.org",
        "@type": "NewsMediaOrganization",
        "name": SITE_NAME,
        "url": SITE_URL + "/",
        "logo": {"@type": "ImageObject", "url": SITE_URL + "/favicon.png"},
        "description": "קודקוד הוא מרכז חדשותי דיגיטלי ישראלי המרכז מבזקים ממיטב מקורות החדשות בעברית - חדשות, כלכלה, טכנולוגיה, חרדים ובישול.",
    }
    website = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": SITE_URL + "/",
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{SITE_URL}/search.html?q={{search_term_string}}",
            "query-input": "required name=search_term_string",
        },
    }
    return json_ld_script(data) + json_ld_script(website)


def build():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
    os.makedirs(os.path.join(OUTPUT_DIR, "assets"))
    os.makedirs(os.path.join(OUTPUT_DIR, "article"))
    os.makedirs(os.path.join(OUTPUT_DIR, "category"))

    articles = load_articles()
    categories = sorted({a["category"] for a in articles})
    ticker_articles = [a for a in articles if a["category"] != RECIPE_CATEGORY]
    ticker_text = "   •   ".join(a["title"] for a in ticker_articles[:12]) or "מערכת קודקוד - חדשות ומבזקים מהארץ ומהעולם"

    # Articles without a real image are never shown in listings (hero, cards,
    # quick strip, related) - only their own article page still renders for
    # anyone who has the direct link. video_id counts as "has visuals".
    listable = [a for a in articles if a["image"] or a.get("video_id")]

    # Homepage (hero + grid). Recipes are a different kind of content
    # (features/lifestyle, not news) and should never be picked as the
    # lead story.
    hero_candidates = [a for a in listable if a["category"] != RECIPE_CATEGORY]
    hero_html = ""
    rest = listable
    if hero_candidates:
        hero = hero_candidates[0]
        hero_img = hero["image"] or PLACEHOLDER_IMG
        hero_dek = f'<p class="hero-dek">{html.escape(hero["dek"])}</p>' if hero.get("dek") else ""
        hero_html = f"""
        <a class="hero" href="/article/{hero['slug']}.html">
          <div class="hero-img-wrap">
            <img src="{html.escape(hero_img)}" class="hero-img" onerror="this.src='{PLACEHOLDER_IMG}'">
          </div>
          <div class="hero-text">
            <span class="card-cat">{html.escape(hero['category'])}</span>
            <h1>{html.escape(hero['title'])}</h1>
            {hero_dek}
            <span class="card-meta">{html.escape(hero['source'])} · {html.escape(hero['date'][:10])}</span>
          </div>
        </a>"""
        rest = [a for a in listable if a["slug"] != hero["slug"]]

    # Bento/mosaic module: one large tile + a stack of smaller ones, instead
    # of dropping straight into a uniform grid right under the hero
    bento_candidates = [a for a in rest if a["category"] != RECIPE_CATEGORY][:5]
    bento_html = ""
    if len(bento_candidates) >= 3:
        big, *small = bento_candidates
        big_img = big["image"] or PLACEHOLDER_IMG
        small_items = "".join(f"""
          <a class="bento-small" href="/article/{s['slug']}.html">
            <div class="bento-small-img" style="background-image:url('{html.escape(s['image'] or PLACEHOLDER_IMG)}')"></div>
            <div class="bento-small-body">
              <span class="card-cat">{html.escape(s['category'])}</span>
              <h4>{html.escape(s['title'])}</h4>
            </div>
          </a>""" for s in small)
        bento_html = f"""
        <section class="bento-section reveal">
          <a class="bento-big" href="/article/{big['slug']}.html">
            <div class="bento-big-img" style="background-image:url('{html.escape(big_img)}')"></div>
            <div class="bento-big-body">
              <span class="card-cat">{html.escape(big['category'])}</span>
              <h2>{html.escape(big['title'])}</h2>
              <span class="card-meta">{html.escape(big['source'])} · {html.escape(big['date'][:10])}</span>
            </div>
          </a>
          <div class="bento-small-stack">{small_items}</div>
        </section>"""

    quick_articles = [a for a in rest if a.get("is_quick")][:8]
    quick_html = ""
    if quick_articles:
        quick_cards = "".join(render_quick_card(a) for a in quick_articles)
        quick_html = f"""
        <section class="quick-section reveal">
          <h2 class="section-title">בקצרה</h2>
          <div class="quick-strip">{quick_cards}</div>
        </section>"""

    recently_viewed_html = """
        <section class="recent-section" id="recently-viewed-section" hidden>
          <h2 class="section-title">כתבות שקראת לאחרונה</h2>
          <div class="grid-inner" id="recently-viewed-grid"></div>
        </section>"""

    # per-category sections: 9 articles each + a "view all" link to the category page
    # (TV_CATEGORY gets its own dedicated /tv.html instead, see below)
    category_sections = []
    for c in categories:
        if c == TV_CATEGORY:
            continue
        c_articles = [a for a in rest if a["category"] == c][:9]
        if not c_articles:
            continue
        c_cards = "".join(render_card(a) for a in c_articles)
        cat_url = f"/category/{slugify(c, c)}.html"
        category_sections.append(f"""
        <section class="cat-section reveal">
          <div class="cat-section-head">
            <h2 class="section-title">{html.escape(c)}</h2>
            <a class="view-all-btn" href="{cat_url}">לכל הכתבות</a>
          </div>
          <div class="grid-inner">{c_cards}</div>
        </section>
        {ad_slot_html()}""")
    categories_html = "".join(category_sections)

    body = f'<main class="grid">{hero_html}{bento_html}{ad_slot_html()}{quick_html}{recently_viewed_html}{categories_html}</main>'
    write_page(os.path.join(OUTPUT_DIR, "index.html"), SITE_NAME,
               "קודקוד חדשות - האתר החדשותי המהיר בישראל: חדשות, כלכלה, טכנולוגיה וחרדים במקום אחד",
               categories, None, body, ticker_text, canonical=SITE_URL + "/",
               structured_data=homepage_structured_data())

    # Category pages (TV_CATEGORY has its own /tv.html instead)
    for c in categories:
        if c == TV_CATEGORY:
            continue
        c_articles = [a for a in listable if a["category"] == c][:100]
        cards = "".join(render_card(a) for a in c_articles)
        sort_bar = """
        <div class="sort-bar">
          <label for="sort-select">מיון:</label>
          <select id="sort-select">
            <option value="newest">החדשות ביותר</option>
            <option value="oldest">הישנות ביותר</option>
          </select>
        </div>"""
        body = f'<main class="grid"><h1 class="page-title">{html.escape(c)}</h1>{sort_bar}<div class="grid-inner" id="category-grid">{cards}</div></main>'
        cat_url = f"{SITE_URL}/category/{slugify(c, c)}.html"
        write_page(os.path.join(OUTPUT_DIR, "category", f"{slugify(c, c)}.html"),
                   f"חדשות {c} - {SITE_NAME}", f"כל הכתבות בקטגוריית {c} - עדכונים שוטפים מהאתר החדשותי קודקוד",
                   categories, c, body, ticker_text, canonical=cat_url,
                   structured_data=category_structured_data(c, cat_url))

    # Video page - short news clips only (TV_CATEGORY has its own page below)
    video_articles = [a for a in listable if a.get("video_id") and a["category"] != TV_CATEGORY]
    video_cards = "".join(render_card(a) for a in video_articles)
    video_body = f'<main class="grid"><h1 class="page-title">וידאו</h1><div class="grid-inner">{video_cards}</div></main>'
    video_url = f"{SITE_URL}/video.html"
    write_page(os.path.join(OUTPUT_DIR, "video.html"), f"וידאו - {SITE_NAME}",
               "קטעי חדשות מצולמים ממיטב ערוצי החדשות בישראל, בנגן הווידאו הייעודי של קודקוד",
               categories, "וידאו", video_body, ticker_text, canonical=video_url,
               structured_data=category_structured_data("וידאו", video_url))

    # Separate page for live broadcasts / full TV episodes, kept apart from
    # the short news-clip video feed
    tv_articles = [a for a in listable if a.get("video_id") and a["category"] == TV_CATEGORY]
    tv_cards = "".join(render_card(a) for a in tv_articles)
    tv_body = f'<main class="grid"><h1 class="page-title">{TV_CATEGORY}</h1><div class="grid-inner">{tv_cards}</div></main>'
    tv_url = f"{SITE_URL}/tv.html"
    write_page(os.path.join(OUTPUT_DIR, "tv.html"), f"{TV_CATEGORY} - {SITE_NAME}",
               "שידורים חיים ופרקים מלאים מערוצי החדשות בישראל",
               categories, TV_CATEGORY, tv_body, ticker_text, canonical=tv_url,
               structured_data=category_structured_data(TV_CATEGORY, tv_url))

    # Weekly magazine - issues are generated separately (generate_magazine.py,
    # its own weekly schedule) and just rendered here as static pages
    magazine_issues = load_magazine_issues()
    os.makedirs(os.path.join(OUTPUT_DIR, "magazine"), exist_ok=True)

    issue_cards = []
    for issue in magazine_issues:
        cover = issue.get("cover") or {}
        cover_img = cover.get("image", "") or PLACEHOLDER_IMG
        issue_cards.append(f"""
        <a class="magazine-issue-card" href="/magazine/{issue['week_id']}.html">
          <div class="magazine-issue-cover" style="background-image:url('{html.escape(cover_img)}')"></div>
          <div class="magazine-issue-info">
            <span class="magazine-issue-label">גיליון {html.escape(issue['week_id'])}</span>
            <h3>{html.escape(cover.get('title', ''))}</h3>
            <span class="card-meta">{issue.get('article_count', 0)} כתבות</span>
          </div>
        </a>""")
    magazine_index_body = f"""
    <main class="grid">
      <h1 class="page-title">המגזין השבועי</h1>
      <p class="magazine-intro">מדי שבוע, קודקוד מרכז את הכתבות הבולטות ביותר שהופיעו באתר לגיליון אחד - בעיצוב מגזין, מסודר לפי נושאים.</p>
      <div class="grid-inner magazine-issues-grid">{"".join(issue_cards) or '<p>הגיליון הראשון בדרך - חזרו בקרוב.</p>'}</div>
    </main>"""
    magazine_index_url = f"{SITE_URL}/magazine.html"
    write_page(os.path.join(OUTPUT_DIR, "magazine.html"), f"המגזין השבועי - {SITE_NAME}",
               "המגזין השבועי של קודקוד - סיכום הכתבות הבולטות של השבוע, מסודר לפי נושאים",
               categories, "מגזין", magazine_index_body, ticker_text, canonical=magazine_index_url,
               structured_data=category_structured_data("מגזין", magazine_index_url))

    for issue in magazine_issues:
        cover = issue.get("cover") or {}
        cover_img = cover.get("image", "") or PLACEHOLDER_IMG
        section_html_parts = []
        for section in issue.get("sections", []):
            article_cards = "".join(f"""
            <a class="magazine-article" href="{html.escape(art['link'])}" target="_blank" rel="noopener">
              <div class="magazine-article-img" style="background-image:url('{html.escape(art['image'] or PLACEHOLDER_IMG)}')"></div>
              <div class="magazine-article-body">
                <h4>{html.escape(art['title'])}</h4>
                <p>{html.escape(art.get('dek', ''))}</p>
                <span class="card-meta">{html.escape(art['source'])}</span>
              </div>
            </a>""" for art in section["articles"])
            section_html_parts.append(f"""
            <section class="magazine-section">
              <h2 class="magazine-section-title">{html.escape(section['category'])}</h2>
              <div class="magazine-section-grid">{article_cards}</div>
            </section>""")

        issue_body = f"""
        <main class="grid magazine-issue-page">
          <div class="magazine-cover" style="background-image:url('{html.escape(cover_img)}')">
            <div class="magazine-cover-overlay">
              <span class="magazine-issue-label">גיליון {html.escape(issue['week_id'])}</span>
              <h1>{html.escape(cover.get('title', 'המגזין השבועי'))}</h1>
            </div>
          </div>
          {"".join(section_html_parts)}
        </main>"""
        issue_url = f"{SITE_URL}/magazine/{issue['week_id']}.html"
        write_page(os.path.join(OUTPUT_DIR, "magazine", f"{issue['week_id']}.html"),
                   f"גיליון {issue['week_id']} - המגזין השבועי - {SITE_NAME}",
                   f"גיליון המגזין השבועי של קודקוד לשבוע {issue['week_id']} - {issue.get('article_count', 0)} כתבות נבחרות",
                   categories, "מגזין", issue_body, ticker_text, canonical=issue_url,
                   structured_data=category_structured_data(f"גיליון {issue['week_id']}", issue_url))

    # Article pages
    for i, a in enumerate(articles):
        if a.get("video_id"):
            vid = html.escape(a["video_id"])
            thumb = a["image"] or f"https://i.ytimg.com/vi/{a['video_id']}/hqdefault.jpg"
            media_html = f"""
            <div class="kk-player" data-video-id="{vid}">
              <div class="kk-player-poster" style="background-image:url('{html.escape(thumb)}')">
                <span class="kk-player-brand">קודקוד פלייר</span>
                <button class="kk-player-play" aria-label="נגן וידאו">
                  <svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                </button>
              </div>
            </div>"""
        elif a["image"]:
            media_html = f'<img src="{html.escape(a["image"])}" class="article-img" loading="eager" onerror="this.src=\'{PLACEHOLDER_IMG}\'">'
        else:
            media_html = ""

        dek_html = f'<p class="article-dek">{html.escape(a["dek"])}</p>' if a.get("dek") else ""

        body_html_full = render_body(a["body"])
        is_long = len(a["body"]) > ARTICLE_PREVIEW_CHARS
        if is_long:
            # split rendered paragraphs at roughly the preview length, not mid-tag
            parts = re.findall(r'<p>.*?</p>', body_html_full, re.DOTALL)
            running = 0
            cut_idx = len(parts)
            for idx, p in enumerate(parts):
                running += len(p)
                if running >= ARTICLE_PREVIEW_CHARS:
                    cut_idx = idx + 1
                    break
            preview_html = "".join(parts[:cut_idx])
            rest_html = "".join(parts[cut_idx:])
            body_content = f"""
              <div class="article-body">{preview_html}</div>
              <div class="article-body article-body-more" hidden>{rest_html}</div>
              <button class="read-more-btn" onclick="
                this.previousElementSibling.hidden = false;
                this.hidden = true;
              ">קרא עוד</button>"""
        else:
            body_content = f'<div class="article-body">{body_html_full}</div>'

        # related articles: same category, excluding this one, most recent first
        related = [x for x in listable if x["category"] == a["category"] and x["slug"] != a["slug"]][:6]
        related_html = ""
        if related:
            related_cards = "".join(render_card(x) for x in related)
            related_html = f"""
            <section class="related-section">
              <h2 class="page-title">עוד בנושא {html.escape(a['category'])}</h2>
              <div class="grid-inner">{related_cards}</div>
            </section>"""

        canonical = f"{SITE_URL}/article/{a['slug']}.html"
        view_tracker = f"""
        <script>
        (function() {{
          try {{
            var key = 'kk_recent';
            var entry = {{slug: {json.dumps(a['slug'], ensure_ascii=False)}, title: {json.dumps(a['title'], ensure_ascii=False)}, img: {json.dumps(a['image'] or PLACEHOLDER_IMG, ensure_ascii=False)}, cat: {json.dumps(a['category'], ensure_ascii=False)}}};
            var list = JSON.parse(localStorage.getItem(key) || '[]');
            list = list.filter(function(x) {{ return x.slug !== entry.slug; }});
            list.unshift(entry);
            localStorage.setItem(key, JSON.stringify(list.slice(0, 12)));
          }} catch (e) {{}}
        }})();
        </script>"""
        engagement_bar = f"""
        <div class="engagement-bar" data-slug="{html.escape(a['slug'])}">
          <button class="like-btn" id="like-btn" aria-pressed="false">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8z"/></svg>
            <span id="like-count">אהבתי</span>
          </button>
          <button class="share-btn" id="share-btn" data-title="{html.escape(a['title'])}" data-url="{html.escape(canonical)}">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.6" y1="10.6" x2="15.4" y2="6.4"/><line x1="8.6" y1="13.4" x2="15.4" y2="17.6"/></svg>
            <span>שיתוף</span>
          </button>
          <a class="source-link-icon" href="{html.escape(a['link'])}" target="_blank" rel="noopener" title="קרא את הכתבה המלאה במקור">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
          </a>
        </div>"""
        body = f"""
        <main class="article">
          <span class="card-cat">{html.escape(a['category'])}</span>
          <h1>{html.escape(a['title'])}</h1>
          {dek_html}
          <div class="article-meta">{html.escape(a['source'])} · {html.escape(a['date'])}</div>
          {media_html}
          {body_content}
          {engagement_bar}
        </main>
        {ad_slot_html()}
        {related_html}
        {view_tracker}"""
        description = re.sub(r'<[^>]+>', '', body_html_full)[:160].strip()
        write_page(os.path.join(OUTPUT_DIR, "article", f"{a['slug']}.html"), a["title"],
                   description or a["title"], categories, a["category"], body, ticker_text,
                   canonical=canonical, og_type="article", og_image=a["image"],
                   structured_data=article_structured_data(a, canonical))

    # Search page
    body = '<main class="grid"><h1 class="page-title">תוצאות חיפוש</h1><div id="search-results" class="grid-inner"></div></main>'
    write_page(os.path.join(OUTPUT_DIR, "search.html"), f"חיפוש - {SITE_NAME}", "חיפוש חדשות באתר קודקוד",
               categories, None, body, ticker_text, canonical=f"{SITE_URL}/search.html")

    # Static pages
    about_schema = {
        "@context": "https://schema.org",
        "@type": "AboutPage",
        "mainEntity": {
            "@type": "Organization",
            "name": SITE_NAME,
            "url": SITE_URL + "/",
            "description": "קודקוד הוא מרכז חדשותי דיגיטלי ישראלי המרכז מבזקים ממיטב מקורות החדשות בעברית - חדשות, כלכלה, טכנולוגיה, חרדים ובישול.",
        },
    }
    about_structured_data = '<script type="application/ld+json">' + json.dumps(about_schema, ensure_ascii=False) + '</script>'
    write_page(os.path.join(OUTPUT_DIR, "about.html"), f"אודות קודקוד - מי אנחנו וכיצד אנחנו עובדים | {SITE_NAME}",
               "קודקוד הוא מרכז חדשותי המרכז מבזקים ממיטב מקורות החדשות בישראל - חדשות, כלכלה, טכנולוגיה, חרדים ובישול. קראו על החזון, תחומי הסיקור והדרך בה אנחנו עובדים.",
               categories, None, ABOUT_BODY, ticker_text, canonical=f"{SITE_URL}/about.html", structured_data=about_structured_data)
    write_page(os.path.join(OUTPUT_DIR, "advertise.html"), f"פרסום - {SITE_NAME}", "פרסמו בקודקוד חדשות",
               categories, None, ADVERTISE_BODY, ticker_text, canonical=f"{SITE_URL}/advertise.html")
    write_page(os.path.join(OUTPUT_DIR, "tip-line.html"), f"שלחו סקופ - {SITE_NAME}", "שלחו סקופ לקודקוד",
               categories, None, TIP_LINE_BODY, ticker_text, canonical=f"{SITE_URL}/tip-line.html")

    # Search index JSON (client-side search, no server/API needed)
    search_index = [
        {
            "title": a["title"],
            "slug": a["slug"],
            "category": a["category"],
            "source": a["source"],
            "date": a["date"],
            "image": a["image"],
            "video": bool(a.get("video_id")),
        }
        for a in articles
    ]
    with open(os.path.join(OUTPUT_DIR, "assets", "search-index.json"), "w", encoding="utf-8") as f:
        json.dump(search_index, f, ensure_ascii=False)

    # sitemap.xml - static pages, categories, and every article (with an
    # <image:image> extension when the article has a real photo, so image
    # search can index it too)
    now = datetime.now()
    static_urls = [f"{SITE_URL}/", f"{SITE_URL}/about.html", f"{SITE_URL}/advertise.html", f"{SITE_URL}/tip-line.html", f"{SITE_URL}/video.html", f"{SITE_URL}/tv.html", f"{SITE_URL}/magazine.html"]
    category_urls = [f"{SITE_URL}/category/{slugify(c, c)}.html" for c in categories]
    magazine_urls = [f"{SITE_URL}/magazine/{issue['week_id']}.html" for issue in magazine_issues]

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
    )
    lastmod_today = now.strftime("%Y-%m-%d")
    for u in static_urls + category_urls + magazine_urls:
        sitemap += f"  <url><loc>{u}</loc><lastmod>{lastmod_today}</lastmod></url>\n"
    for a in articles:
        loc = f"{SITE_URL}/article/{a['slug']}.html"
        lastmod = (a["dt"] if a["dt"] != datetime.min else now).strftime("%Y-%m-%d")
        image_tag = f"<image:image><image:loc>{html.escape(a['image'])}</image:loc></image:image>" if a["image"] else ""
        sitemap += f"  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod>{image_tag}</url>\n"
    sitemap += "</urlset>\n"
    with open(os.path.join(OUTPUT_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap)

    # Google News sitemap - only articles from the last 48 hours, per spec
    # (https://support.google.com/news/publisher-center/answer/9606224)
    news_cutoff = now.timestamp() - 48 * 3600
    recent_articles = [a for a in articles if a["dt"] != datetime.min and a["dt"].timestamp() >= news_cutoff]
    news_sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">\n'
    )
    for a in recent_articles:
        loc = f"{SITE_URL}/article/{a['slug']}.html"
        pub_date = a["dt"].strftime("%Y-%m-%dT%H:%M:%S+03:00")
        news_sitemap += (
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            "    <news:news>\n"
            f"      <news:publication><news:name>{html.escape(SITE_NAME)}</news:name><news:language>he</news:language></news:publication>\n"
            f"      <news:publication_date>{pub_date}</news:publication_date>\n"
            f"      <news:title>{html.escape(a['title'])}</news:title>\n"
            "    </news:news>\n"
            "  </url>\n"
        )
    news_sitemap += "</urlset>\n"
    with open(os.path.join(OUTPUT_DIR, "news-sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(news_sitemap)

    # robots.txt
    with open(os.path.join(OUTPUT_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(
            f"User-agent: *\nAllow: /\n"
            f"Sitemap: {SITE_URL}/sitemap.xml\n"
            f"Sitemap: {SITE_URL}/news-sitemap.xml\n"
        )

    print(f"נבנה אתר עם {len(articles)} כתבות ב-{len(categories)} קטגוריות.")


if __name__ == "__main__":
    build()
