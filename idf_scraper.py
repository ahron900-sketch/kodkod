import feedparser
import glob
import html
import json
import os
import re
import time
import shutil
import urllib.request
from datetime import datetime, timedelta
from build_site import slugify, SITE_URL  # single source of truth for slug computation

# מקורות RSS - כולם בעברית, ממוינים לקטגוריות (כל URL כאן נבדק ואומת שמחזיר כתבות)
rss_feeds = {
    # חרדים
    "אמס": ("https://www.emess.co.il/feed/", "חרדים"),
    "כל רגע": ("https://93fm.co.il/feed/", "חרדים"),
    "בחדרי חרדים": ("https://www.bhol.co.il/feed", "חרדים"),

    # חדשות ישראל
    "ynet": ("https://www.ynet.co.il/Integration/StoryRss2.xml", "חדשות"),
    "וואלה חדשות": ("https://rss.walla.co.il/feed/1?type=main", "חדשות"),
    "מאקו": ("https://www.mako.co.il/rss/news-israel.xml", "חדשות"),
    "מעריב": ("https://www.maariv.co.il/Rss/RssFeedsAllNews", "חדשות"),

    # כלכלה
    "גלובס": ("https://www.globes.co.il/webservice/rss/rssfeeder.asmx/FeederNode?iID=585", "כלכלה"),

    # טכנולוגיה
    "Geektime": ("https://www.geektime.co.il/feed/", "טכנולוגיה"),

    # בישול ומתכונים
    "מאקו אוכל": ("https://rcs.mako.co.il/rss/food-recipes.xml", "בישול ומתכונים"),
    "מאקו - כל האוכל": ("https://rcs.mako.co.il/rss/c7250a2610f26110VgnVCM1000005201000aRCRD.xml", "בישול ומתכונים"),
    "וואלה אוכל": ("https://rss.walla.co.il/feed/9?type=main", "בישול ומתכונים"),
    "Foody": ("https://www.foody.co.il/feed", "בישול ומתכונים"),

    # ספורט
    "וואלה ספורט": ("https://rss.walla.co.il/feed/3?type=main", "ספורט"),

    # בריאות
    "וואלה בריאות": ("https://rss.walla.co.il/feed/139?type=main", "בריאות"),
    "מאקו בריאות": ("https://rcs.mako.co.il/rss/c827a3ef43336410VgnVCM2000002a0c10acRCRD.xml", "בריאות"),

    # תרבות ובידור
    "וואלה תרבות": ("https://rss.walla.co.il/feed/4?type=main", "תרבות ובידור"),
    "מאקו תרבות": ("https://rcs.mako.co.il/rss/c7a987610879a310VgnVCM2000002a0c10acRCRD.xml", "תרבות ובידור"),

    # רכב
    "וואלה רכב": ("https://rss.walla.co.il/feed/31?type=main", "רכב"),
}

# ערוצי יוטיוב - נשאבים כווידאו דרך YouTube RSS (אין צורך במפתח API)
# הוסף כאן channel_id אמיתיים (נמצא ב-view-source של דף הערוץ, tag <meta itemprop="channelId">)
youtube_channels = {
    "UC_HwfTAcjBESKZRJq6BTCpg": ("כאן חדשות", "חדשות"),
    "UCvQmPpU20hw1Trss_CVwaew": ("חדשות 13", "חדשות"),
    "UCpSSzrovhI4fA2PQNItecUA": ("ynet", "חדשות"),
    "UCisowXt5wZkp2sR3rFh9lnQ": ("i24NEWS עברית", "חדשות"),
}

LIVE_DIR = "content/news"
PENDING_DIR = "content/pending"
ARCHIVE_DIR = "content/archive"

def sanitize_filename(title):
    clean_name = re.sub(r'[\\/*?:"<>|]', "", title).strip()[:50]
    return clean_name if clean_name else "untitled"

def clean_html(raw_html):
    if not raw_html:
        return ""
    cleanr = re.compile('<.*?>')
    text = re.sub(cleanr, '', raw_html).strip()
    return html.unescape(text)

def upgrade_image_quality(url):
    """Some sources' RSS gives a tiny thumbnail variant of the real image -
    swap in the full-resolution version where we know the URL pattern."""
    if not url:
        return url
    # mako.co.il: "..._autoOrient_a.jpg" is an ~80x60 crop; the same filename
    # without the trailing "_a" is the real, full-size image
    url = re.sub(r'(_autoOrient)_a(\.\w+)(\?.*)?$', r'\1\2', url)
    return url


