import os
import re
import json
import glob
import html
import shutil
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

CONTENT_DIR = "content/news"
MAGAZINE_DIR = "content/magazine"
OUTPUT_DIR = "public_site"
SITE_NAME = "קודקוד חדשות"
SITE_URL = "https://kodkodnews.co.il"
TIP_FORM_ACTION = "https://formspree.io/f/xeelpjwg"

# Comments (giscus - GitHub Discussions as the backend, no server of our own).
# Commenters log in with an existing GitHub account (not anonymous - giscus
# doesn't support that; see the write-up on this). GISCUS_REPO_ID is this
# repo's real node_id, fetched from the public GitHub API. GISCUS_CATEGORY_ID
# can't be obtained the same way: it only exists once Discussions is enabled
# on the repo, which is a one-time owner action giscus.app's setup flow
# walks through. Comments stay off (this constant empty) until it's filled in.
GISCUS_REPO_ID = "R_kgDORWVAhg"
GISCUS_CATEGORY_ID = ""

COMMENTS_SECTION_HTML = ""
if GISCUS_CATEGORY_ID:
    COMMENTS_SECTION_HTML = f"""
        <section class="comments-section">
          <h2 class="section-title">תגובות</h2>
          <script src="https://giscus.app/client.js"
                  data-repo="ahron900-sketch/kodkod"
                  data-repo-id="{GISCUS_REPO_ID}"
                  data-category="General"
                  data-category-id="{GISCUS_CATEGORY_ID}"
                  data-mapping="pathname"
                  data-strict="0"
                  data-reactions-enabled="1"
                  data-emit-metadata="0"
                  data-input-position="top"
                  data-theme="{SITE_URL}/assets/giscus-theme.css"
                  data-lang="he"
                  crossorigin="anonymous"
                  async>
          </script>
        </section>"""

ARTICLE_PREVIEW_CHARS = 900

# Populated once per build() run (needs real article/category data, so it
# can't be a plain literal like the constants above) - safe empty default in
# case anything ever imports this module without calling build() first
FOOTER_PROMO_HTML = ""
WEATHER_BAR_HTML = ""
SHABBAT_OVERLAY_HTML = ""
SHABBAT_HEAD_SCRIPT = ""

# Weather: open-meteo.com is genuinely free and keyless (no account/API key
# of any kind, verified before wiring this up) - fetched once per build at
# the same 2h cadence as everything else, never client-side. Real
# coordinates for real cities, no placeholders.
WEATHER_CITIES = [
    ("תל אביב", 32.0853, 34.7818),
    ("ירושלים", 31.7683, 35.2137),
    ("חיפה", 32.7940, 34.9896),
    ("באר שבע", 31.2530, 34.7915),
]
HEBREW_WEEKDAYS = ["יום שני", "יום שלישי", "יום רביעי", "יום חמישי", "יום שישי", "יום שבת", "יום ראשון"]
HEBREW_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
                 "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
# Standard WMO weather codes (open-meteo's own documented scheme) - mapped
# to icon keys, never colorful emoji (site-wide rule: monochrome
# stroke-based SVGs only, same idiom as every other icon on the site)
WEATHER_CODE_MAP = {
    0: ("בהיר", "sun"), 1: ("בהיר בעיקר", "sun"), 2: ("מעונן חלקית", "partly-cloudy"), 3: ("מעונן", "cloud"),
    45: ("ערפילי", "fog"), 48: ("ערפילי", "fog"),
    51: ("טפטוף קל", "drizzle"), 53: ("טפטוף", "drizzle"), 55: ("טפטוף חזק", "drizzle"),
    56: ("טפטוף קפוא", "rain"), 57: ("טפטוף קפוא חזק", "rain"),
    61: ("גשם קל", "rain"), 63: ("גשם", "rain"), 65: ("גשם חזק", "rain"),
    66: ("גשם קפוא", "rain"), 67: ("גשם קפוא חזק", "rain"),
    71: ("שלג קל", "snow"), 73: ("שלג", "snow"), 75: ("שלג כבד", "snow"), 77: ("גרגירי שלג", "snow"),
    80: ("ממטרים קלים", "drizzle"), 81: ("ממטרים", "drizzle"), 82: ("ממטרים חזקים", "rain"),
    85: ("ממטרי שלג קלים", "snow"), 86: ("ממטרי שלג", "snow"),
    95: ("סופת רעמים", "storm"), 96: ("סופת רעמים עם ברד", "storm"), 99: ("סופת רעמים עם ברד כבד", "storm"),
}

_SVG_OPEN = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">'
WEATHER_ICONS = {
    "sun": _SVG_OPEN + '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/></svg>',
    "partly-cloudy": _SVG_OPEN + '<circle cx="8" cy="9" r="3.2"/><path d="M8 3.5v1.5M3.5 9H5M11.5 6.5l-1 1M4.5 5.5l1 1"/><path d="M9 20h7a3.5 3.5 0 0 0 .4-6.98A5 5 0 0 0 7 12.5"/></svg>',
    "cloud": _SVG_OPEN + '<path d="M6 19h11a4 4 0 0 0 .5-7.97A6 6 0 0 0 6 12.2 4 4 0 0 0 6 19Z"/></svg>',
    "fog": _SVG_OPEN + '<path d="M6 15h11a4 4 0 0 0 .5-7.97A6 6 0 0 0 6 8.2 4 4 0 0 0 6 15Z"/><path d="M4 19h16M4 22h11"/></svg>',
    "drizzle": _SVG_OPEN + '<path d="M6 13h11a4 4 0 0 0 .5-7.97A6 6 0 0 0 6 6.2 4 4 0 0 0 6 13Z"/><path d="M9 17.5v2M13 17.5v2M17 17.5v2"/></svg>',
    "rain": _SVG_OPEN + '<path d="M6 13h11a4 4 0 0 0 .5-7.97A6 6 0 0 0 6 6.2 4 4 0 0 0 6 13Z"/><path d="M8 17l-1.5 4M13 17l-1.5 4M18 17l-1.5 4"/></svg>',
    "snow": _SVG_OPEN + '<path d="M6 12h11a4 4 0 0 0 .5-7.97A6 6 0 0 0 6 5.2 4 4 0 0 0 6 12Z"/><path d="M8 17v4M8 17.5l-1.7 1M8 17.5l1.7 1M8 20.5l-1.7-1M8 20.5l1.7-1M16 17v4M16 17.5l-1.7 1M16 17.5l1.7 1M16 20.5l-1.7-1M16 20.5l1.7-1"/></svg>',
    "storm": _SVG_OPEN + '<path d="M6 12h11a4 4 0 0 0 .5-7.97A6 6 0 0 0 6 5.2 4 4 0 0 0 6 12Z"/><path d="m13 15-3 5h3l-2 4"/></svg>',
}


def hebrew_date_str(dt):
    weekday = HEBREW_WEEKDAYS[dt.weekday()]
    month = HEBREW_MONTHS[dt.month - 1]
    return f"{weekday}, {dt.day} ב{month} {dt.year}"


def weather_desc(code):
    return WEATHER_CODE_MAP.get(code, ("", "cloud"))


