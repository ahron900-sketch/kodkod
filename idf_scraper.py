import feedparser
import html
import os
import re
import time
import shutil
import urllib.request
from datetime import datetime

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

MIN_CONTENT_LEN = 400

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


def save_article(title, link, content, image_url, source_name, category, video_id=""):
    filename = f"{sanitize_filename(title)}.md"
    exists = any(os.path.exists(os.path.join(d, filename)) for d in [LIVE_DIR, PENDING_DIR, ARCHIVE_DIR])
    if exists:
        return

    # Filter 3: no sponsored/advertorial content, checked against the RSS
    # teaser first (cheap, before any network fetch)
    if is_sponsored_content(title, link, content):
        print(f"נפסל (תוכן ממומן חשוד): {title}")
        return

    # Video entries skip the image/full-text gates below (they have their
    # own visual - the video itself) but go through the live-broadcast filter
    if video_id:
        if is_live_broadcast(title):
            print(f"נפסל (שידור חי/פרק מלא, לא קליפ חדשות): {title}")
            return
        if not image_url:
            image_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _write_article_file(filename, title, date_str, source_name, image_url, link, category, content, video_id)
        return

    # Filter 1: a real image is mandatory - try the RSS image first, then
    # the article page's og:image; no image at all means the article is
    # rejected outright, not just hidden from listings
    if not image_url:
        image_url = fetch_og_image(link)
    if not image_url:
        print(f"נפסל (אין תמונה איכותית): {title}")
        return

    # Filter 2: need the full article body, not just a short RSS teaser -
    # if the full-text fetch fails, this article is rejected rather than
    # saved with a stub/snippet
    if len(content) < MIN_CONTENT_LEN:
        full_text = fetch_full_article_text(link, MIN_CONTENT_LEN)
        if not full_text:
            print(f"נפסל (לא נמצאה כתבה מלאה, רק תקציר): {title}")
            return
        content = full_text

    if is_gibberish_or_broken(content):
        print(f"נפסל (תוכן שבור/גיבריש/קישורים שיוריים): {title}")
        return

    # re-check after pulling the full article body - sponsorship disclosure
    # is often buried lower in the text, not in the short RSS teaser
    if is_sponsored_content(title, link, content):
        print(f"נפסל (תוכן ממומן חשוד - זוהה בגוף הכתבה): {title}")
        return

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_article_file(filename, title, date_str, source_name, image_url, link, category, content)


def _write_article_file(filename, title, date_str, source_name, image_url, link, category, content, video_id=""):
    video_line = f'\nvideo_id: "{video_id}"' if video_id else ""
    md_content = f"""---
title: >-
  {title}
date: "{date_str}"
source: "{source_name}"
image: "{image_url}"
link: "{link}"
category: "{category}"{video_line}
---

{content}

[קרא את הכתבה המלאה במקור]({link})
"""
    with open(os.path.join(LIVE_DIR, filename), "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"נשמר: {title}")


def fetch_news():
    manage_archive()

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
            save_article(title, link, content, image_url, source_name, category)

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
            save_article(title, link, content, image_url, source_name, category, video_id=video_id)


if __name__ == "__main__":
    fetch_news()