def extract_image(entry):
    if 'media_thumbnail' in entry and len(entry.media_thumbnail) > 0:
        return upgrade_image_quality(entry.media_thumbnail[0].get('url', ""))
    if 'media_content' in entry and len(entry.media_content) > 0:
        return upgrade_image_quality(entry.media_content[0].get('url', ""))
    if 'links' in entry:
        for link in entry.links:
            if 'image' in link.get('type', ''):
                return upgrade_image_quality(link.href)
    if 'enclosures' in entry and len(entry.enclosures) > 0:
        return upgrade_image_quality(entry.enclosures[0].get('url', ""))
    # fall back to first <img> found in the description HTML
    desc = entry.get('description', '') or entry.get('summary', '')
    m = re.search(r'<img[^>]+src="([^"]+)"', desc)
    if m:
        return upgrade_image_quality(m.group(1))
    return ""


OG_IMAGE_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def fetch_page(link, max_bytes=400_000):
    if not link:
        return ""
    try:
        req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0 (compatible; KodkodBot/1.0)"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            html_bytes = resp.read(max_bytes)
        return html_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def fetch_og_image(link):
    html_text = fetch_page(link, max_bytes=200_000)
    if not html_text:
        return ""
    m = OG_IMAGE_RE.search(html_text)
    return upgrade_image_quality(m.group(1)) if m else ""


JPEG_SOF_MARKERS = frozenset({0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF})


def get_image_dimensions(image_bytes):
    """Best-effort (width, height) for JPEG/PNG from just the first chunk of
    bytes - no imaging library needed. Returns None on anything unexpected
    (truncated data, unrecognized format); callers must treat that as
    "couldn't tell" rather than "bad", never blocking an article just
    because its image couldn't be parsed this way."""
    if not image_bytes:
        return None
    try:
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            width = int.from_bytes(image_bytes[16:20], 'big')
            height = int.from_bytes(image_bytes[20:24], 'big')
            return (width, height) if width and height else None
        if image_bytes[:2] == b'\xff\xd8':
            i, n = 2, len(image_bytes)
            while i < n - 9:
                if image_bytes[i] != 0xFF:
                    i += 1
                    continue
                marker = image_bytes[i + 1]
                if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                seg_len = int.from_bytes(image_bytes[i + 2:i + 4], 'big')
                if marker in JPEG_SOF_MARKERS:
                    height = int.from_bytes(image_bytes[i + 5:i + 7], 'big')
                    width = int.from_bytes(image_bytes[i + 7:i + 9], 'big')
                    return (width, height) if width and height else None
                i += 2 + seg_len
    except Exception:
        return None
    return None


# Anything wider or taller than this reads as a banner/strip crop, not a
# normal editorial photo - such images get routed to the compact "quick"
# card style instead of the large hero/bento treatment they'd otherwise get
BAD_ASPECT_MAX = 2.4
BAD_ASPECT_MIN = 0.42


def is_bad_image_aspect(image_url):
    if not image_url:
        return False
    try:
        req = urllib.request.Request(
            image_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KodkodBot/1.0)", "Range": "bytes=0-131071"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            chunk = resp.read(131_072)
    except Exception:
        return False
    dims = get_image_dimensions(chunk)
    if not dims:
        return False
    width, height = dims
    ratio = width / height
    return ratio > BAD_ASPECT_MAX or ratio < BAD_ASPECT_MIN


ARTICLE_TAG_RE = re.compile(r'<article[^>]*>(.*?)</article>', re.DOTALL | re.IGNORECASE)
# common WordPress/CMS content-wrapper class names, tried when there's no <article> tag.
# We don't try to precisely match the closing </div> (nesting makes that unreliable with
# regex) - instead grab a generous bounded slice after the opening tag and let the
# paragraph-length + junk-marker filters below reject anything that isn't real prose.
CONTENT_DIV_OPEN_RE = re.compile(
    r'<div[^>]+class=["\'][^"\']*\b(?:article-content-inside|entry-content|post-content|article-body|article__content)\b[^"\']*["\'][^>]*>',
    re.IGNORECASE,
)
PARAGRAPH_RE = re.compile(r'<p[^>]*>(.*?)</p>', re.DOTALL | re.IGNORECASE)
# ynet (and other Draft.js-based editors) don't use <p> at all - each
# paragraph is a <div class="...text_editor_paragraph...">; fall back to
# this when no <p> tags are found in the content scope
DIV_PARAGRAPH_RE = re.compile(
    r'<div[^>]+class=["\'][^"\']*text_editor_paragraph[^"\']*["\'][^>]*>(.*?)</div>',
    re.DOTALL | re.IGNORECASE,
)
TAG_STRIP_RE = re.compile(r'<[^>]+>')
SCRIPT_STYLE_RE = re.compile(r'<(script|style)\b[^>]*>.*?</\1>', re.DOTALL | re.IGNORECASE)
CONTENT_SLICE_SIZE = 20_000