def fetch_weather():
    results = []
    for name, lat, lon in WEATHER_CITIES:
        try:
            url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                   f"&current=temperature_2m,weather_code"
                   f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
                   f"&timezone=Asia%2FJerusalem&forecast_days=5")
            with urllib.request.urlopen(url, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            current = data.get("current", {})
            desc, icon_key = weather_desc(current.get("weather_code"))
            results.append({
                "name": name,
                "temp": current.get("temperature_2m"),
                "desc": desc,
                "icon": WEATHER_ICONS.get(icon_key, WEATHER_ICONS["cloud"]),
                "daily": data.get("daily", {}),
            })
        except Exception as e:
            print(f"מזג אוויר עבור {name} נכשל (מדלג): {e}")
            continue
    return results


# Real Shabbat times from Hebcal's public REST API (hebcal.github.io/api) -
# free, keyless, no fabricated/approximated times. b=10 requests candle-
# lighting with a custom 10-minute-before-sunset offset (owner directive:
# close 10 minutes before actual sunset, not the usual 18/40-minute
# candle-lighting custom) - Hebcal computes this directly, no separate raw-
# sunset lookup needed. M=on requests Havdalah at nightfall (tzeit
# hakochavim) for the reopen time. Tel Aviv (same reference city already
# used for weather) rather than Jerusalem, which overrides the offset
# parameter with its own fixed stricter local custom.
HEBCAL_GEONAME_ID = 293397  # Tel Aviv


def fetch_shabbat_times():
    try:
        url = f"https://www.hebcal.com/shabbat?cfg=json&geonameid={HEBCAL_GEONAME_ID}&b=10&M=on&leyning=off"
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        close_iso = reopen_iso = None
        for item in data.get("items", []):
            if item.get("category") == "candles":
                close_iso = item.get("date")
            elif item.get("category") == "havdalah":
                reopen_iso = item.get("date")
        if close_iso and reopen_iso:
            return close_iso, reopen_iso
    except Exception as e:
        print(f"שאיבת זמני שבת נכשלה (מדלג, האתר לא ייסגר הפעם): {e}")
    return None, None


WP_BOILERPLATE_RE = re.compile(r'^The post .* appeared first on .*\.?$')
RECIPE_CATEGORY = "בישול ומתכונים"
TV_CATEGORY = "טלוויזיה ושידורים חיים"

# Editorial-desk byline shown on every article - an honest description of how
# the site is actually organized (real content desks by topic), not invented
# named "reporters" with fabricated photos/credentials attached to bot-written
# text. This is the same kind of attribution many real wire/aggregator outlets
# use ("Reuters Staff", "Times of Israel Staff") - it tells readers and search
# engines the content has real editorial structure without claiming a specific
# human wrote it when none did.
DESK_BY_CATEGORY = {
    "חדשות": "מדור חדשות",
    "ספורט": "מדור ספורט",
    "כלכלה": "מדור כלכלה",
    "טכנולוגיה": "מדור טכנולוגיה",
    "בריאות": "מדור בריאות",
    "רכב": "מדור רכב",
    "תרבות ובידור": "מדור תרבות ובידור",
    RECIPE_CATEGORY: "מדור אוכל ומתכונים",
    "חרדים": "מדור חברה חרדית",
    TV_CATEGORY: "מדור תקשורת",
}


def byline_for(category):
    desk = DESK_BY_CATEGORY.get(category)
    return f"מערכת קודקוד | {desk}" if desk else "מערכת קודקוד"


# Real, substantive per-category meta descriptions (~25-40 words each,
# naming actual sub-topics) instead of one generic template reused for every
# category - this is the invisible <meta name="description"> tag, not
# visible page text. Checked against real competitor category pages first
# (ynet/mako/walla/calcalist): none show a visible "about this section"
# blurb on primary categories, all rely on a real per-category meta
# description to drive their Google sitelink snippets - same approach here.
CATEGORY_META_DESCRIPTIONS = {
    "חדשות": "חדשות מבזקות מישראל והעולם: ביטחון, פוליטיקה, פשיעה ואירועים שוטפים, כולל עדכונים ישירים מדוברויות ממשלתיות וצבאיות - מרוכז במקום אחד ומתעדכן לאורך היום.",
    "ספורט": "עדכוני ספורט מישראל והעולם: כדורגל, כדורסל, תוצאות, העברות והכרזות מההתאחדויות ומהקבוצות המובילות בליגות - הכל במקום אחד.",
    "כלכלה": "חדשות כלכלה ושוק ההון: ריבית, אינפלציה, שערי מניות, החלטות בנק ישראל ומשרד האוצר, ועדכוני שוק העבודה והנדל\"ן.",
    "טכנולוגיה": "חדשות טכנולוגיה מישראל והעולם: הייטק, סטארט-אפים, בינה מלאכותית ומוצרי צריכה - עדכונים שוטפים מהעולם הדיגיטלי.",
    "בריאות": "עדכוני בריאות ורפואה: הודעות והנחיות ממשרד הבריאות, מחקרים ועדכוני מערכת הבריאות בישראל.",
    "רכב": "חדשות רכב: השקות דגמים חדשים, מחירי דלק ותחבורה, רפורמות במשרד התחבורה ועדכונים מיבואני הרכב בישראל.",
    "תרבות ובידור": "עדכוני תרבות ובידור: קולנוע, טלוויזיה, מוזיקה, סלבריטאים ואירועים מעולם הבידור בישראל ובעולם.",
    RECIPE_CATEGORY: "מתכונים, טיפים למטבח וסקירות אוכל - כל מה שצריך כדי לבשל ולאפות בבית.",
    "חרדים": "חדשות ועדכונים מהחברה החרדית בישראל, כולל דוברויות ואירועים ייחודיים למגזר.",
}


def category_meta_description(category):
    return CATEGORY_META_DESCRIPTIONS.get(category, f"כל הכתבות בקטגוריית {category} - עדכונים שוטפים מהאתר החדשותי קודקוד")


# Colored category tag chips - a pattern present on every major Israeli news
# site (mako's yellow chips, ynet's colored kickers, Walla's colored
# eyebrows, Kan's red LIVE badge) instead of plain accent-colored text.
# A distinct, tasteful color per category (not the site's own bronze accent,
# which stays reserved for interactive/brand elements) so a reader can
# recognize a category at a glance the same way they can on those sites.
CATEGORY_COLORS = {
    "חדשות": "#7b241c",
    "ספורט": "#1e8449",
    "כלכלה": "#1a5276",
    "טכנולוגיה": "#6c3483",
    "בריאות": "#148f77",
    "רכב": "#616a6b",
    "תרבות ובידור": "#a1335c",
    RECIPE_CATEGORY: "#ca6f1e",
    "חרדים": "#7d6608",
    TV_CATEGORY: "#c0392b",
}


def cat_chip_style(category):
    color = CATEGORY_COLORS.get(category, "#8a7355")
    return f'style="background:{color};color:#fff;"'


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
        # ai_takeaways is written as "• point one • point two ..." (each
        # physical line in the frontmatter block-scalar prefixed with "•"),
        # so re-splitting on that character recovers the original list
        ai_takeaways = [t.strip() for t in data.get("ai_takeaways", "").split("•") if t.strip()]
        ai_tags = [t.strip() for t in data.get("ai_tags", "").split(",") if t.strip()]
        quick_image = data.get("quick_image") == "1"
        is_sponsored = data.get("sponsored") == "1"
        # detect_tv_watermark() in idf_scraper.py already flagged this once,
        # at scrape time, via a real vision check - not re-checked here.
        # A flagged thumbnail is swapped for the placeholder everywhere
        # (article page, cards, tv.html), not just hidden from hero/bento.
        has_watermark = data.get("has_watermark") == "1"
        image = PLACEHOLDER_IMG if has_watermark else data.get("image", "")
        # set by idf_scraper.py's AI enrichment - true only for real breaking
        # news in the owner's fixed hero-eligible topic list (security/
        # military, serious crime, major sports, celebrity/entertainment,
        # significant economy). Older articles scraped before this field
        # existed simply default to not-eligible, same as an enrichment
        # failure would - a conservative default, not a bug.
        hero_worthy = data.get("hero_worthy") == "1"
        is_short = data.get("is_short") == "1"

        articles.append({
            "title": title,
            "date": date_str,
            "dt": dt,
            "source": data.get("source", ""),
            "image": image,
            "link": data.get("link", ""),
            "category": data.get("category", "חדשות"),
            "video_id": data.get("video_id", ""),
            "body": body,
            "slug": slug,
            "dek": extract_dek(body),
            "is_quick": (len(body) < 500 and not data.get("video_id")) or quick_image,
            "quick_image": quick_image,
            "ai_takeaways": ai_takeaways,
            "ai_tags": ai_tags,
            "ai_tags_set": set(ai_tags),  # precomputed once - pick_related_articles compares this per pair, O(n^2) over ~14k articles
            "is_sponsored": is_sponsored,
            "has_watermark": has_watermark,
            "hero_worthy": hero_worthy,
            "is_short": is_short,
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
<meta name="robots" content="{robots_content}">
<link rel="icon" href="/favicon.png">
<link rel="sitemap" type="application/xml" href="/sitemap.xml">
<link rel="alternate" type="application/rss+xml" title="{site_name} - כל הכתבות" href="{site_url}/rss.xml">
{extra_rss_link}
<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/style.css">
{structured_data}
</head>
<body>
<header class="site-header">
  <a href="/" class="logo">קודקוד <span>חדשות</span></a>
  <nav class="categories">{cat_links}</nav>
  <button class="categories-toggle" id="categories-toggle" aria-label="כל הקטגוריות" aria-expanded="false">
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="17" x2="20" y2="17"/></svg>
  </button>
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
<div class="categories-drawer" id="categories-drawer">
  <nav class="categories-drawer-grid">{cat_links}</nav>
</div>
<nav class="mobile-tab-bar">
  <a href="/">
    <svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h14V10"/></svg>
    <span>בית</span>
  </a>
  <button type="button" id="tab-categories-toggle">
    <svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="2"><line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="12" x2="20" y2="12"/><line x1="4" y1="17" x2="20" y2="17"/></svg>
    <span>קטגוריות</span>
  </button>
  <button type="button" id="tab-search-toggle">
    <svg viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    <span>חיפוש</span>
  </button>
  <a href="/tv.html">
    {video_icon_svg}
    <span>טלוויזיה</span>
  </a>
</nav>
"""

PAGE_FOOT = """
{footer_promo}
<footer class="site-footer">
  <nav class="footer-nav">
    <a href="/about.html">אודות</a>
    <a href="/tip-line.html">שלחו לנו סקופ</a>
    <a href="/advertise.html">פרסמו אצלנו</a>
    <a href="/privacy.html">מדיניות פרטיות</a>
    <a href="/terms.html">תנאי שימוש</a>
    <a href="/accessibility.html">הצהרת נגישות</a>
  </nav>
  <p>© {year} קודקוד חדשות — כל הזכויות שמורות</p>
</footer>
<div class="cookie-banner" id="cookie-banner" hidden>
  <p>קודקוד שומר מידע מקומי בדפדפן שלכם (כתבות אחרונות, סימוני "אהבתי") כדי לשפר את החוויה. המידע נשאר במכשיר שלכם בלבד ואינו נשלח לשרת. פרטים ב<a href="/privacy.html" target="_blank">מדיניות הפרטיות</a>.</p>
  <div class="cookie-banner-actions">
    <button id="cookie-decline" class="cookie-btn cookie-btn-secondary">דחייה</button>
    <button id="cookie-accept" class="cookie-btn cookie-btn-primary">אישור</button>
  </div>
</div>
<div class="a11y-widget" id="a11y-widget">
  <button class="a11y-toggle" id="a11y-toggle" aria-label="פתח אפשרויות נגישות" aria-expanded="false" aria-controls="a11y-drawer">
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="4" r="2"/><path d="M19 7h-6.5L10 4H5a2 2 0 0 0-2 2v1a2 2 0 0 0 2 2h2l1.5 2L7 20h3l1.7-7h.6L14 20h3l-2.5-9L17 9h2a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/></svg>
  </button>
</div>
<div class="a11y-drawer" id="a11y-drawer" hidden>
  <div class="a11y-drawer-head">
    <h2>נגישות</h2>
    <button class="a11y-close" id="a11y-close" aria-label="סגור נגישות">&times;</button>
  </div>

  <div class="a11y-group">
    <h3>טקסט</h3>
    <div class="a11y-row">
      <button class="a11y-step-btn" data-a11y="font-dec" aria-label="הקטן גופן">א-</button>
      <button class="a11y-step-btn" data-a11y="font-inc" aria-label="הגדל גופן">א+</button>
    </div>
    <button class="a11y-toggle-btn" data-a11y="line-height">ריווח שורות מוגדל</button>
    <button class="a11y-toggle-btn" data-a11y="letter-spacing">ריווח אותיות מוגדל</button>
    <button class="a11y-toggle-btn" data-a11y="readable-font">גופן קריא</button>
  </div>

  <div class="a11y-group">
    <h3>תצוגה</h3>
    <button class="a11y-toggle-btn" data-a11y="contrast">ניגודיות גבוהה</button>
    <button class="a11y-toggle-btn" data-a11y="invert">היפוך צבעים</button>
    <button class="a11y-toggle-btn" data-a11y="grayscale">גווני אפור</button>
    <button class="a11y-toggle-btn" data-a11y="underline-links">הדגשת קישורים</button>
    <button class="a11y-toggle-btn" data-a11y="big-cursor">סמן עכבר מוגדל</button>
    <button class="a11y-toggle-btn" data-a11y="stop-motion">עצירת אנימציות</button>
  </div>

  <div class="a11y-group">
    <h3>כלים</h3>
    <button class="a11y-toggle-btn" data-a11y="reading-guide">סרגל קריאה</button>
    <button class="a11y-toggle-btn" id="a11y-read-aloud" data-a11y="read-aloud">הקראת הכתבה</button>
  </div>

  <button class="a11y-reset-btn" data-a11y="reset">איפוס כל ההגדרות</button>
</div>
<script src="/assets/search.js"></script>
</body>
</html>
"""


def content_type_of(a):
    """One of video/quick/standard - a coarse content-style signal used by
    the client-side affinity engine (assets/search.js) to learn which style
    of article a visitor tends to engage with, alongside category/source."""
    if a.get("video_id"):
        return "video"
    if a.get("is_quick") and a["category"] != RECIPE_CATEGORY:
        return "quick"
    return "standard"


def render_card(a):
    img = a["image"] or PLACEHOLDER_IMG
    is_recipe = a["category"] == RECIPE_CATEGORY
    video_badge = '<span class="badge badge-video">וידאו</span>' if a.get("video_id") else ""
    quick_badge = '<span class="badge badge-quick">בקצרה</span>' if a.get("is_quick") and not a.get("video_id") and not is_recipe else ""
    recipe_badge = '<span class="badge badge-recipe">מתכון</span>' if is_recipe else ""
    sponsored_badge = '<span class="badge badge-sponsored">תוכן שיווקי</span>' if a.get("is_sponsored") else ""
    card_cls = "card card-recipe" if is_recipe else "card"
    return f"""
    <a class="{card_cls}" href="/article/{a['slug']}.html" data-slug="{html.escape(a['slug'])}" data-title="{html.escape(a['title'])}" data-img="{html.escape(img)}" data-cat="{html.escape(a['category'])}" data-source="{html.escape(a['source'])}" data-type="{content_type_of(a)}">
      <div class="card-img-wrap">
        <img class="card-img" src="{html.escape(img)}" alt="{html.escape(a['title'])}" loading="lazy" onerror="this.src='{PLACEHOLDER_IMG}'">
        {video_badge}{quick_badge}{recipe_badge}{sponsored_badge}
      </div>
      <div class="card-body">
        <span class="card-cat" {cat_chip_style(a['category'])}>{html.escape(a['category'])}</span>
        <h3>{html.escape(a['title'])}</h3>
        <span class="card-meta">{html.escape(a['source'])} · {html.escape(a['date'][:10])}</span>
      </div>
    </a>"""


def render_quick_card(a):
    return f"""
    <a class="quick-card" href="/article/{a['slug']}.html">
      <span class="card-cat" {cat_chip_style(a['category'])}>{html.escape(a['category'])}</span>
      <h4>{html.escape(a['title'])}</h4>
      <span class="card-meta">{html.escape(a['source'])} · {html.escape(a['date'][:10])}</span>
    </a>"""


def render_short_card(a):
    """Vertical/portrait card (9:16) for YouTube Shorts and other social-
    style vertical video - a compact thumbnail-first treatment (title
    overlaid directly on the image, no separate white card body) matching
    the dedicated "Shorts" strip real Israeli news sites (e.g. Kikar
    HaShabbat) use for this content, distinct from קודקוד's regular
    landscape article cards."""
    img = a["image"] or PLACEHOLDER_IMG
    return f"""
    <a class="short-card" href="/article/{a['slug']}.html">
      <img class="short-card-img" src="{html.escape(img)}" alt="{html.escape(a['title'])}" loading="lazy" onerror="this.src='{PLACEHOLDER_IMG}'">
      <span class="short-card-play">{VIDEO_ICON_SVG}</span>
      <span class="short-card-title">{html.escape(a['title'])}</span>
    </a>"""


PLACEHOLDER_IMG = "/assets/placeholder.svg"

# Center/horizontal ad slots - only the creative the owner actually supplied,
# per explicit instruction to remove every other placeholder/house ad from
# rotation. No title/body/cta text was supplied for it, so none is invented.
MOCK_ADS = [
    {
        "cls": "ad-center-banner",
        "img": "/assets/ads/center-banner-01.gif",
        "eyebrow": "", "title": "", "body": "", "cta": "",
        "href": "https://veto-app.base44.app/",
    },
]

# Side-rail (both sides of the page) shows only this creative - a real
# paid/house placement the owner supplied directly, not part of the normal
# MOCK_ADS rotation. No title/body/cta text was supplied for it, so none is
# invented here - it's rendered as a pure clickable image.
SIDE_RAIL_ADS = [
    {
        "cls": "ad-side-banner",
        "img": "/assets/ads/side-banner-01.gif",
        "eyebrow": "", "title": "", "body": "", "cta": "",
        "href": "/advertise.html",
    },
]

_ad_counter = {"i": 0}

# the self-promo house-ad gets a handful of small floating icons drifting
# around the creative - part of the requested "busy/eye-catching" energetic
# treatment, not present on the plain content-recommendation slide. Position
# assigned inline per-icon (not via CSS nth-child) so the placement doesn't
# silently break if the surrounding markup is ever reordered.
def _icon_svg(inner, size=22):
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" '
            f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{inner}</svg>')


ICON_MEGAPHONE = _icon_svg('<path d="M3 11v2a2 2 0 0 0 2 2h1l1 5h2l-1-5h1l9 4V6l-9 4H6a2 2 0 0 0-2 2Z"/><path d="M19 9.5a3 3 0 0 1 0 5"/>')
ICON_SPARKLE = _icon_svg('<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/>', size=18)
ICON_ROCKET = _icon_svg('<path d="M12 2c2.5 2 4 5.5 4 9 0 2-.7 3.8-1.5 5.3L12 19l-2.5-2.7C8.7 14.8 8 13 8 11c0-3.5 1.5-7 4-9Z"/><circle cx="12" cy="10" r="1.6"/><path d="M9 16.5 6 20M15 16.5l3 3.5M10 19l-1 3M14 19l1 3"/>')
ICON_TARGET = _icon_svg('<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>', size=19)

AD_PROMO_ICONS = [
    (ICON_MEGAPHONE, "top:14%; left:8%; animation-delay:0s;"),
    (ICON_SPARKLE, "top:62%; left:4%; animation-delay:0.8s;"),
    (ICON_ROCKET, "top:18%; right:10%; animation-delay:1.6s;"),
    (ICON_TARGET, "top:66%; right:6%; animation-delay:2.4s;"),
]


def ad_slot_html(compact=False, ads=None, lazy_viewport=False):
    # each call embeds every ad entry as its own crossfade slide
    # (assets/search.js rotates .active between them client-side, same
    # crossfade technique as the homepage hero) - _ad_counter only picks
    # which slide starts active, so multiple slots on one page don't all
    # open on the same creative
    ads = ads if ads is not None else MOCK_ADS
    start = _ad_counter["i"] % len(ads)
    _ad_counter["i"] += 1
    size_cls = "ad-slot-compact" if compact else ""

    slides = []
    for i, ad in enumerate(ads):
        active_cls = " active" if i == start else ""
        # side-rail slots are display:none below 1500px viewport width, but a
        # plain CSS background-image still gets fetched by every visitor
        # regardless - deferring it to JS gated on the same media query means
        # mobile visitors (the majority of this site's traffic) never
        # download it at all
        if ad.get("img") and lazy_viewport:
            bg_style = f" data-bg-lazy=\"{html.escape(ad['img'])}\""
        elif ad.get("img"):
            bg_style = f" style=\"background-image:url('{html.escape(ad['img'])}')\""
        else:
            bg_style = ""
        icons_html = "".join(
            f'<span class="ad-promo-icon" style="{pos}">{icon}</span>' for icon, pos in AD_PROMO_ICONS
        ) if ad["cls"] == "ad-promo-self" else ""
        badge_html = '<span class="ad-promo-badge">חינם!</span>' if ad["cls"] == "ad-promo-self" else ""
        # a pure-image creative (no title supplied) skips the text overlay
        # entirely instead of rendering empty eyebrow/title/body/cta spans
        creative_html = "" if not ad.get("title") else f"""
        <div class="ad-creative">
          <span class="ad-eyebrow">{html.escape(ad['eyebrow'])}</span>
          <h4 class="ad-title">{html.escape(ad['title'])}</h4>
          <p class="ad-body">{html.escape(ad['body'])}</p>
          <span class="ad-cta">{html.escape(ad['cta'])}</span>
        </div>"""
        tag_html = "" if not ad.get("title") else f'<span class="ad-tag">{"מומלץ" if ad["cls"] != "ad-promo-self" else "פרסומת"}</span>'
        ad_href = ad.get("href", "#")
        # a real paid advertiser link (external URL) opens in a new tab and
        # is marked rel="sponsored" per Google's own guidance for paid
        # links, same treatment already used for the article source-credit
        # link when is_sponsored is set - internal links (e.g. /advertise.
        # html) keep the plain same-tab behavior
        ext_attrs = ' target="_blank" rel="sponsored noopener"' if ad_href.startswith("http") else ""
        slides.append(f"""
      <a class="ad-slide {ad['cls']}{active_cls}" href="{html.escape(ad_href)}"{ext_attrs} data-index="{i}">
        <div class="ad-slot-bg"{bg_style}></div>
        <div class="ad-slot-shine"></div>
        {icons_html}
        {tag_html}
        {badge_html}
        {creative_html}
      </a>""")

    return f'<div class="ad-slot {size_cls}">{"".join(slides)}</div>'




VIDEO_ICON_SVG = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>'
MAGAZINE_ICON_SVG = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>'


def cat_nav(categories, active=None):
    # recipes are lifestyle/feature content, not news - keep them last in
    # the nav rather than wherever they happen to fall alphabetically
    ordered = sorted(categories, key=lambda c: (c == RECIPE_CATEGORY, c))
    links = ['<a href="/" class="{}">כל החדשות</a>'.format("active" if active is None else "")]
    for c in ordered:
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


# Matches both external (https?://) links and internal relative (/article/..)
# links - the latter used by the auto internal-linking engine in
# idf_scraper.py, which writes plain [text](/article/slug.html) markdown
MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(((?:https?://|/)[^\s)]+)\)')


def render_body(body_text):
    paragraphs = []
    for line in body_text.split("\n"):
        line = line.strip()
        if not line or WP_BOILERPLATE_RE.match(line):
            continue
        escaped = html.escape(line)

        def repl(m):
            text, url = m.group(1), m.group(2)
            if url.startswith("/"):
                return f'<a href="{html.escape(url)}">{text}</a>'
            return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{text}</a>'

        linked = MD_LINK_RE.sub(repl, escaped)
        paragraphs.append(f"<p>{linked}</p>")
    return "".join(paragraphs)


def write_page(path, title, description, categories, active_cat, body_html,
               ticker_text, canonical=None, og_type="website", og_image="", structured_data="",
               category_rss_url=None, noindex=False):
    canonical = canonical or SITE_URL + "/"
    og_image_tag = f'<meta property="og:image" content="{html.escape(og_image)}">' if og_image else ""
    extra_rss_link = ""
    if category_rss_url:
        extra_rss_link = (f'<link rel="alternate" type="application/rss+xml" '
                           f'title="{html.escape(active_cat)} - {SITE_NAME}" href="{html.escape(category_rss_url)}">')
    robots_content = "noindex, follow" if noindex else "index, follow, max-image-preview:large"
    full = PAGE_HEAD.format(
        title=html.escape(title),
        description=html.escape(description),
        canonical=html.escape(canonical),
        og_type=og_type,
        site_name=SITE_NAME,
        site_url=SITE_URL,
        og_image_tag=og_image_tag,
        cat_links=cat_nav(categories, active_cat),
        structured_data=structured_data,
        extra_rss_link=extra_rss_link,
        robots_content=robots_content,
        video_icon_svg=VIDEO_ICON_SVG,
    )
    full = full.replace('<meta charset="UTF-8">', f'<meta charset="UTF-8">\n{SHABBAT_HEAD_SCRIPT}')
    full = full.replace("<header class=\"site-header\">",
                         f'{WEATHER_BAR_HTML}\n<div class="ticker"><div class="ticker-move">{html.escape(ticker_text)}</div></div>\n<header class="site-header">')
    page_shell = f"""
<div class="page-shell">
  <aside class="side-rail side-rail-right">{ad_slot_html(compact=True, ads=SIDE_RAIL_ADS, lazy_viewport=True)}</aside>
  <div class="page-shell-content">{body_html}</div>
  <aside class="side-rail side-rail-left">{ad_slot_html(compact=True, ads=SIDE_RAIL_ADS, lazy_viewport=True)}</aside>
</div>"""
    foot = PAGE_FOOT.format(year=datetime.now().year, footer_promo=FOOTER_PROMO_HTML)
    if SHABBAT_OVERLAY_HTML:
        foot = foot.replace("</body>", f"{SHABBAT_OVERLAY_HTML}\n</body>")
    full += page_shell + foot
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
    <li><strong>ספורט:</strong> תוצאות, סיקור אירועי ספורט ותקצירים מהארץ ומהעולם.</li>
    <li><strong>בריאות:</strong> עדכונים ומחקרים מעולם הרפואה והבריאות.</li>
    <li><strong>תרבות ובידור:</strong> קולנוע, טלוויזיה, מוזיקה וספרות.</li>
    <li><strong>רכב:</strong> חדשות רכב, מבחני דרכים ועדכוני תעשייה.</li>
    <li><strong>בישול ומתכונים:</strong> תוכן אוכל ולייף-סטייל ממיטב אתרי הבישול בישראל.</li>
    <li><strong>וידאו:</strong> קטעי חדשות מצולמים מערוצי החדשות המובילים, מוצגים בנגן הווידאו הייעודי של קודקוד.</li>
  </ul>

  <h2>למה קודקוד?</h2>
  <ul>
    <li><strong>מהירות:</strong> עדכון אוטומטי לאורך היממה, כל 15 דקות, ממגוון רחב של מקורות.</li>
    <li><strong>מגוון:</strong> חדשות, כלכלה, טכנולוגיה, ספורט, בריאות, תרבות, רכב, חרדים ובישול - הכול תחת קורת גג אחת.</li>
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

ICON_PIN = _icon_svg('<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21Z"/><circle cx="12" cy="9.5" r="2.4"/>', size=26)
ICON_TAG = _icon_svg('<path d="M20 12.5 12.5 20a1.5 1.5 0 0 1-2.1 0L4 13.6a1.5 1.5 0 0 1 0-2.1L11.5 4H18a2 2 0 0 1 2 2v6.5Z"/><circle cx="15.5" cy="8.5" r="1.2"/>', size=26)
ICON_BOLT = _icon_svg('<path d="M13 3 5 13.5h5.5L11 21l8-10.5h-5.5L13 3Z"/>', size=26)
ICON_PALETTE = _icon_svg('<path d="M12 3a9 9 0 1 0 0 18c1.2 0 2-1 2-2 0-.6-.2-1-.5-1.4-.3-.3-.5-.7-.5-1.1 0-1 .8-1.5 1.8-1.5H17a4 4 0 0 0 4-4c0-4.4-4-8-9-8Z"/><circle cx="7.5" cy="10.5" r="1.1"/><circle cx="10.5" cy="7" r="1.1"/><circle cx="15" cy="7.5" r="1.1"/><circle cx="17" cy="11" r="1.1"/>', size=26)
ICON_PERSON = _icon_svg('<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.5 3-6 7-6s7 2.5 7 6"/>', size=30)
ICON_MAIL = _icon_svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/>', size=30)
ICON_CHECK = _icon_svg('<circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.5 2.5L16 9"/>', size=30)

ADVERTISE_INFO_CARDS = [
    (ICON_PIN, "איפה זה מופיע", "באנר בעמוד הבית, בין מקטעי הקטגוריות, בסיום כל כתבה, ובצדי העמוד בדסקטופ."),
    (ICON_TAG, "המחיר", "הפעם זה באמת חינם - ללא עלות, שבוע אחד לפחות, ללא התחייבות מעבר לכך."),
    (ICON_BOLT, "התהליך", "שולחים חומר מוכן בטופס למטה, עובר אישור ידני, ובדרך כלל עולה לאוויר תוך יום."),
    (ICON_PALETTE, "מה שאנחנו לא עושים", "אנחנו לא עורכים או יוצרים את הפרסומת - רק מעלים חומר שמגיע מוכן בדיוק כפי שצריך."),
]

ADVERTISE_FAQ = [
    ("איזה פורמט תמונה אתם צריכים?",
     "תמונה או GIF ביחס אורך-רוחב נוח - בסביבות 3:1 עד 16:9 לבאנרים אופקיים, ו-1:2 (לדוגמה 300x600 פיקסלים) לבאנרים אנכיים בצדי העמוד. קובץ JPG, PNG, WebP או GIF."),
    ("אתם עורכים או מעצבים את הפרסומת בשבילי?",
     "לא. אנחנו מעלים בדיוק את מה שנשלח - חומר צריך להגיע מוכן, כולל כל הטקסט (כותרת, תיאור, טקסט כפתור) וקישור היעד."),
    ("כמה זמן לוקח עד שהפרסומת עולה לאוויר?",
     "הבקשה עוברת בדיקה ואישור ידני מצידנו - במרבית המקרים תוך יום מרגע שהחומר מגיע מוכן ותקין."),
    ("יש עלות כלשהי?",
     "לא, כרגע זה באמת חינם. אין תשלום, ואין התחייבות מעבר לשבוע ההופעה הראשון."),
    ("יש התחייבות ארוכת טווח?",
     "לא - שבוע אחד הוא משך ההופעה המינימלי, ואין מחויבות שלנו להארכה מעבר לכך."),
    ("איפה בדיוק הפרסומת תוצג?",
     "תלוי בסוג הבאנר שנשלח: אופקי - בעמוד הבית ובין קטגוריות; אנכי - בצדי העמוד בתצוגת דסקטופ רחבה."),
]


def _advertise_faq_html():
    items = []
    for q, a in ADVERTISE_FAQ:
        items.append(f"""
    <details class="faq-item">
      <summary>{html.escape(q)}<span class="faq-toggle">+</span></summary>
      <p>{html.escape(a)}</p>
    </details>""")
    return "".join(items)


def _advertise_info_cards_html():
    cards = []
    for icon, title, desc in ADVERTISE_INFO_CARDS:
        cards.append(f"""
    <div class="advertise-info-card">
      <span class="advertise-info-icon">{icon}</span>
      <h3>{html.escape(title)}</h3>
      <p>{html.escape(desc)}</p>
    </div>""")
    return "".join(cards)


ADVERTISE_BODY = f"""
<main class="static-page advertise-page">
  <section class="advertise-hero">
    <h1>פרסמו <span>אצלנו</span></h1>
    <p class="lead">קודקוד חדשות מגיע לקהל קוראים רחב ומגוון. הפעם זה באמת חינם: שלחו לנו חומר פרסומי מוכן, ומחר הוא באוויר.</p>
  </section>

  <section class="advertise-info-grid">{_advertise_info_cards_html()}
  </section>

  <section class="advertise-faq">
    <h2>שאלות <span>ותשובות</span></h2>
    {_advertise_faq_html()}
  </section>

  <section class="advertise-wizard-section">
    <h2>השאירו <span>פרטים</span></h2>
    <div class="ad-wizard-card">
    <div class="ad-wizard-progress">
      <span class="ad-wizard-dot active" data-dot="0"></span>
      <span class="ad-wizard-dot" data-dot="1"></span>
      <span class="ad-wizard-dot" data-dot="2"></span>
      <span class="ad-wizard-dot" data-dot="3"></span>
    </div>
    <form class="contact-form ad-wizard-form" action="{TIP_FORM_ACTION}" method="POST">
      <div class="ad-wizard-step active" data-step="0">
        <span class="ad-wizard-icon">{ICON_PERSON}</span>
        <h3>קודם כל, מי אתם?</h3>
        <p class="ad-wizard-hint">שם מלא, שם חברה, או שם חברת הפרסום</p>
        <input type="text" name="name" placeholder="השם שלכם" required>
        <div class="ad-wizard-nav"><button type="button" class="ad-wizard-next">הבא ←</button></div>
      </div>
      <div class="ad-wizard-step" data-step="1">
        <span class="ad-wizard-icon">{ICON_MAIL}</span>
        <h3>איך נחזור אליכם?</h3>
        <p class="ad-wizard-hint">נשתמש בזה רק כדי לאשר ולתאם את ההעלאה</p>
        <input type="email" name="email" placeholder="אימייל" required>
        <div class="ad-wizard-nav">
          <button type="button" class="ad-wizard-back">→ הקודם</button>
          <button type="button" class="ad-wizard-next">הבא ←</button>
        </div>
      </div>
      <div class="ad-wizard-step" data-step="2">
        <span class="ad-wizard-icon">{ICON_PALETTE}</span>
        <h3>פרטי הפרסומת</h3>
        <p class="ad-wizard-hint">קישור לתמונה המוכנה, ופירוט הכותרת/תיאור/טקסט כפתור/קישור יעד</p>
        <input type="text" name="creative_link" placeholder="קישור לתמונה/לחומר הפרסומי (אם קיים)">
        <textarea name="message" rows="5" placeholder="כותרת, תיאור, טקסט כפתור, וקישור היעד - כפי שפורט למעלה..." required></textarea>
        <div class="ad-wizard-nav">
          <button type="button" class="ad-wizard-back">→ הקודם</button>
          <button type="button" class="ad-wizard-next">הבא ←</button>
        </div>
      </div>
      <div class="ad-wizard-step" data-step="3">
        <span class="ad-wizard-icon">{ICON_CHECK}</span>
        <h3>כמעט סיימנו</h3>
        <p class="ad-wizard-hint">הבקשה תישלח לאישור ידני - נחזור אליכם ברגע שהפרסומת עולה לאוויר</p>
        <label class="consent-checkbox">
          <input type="checkbox" name="privacy_consent" value="yes" required>
          <span>קראתי ואני מסכים/ה ל<a href="/privacy.html" target="_blank">מדיניות הפרטיות</a> - הפרטים ישמשו ליצירת קשר בלבד</span>
        </label>
        <div class="ad-wizard-nav">
          <button type="button" class="ad-wizard-back">→ הקודם</button>
          <button type="submit">שליחה לאישור</button>
        </div>
      </div>
    </form>
  </div>
  </section>
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
    <label class="consent-checkbox">
      <input type="checkbox" name="privacy_consent" value="yes" required>
      <span>קראתי ואני מסכים/ה ל<a href="/privacy.html" target="_blank">מדיניות הפרטיות</a> - הפרטים ישמשו ליצירת קשר בלבד</span>
    </label>
    <button type="submit">שגר דיווח לחדר המבזקים</button>
  </form>
</main>"""

PRIVACY_BODY = """
<main class="static-page legal-page">
  <h1>מדיניות <span>פרטיות</span></h1>
  <p class="lead">מדיניות זו מסבירה אילו נתונים קודקוד אוסף, כיצד הם נשמרים, ומהן הזכויות שלכם. המדיניות מנוסחת בהתאם לחוק הגנת הפרטיות, התשמ"א-1981, ותיקון 13 לחוק (בתוקף מאוגוסט 2025).</p>

  <h2>מה קודקוד הוא - ומה הוא לא</h2>
  <p>קודקוד הוא אתר סטטי המתארח על תשתית GitHub Pages, ללא שרת צד-שרת, ללא בסיס נתונים, וללא מערכת הרשמת משתמשים. האתר אינו אוסף, שומר, או מעבד מידע אישי בשרתים שלו - כי אין לו שרתים כאלה.</p>

  <h2>מידע הנשמר בדפדפן שלכם (localStorage)</h2>
  <p>האתר שומר מידע מקומי בדפדפן שלכם בלבד, באמצעות טכנולוגיית localStorage (דומה לעוגיות אך אינה נשלחת לשרת כלשהו). מידע זה כולל:</p>
  <ul>
    <li><strong>כתבות שנצפו לאחרונה:</strong> רשימת הכתבות שקראתם, כדי להציג לכם אותן בעמוד הבית.</li>
    <li><strong>כתבות שסימנתם "אהבתי":</strong> נשמר מקומית כדי להציג את הסימון בביקור הבא.</li>
    <li><strong>העדפות תוכן:</strong> ספירה מקומית ומצטברת של הקטגוריות, המקורות וסוגי התוכן (וידאו/בקצרה/רגיל) שבהם צפיתם או שאהבתם, המשמשת להתאמת סדר הכתבות המוצגות לכם. אינה כוללת שום זיהוי אישי, ואינה יוצאת מהדפדפן שלכם.</li>
    <li><strong>העדפות נגישות:</strong> כל שינוי שביצעתם דרך מגירת הנגישות (גודל גופן, ניגודיות, ריווח, גופן קריא, היפוך צבעים ועוד).</li>
    <li><strong>בחירת ההסכמה שלכם למדיניות זו.</strong></li>
  </ul>
  <p>מידע זה <strong>אינו</strong> נשלח לשרת כלשהו, אינו משותף עם צד שלישי, ואינו מזהה אתכם אישית. הוא קיים רק במכשיר שלכם, ואתם יכולים למחוק אותו בכל עת דרך הגדרות הדפדפן, או על-ידי לחיצה על "דחייה" בבאנר העוגיות.</p>

  <h2>טפסים ויצירת קשר</h2>
  <p>כאשר אתם ממלאים טופס באתר (יצירת קשר, פרסום, או דיווח על סקופ), הפרטים שאתם מזינים - שם, אימייל, ותוכן הפנייה - נשלחים באמצעות שירות חיצוני בשם <strong>Formspree</strong>, המעבד את הטופס ומעביר אותו אלינו במייל. Formspree הוא צד שלישי, ומדיניות הפרטיות שלו חלה על עיבוד הנתונים בצדו. איננו משתמשים במידע זה למטרה כלשהי מעבר למענה לפנייתכם.</p>

  <h2>עיבוד AI בכתבות</h2>
  <p>חלק מהכתבות באתר עשויות לכלול תיבת "עיקרי הדברים - AI" (תמצית של 3-4 נקודות עובדתיות) ותגיות נושא, מעל הכתבה עצמה - הכל נוצר אוטומטית על סמך טקסט הכתבה המקורית בלבד, באמצעות שירות בינה מלאכותית חיצוני (Groq). אותו תהליך עשוי גם לתקן שגיאות כתיב ופיסוק בטקסט הכתבה, מבלי לשנות עובדות או משמעות. תהליך זה שולח את טקסט הכתבה (לא מידע אישי של המבקרים באתר) לעיבוד אצל הספק החיצוני. התוצרים מתפרסמים בנוסף לכתבה המלאה עם ייחוס וקישור למקור, ולעולם לא במקומה.</p>

  <h2>תגובות בכתבות</h2>
  <p>מערכת התגובות באתר (giscus) מבוססת על GitHub Discussions - כדי להשאיר תגובה נדרשת התחברות עם חשבון GitHub קיים (התגובות אינן אנונימיות; שם המשתמש ותמונת הפרופיל שלכם ב-GitHub מוצגים לצד התגובה, כפי שקורה בכל דיון ב-GitHub). תוכן התגובה מאוחסן כדיון ציבורי במאגר ה-GitHub של האתר, בכפוף למדיניות הפרטיות ותנאי השימוש של GitHub. אינכם חייבים להשתמש במערכת התגובות כדי לקרוא את האתר.</p>

  <h2>עוגיות וכלי מעקב</h2>
  <p>קודקוד אינו משתמש בעוגיות מעקב (tracking cookies), פיקסלים פרסומיים, או כלי אנליטיקה חיצוניים כלשהם, נכון לכתיבת מדיניות זו. מיקומי הפרסומת המוצגים באתר הם תוכן הדגמה בלבד ואינם טוענים סקריפטים של רשת פרסום חיצונית.</p>

  <h2>קישורים לאתרים חיצוניים</h2>
  <p>קודקוד הוא אתר המרכז כתבות ממקורות חדשות שונים. כל כתבה מקושרת לאתר המקור המקורי. לאחר לחיצה על קישור כזה, אתם עוברים לאתר חיצוני שאינו בשליטתנו, ומדיניות הפרטיות שלו חלה משם ואילך.</p>

  <h2>הזכויות שלכם</h2>
  <p>מאחר שהאתר אינו שומר מידע אישי מזהה בשרת כלשהו, אין לנו מאגר מידע לעיין בו, לתקן, או למחוק על-פי בקשה. מידע שנשמר בדפדפן שלכם (localStorage) ניתן למחיקה בכל עת דרך הגדרות הדפדפן. אם שלחתם לנו טופס, ניתן לפנות אלינו לבקש מחיקת הפנייה.</p>

  <h2>יצירת קשר בנושאי פרטיות</h2>
  <p>לשאלות או בקשות בנושא פרטיות, ניתן לפנות אלינו דרך <a href="/tip-line.html">עמוד יצירת הקשר</a>.</p>

  <p class="legal-updated">מדיניות זו עודכנה לאחרונה: יולי 2026.</p>
</main>"""

TERMS_BODY = """
<main class="static-page legal-page">
  <h1>תנאי <span>שימוש</span></h1>
  <p class="lead">השימוש באתר קודקוד כפוף לתנאים המפורטים להלן. גלישה באתר מהווה הסכמה לתנאים אלה.</p>

  <h2>אופי האתר</h2>
  <p>קודקוד הוא אגרגטור חדשות אוטומטי. האתר אוסף ומציג מבזקים ממקורות חדשות קיימים בישראל, עם ייחוס וקישור מלא למקור המקורי של כל כתבה. קודקוד אינו כותב, עורך, או אחראי לתוכן הכתבות המקוריות, ואינו טוען לבעלות עליהן. זכויות היוצרים בתוכן הכתבות שייכות למקור המקורי שלהן בלבד. חלק מהכתבות עשויות לכלול, בנוסף, תיבת "עיקרי הדברים - AI" ותגיות נושא, המסומנות בבירור - נוצרות אוטומטית מטקסט הכתבה המקורית, ומתפרסמות לצד הכתבה המלאה ולא במקומה.</p>
  <p>לצד הכתבות המצוטטות, קודקוד עשוי לפרסם מדי פעם תוכן שיווקי בתשלום מטעם גורם עסקי. תוכן כזה מסומן תמיד ובבירור - הן בתג "תוכן שיווקי" בכל מקום שבו הכתבה מופיעה באתר, והן בבאנר גלוי בראש הכתבה עצמה - ואינו מוצג כתוכן עיתונאי.</p>

  <h2>שימוש הוגן</h2>
  <p>הצגת קטעי כתבות עם ייחוס וקישור למקור נעשית במסגרת שימוש הוגן ומקובל באגרגציית חדשות. כל כתבה כוללת קישור ברור לכתבה המלאה באתר המקור, וקודקוד ממליץ לקוראים לבקר באתר המקור לקריאה מלאה ולתמיכה בעיתונות המקורית.</p>

  <h2>אין אחריות לתוכן צד שלישי</h2>
  <p>קודקוד אינו אחראי לדיוק, לעדכניות, או לאמינות התוכן המקורי המוצג באתר, שכן מדובר בתוכן שנוצר ונערך על-ידי גורמים שלישיים (מקורות החדשות). כל טענה בנוגע לתוכן כתבה יש להפנות למקור המקורי שלה.</p>

  <h2>שימוש אסור</h2>
  <p>אין להשתמש באתר לצורך פעילות בלתי חוקית, להעתיק או להפיץ מחדש את מבנה האתר או קוד המקור שלו לצרכים מסחריים ללא אישור, או לנסות לשבש את פעילות האתר.</p>

  <h2>שינויים בתנאים</h2>
  <p>קודקוד רשאי לעדכן תנאים אלה מעת לעת. המשך השימוש באתר לאחר עדכון מהווה הסכמה לתנאים המעודכנים.</p>

  <h2>יצירת קשר</h2>
  <p>לשאלות בנוגע לתנאי השימוש, ניתן לפנות אלינו דרך <a href="/tip-line.html">עמוד יצירת הקשר</a>.</p>

  <p class="legal-updated">תנאים אלה עודכנו לאחרונה: יולי 2026.</p>
</main>"""

ACCESSIBILITY_BODY = """
<main class="static-page legal-page">
  <h1>הצהרת <span>נגישות</span></h1>
  <p class="lead">קודקוד רואה חשיבות רבה במתן שירות שוויוני ונגיש לכלל הציבור, לרבות אנשים עם מוגבלות, ופועל להנגשת האתר בהתאם לתקן הישראלי (ת"י) 5568 להנגשת תכנים באינטרנט, ברמת AA, ובהתאם לחוק שוויון זכויות לאנשים עם מוגבלות, התשנ"ח-1998.</p>

  <h2>אמצעי הנגישות באתר</h2>
  <ul>
    <li><strong>רכיב נגישות:</strong> בכל עמוד קיים כפתור צף שפותח מגירת נגישות מלאה - הגדלת/הקטנת גופן, ריווח שורות ואותיות מוגדל, גופן קריא, ניגודיות גבוהה, היפוך צבעים, גווני אפור, הדגשת קישורים, סמן עכבר מוגדל, סרגל קריאה עוקב עכבר, עצירת אנימציות, והקראת כתבות בקול (באמצעות מנוע הקראה מובנה של הדפדפן) - עם אפשרות איפוס מלאה.</li>
    <li><strong>ניווט מקלדת:</strong> ניתן לנווט בין כל הקישורים, הכפתורים והשדות באתר באמצעות מקש Tab בלבד.</li>
    <li><strong>טקסט חלופי לתמונות:</strong> תמונות הכתבות באתר כוללות תיאור טקסטואלי חלופי (alt) המאפשר לתוכנות הקראה להנגיש את התוכן.</li>
    <li><strong>מבנה סמנטי:</strong> האתר בנוי עם כותרות היררכיות (H1-H3) ותגיות HTML סמנטיות, לתמיכה בקוראי מסך.</li>
    <li><strong>ניגודיות צבעים:</strong> צבעי הטקסט והרקע באתר נבחרו כך שיעמדו ביחס ניגודיות של 4.5:1 לפחות.</li>
  </ul>

  <h2>מגבלות ידועות</h2>
  <p>קודקוד הוא אגרגטור המציג תוכן חיצוני (כתבות, תמונות, ולעיתים מוצגים גם סרטוני וידאו) שמקורו באתרי חדשות אחרים. ייתכן שתוכן זה, בהיותו חיצוני, אינו עומד באופן מלא בדרישות הנגישות. בנוסף, מערכת התגובות (giscus) טעונה כווידג'ט חיצוני שאיננו שולטים באופן מלא בנגישותו. אנו פועלים לשפר את חוויית הנגישות באופן שוטף.</p>

  <h2>פנייה בנושא נגישות</h2>
  <p>נתקלתם בבעיית נגישות באתר? נשמח לדעת ולטפל בפנייתכם. ניתן לפנות אלינו דרך <a href="/tip-line.html">עמוד יצירת הקשר</a>, בציון "נגישות" בתוכן הפנייה.</p>

  <p class="legal-updated">הצהרה זו עודכנה לאחרונה ונבדקה: יולי 2026.</p>
</main>"""


def json_ld_script(data):
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'


RSS_FEED_LIMIT = 40


def rss_item_xml(a):
    canonical = f"{SITE_URL}/article/{a['slug']}.html"
    pub_date = format_datetime(a["dt"].replace(tzinfo=timezone.utc)) if a["dt"] != datetime.min else ""
    description = html.escape(a.get("dek") or a["title"])
    enclosure = f'<enclosure url="{html.escape(a["image"])}" type="image/jpeg"/>' if a.get("image") else ""
    return f"""  <item>
    <title>{html.escape(a['title'])}</title>
    <link>{canonical}</link>
    <guid isPermaLink="true">{canonical}</guid>
    <pubDate>{pub_date}</pubDate>
    <category>{html.escape(a['category'])}</category>
    <description>{description}</description>
    {enclosure}
  </item>"""


def write_rss_feed(path, feed_url, title, description, articles, limit=RSS_FEED_LIMIT):
    items = "".join(rss_item_xml(a) for a in articles[:limit])
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{html.escape(title)}</title>
  <link>{SITE_URL}/</link>
  <description>{html.escape(description)}</description>
  <language>he-il</language>
  <atom:link href="{html.escape(feed_url)}" rel="self" type="application/rss+xml"/>
{items}
</channel>
</rss>"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)


def article_structured_data(a, canonical):
    published = a["dt"].isoformat() if a["dt"] != datetime.min else ""
    # Sponsored/paid content doesn't get marked up as NewsArticle - Google's
    # guidance treats that as editorial content, and this isn't; a plain
    # BreadcrumbList (still accurate regardless of content type) is enough
    if a.get("is_sponsored"):
        breadcrumb_only = {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": SITE_URL + "/"},
                {"@type": "ListItem", "position": 2, "name": a["category"], "item": f"{SITE_URL}/category/{slugify(a['category'], a['category'])}.html"},
                {"@type": "ListItem", "position": 3, "name": a["title"], "item": canonical},
            ],
        }
        return json_ld_script(breadcrumb_only)
    data = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": a["title"],
        "description": (" ".join(a["ai_takeaways"][:2]) if a.get("ai_takeaways")
                         else a.get("dek", "") or a["title"]),
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
        # mainEntityOfPage stays our OWN canonical URL, not the source's -
        # this page is the NewsArticle entity being described; pointing it
        # at the third-party source would be both spec-incorrect (that
        # property means "the page that most represents this entity") and
        # would undercut our own attribution model, not reinforce it
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
    }
    if a.get("ai_tags"):
        data["keywords"] = ", ".join(a["ai_tags"])
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


def article_list_items(articles, limit=20):
    """Minimal ListItem entries (position + url) for an ItemList of articles -
    Google's documented pattern for a listing page, deliberately not nesting
    full NewsArticle objects here since each article already carries its own
    complete NewsArticle schema on its own page."""
    return [
        {"@type": "ListItem", "position": i + 1, "url": f"{SITE_URL}/article/{a['slug']}.html"}
        for i, a in enumerate(articles[:limit])
    ]


def category_structured_data(category_name, canonical, articles=None):
    data = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f"{category_name} - {SITE_NAME}",
        "url": canonical,
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": SITE_URL + "/"},
    }
    if articles:
        data["mainEntity"] = {"@type": "ItemList", "itemListElement": article_list_items(articles)}
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": SITE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": category_name, "item": canonical},
        ],
    }
    return json_ld_script(data) + json_ld_script(breadcrumb)


def homepage_structured_data(articles=None):
    data = {
        "@context": "https://schema.org",
        "@type": "NewsMediaOrganization",
        "name": SITE_NAME,
        "url": SITE_URL + "/",
        "logo": {"@type": "ImageObject", "url": SITE_URL + "/favicon.png"},
        "description": "קודקוד הוא מרכז חדשותי דיגיטלי ישראלי המרכז מבזקים ממיטב מקורות החדשות בעברית - חדשות, כלכלה, טכנולוגיה, חרדים, ספורט, בריאות, תרבות ורכב.",
        "correctionsPolicy": SITE_URL + "/tip-line.html",
        "missionCoveragePrioritiesPolicy": SITE_URL + "/about.html",
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
    parts = [json_ld_script(data), json_ld_script(website)]
    if articles:
        item_list = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": f"כתבות אחרונות - {SITE_NAME}",
            "itemListElement": article_list_items(articles),
        }
        parts.append(json_ld_script(item_list))
    return "".join(parts)


def pick_diverse(articles, count, max_per_category):
    """Picks up to `count` articles from a date-sorted list, capping how many
    can share the same category - so a burst of scraped articles from one
    feed/category (e.g. a run of car-review posts) can't crowd out every
    other category in the homepage's mixed sections. Still prioritizes
    recency: only skips an article for exceeding its category's cap, never
    for any other reason. Falls back to filling remaining slots from
    whatever's left over (even past the cap) rather than coming up short."""
    picked, leftover, cat_counts = [], [], {}
    for a in articles:
        if len(picked) >= count:
            break
        cat = a["category"]
        if cat_counts.get(cat, 0) < max_per_category:
            picked.append(a)
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        else:
            leftover.append(a)
    if len(picked) < count:
        picked.extend(leftover[:count - len(picked)])
    return picked


def pick_related_articles(a, listable, count=6):
    """Shared AI tags (specific people/orgs/topics) are a much stronger
    relevance signal than "same category" alone - two same-category articles
    can be about completely unrelated things, while a shared tag means they
    are actually about the same story/subject. Pages-per-visit is the single
    strongest predictor of a return visit (real data: 1-page visitors return
    at ~8%, 2-page visitors at ~22%), so better "keep reading" relevance
    directly serves retention, not just a nicer related-section.
    Falls back to same-category (the old behavior) when no tag overlap
    exists, so categories with sparse tagging still get a related section."""
    own_tags = a.get("ai_tags_set") or set()
    scored = []
    for x in listable:
        if x["slug"] == a["slug"]:
            continue
        shared_tags = len(own_tags & x.get("ai_tags_set", set()))
        same_category = x["category"] == a["category"]
        if shared_tags == 0 and not same_category:
            continue
        scored.append((shared_tags, same_category, x))
    # stable sort: listable is already recency-sorted, so ties keep that order
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [x for _, _, x in scored[:count]]


def build_footer_promo_html(categories, recent_articles):
    cat_links = "".join(
        f'<a href="/category/{slugify(c, c)}.html">{html.escape(c)}</a>'
        for c in sorted(categories, key=lambda c: (c == RECIPE_CATEGORY, c)) if c != TV_CATEGORY
    )
    article_links = "".join(
        f'<a href="/article/{a["slug"]}.html">{html.escape(a["title"])}</a>'
        for a in recent_articles[:16]
    )
    return f"""
    <div class="footer-promo">
      <div class="footer-promo-col">
        <h3>קטגוריות</h3>
        {cat_links}
      </div>
      <div class="footer-promo-col">
        <h3>כתבות אחרונות</h3>
        {article_links}
      </div>
    </div>"""


def build():
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
    os.makedirs(os.path.join(OUTPUT_DIR, "assets"))
    os.makedirs(os.path.join(OUTPUT_DIR, "article"))
    os.makedirs(os.path.join(OUTPUT_DIR, "category"))

    articles = load_articles()
    categories = sorted({a["category"] for a in articles})
    ticker_articles = [a for a in articles
                       if a["category"] != RECIPE_CATEGORY and a["source"] != "i24NEWS עברית"]
    ticker_text = "   •   ".join(a["title"] for a in ticker_articles[:12]) or "מערכת קודקוד - חדשות ומבזקים מהארץ ומהעולם"

    global FOOTER_PROMO_HTML
    FOOTER_PROMO_HTML = build_footer_promo_html(categories, ticker_articles)

    global WEATHER_BAR_HTML
    weather_data = fetch_weather()
    if weather_data:
        main_city = weather_data[0]
        WEATHER_BAR_HTML = (
            '<a class="weather-bar" href="/weather.html">'
            f'<span class="weather-date">{html.escape(hebrew_date_str(datetime.now()))}</span>'
            f'<span class="weather-now">{main_city["icon"]} {html.escape(main_city["name"])} '
            f'{round(main_city["temp"]) if main_city["temp"] is not None else "-"}°</span>'
            '</a>'
        )

    # Owner directive: the site closes 10 minutes before Shabbat (real
    # sunset-based time from Hebcal, not approximated) and reopens at
    # Shabbat's end - visitors already on the site 15 minutes before
    # closure get a warning, then the lockout triggers live via a timer,
    # no reload needed. Real timestamps embedded here; assets/search.js
    # does the actual comparison/timer against the visitor's own clock -
    # this only needs to run once per build (times are stable all week).
    global SHABBAT_OVERLAY_HTML, SHABBAT_HEAD_SCRIPT
    shabbat_close_iso, shabbat_reopen_iso = fetch_shabbat_times()
    if shabbat_close_iso and shabbat_reopen_iso:
        SHABBAT_OVERLAY_HTML = f"""
<div id="shabbat-lockout" class="shabbat-lockout" data-close="{html.escape(shabbat_close_iso)}" data-reopen="{html.escape(shabbat_reopen_iso)}" hidden>
  <img src="/assets/shabbat/closure-image.jpg" alt="שבת שלום ומבורך" class="shabbat-lockout-img">
  <div class="shabbat-lockout-inner">
    <p class="shabbat-lockout-reopen" id="shabbat-reopen-text"></p>
  </div>
</div>
<div id="shabbat-warning" class="shabbat-warning" hidden><span id="shabbat-warning-text"></span></div>"""
        # A visitor arriving via a direct link straight to an article (not
        # the homepage) was seeing the real page content before the lockout
        # ever appeared - assets/search.js only runs once the whole page has
        # loaded, at the bottom of <body>. This runs synchronously in <head>,
        # before the browser paints anything, on every single page - no
        # flash of real content regardless of which URL is the entry point.
        SHABBAT_HEAD_SCRIPT = f"""<script>(function(){{
var c={json.dumps(shabbat_close_iso)},r={json.dumps(shabbat_reopen_iso)};
var n=Date.now(),ct=new Date(c).getTime(),rt=new Date(r).getTime();
if(n>=ct&&n<rt)document.documentElement.className+=" kk-shabbat-locked";
}})();</script>"""

    # Articles without a real image are never shown in listings (hero, cards,
    # quick strip, related) - only their own article page still renders for
    # anyone who has the direct link. video_id counts as "has visuals".
    listable = [a for a in articles if a["image"] or a.get("video_id")]

    # Homepage hero carousel: top 5 non-recipe candidates, one active slide at
    # a time, auto-rotated client-side every 2s (assets/search.js). The pool
    # itself only changes when the site rebuilds (every 2h via deploy.yml),
    # since it's just the 5 freshest qualifying articles at build time.
    # TV/live-broadcast clips carry their own network's on-air branding
    # A TV thumbnail whose vision check (idf_scraper.py's detect_tv_watermark)
    # actually found an on-screen channel bug/logo has its image swapped for
    # a placeholder in load_articles() - such an article is excluded from
    # these two most prominent placements too, so a placeholder graphic
    # isn't the first thing on the page. TV articles whose thumbnail came
    # back clean keep their real image and are eligible like anything else;
    # they all still show normally on their own /tv.html page and category
    # grid, credited as usual.
    # owner directive: the homepage's prominent slots (hero, bento, and each
    # category's own lead) only ever show today-or-yesterday's articles -
    # older content still exists on its category/archive pages, it just
    # doesn't get to occupy the front page's real estate. Also: the hero
    # specifically is meant to read as urgent/important news, not lifestyle
    # content - recipes were already excluded, health joins that exclusion.
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    def is_fresh(a):
        return a["dt"] != datetime.min and a["dt"].date() in (today, yesterday)

    # owner directive: hero/bento are reserved for real breaking news in a
    # fixed topic list (security/military, serious crime, major sports,
    # celebrity/entertainment, significant economy) - never decided by
    # category label alone, since a source's default category can be wrong
    # (e.g. a Haredi-affiliated outlet publishing a general health item).
    # hero_worthy is set by idf_scraper.py's AI classification at scrape
    # time. Falls back to the pre-existing (category-only) filter when that
    # yields nothing, since hero_worthy is a new field - the ~14k articles
    # scraped before it existed all default to False, and without this
    # fallback the hero section could go empty until enough freshly-
    # classified articles accumulate. The fallback ALSO has to stay within
    # the same category allowlist, though - a רכב (car review) article once
    # made it to hero this way, since the old fallback only excluded
    # recipes/health, not every other off-list category (cars, tech,
    # Haredi-affiliated content, TV/live). Categories that can never contain
    # hero-worthy content per the owner's list are excluded here too, even
    # in the fallback path.
    HERO_ELIGIBLE_CATEGORIES = {"חדשות", "ספורט", "כלכלה", "תרבות ובידור"}

    def base_prominent_filter(a):
        return (is_fresh(a)
                and a["category"] in HERO_ELIGIBLE_CATEGORIES
                and not a.get("has_watermark")
                and a["source"] != "i24NEWS עברית"
                and not a.get("quick_image"))

    HERO_SLIDE_COUNT = 5
    hero_candidates = [a for a in listable if base_prominent_filter(a) and a.get("hero_worthy")]
    if not hero_candidates:
        hero_candidates = [a for a in listable if base_prominent_filter(a)]
    hero_html = ""
    rest = listable
    if hero_candidates:
        hero_slides = pick_diverse(hero_candidates, HERO_SLIDE_COUNT, max_per_category=1)
        slides_html = []
        dots_html = []
        for i, hero in enumerate(hero_slides):
            hero_img = hero["image"] or PLACEHOLDER_IMG
            hero_dek = f'<p class="hero-dek">{html.escape(hero["dek"])}</p>' if hero.get("dek") else ""
            active_cls = " active" if i == 0 else ""
            slides_html.append(f"""
          <a class="hero-slide{active_cls}" href="/article/{hero['slug']}.html" data-slide="{i}">
            <div class="hero-img-wrap">
              <img src="{html.escape(hero_img)}" class="hero-img" onerror="this.src='{PLACEHOLDER_IMG}'">
            </div>
            <div class="hero-text">
              <span class="card-cat" {cat_chip_style(hero['category'])}>{html.escape(hero['category'])}</span>
              <h1>{html.escape(hero['title'])}</h1>
              {hero_dek}
              <span class="card-meta">{html.escape(hero['source'])} · {html.escape(hero['date'][:10])}</span>
            </div>
          </a>""")
            dots_html.append(f'<button class="hero-dot{active_cls}" data-slide="{i}" aria-label="כתבה {i + 1}"></button>')
        hero_html = f"""
        <div class="hero" id="hero-carousel">{''.join(slides_html)}
          <div class="hero-dots">{''.join(dots_html)}</div>
        </div>"""
        hero_slugs = {h["slug"] for h in hero_slides}
        rest = [a for a in listable if a["slug"] not in hero_slugs]

    # Bento/mosaic module: one large tile + a stack of smaller ones, instead
    # of dropping straight into a uniform grid right under the hero
    bento_pool = [a for a in rest if base_prominent_filter(a) and a.get("hero_worthy")]
    if not bento_pool:
        bento_pool = [a for a in rest if base_prominent_filter(a)]
    bento_candidates = pick_diverse(bento_pool, 5, max_per_category=2)
    bento_html = ""
    if len(bento_candidates) >= 3:
        big, *small = bento_candidates
        big_img = big["image"] or PLACEHOLDER_IMG
        small_items = "".join(f"""
          <a class="bento-small" href="/article/{s['slug']}.html">
            <div class="bento-small-img" style="background-image:url('{html.escape(s['image'] or PLACEHOLDER_IMG)}')"></div>
            <div class="bento-small-body">
              <span class="card-cat" {cat_chip_style(s['category'])}>{html.escape(s['category'])}</span>
              <h4>{html.escape(s['title'])}</h4>
            </div>
          </a>""" for s in small)
        bento_html = f"""
        <section class="bento-section reveal">
          <a class="bento-big" href="/article/{big['slug']}.html">
            <div class="bento-big-img" style="background-image:url('{html.escape(big_img)}')"></div>
            <div class="bento-big-body">
              <span class="card-cat" {cat_chip_style(big['category'])}>{html.escape(big['category'])}</span>
              <h2>{html.escape(big['title'])}</h2>
              <span class="card-meta">{html.escape(big['source'])} · {html.escape(big['date'][:10])}</span>
            </div>
          </a>
          <div class="bento-small-stack">{small_items}</div>
        </section>"""

    quick_articles = pick_diverse([a for a in rest if a.get("is_quick") and is_fresh(a)], 20, max_per_category=3)
    quick_html = ""
    if quick_articles:
        # rendered twice back-to-back so the CSS marquee (assets/style.css,
        # .quick-strip-track) can loop by shifting exactly one copy's width
        # (translateX 0 -> +shift) and land on an identical frame - a pure-CSS
        # continuous scroll, no JS swap/replace logic needed
        quick_cards_once = "".join(render_quick_card(a) for a in quick_articles)
        n = len(quick_articles)
        # exact pixel width of one copy INCLUDING the connecting gap to the
        # next copy - card width + gap are fixed in CSS (.quick-card is
        # flex:0 0 240px, .quick-strip-track gap is 14px), and since the flex
        # gap applies uniformly between every adjacent pair (including at
        # the copy1/copy2 boundary), one copy "owns" exactly n gaps, not
        # n-1 - using n-1 here left a 14px seam every loop
        quick_shift_px = n * (240 + 14)
        quick_duration = max(30, round(n * 3.6))
        quick_html = f"""
        <section class="quick-section reveal">
          <h2 class="section-title">בקצרה</h2>
          <div class="quick-strip">
            <div class="quick-strip-track" style="animation-duration:{quick_duration}s;--quick-shift:{quick_shift_px}px">{quick_cards_once}<div class="quick-strip-dup" aria-hidden="true">{quick_cards_once}</div></div>
          </div>
        </section>"""

    # vertical/portrait short-video strip ("חדשות עומדות") - YouTube Shorts
    # and other social-style vertical video, detected at scrape time by
    # idf_scraper.py via the platform's own /shorts/ URL scheme. A new
    # field, so this naturally starts empty and fills in as new Shorts get
    # scraped rather than needing a backfill of the existing corpus.
    shorts_articles = pick_diverse([a for a in rest if a.get("is_short") and is_fresh(a)], 12, max_per_category=4)
    shorts_html = ""
    if shorts_articles:
        shorts_html = f"""
        <section class="shorts-section reveal">
          <h2 class="section-title">חדשות עומדות</h2>
          <div class="shorts-strip">{"".join(render_short_card(a) for a in shorts_articles)}</div>
        </section>"""

    # per-category sections: each gets its own lead (its single freshest
    # article, prominent) + a 2x2 grid of the next 4 beside it - instead of
    # a flat uniform grid, so scrolling past each category feels like its
    # own small front page. TV_CATEGORY gets its own dedicated /tv.html
    # instead. Recipes are lifestyle content, not news - shown last, not
    # wherever it happens to fall alphabetically.
    category_sections = []
    for c in sorted(categories, key=lambda c: (c == RECIPE_CATEGORY, c)):
        if c == TV_CATEGORY:
            continue
        c_articles = [a for a in rest if a["category"] == c and is_fresh(a)][:5]
        if not c_articles:
            continue
        cat_url = f"/category/{slugify(c, c)}.html"
        lead, *smalls = c_articles
        lead_dek = f'<p class="cat-lead-dek">{html.escape(lead["dek"])}</p>' if lead.get("dek") else ""
        lead_html = f"""
            <a class="cat-lead-main" href="/article/{lead['slug']}.html">
              <div class="cat-lead-img" style="background-image:url('{html.escape(lead['image'] or PLACEHOLDER_IMG)}')"></div>
              <div class="cat-lead-body">
                <h3>{html.escape(lead['title'])}</h3>
                {lead_dek}
                <span class="card-meta">{html.escape(lead['source'])} · {html.escape(lead['date'][:10])}</span>
              </div>
            </a>"""
        grid_html = ""
        if smalls:
            small_cards = "".join(render_card(a) for a in smalls)
            # grid-inner (in addition to cat-lead-grid) so this still gets
            # picked up by the existing client-side affinity re-ranker,
            # which selects by that class
            grid_html = f'<div class="cat-lead-grid grid-inner">{small_cards}</div>'
        category_sections.append(f"""
        <div class="cat-section-wrap" data-category="{html.escape(c)}">
        <section class="cat-section reveal">
          <div class="cat-section-head">
            <h2 class="section-title">{html.escape(c)}</h2>
            <a class="view-all-btn" href="{cat_url}">לכל הכתבות</a>
          </div>
          <div class="cat-lead-layout">{lead_html}{grid_html}</div>
        </section>
        {ad_slot_html()}
        </div>""")
    categories_html = f'<div id="personalized-sections">{"".join(category_sections)}</div>'

    desc_categories = [c for c in categories if c != TV_CATEGORY]
    homepage_description = f"קודקוד חדשות - האתר החדשותי המהיר בישראל: {', '.join(desc_categories)} ועוד, במקום אחד"

    body = f'<main class="grid">{hero_html}{bento_html}{ad_slot_html()}{quick_html}{shorts_html}{categories_html}</main>'
    write_page(os.path.join(OUTPUT_DIR, "index.html"), SITE_NAME,
               homepage_description,
               categories, None, body, ticker_text, canonical=SITE_URL + "/",
               structured_data=homepage_structured_data(
                   [a for a in listable if a["source"] != "i24NEWS עברית"]))

    write_rss_feed(os.path.join(OUTPUT_DIR, "rss.xml"), f"{SITE_URL}/rss.xml",
                   SITE_NAME, "עדכוני חדשות שוטפים מקודקוד - כל הקטגוריות במקום אחד",
                   [a for a in listable if a["category"] != TV_CATEGORY and not a.get("is_sponsored")])

    # Category pages (TV_CATEGORY has its own /tv.html instead)
    for c in categories:
        if c == TV_CATEGORY:
            continue
        c_all_articles = [a for a in listable if a["category"] == c]
        c_articles = c_all_articles[:100]
        cards = "".join(render_card(a) for a in c_articles)
        sort_bar = """
        <div class="sort-bar">
          <label for="sort-select">מיון:</label>
          <select id="sort-select">
            <option value="newest">החדשות ביותר</option>
            <option value="oldest">הישנות ביותר</option>
          </select>
        </div>"""
        body = f"""<main class="grid"><h1 class="page-title">{html.escape(c)}</h1>{sort_bar}
        <div class="grid-inner" id="category-grid" data-category="{html.escape(c)}" data-shown-count="{len(c_articles)}">{cards}</div>
        <div class="load-more-sentinel" id="load-more-sentinel" hidden><span class="load-more-spinner"></span>טוען עוד כתבות...</div>
        </main>"""
        cat_url = f"{SITE_URL}/category/{slugify(c, c)}.html"
        cat_rss_url = f"{SITE_URL}/rss/{slugify(c, c)}.xml"
        write_page(os.path.join(OUTPUT_DIR, "category", f"{slugify(c, c)}.html"),
                   f"חדשות {c} - {SITE_NAME}", category_meta_description(c),
                   categories, c, body, ticker_text, canonical=cat_url,
                   structured_data=category_structured_data(c, cat_url, c_all_articles),
                   category_rss_url=cat_rss_url,
                   noindex=not c_all_articles)
        write_rss_feed(os.path.join(OUTPUT_DIR, "rss", f"{slugify(c, c)}.xml"), cat_rss_url,
                        f"{c} - {SITE_NAME}", f"עדכוני {c} מקודקוד",
                        [a for a in c_all_articles if not a.get("is_sponsored")])

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
              <div class="kk-player-endcard" hidden>
                <span class="kk-player-brand">קודקוד פלייר</span>
                <button class="kk-player-replay" aria-label="נגן שוב">
                  <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
                  <span>נגן שוב</span>
                </button>
              </div>
            </div>"""
        elif a["image"]:
            media_html = f'<img src="{html.escape(a["image"])}" class="article-img" loading="eager" onerror="this.src=\'{PLACEHOLDER_IMG}\'">'
        else:
            media_html = ""

        dek_html = f'<p class="article-dek">{html.escape(a["dek"])}</p>' if a.get("dek") else ""

        # Optional, honestly-labeled AI-generated key takeaways (see
        # idf_scraper.py's enrich_article_with_ai) - sits above the real
        # excerpt, never replaces it; only present when a GROQ_API_KEY was
        # configured for the scraper
        ai_summary_html = ""
        if a.get("ai_takeaways"):
            points_html = "".join(f"<li>{html.escape(p)}</li>" for p in a["ai_takeaways"])
            ai_summary_html = f"""
          <div class="ai-summary-box">
            <span class="ai-summary-label">עיקרי הדברים - AI</span>
            <ul>{points_html}</ul>
          </div>"""

        tags_html = ""
        if a.get("ai_tags"):
            tag_chips = "".join(
                f'<a class="tag-chip" href="/search.html?q={html.escape(t)}">{html.escape(t)}</a>'
                for t in a["ai_tags"]
            )
            tags_html = f'<div class="tag-chips">{tag_chips}</div>'

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

        related = pick_related_articles(a, listable, count=9)
        related_html = ""
        if related:
            related_cards = "".join(render_card(x) for x in related)
            # continues past the initial tag-matched picks with more of this
            # article's own category (same infinite-scroll mechanism as
            # category pages, assets/search.js's setupInfiniteGrid) - a
            # related-articles section that visibly ends is exactly the
            # moment a reader has a natural reason to leave the site
            related_html = f"""
            <section class="related-section">
              <h2 class="page-title">כתבות קשורות</h2>
              <div class="grid-inner" id="related-grid" data-category="{html.escape(a['category'])}" data-shown-count="{len(related)}" data-exclude-slug="{html.escape(a['slug'])}">{related_cards}</div>
              <div class="load-more-sentinel" id="related-load-more-sentinel" hidden><span class="load-more-spinner"></span>טוען עוד כתבות...</div>
            </section>"""

        canonical = f"{SITE_URL}/article/{a['slug']}.html"
        view_tracker = f"""
        <script>
        (function() {{
          try {{
            if (localStorage.getItem('kk_cookie_consent') === 'declined') return;
            var key = 'kk_recent';
            var entry = {{slug: {json.dumps(a['slug'], ensure_ascii=False)}, title: {json.dumps(a['title'], ensure_ascii=False)}, img: {json.dumps(a['image'] or PLACEHOLDER_IMG, ensure_ascii=False)}, cat: {json.dumps(a['category'], ensure_ascii=False)}, source: {json.dumps(a['source'], ensure_ascii=False)}, type: {json.dumps(content_type_of(a), ensure_ascii=False)}}};
            var list = JSON.parse(localStorage.getItem(key) || '[]');
            list = list.filter(function(x) {{ return x.slug !== entry.slug; }});
            list.unshift(entry);
            localStorage.setItem(key, JSON.stringify(list.slice(0, 12)));
          }} catch (e) {{}}
        }})();
        </script>"""
        engagement_bar = f"""
        <div class="engagement-bar" data-slug="{html.escape(a['slug'])}" data-cat="{html.escape(a['category'])}" data-source="{html.escape(a['source'])}" data-type="{content_type_of(a)}" data-title="{html.escape(a['title'])}" data-img="{html.escape(a['image'] or PLACEHOLDER_IMG)}" data-date="{html.escape(a['date'])}">
          <button class="like-btn" id="like-btn" aria-pressed="false">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8z"/></svg>
            <span id="like-count">אהבתי</span>
          </button>
          <button class="share-btn" id="share-btn" data-title="{html.escape(a['title'])}" data-url="{html.escape(canonical)}">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.6" y1="10.6" x2="15.4" y2="6.4"/><line x1="8.6" y1="13.4" x2="15.4" y2="17.6"/></svg>
            <span>שיתוף</span>
          </button>
          <details class="report-details">
            <summary class="report-btn">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <span>דיווח על בעיה</span>
            </summary>
            <form class="report-form" action="{TIP_FORM_ACTION}" method="POST">
              <input type="hidden" name="_subject" value="דיווח על כתבה: {html.escape(a['title'])}">
              <input type="hidden" name="article_url" value="{html.escape(canonical)}">
              <select name="reason" required>
                <option value="">בחרו סוג בעיה</option>
                <option value="כתבה שבורה">כתבה שבורה (טקסט/תמונה/וידאו לא עובדים)</option>
                <option value="תוכן כפול">תוכן כפול - כבר פורסם באתר</option>
                <option value="אחר">אחר</option>
              </select>
              <textarea name="details" rows="3" placeholder="פרטים נוספים (אופציונלי)"></textarea>
              <button type="submit">שליחת דיווח</button>
            </form>
          </details>
        </div>"""
        # Source credit shown once, at the very end of the article only (not
        # repeated near the headline) - keeps the reader's focus on our own
        # page and content first, attribution comes after they've read it.
        # Paid/sponsored placements get rel="sponsored" per Google's own
        # guidance on disclosing paid links, on top of the visible label.
        credit_rel = "sponsored noopener" if a.get("is_sponsored") else "noopener"
        source_credit_html = f"""
        <div class="source-credit-box">
          <span>המקור: {html.escape(a['source'])}</span>
          <a href="{html.escape(a['link'])}" target="_blank" rel="{credit_rel}">לכתבה המלאה באתר המקור ←</a>
        </div>"""
        # Sponsored content gets an unmissable disclosure banner above the
        # headline - required by Israeli consumer protection law and by
        # Google's paid-content policy; the badge alone (shown in listings)
        # isn't enough once someone is actually on the article page
        sponsored_banner_html = ""
        if a.get("is_sponsored"):
            sponsored_banner_html = f'<div class="sponsored-banner">תוכן שיווקי בשיתוף {html.escape(a["source"])}</div>'
        body = f"""
        <main class="article">
          {sponsored_banner_html}
          <span class="card-cat" {cat_chip_style(a['category'])}>{html.escape(a['category'])}</span>
          <h1>{html.escape(a['title'])}</h1>
          {dek_html}
          <div class="article-meta"><span class="article-byline">{html.escape(byline_for(a['category']))}</span> · {html.escape(a['date'])}</div>
          {media_html}
          {ai_summary_html}
          {tags_html}
          {body_content}
          {source_credit_html}
          {engagement_bar}
        </main>
        {ad_slot_html()}
        {related_html}
        {COMMENTS_SECTION_HTML}
        {view_tracker}"""
        description = (" ".join(a["ai_takeaways"][:2]) if a.get("ai_takeaways")
                        else re.sub(r'<[^>]+>', '', body_html_full))[:160].strip()
        write_page(os.path.join(OUTPUT_DIR, "article", f"{a['slug']}.html"), a["title"],
                   description or a["title"], categories, a["category"], body, ticker_text,
                   canonical=canonical, og_type="article", og_image=a["image"],
                   structured_data=article_structured_data(a, canonical))

    # Search page - noindex: results are rendered client-side per query, so
    # the static page itself is a thin, empty shell with no unique content
    # for Google to index (the same reasoning real news sites apply to
    # on-site search results pages)
    body = '<main class="grid"><h1 class="page-title">תוצאות חיפוש</h1><div id="search-results" class="grid-inner"></div></main>'
    write_page(os.path.join(OUTPUT_DIR, "search.html"), f"חיפוש - {SITE_NAME}", "חיפוש חדשות באתר קודקוד",
               categories, None, body, ticker_text, canonical=f"{SITE_URL}/search.html", noindex=True)

    # Weather page - real server-rendered content (refreshed every build,
    # same 2h cadence as everything else), so unlike search/liked this one
    # is left indexable
    if weather_data:
        city_cards = []
        for city in weather_data:
            daily = city.get("daily", {})
            days = daily.get("time", [])
            highs = daily.get("temperature_2m_max", [])
            lows = daily.get("temperature_2m_min", [])
            codes = daily.get("weather_code", [])
            day_rows = []
            for i in range(len(days)):
                d = datetime.strptime(days[i], "%Y-%m-%d")
                day_name = HEBREW_WEEKDAYS[d.weekday()]
                _, day_icon_key = weather_desc(codes[i] if i < len(codes) else None)
                day_rows.append(f"""
                <div class="weather-day">
                  <span class="weather-day-name">{html.escape(day_name)}</span>
                  <span class="weather-day-icon">{WEATHER_ICONS.get(day_icon_key, WEATHER_ICONS["cloud"])}</span>
                  <span class="weather-day-temps">{round(highs[i])}° / {round(lows[i])}°</span>
                </div>""")
            city_cards.append(f"""
            <div class="weather-city-card">
              <h2>{html.escape(city['name'])}</h2>
              <div class="weather-current">
                <span class="weather-current-icon">{city['icon']}</span>
                <span class="weather-current-temp">{round(city['temp']) if city['temp'] is not None else '-'}°</span>
                <span class="weather-current-desc">{html.escape(city['desc'])}</span>
              </div>
              <div class="weather-forecast">{''.join(day_rows)}</div>
            </div>""")
        weather_body = f"""<main class="grid">
          <h1 class="page-title">מזג האוויר - {html.escape(hebrew_date_str(datetime.now()))}</h1>
          <div class="weather-cities">{''.join(city_cards)}</div>
        </main>"""
        write_page(os.path.join(OUTPUT_DIR, "weather.html"), f"מזג אוויר - {SITE_NAME}",
                   "תחזית מזג אוויר עדכנית לערים המרכזיות בישראל",
                   categories, None, weather_body, ticker_text, canonical=f"{SITE_URL}/weather.html")

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
    # FAQPage schema mirroring the actual visible Q&A in ABOUT_BODY above -
    # same 3 pairs, same wording, so the schema never claims anything the
    # page itself doesn't already say
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "האם קודקוד כותב את הכתבות בעצמו?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "לא. קודקוד הוא אגרגטור - אנו אוספים ומציגים מבזקים ממקורות חדשות קיימים, עם ייחוס וקישור מלא למקור המקורי.",
                },
            },
            {
                "@type": "Question",
                "name": "באיזו תדירות האתר מתעדכן?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "מערכת האיסוף האוטומטית שלנו רצה כל 15 דקות, מסביב לשעון.",
                },
            },
            {
                "@type": "Question",
                "name": "איך אפשר לדווח על טעות או לשלוח משוב?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f"אפשר לפנות בכל עת דרך עמוד יצירת הקשר, {SITE_URL}/tip-line.html.",
                },
            },
        ],
    }
    about_structured_data = (
        '<script type="application/ld+json">' + json.dumps(about_schema, ensure_ascii=False) + '</script>'
        '<script type="application/ld+json">' + json.dumps(faq_schema, ensure_ascii=False) + '</script>'
    )
    write_page(os.path.join(OUTPUT_DIR, "about.html"), f"אודות קודקוד - מי אנחנו וכיצד אנחנו עובדים | {SITE_NAME}",
               "קודקוד הוא מרכז חדשותי המרכז מבזקים ממיטב מקורות החדשות בישראל - חדשות, כלכלה, טכנולוגיה, חרדים ובישול. קראו על החזון, תחומי הסיקור והדרך בה אנחנו עובדים.",
               categories, None, ABOUT_BODY, ticker_text, canonical=f"{SITE_URL}/about.html", structured_data=about_structured_data)
    write_page(os.path.join(OUTPUT_DIR, "advertise.html"), f"פרסום - {SITE_NAME}", "פרסמו בקודקוד חדשות",
               categories, None, ADVERTISE_BODY, ticker_text, canonical=f"{SITE_URL}/advertise.html")
    write_page(os.path.join(OUTPUT_DIR, "tip-line.html"), f"שלחו סקופ - {SITE_NAME}", "שלחו סקופ לקודקוד",
               categories, None, TIP_LINE_BODY, ticker_text, canonical=f"{SITE_URL}/tip-line.html")
    write_page(os.path.join(OUTPUT_DIR, "privacy.html"), f"מדיניות פרטיות - {SITE_NAME}",
               "מדיניות הפרטיות של קודקוד חדשות - אילו נתונים נאספים, כיצד הם נשמרים, ומהן זכויותיכם",
               categories, None, PRIVACY_BODY, ticker_text, canonical=f"{SITE_URL}/privacy.html")
    write_page(os.path.join(OUTPUT_DIR, "terms.html"), f"תנאי שימוש - {SITE_NAME}",
               "תנאי השימוש באתר קודקוד חדשות",
               categories, None, TERMS_BODY, ticker_text, canonical=f"{SITE_URL}/terms.html")
    write_page(os.path.join(OUTPUT_DIR, "accessibility.html"), f"הצהרת נגישות - {SITE_NAME}",
               "הצהרת הנגישות של קודקוד חדשות בהתאם לתקן הישראלי 5568 ולחוק שוויון זכויות לאנשים עם מוגבלות",
               categories, None, ACCESSIBILITY_BODY, ticker_text, canonical=f"{SITE_URL}/accessibility.html")

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
    static_urls = [f"{SITE_URL}/", f"{SITE_URL}/about.html", f"{SITE_URL}/advertise.html", f"{SITE_URL}/tip-line.html", f"{SITE_URL}/video.html", f"{SITE_URL}/tv.html", f"{SITE_URL}/magazine.html", f"{SITE_URL}/privacy.html", f"{SITE_URL}/terms.html", f"{SITE_URL}/accessibility.html"]
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
        # sponsored articles carry no NewsArticle schema and aren't real
        # editorial content - keep the sitemap consistent with the RSS
        # feeds/news-sitemap, which already exclude them the same way
        if a.get("is_sponsored"):
            continue
        loc = f"{SITE_URL}/article/{a['slug']}.html"
        lastmod = (a["dt"] if a["dt"] != datetime.min else now).strftime("%Y-%m-%d")
        image_tag = f"<image:image><image:loc>{html.escape(a['image'])}</image:loc></image:image>" if a["image"] else ""
        sitemap += f"  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod>{image_tag}</url>\n"
    sitemap += "</urlset>\n"
    with open(os.path.join(OUTPUT_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap)

    # Google News sitemap - only articles from the last 48 hours, per spec
    # (https://support.google.com/news/publisher-center/answer/9606224).
    # Sponsored/paid content is explicitly excluded - Google News publisher
    # guidelines don't consider that eligible "news" content
    news_cutoff = now.timestamp() - 48 * 3600
    recent_articles = [a for a in articles
                       if a["dt"] != datetime.min and a["dt"].timestamp() >= news_cutoff and not a.get("is_sponsored")]
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

    # robots.txt - "User-agent: *" already allows everything, but AI search
    # bots are named explicitly too (owner directive: maximize citation by
    # every search + AI engine) since some GEO audits check for explicit
    # mentions, not just wildcard coverage, as a readiness signal
    ai_bots = [
        "GPTBot", "OAI-SearchBot", "ChatGPT-User",       # OpenAI
        "PerplexityBot", "Perplexity-User",              # Perplexity
        "ClaudeBot", "anthropic-ai", "Claude-Web",        # Anthropic
        "Google-Extended",                                # Gemini/Bard training
        "CCBot",                                          # Common Crawl (many trainers)
        "MistralAI-User",                                 # Le Chat
        "Meta-ExternalAgent",                             # Meta AI
        "Bingbot", "Applebot",
    ]
    robots_lines = ["User-agent: *", "Allow: /", ""]
    for bot in ai_bots:
        robots_lines += [f"User-agent: {bot}", "Allow: /", ""]
    robots_lines += [f"Sitemap: {SITE_URL}/sitemap.xml", f"Sitemap: {SITE_URL}/news-sitemap.xml"]
    with open(os.path.join(OUTPUT_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(robots_lines) + "\n")

    # llms.txt / llms-full.txt - an emerging (advisory, not a ranking signal)
    # convention AI crawlers/agents use as a structured index instead of
    # guessing from HTML; kept short/factual, no marketing language
    top_categories = [c for c in categories if c != TV_CATEGORY]
    llms_txt = f"""# {SITE_NAME}

> {SITE_NAME} הוא אתר חדשות ישראלי המצטט ומקשר בחזרה למקורות המקוריים - חדשות, כלכלה, טכנולוגיה, ספורט, בריאות, תרבות, רכב ועוד.

כל כתבה מציגה תקציר/ציטוט עם קרדיט וקישור למקור המקורי - {SITE_NAME} אינו טוען לבעלות על התוכן המצוטט.

## עמודים מרכזיים

{chr(10).join(f"- [{c}]({SITE_URL}/category/{slugify(c, c)}.html)" for c in top_categories)}
- [אודות]({SITE_URL}/about.html)
- [כל הכתבות (sitemap)]({SITE_URL}/sitemap.xml)
- [עדכוני RSS]({SITE_URL}/rss.xml)
"""
    with open(os.path.join(OUTPUT_DIR, "llms.txt"), "w", encoding="utf-8") as f:
        f.write(llms_txt)

    llms_full_lines = [f"# {SITE_NAME} - אינדקס מלא\n"]
    for a in listable[:500]:
        if a["source"] == "i24NEWS עברית":
            continue
        llms_full_lines.append(
            f"## {a['title']}\n"
            f"מקור: {a['source']} | קטגוריה: {a['category']} | תאריך: {a['date'][:10]}\n"
            f"{a.get('dek', '')}\n"
            f"קישור: {SITE_URL}/article/{a['slug']}.html\n"
        )
    with open(os.path.join(OUTPUT_DIR, "llms-full.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(llms_full_lines))

    print(f"נבנה אתר עם {len(articles)} כתבות ב-{len(categories)} קטגוריות.")


if __name__ == "__main__":
    build()