# words that show up in nav/cookie/menu junk but essentially never in real article prose -
# if too many paragraphs contain these, we probably scraped chrome, not content
JUNK_MARKERS_RE = re.compile(
    r'\b(cookie|subscribe|navigation|skip to content|sign in|newsletter|all rights reserved|privacy policy)\b',
    re.IGNORECASE,
)
# leaked inline JS/JSON that sometimes rides along inside a caption <p> on JS-heavy
# sites (e.g. Next.js's self.__next_s.push hydration snippets) - reject any paragraph
# containing these outright rather than just down-weighting it
SCRIPT_LEAK_RE = re.compile(r'(self\.__next_s|"@context"|\.push\(\[|application/ld\+json)')
# photo-credit captions ("caption text | צילום: X") sometimes get concatenated into the
# same <p> as real body text with no separator but the pipe - split on each "| credit:"
# segment and drop everything up to and including it, keeping only what follows
CAPTION_SPLIT_RE = re.compile(r'.*?\|\s*(?:צילום|Photo|AP|Reuters|AFP|Credit)\s*:[^|]*', re.IGNORECASE)


def fetch_full_article_text(link, min_len_needed):
    """Best-effort: pull the <article> block's paragraphs from the live page
    when the RSS summary is too short. Returns '' if it can't find enough,
    or if what it found looks like nav/cookie-banner junk rather than prose."""
    html_text = fetch_page(link)
    if not html_text:
        return ""
    scope = None
    m = ARTICLE_TAG_RE.search(html_text)
    if m:
        scope = m.group(1)
    else:
        m2 = CONTENT_DIV_OPEN_RE.search(html_text)
        if m2:
            scope = html_text[m2.end():m2.end() + CONTENT_SLICE_SIZE]
    if not scope:
        return ""
    scope = SCRIPT_STYLE_RE.sub("", scope)
    raw_paragraphs = PARAGRAPH_RE.findall(scope)
    if not raw_paragraphs:
        raw_paragraphs = DIV_PARAGRAPH_RE.findall(scope)
    paragraphs = []
    junk_hits = 0
    for p in raw_paragraphs:
        if SCRIPT_LEAK_RE.search(p):
            continue
        text = TAG_STRIP_RE.sub("", p).strip()
        text = re.sub(r'\s+', ' ', text)
        text = html.unescape(text)
        text = CAPTION_SPLIT_RE.sub("", text).strip()
        if len(text) > 30:  # skip short boilerplate/caption paragraphs
            paragraphs.append(text)
            if JUNK_MARKERS_RE.search(text):
                junk_hits += 1
    if not paragraphs or junk_hits > len(paragraphs) // 3:
        return ""
    joined = "\n\n".join(paragraphs)
    return joined if len(joined) > min_len_needed else ""

def manage_archive():
    now = time.time()
    for d in [LIVE_DIR, PENDING_DIR]:
        if not os.path.exists(d):
            os.makedirs(d)
        for f in os.listdir(d):
            f_path = os.path.join(d, f)
            if os.path.isfile(f_path) and f != ".gitkeep":
                if os.stat(f_path).st_mtime < now - 3 * 86400:
                    if not os.path.exists(ARCHIVE_DIR):
                        os.makedirs(ARCHIVE_DIR)
                    try:
                        shutil.move(f_path, os.path.join(ARCHIVE_DIR, f))
                    except Exception:
                        pass

# ~2400 Hebrew characters is roughly 400+ words (same ~6 chars/word ratio
# this file always used) - owner directive: raised from 900 (~150 words)
# since that floor was letting real thin-content through; Google's own spam
# policy flags auto-generated/scraped pages that don't clear a meaningful
# length, not just "long enough to bother keeping"
MIN_CONTENT_LEN = 2400

# Sponsored/advertorial content filter - strict by design: any hint of paid
# promotion, in the title, URL, or body, rejects the article outright. When
# in doubt, reject rather than risk publishing an ad as a news item.
SPONSORED_MARKERS = [
    "בשיתוף", "מאמר ממומן", "תוכן ממומן", "תוכן שיווקי", "פרסומת", "פרסום מסחרי",
    "פוסט ממומן", "כתבה ממומנת", "פרסומי", "מקודם", "sponsored", "advertorial",
    "promoted", "paid content", "in partnership with", "in collaboration with",
    "מומלץ ע\"י", "מומלץ על ידי",
]
SPONSORED_URL_MARKERS = [
    "/sponsored/", "/advertorial/", "/promoted/", "/marketing/", "/tazarot/",
    "/paid/", "/ads/", "sponsored=1", "utm_source=sponsored",
]


def is_sponsored_content(title, link, content):
    haystacks = [title or "", link or "", content or ""]
    combined = " ".join(haystacks).lower()
    for marker in SPONSORED_MARKERS:
        if marker.lower() in combined:
            return True
    link_lower = (link or "").lower()
    for marker in SPONSORED_URL_MARKERS:
        if marker in link_lower:
            return True
    return False


# Gibberish/broken-content detector: catches leftover markdown links, raw
# HTML tags, or text that's mostly not real words (mojibake, stray symbol
# soup) slipping past the earlier extraction filters.
LEFTOVER_MARKUP_RE = re.compile(r'\[[^\]]*\]\([^)]*\)|<[a-zA-Z/][^>]*>')


def is_gibberish_or_broken(content):
    if not content:
        return True
    if LEFTOVER_MARKUP_RE.search(content):
        return True
    letters = sum(1 for ch in content if ch.isalpha())
    if letters < len(content) * 0.5:
        return True
    return False


# Video filter: YouTube's public RSS feed has no duration field (that needs
# the paid Data API), so we can only filter by title/keyword heuristics -
# reject anything that reads as a live stream or a full broadcast segment
# rather than a short news clip.
LIVE_BROADCAST_MARKERS = [
    "live", "לייב", "שידור חי", "בשידור חי", "פרק מלא", "השידור המלא",
    "מהדורה מלאה", "הכל תקשורת", "לצפייה ישירה", "שידור ישיר",
]


def is_live_broadcast(title):
    title_lower = (title or "").lower()
    return any(marker.lower() in title_lower for marker in LIVE_BROADCAST_MARKERS)


# Cross-source duplicate-story detection: the same breaking story often gets
# published, independently, by several outlets within minutes of each other,
# each with a slightly different headline. Filesystem mtimes can't be used to
# find "recent" articles here - a fresh git checkout resets every file's mtime
# to checkout time, so we parse the real `date:` field out of each article's
# frontmatter instead (same approach build_site.py / generate_magazine.py use).
DUPLICATE_LOOKBACK_HOURS = 48
DUPLICATE_SIMILARITY_THRESHOLD = 0.55
DUPLICATE_MIN_SHARED_WORDS = 4
FRONTMATTER_TITLE_RE = re.compile(r'title:\s*>-\s*\n((?:[ \t]+.*\n?)+)')
FRONTMATTER_DATE_RE = re.compile(r'\ndate:\s*"([^"]+)"')
# deliberately excludes bare numbers: dates/times/episode numbers in template-y
# titles (e.g. daily broadcast videos "NEWS 24/26 הבוקר 18/07" vs "...19/07")
# are the single biggest false-positive source - they share every word except
# the day-of-month digit, which digits-as-words would wrongly count as signal
TITLE_WORD_RE = re.compile(r'[א-ת]{2,}|[a-zA-Z]{2,}')
TITLE_STOPWORDS = {
    "של", "עם", "על", "אל", "אך", "או", "גם", "לא", "כי", "זה", "זו", "אלה",
    "הוא", "היא", "הם", "הן", "אני", "אתה", "את", "אנחנו", "יש", "אין",
    "כך", "כן", "רק", "עוד", "כבר", "מה", "מי", "איך", "למה", "מתי", "אחרי",
    "לפני", "בין", "תוך", "בעקבות", "לאחר", "במהלך", "בשל", "נגד", "כדי",
}


def normalize_title_words(title):
    words = TITLE_WORD_RE.findall(title or "")
    return {w for w in words if w not in TITLE_STOPWORDS}


def load_recent_titles(hours=DUPLICATE_LOOKBACK_HOURS):
    """Returns a list of normalized word-sets, one per article published (per
    its frontmatter date) within the last `hours` - used to catch the same
    story being re-saved from a different source."""
    cutoff = datetime.now() - timedelta(hours=hours)
    titles = []
    for path in glob.glob(os.path.join(LIVE_DIR, "*.md")):
        try:
            with open(path, encoding="utf-8") as f:
                head = f.read(600)
        except Exception:
            continue
        date_m = FRONTMATTER_DATE_RE.search(head)
        if not date_m:
            continue
        try:
            dt = datetime.strptime(date_m.group(1), "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if dt < cutoff:
            continue
        title_m = FRONTMATTER_TITLE_RE.search(head)
        if not title_m:
            continue
        title_text = " ".join(line.strip() for line in title_m.group(1).splitlines() if line.strip())
        words = normalize_title_words(title_text)
        if words:
            titles.append(words)
    return titles


def is_duplicate_of_recent(title, recent_title_word_sets):
    """Fuzzy (Jaccard-similarity) check against titles already published in
    the lookback window - catches the same story from a different outlet,
    not just an exact-filename repeat (already handled separately)."""
    words = normalize_title_words(title)
    if len(words) < DUPLICATE_MIN_SHARED_WORDS:
        return False
    for other in recent_title_word_sets:
        if not other:
            continue
        shared = words & other
        if len(shared) < DUPLICATE_MIN_SHARED_WORDS:
            continue
        union = words | other
        if union and len(shared) / len(union) >= DUPLICATE_SIMILARITY_THRESHOLD:
            return True
    return False


# Deterministic junk-phrase stripping: known boilerplate/share-button/leftover
# text that crawlers sometimes drag in alongside the real article body. A
# fixed phrase list is used instead of asking the AI to find these, because
# an LLM asked to "clean up junk" over a full article has to re-emit the
# entire text to do it - risking silent truncation or drift on long articles.
# Removing a KNOWN, finite set of phrases is something plain string matching
# does perfectly and auditably; no reason to spend an AI call on it.
JUNK_PHRASE_PATTERNS = [
    r'שתפו (?:את הכתבה )?בפייסבוק', r'שתף בפייסבוק', r'שתפו בוואטסאפ',
    r'עקבו אחרינו ב(?:פייסבוק|טוויטר|אינסטגרם)', r'הישארו מעודכנים',
    r'להצטרפות לערוץ (?:הטלגרם|הוואטסאפ)', r'לחצו כאן למעבר לערוץ',
    r'כתבה זו פורסמה לראשונה ב', r'תגובות\s*:?\s*\d+',
]
JUNK_PHRASE_RE = re.compile("|".join(JUNK_PHRASE_PATTERNS))


def strip_known_junk_phrases(text):
    return re.sub(r'[ \t]{2,}', ' ', JUNK_PHRASE_RE.sub('', text)).strip()


# Optional AI enrichment: grammar/typo proofreading, junk-phrase awareness,
# a short factual "key takeaways" bullet list, and 3-4 semantic tags/entities
# - all derived strictly from the REAL scraped article text. None of this
# ever replaces the real excerpt+attribution+link, and the prompt explicitly
# forbids presenting anything as original reporting or inventing facts. Uses
# Groq's free-tier, OpenAI-compatible API (plain HTTPS POST, no SDK). If
# GROQ_API_KEY isn't set or the call fails for any reason, this silently
# no-ops and the article is still published normally, just without the
# enrichment. The AI layer NEVER decides whether an article gets published -
# that stays fully deterministic (the filters above) - it only adds polish.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# llama-3.3-70b-versatile was deprecated by Groq on 2026-06-17 - every
# enrichment call since then silently failed and returned {} via the
# fail-open except-block below, meaning no takeaways/tags/proofreading
# actually ran for ~6 weeks despite articles still publishing normally.
# qwen/qwen3.6-27b is Groq's own recommended migration target for this
# exact model, and is already verified working on this account (used for
# GROQ_VISION_MODEL's watermark detection above).
GROQ_MODEL = "qwen/qwen3.6-27b"
GROQ_VISION_MODEL = "qwen/qwen3.6-27b"
AI_ENRICH_SYSTEM_PROMPT = (
    "אתה עוזר עריכה לאתר חדשות ישראלי. תקבל כותרת וגוף כתבה אמיתית שנשאבה "
    "ממקור חדשות. בצע שלוש משימות, אך ורק על סמך העובדות שמופיעות בטקסט "
    "עצמו - ללא הוספת פרטים, השערות, או דעות שאינם מופיעים בו, וללא ניסוח "
    "שמציג את התוצר כאילו הוא הכתבה המקורית או כאילו אתה מקור הידיעה:\n"
    "1. cleaned_content - הטקסט המלא, מוגה: תקן שגיאות כתיב, פיסוק ותחביר "
    "בלבד. אסור לקצר, לסכם, להשמיט קטעים, לשנות עובדות, או לנסח מחדש "
    "משפטים באופן שמשנה את המשמעות. אם אינך יכול להחזיר את הטקסט המלא, "
    "החזר אותו כפי שהוא ללא שינוי.\n"
    "2. takeaways - רשימה של 3-4 משפטים קצרים (עיקרי הדברים), כל אחד עובדה "
    "בודדת מתוך הטקסט.\n"
    "3. tags - רשימה של 3-4 מילות מפתח סמנטיות (שמות אנשים, ארגונים, "
    "מקומות, או נושאים ספציפיים המוזכרים בכתבה בפועל).\n"
    'השב אך ורק ב-JSON תקני: {"cleaned_content": "...", "takeaways": '
    '["...", "..."], "tags": ["...", "..."]}'
)


def enrich_article_with_ai(title, content):
    if not GROQ_API_KEY:
        return {}
    try:
        payload = json.dumps({
            "model": GROQ_MODEL,
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": AI_ENRICH_SYSTEM_PROMPT},
                {"role": "user", "content": f"כותרת: {title}\n\nגוף הכתבה:\n{content[:6000]}"},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            GROQ_API_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        raw = result["choices"][0]["message"]["content"]
        parsed = json.loads(raw)

        cleaned = re.sub(r'\s+', ' ', (parsed.get("cleaned_content") or "")).strip()
        # safety net: an AI "proofread" that comes back a lot shorter or
        # longer than the original almost always means truncation or
        # unwanted rewriting, not a faithful cleanup - fall back to the
        # original text rather than trust a suspicious result
        if cleaned and 0.7 * len(content) <= len(cleaned) <= 1.3 * len(content):
            content_out = cleaned
        else:
            content_out = content

        # each item forced single-line for the same frontmatter-safety reason
        # as the summary field used to be - see the note further down where
        # these get written into the file
        takeaways = [re.sub(r'\s+', ' ', str(t)).strip() for t in (parsed.get("takeaways") or [])]
        takeaways = [t for t in takeaways if t][:4]
        tags = [re.sub(r'\s+', ' ', str(t)).strip().strip(',') for t in (parsed.get("tags") or [])]
        tags = [t for t in tags if t and ',' not in t][:4]

        return {"content": content_out, "takeaways": takeaways, "tags": tags}
    except Exception as e:
        print(f"העשרת AI נכשלה (מדלג, הכתבה עדיין תתפרסם): {e}")
        return {}


# Real per-image vision check (Groq's hosted qwen/qwen3.6-27b, confirmed
# vision-capable and JSON-mode compatible via console.groq.com/docs/vision)
# for whether a TV/live-broadcast video's thumbnail visibly shows a channel
# logo, on-screen "bug", or lower-third graphic - replaces a blanket
# "hide all TV articles" rule with a per-thumbnail decision, so a clean
# establishing shot still gets to use its real image while a shot that
# actually shows a competing channel's branding gets swapped for the site's
# own placeholder instead. Fails open (assumes no watermark) on any error,
# same non-blocking philosophy as enrich_article_with_ai above - a failed
# check never blocks publishing, it just skips the extra precision.
def detect_tv_watermark(image_url):
    if not GROQ_API_KEY or not image_url:
        return False
    try:
        payload = json.dumps({
            "model": GROQ_VISION_MODEL,
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 100,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": (
                        "בתמונה הזו - תמונת תצוגה מקדימה של סרטון חדשות - "
                        "האם נראה בבירור סמל/לוגו של ערוץ טלוויזיה, 'באג' "
                        "תחנה (סמל שקוף בפינת המסך), כתובית תחתונה עם שם "
                        "התחנה, או כל גרפיקת שידור אחרת שמזהה במפורש מאיזו "
                        'תחנה זה הגיע? השב אך ורק ב-JSON תקני: '
                        '{"has_watermark": true} או {"has_watermark": false}'
                    )},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }],
        }).encode("utf-8")
        req = urllib.request.Request(
            GROQ_API_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        parsed = json.loads(result["choices"][0]["message"]["content"])
        return bool(parsed.get("has_watermark"))
    except Exception as e:
        print(f"זיהוי סימני מים נכשל (מדלג, מניח שאין): {e}")
        return False


# Cross-posts newly-published articles to קודקוד's OWN official Telegram
# channel - not third-party groups/channels we don't control, which would
# be spam/ToS territory on Telegram's side and wouldn't legitimately help
# SEO anyway. Opt-in via env vars (same fail-open pattern as GROQ_API_KEY
# above): silently no-ops until TELEGRAM_BOT_TOKEN/TELEGRAM_CHANNEL_ID are
# set as repo secrets. Owner setup: create a channel, add @BotFather's bot
# to it as admin, get the bot token from BotFather and the channel's
# @username or numeric chat_id.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")


def notify_telegram(title, source_name, category, slug_guess):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        return
    if category == "טלוויזיה ושידורים חיים":  # iron rule: i24/TV content stays out of every other surface too
        return
    try:
        article_url = f"{SITE_URL}/article/{slug_guess}.html"
        text = f"{title}\n\nמקור: {source_name}\n{article_url}"
        payload = json.dumps({
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": text,
            "disable_web_page_preview": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"שיתוף לטלגרם נכשל (מדלג, הכתבה עדיין פורסמה): {e}")


# Internal linking engine: every article's AI-extracted tags get recorded
# here (tag -> the article that introduced it), so the NEXT new article that
# mentions the same tag automatically gets a link back to it. Runs once per
# newly-scraped article, entirely at scrape time - the resulting links are
# baked into the static markdown file itself, so there's no client-side JS
# or per-page-load cost involved at all.
TAGS_INDEX_PATH = os.path.join("data", "tags_index.json")
MAX_AUTO_LINKS_PER_ARTICLE = 3
MIN_TAG_LEN_FOR_LINKING = 3


def load_tags_index():
    try:
        with open(TAGS_INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_tags_index(index):
    os.makedirs(os.path.dirname(TAGS_INDEX_PATH), exist_ok=True)
    with open(TAGS_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def auto_link_internal_tags(content, tags_index):
    candidates = []
    for tag, info in tags_index.items():
        if len(tag) < MIN_TAG_LEN_FOR_LINKING:
            continue
        idx = content.find(tag)
        if idx == -1:
            continue
        candidates.append((idx, idx + len(tag), tag, info["slug"]))
    if not candidates:
        return content

    candidates.sort(key=lambda c: c[0])
    chosen, last_end = [], -1
    for start, end, tag, slug in candidates:
        if start < last_end:
            continue  # overlaps an already-chosen match - skip it
        chosen.append((start, end, tag, slug))
        last_end = end
        if len(chosen) >= MAX_AUTO_LINKS_PER_ARTICLE:
            break

    # rebuild right-to-left so earlier (still-pending) match offsets stay valid
    for start, end, tag, slug in sorted(chosen, key=lambda c: -c[0]):
        content = content[:start] + f"[{tag}](/article/{slug}.html)" + content[end:]
    return content


def save_article(title, link, content, image_url, source_name, category, video_id="", recent_titles=None, tags_index=None):
    filename = f"{sanitize_filename(title)}.md"
    exists = any(os.path.exists(os.path.join(d, filename)) for d in [LIVE_DIR, PENDING_DIR, ARCHIVE_DIR])
    if exists:
        return

    # Filter 0: same story already published by another source recently
    if recent_titles is not None and is_duplicate_of_recent(title, recent_titles):
        print(f"נפסל (כפילות - הסיפור כבר פורסם ממקור אחר): {title}")
        return

    # Filter 3: no sponsored/advertorial content, checked against the RSS
    # teaser first (cheap, before any network fetch)
    if is_sponsored_content(title, link, content):
        print(f"נפסל (תוכן ממומן חשוד): {title}")
        return

    # Video entries skip the image/full-text gates below (they have their
    # own visual - the video itself). Live broadcasts / full episodes are
    # kept, but routed to their own category instead of the regular news
    # video feed, so they land on a separate page rather than being lost.
    # i24NEWS specifically is a hard rule (owner directive): never shown in
    # regular article listings, only reachable via the TV menu/section -
    # every i24 video is routed there regardless of the live-broadcast check.
    if video_id:
        is_i24 = source_name == "i24NEWS עברית"
        video_category = "טלוויזיה ושידורים חיים" if (is_i24 or is_live_broadcast(title)) else category
        if not image_url:
            image_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        has_watermark = False
        if video_category == "טלוויזיה ושידורים חיים":
            has_watermark = detect_tv_watermark(image_url)
            time.sleep(1)  # brief pacing between Groq calls, same margin as the text enrichment call
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _write_article_file(filename, title, date_str, source_name, image_url, link, video_category, content, video_id,
                             has_watermark=has_watermark)
        if recent_titles is not None:
            recent_titles.append(normalize_title_words(title))
        notify_telegram(title, source_name, video_category, slugify(title, sanitize_filename(title)))
        return

    # Filter 1: a real image is mandatory - try the RSS image first, then
    # the article page's og:image; no image at all means the article is
    # rejected outright, not just hidden from listings
    if not image_url:
        image_url = fetch_og_image(link)
    if not image_url:
        print(f"נפסל (אין תמונה איכותית): {title}")
        return

    # A banner/strip-shaped image (not a normal photo) doesn't get rejected
    # outright - it's downgraded to the compact "quick" card style instead
    # of the large hero/bento treatment, similar to how a short news-in-brief
    # item is handled
    quick_image = is_bad_image_aspect(image_url)

    # Filter 2: need the full article body, not just a short RSS teaser.
    # Always attempt the real full-text fetch first (an RSS teaser is
    # rarely as complete as the actual article, even when it happens to
    # clear MIN_CONTENT_LEN on its own) - only fall back to the teaser if
    # the fetch fails and the teaser itself is substantial; otherwise the
    # article is rejected rather than saved with a stub/snippet.
    full_text = fetch_full_article_text(link, MIN_CONTENT_LEN)
    if full_text:
        content = full_text
    elif len(content) < MIN_CONTENT_LEN:
        print(f"נפסל (לא נמצאה כתבה מלאה, רק תקציר קצר מדי): {title}")
        return

    content = strip_known_junk_phrases(content)

    if is_gibberish_or_broken(content):
        print(f"נפסל (תוכן שבור/גיבריש/קישורים שיוריים): {title}")
        return

    # re-check after pulling the full article body - sponsorship disclosure
    # is often buried lower in the text, not in the short RSS teaser
    if is_sponsored_content(title, link, content):
        print(f"נפסל (תוכן ממומן חשוד - זוהה בגוף הכתבה): {title}")
        return

    enrichment = enrich_article_with_ai(title, content)
    if enrichment:
        time.sleep(2)  # free-tier rate-limit safety margin between Groq calls
        content = enrichment.get("content", content)
    takeaways = enrichment.get("takeaways", [])
    tags = enrichment.get("tags", [])

    if tags_index is not None:
        content = auto_link_internal_tags(content, tags_index)

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_article_file(filename, title, date_str, source_name, image_url, link, category, content,
                         takeaways=takeaways, tags=tags, quick_image=quick_image)
    if recent_titles is not None:
        recent_titles.append(normalize_title_words(title))
    # best-effort slug prediction (mirrors build_site.py's own slugify); a
    # rare title-collision could shift the real slug by a "-1" suffix at
    # build time, in which case this specific link would go stale -
    # low-severity, and not worth the complexity of resolving it exactly
    slug_guess = slugify(title, sanitize_filename(title))
    if tags_index is not None and tags:
        for tag in tags:
            tags_index[tag] = {"slug": slug_guess, "title": title}
    notify_telegram(title, source_name, category, slug_guess)


def _write_article_file(filename, title, date_str, source_name, image_url, link, category, content,
                         video_id="", takeaways=None, tags=None, quick_image=False, has_watermark=False):
    video_line = f'\nvideo_id: "{video_id}"' if video_id else ""

    # Each takeaway is written as its own indented continuation line (what
    # the >- block-scalar parser in build_site.py actually expects), prefixed
    # with "•" so the parser's space-joined result can be re-split back into
    # a list on the read side without needing to change that shared parser.
    takeaways_line = ""
    if takeaways:
        block = "\n".join(f"  • {t.replace(chr(8226), '')}" for t in takeaways)
        takeaways_line = f"\nai_takeaways: >-\n{block}"

    tags_line = ""
    if tags:
        joined = ", ".join(t.replace('"', "'").replace(",", "") for t in tags)
        tags_line = f'\nai_tags: "{joined}"'

    quick_image_line = '\nquick_image: "1"' if quick_image else ""
    has_watermark_line = '\nhas_watermark: "1"' if has_watermark else ""

    md_content = f"""---
title: >-
  {title}
date: "{date_str}"
source: "{source_name}"
image: "{image_url}"
link: "{link}"
category: "{category}"{video_line}{takeaways_line}{tags_line}{quick_image_line}{has_watermark_line}
---

{content}

[קרא את הכתבה המלאה במקור]({link})
"""
    with open(os.path.join(LIVE_DIR, filename), "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"נשמר: {title}")


GOOGLE_TRENDS_RSS_URL = "https://trends.google.com/trending/rss?geo=IL"


def fetch_trending_keywords():
    """Real, currently-working Google Trends RSS endpoint for Israel (the
    older trends/trendingsearches/daily/rss path Google used to publish is
    gone - verified by hand before wiring this up, not assumed). Used only
    to reorder processing within THIS run so a trending story is more likely
    to get published even if the run gets cut short partway through - never
    to alter headlines or stuff keywords into anything (see notes on those
    two ideas in the project write-up: both are real Google spam-policy
    risks, not implemented here)."""
    try:
        feed = feedparser.parse(GOOGLE_TRENDS_RSS_URL)
        keywords = [e.get('title', '').strip().lower() for e in feed.entries if e.get('title')]
        return [k for k in keywords if k]
    except Exception as e:
        print(f"שגיאה בשאיבת טרנדים (מדלג, לא משפיע על תפקוד הבוט): {e}")
        return []


def fetch_news():
    manage_archive()
    recent_titles = load_recent_titles()
    tags_index = load_tags_index()
    trending_keywords = fetch_trending_keywords()
    print(f"נטענו {len(recent_titles)} כותרות מ-{DUPLICATE_LOOKBACK_HOURS} השעות האחרונות לבדיקת כפילויות")
    print(f"נטען אינדקס תגיות עם {len(tags_index)} תגיות לקישור פנימי אוטומטי")
    print(f"נטענו {len(trending_keywords)} מגמות חמות מגוגל טרנדס לתעדוף עיבוד")

    candidates = []

    for source_name, (url, category) in rss_feeds.items():
        print(f"מתחיל שאיבה מ-{source_name}...")
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            print(f"שגיאה בשאיבה מ-{source_name}: {e}")
            continue

        for entry in feed.entries[:15]:
            title = entry.get('title', 'ללא כותרת').strip().replace("\n", " ")
            link = entry.get('link', '')
            content = clean_html(entry.get('description', '') or entry.get('summary', ''))
            image_url = extract_image(entry)
            candidates.append({
                "title": title, "link": link, "content": content, "image_url": image_url,
                "source_name": source_name, "category": category, "video_id": "",
            })

    for channel_id, (source_name, category) in youtube_channels.items():
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        print(f"מתחיל שאיבת וידאו מ-{source_name}...")
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"שגיאה בשאיבת וידאו מ-{source_name}: {e}")
            continue

        for entry in feed.entries[:10]:
            title = entry.get('title', 'ללא כותרת').strip().replace("\n", " ")
            link = entry.get('link', '')
            video_id = entry.get('yt_videoid', '')
            content = clean_html(entry.get('summary', ''))
            image_url = extract_image(entry)
            candidates.append({
                "title": title, "link": link, "content": content, "image_url": image_url,
                "source_name": source_name, "category": category, "video_id": video_id,
            })

    def is_trending(candidate):
        title_lower = candidate["title"].lower()
        return any(kw in title_lower for kw in trending_keywords)

    # stable sort: trending-matched candidates first, original order preserved
    # within each group (across ALL sources, not just per-feed)
    candidates.sort(key=lambda c: 0 if is_trending(c) else 1)
    trending_count = sum(1 for c in candidates if is_trending(c))
    if trending_count:
        print(f"{trending_count} כתבות תואמות מגמה חמה - יעובדו ראשונות")

    for c in candidates:
        save_article(c["title"], c["link"], c["content"], c["image_url"], c["source_name"], c["category"],
                     video_id=c["video_id"], recent_titles=recent_titles, tags_index=tags_index)

    save_tags_index(tags_index)


if __name__ == "__main__":
    fetch_news()
