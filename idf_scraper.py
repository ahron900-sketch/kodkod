import feedparser
import glob
import html
import io
import json
import os
import re
import time
import shutil
import urllib.request
from datetime import datetime, timedelta
from build_site import slugify, SITE_URL  # single source of truth for slug computation

# Real pixel-level image analysis (blur detection, perceptual duplicate
# hashing) needs Pillow, which .github/workflows/idf_bot.yml now installs.
# Guarded import so a local run without it installed still works - every
# function using PIL below fails open (skips the check, never blocks
# publishing) rather than crashing when this is unavailable.
try:
    from PIL import Image, ImageFilter
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

# Owner directive (2026-08-02): closed allowed-source list only, pending
# real legal clearance - every commercial RSS feed that used to be here
# (ynet, Walla, mako, Maariv, Globes, Geektime, Foody, ONE, Techtime, אמס,
# כל רגע, בחדרי חרדים) is removed, not just filtered downstream. The
# fail-closed rewrite gate shipped tonight would eventually reject most of
# this content anyway, but leaving the feeds wired in here still means
# needless requests to commercial sites and depends on the AI call
# succeeding to enforce a policy that should hold regardless of Groq's
# availability. Empty until the new gov.il/NASA/Wikipedia/etc. pipeline is
# built against the closed source list the owner specified.
rss_feeds = {}

# מקורות שנבדקו ונפסלו במחקר המקורות (2026-07-30) - לא להוסיף שוב בלי סיבה טובה:
# - מאקו רכב: robots.txt חוסם במפורש (Disallow: /cars-)
# - כיכר השבת: התנאים שלהם אוסרים במפורש העתקה/סריקה אוטומטית, גם שהפיד עצמו עובד
# - Calcalist, בחדרי חרדים (מקור קיים, חסום עכשיו), כאן חרדי: מחזירים 403 לבקשות אוטומטיות
# - Ynet תחום טכנולוגיה: לא קיים בכלל, ותנאי ה-RSS הכלליים של ynet מגבילים לשימוש
#   פרטי-לא-מסחרי בלבד - הבוט כבר משתמש ב-ynet (חדשות + יוטיוב) מלפני המחקר הזה;
#   שיקול משפטי שדורש החלטה של הבעלים, לא הוספה נוספת חד-צדדית בינתיים
# - יבואני רכב (טויוטה/קיה) יש להם עמודי חדשות רשמיים אמיתיים אך בלי RSS - ידרוש
#   פונקציית סריקת HTML נפרדת, לא מומש עדיין
#
# סבב שני (דוברויות/מקורות ראשוניים, 2026-07-30) - נבדק ונפסל:
# - כבאות והצלה, רשות שדות התעופה: הערוץ קיים אך שומם (ללא העלאות חדשות חודשים)
# - פיקוד העורף: נבדק פעמיים - רוב התוכן פרסומי/חינוכי ולא באמת חדשותי, וישן
# - רשות ניירות ערך: ערוץ אמיתי אך שומם (העלאה אחרונה לפני כ-7 חודשים)
# - איגוד הכדורסל, מנהלת הליגות לכדורגל (IPFL): רוב התוכן שידורי משחקים מלאים/
#   הייליטס בבעלות זכויות שידור - לא מתאים לציטוט טקסטואלי כמו שאר המקורות
# - תרבות ובידור: לא נמצא אף מקור דוברות/PR פתוח ואמיתי (כאן/קשת/רשת/HOT/yes) -
#   הדפים הרלוונטיים דורשים גישה מוגבלת לעיתונאים או חסומים לבקשות אוטומטיות

# ערוצי יוטיוב - נשאבים כווידאו דרך YouTube RSS (אין צורך במפתח API)
# הוסף כאן channel_id אמיתיים (נמצא ב-view-source של דף הערוץ, tag <meta itemprop="channelId">)
#
# Owner directive (2026-08-02): closed allowed-source list only. Removed
# every non-government channel that used to be here - כאן חדשות, חדשות 13,
# ynet, i24NEWS עברית, ספורט 5, and the sports-body channels (ההתאחדות
# לכדורגל, מכבי ת"א, הפועל ת"א, מכבי חיפה) - a public broadcaster or a
# sports team's own footage is still someone else's copyrighted content,
# not an official publication of the state. Only actual government
# ministries/statutory bodies remain, matching exactly the safe-source list
# used for the 2026-08-02 corpus archive.
youtube_channels = {
    "UCjBj9fgK60mlAH-nvtSOojg": ("דובר צה\"ל", "חדשות"),
    "UCrwyHUb4iIrpknhP6MTvnww": ("דוברות המשטרה", "חדשות"),
    "UCKTHc_HFDiAiOr0vE_Imj5g": ("משרד הבריאות", "בריאות"),
    "UC4elaDPpw25TipG2U33paLA": ("הכנסת", "חדשות"),
    "UC4XJnRPZjXhgvVMhXKNSJvQ": ("משרד ראש הממשלה", "חדשות"),
    "UCMT8Bdqj1OGwmOAGCBkvh3Q": ("משרד האוצר", "כלכלה"),
    "UChJvckHJmDDQu3ujhGNJ5bg": ("בנק ישראל", "כלכלה"),
    "UC_5RpglK4gBbtE7vPMDTOWw": ("רשות המסים", "כלכלה"),
    "UCcoZAalDFqahuJRvmEPV-kQ": ("משרד החינוך", "חדשות"),
    "UCDZjiJmSjN_3x2oK3qURmIA": ("משרד התחבורה", "רכב"),
    "UCRiWtBVOhosO4B_QSSMxSbA": ("מגן דוד אדום", "חדשות"),
    "UCXnvhZNewGAIQrUKYYJNeIQ": ("שירות בתי הסוהר", "חדשות"),
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
    swap in a larger rendition through the same URL pattern/CDN the source
    itself already serves, rather than guessing at a URL that might not
    exist. Zero storage cost - the CDN generates the resize on the fly."""
    if not url:
        return url
    # mako.co.il: "..._autoOrient_a.jpg" is an ~80x60 crop; the same filename
    # without the trailing "_a" is the real, full-size image
    url = re.sub(r'(_autoOrient)_a(\.\w+)(\?.*)?$', r'\1\2', url)
    # Cloudinary-style resize path segment, e.g. Walla's
    # "images.wcdn.co.il/f_auto,q_auto,w_300/..." - bumps a small requested
    # width up; only touches width (not height) since an unfamiliar CDN's
    # exact crop/fit behavior for a two-dimension change isn't something to
    # guess at, but requesting a wider image through the same live resize
    # endpoint is safe and well-verified for this specific pattern
    def _bump_cloudinary_width(m):
        w = int(m.group(1))
        return f"w_{1200}" if w < 600 else m.group(0)
    url = re.sub(r'w_(\d+)', _bump_cloudinary_width, url)
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

# Below this in either dimension reads as a thumbnail/tracking-pixel/broken
# placeholder, not a real editorial photo - genuinely rejected, not just
# downgraded like the aspect-ratio check above
MIN_IMAGE_WIDTH = 200
MIN_IMAGE_HEIGHT = 150


def _fetch_image_chunk(image_url):
    """Real bytes from the image URL (first 128KB, enough for any format's
    dimension header) - shared by the aspect-ratio downgrade check and the
    hard quality-reject gate below, so a bad/slow image source only costs
    one request per article, not two. Returns None on any failure (network
    error, timeout, non-2xx) - a genuinely unreachable image, not "couldn't
    parse the bytes we got"."""
    if not image_url:
        return None
    try:
        req = urllib.request.Request(
            image_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KodkodBot/1.0)", "Range": "bytes=0-131071"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            return resp.read(131_072)
    except Exception:
        return None


def is_bad_image_aspect(chunk):
    dims = get_image_dimensions(chunk) if chunk else None
    if not dims:
        return False
    width, height = dims
    ratio = width / height
    return ratio > BAD_ASPECT_MAX or ratio < BAD_ASPECT_MIN


def is_low_quality_image(chunk):
    """True only when we can positively confirm a problem - never for a
    format get_image_dimensions() doesn't parse (WebP/AVIF are common on
    Israeli news sites and would otherwise get wrongly rejected). A real,
    non-trivial byte response with no parseable header is given the
    benefit of the doubt, same fail-open philosophy as the rest of this
    file; only a genuinely-measured too-small image is rejected."""
    if not chunk:
        return True  # image URL didn't resolve to anything at all
    if len(chunk) < 800:
        return True  # a real photo is never this few bytes - tracking pixel/broken stub
    dims = get_image_dimensions(chunk)
    if not dims:
        return False
    width, height = dims
    return width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT


MAX_FULL_IMAGE_BYTES = 6_000_000


def _fetch_full_image(image_url):
    """Unlike _fetch_image_chunk (128KB, just enough for a dimension
    header), blur detection and perceptual hashing need real decodable
    pixel data - fetches the whole image, capped so a pathologically large
    file can't stall a scrape run. Returns None on any failure, same
    fail-open contract as the rest of this file."""
    if not image_url:
        return None
    try:
        req = urllib.request.Request(
            image_url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KodkodBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read(MAX_FULL_IMAGE_BYTES)
    except Exception:
        return None


# Laplacian-style edge variance (the standard, well-known blur-detection
# heuristic - a sharp photo has high-variance edges, a blurry/flat one
# doesn't) - resized to a fixed size first so the threshold means the same
# thing regardless of the source image's original resolution. Threshold is
# a conservative starting point (only rejects clearly, badly blurry images)
# - meant to be tuned against real results over time, not a precise science.
BLUR_VARIANCE_THRESHOLD = 50


def is_blurry_image(image_bytes):
    if not HAVE_PIL or not image_bytes:
        return False
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L").resize((300, 300))
        edges = list(img.filter(ImageFilter.FIND_EDGES).getdata())
        mean = sum(edges) / len(edges)
        variance = sum((p - mean) ** 2 for p in edges) / len(edges)
        return variance < BLUR_VARIANCE_THRESHOLD
    except Exception:
        return False  # can't decode it here - Filter 1's own checks already gate real corruption


# Perceptual average-hash (aHash): resize to 8x8 grayscale, threshold each
# pixel against the mean brightness - two images that look alike (same wire
# photo, a re-compressed/resized copy, a minor crop) end up with a small
# Hamming distance between their hashes, unlike a byte-exact hash which
# would only catch a literally identical file.
IMAGE_HASH_INDEX_PATH = os.path.join("data", "image_hashes.json")
IMAGE_DEDUPE_LOOKBACK_HOURS = 72
IMAGE_HASH_DUPLICATE_DISTANCE = 6


def image_ahash(image_bytes):
    if not HAVE_PIL or not image_bytes:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L").resize((8, 8))
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        return "".join("1" if p > avg else "0" for p in pixels)
    except Exception:
        return None


def hamming_distance(hash_a, hash_b):
    if not hash_a or not hash_b or len(hash_a) != len(hash_b):
        return 999
    return sum(a != b for a, b in zip(hash_a, hash_b))


def load_recent_image_hashes():
    """Returns {hash: {"title":..., "ts": unix_time}}, pruned to the lookback
    window - mirrors load_recent_titles()'s pattern for duplicate stories,
    but for images reused across otherwise-unrelated articles."""
    try:
        with open(IMAGE_HASH_INDEX_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    cutoff = time.time() - IMAGE_DEDUPE_LOOKBACK_HOURS * 3600
    return {h: v for h, v in data.items() if v.get("ts", 0) >= cutoff}


def save_image_hashes(index):
    os.makedirs(os.path.dirname(IMAGE_HASH_INDEX_PATH), exist_ok=True)
    with open(IMAGE_HASH_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def find_duplicate_image(new_hash, recent_hashes):
    if not new_hash:
        return None
    for h, info in recent_hashes.items():
        if hamming_distance(new_hash, h) <= IMAGE_HASH_DUPLICATE_DISTANCE:
            return info.get("title")
    return None


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
FIGCAPTION_RE = re.compile(r'<figcaption\b[^>]*>.*?</figcaption>', re.DOTALL | re.IGNORECASE)
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


def fetch_full_article_text(link):
    """Best-effort: pull the <article> block's paragraphs from the live page
    when the RSS summary is too short. Returns '' if it can't find real
    prose, or if what it found looks like nav/cookie-banner junk. Does NOT
    gate on length itself - callers decide what a given length qualifies
    as (a full article vs. an honest short bulletin vs. too little to
    publish at all). Previously this discarded real, genuinely-extracted
    prose outright just for being under the full-article length floor,
    which meant honest early/breaking coverage got thrown away instead of
    published as what it actually was."""
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
    # photo/video captions (e.g. Walla's <figcaption><span class="media-
    # description">...</span><span class="slash-between">/</span><span
    # class="media-credit">...</span></figcaption>, confirmed by fetching a
    # real article page) are never article prose - stripped entirely before
    # paragraph extraction, instead of leaking in as "caption/creditNEXT
    # SENTENCE" glued with zero separator
    scope = FIGCAPTION_RE.sub("", scope)
    raw_paragraphs = PARAGRAPH_RE.findall(scope)
    if not raw_paragraphs:
        raw_paragraphs = DIV_PARAGRAPH_RE.findall(scope)
    paragraphs = []
    junk_hits = 0
    for p in raw_paragraphs:
        if SCRIPT_LEAK_RE.search(p):
            continue
        # some sources (Walla and others) put an entire multi-line article
        # inside ONE <p> and separate lines with <br> rather than real <p>
        # tags - stripping those to "" like every other tag glues the
        # surrounding sentences together with zero separator ("...לוד.במשך
        # תקופה..."). Block-boundary tags need to become whitespace first,
        # everything else can still just disappear.
        text = re.sub(r'<br\s*/?>|</p>|</div>|</li>|</h[1-6]>', ' ', p, flags=re.IGNORECASE)
        text = TAG_STRIP_RE.sub("", text).strip()
        text = re.sub(r'\s+', ' ', text)
        text = html.unescape(text)
        text = CAPTION_SPLIT_RE.sub("", text).strip()
        if len(text) > 30:  # skip short boilerplate/caption paragraphs
            paragraphs.append(text)
            if JUNK_MARKERS_RE.search(text):
                junk_hits += 1
    if not paragraphs or junk_hits > len(paragraphs) // 3:
        return ""
    return "\n\n".join(paragraphs)

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

# Genuine breaking-news bulletins - real, early coverage of something still
# developing, honestly short rather than padded to a length it doesn't
# deserve yet. Previously this content was fetched successfully (real
# prose, not junk) but discarded outright because it didn't clear
# MIN_CONTENT_LEN - the site published nothing at all rather than an
# honest short update. 250 chars is a real floor (a genuine sentence or
# two of substance), not a token amount.
MIN_BULLETIN_LEN = 250

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


MAX_SYNTHESIS_CLUSTER_SIZE = 3


def cluster_candidates_by_story(candidates):
    """Groups same-story candidates from DIFFERENT sources within a single
    scrape batch, using the exact same title-similarity signal as
    is_duplicate_of_recent (Jaccard >= DUPLICATE_SIMILARITY_THRESHOLD, >=
    DUPLICATE_MIN_SHARED_WORDS shared significant words). Previously, when
    2+ outlets covered the same story in one run, only the first candidate
    processed was kept - every later one silently hit Filter 0 and was
    discarded as "already published". Now those candidates are grouped so
    real multi-source synthesis can run on them instead of throwing the
    extra coverage away. Video candidates are never clustered - a video's
    own footage is its content, not interchangeable with another outlet's
    text coverage of the same event."""
    text_candidates = [c for c in candidates if not c.get("video_id")]
    video_candidates = [c for c in candidates if c.get("video_id")]

    word_sets = [normalize_title_words(c["title"]) for c in text_candidates]
    used = set()
    clusters = []

    for i, c in enumerate(text_candidates):
        if i in used:
            continue
        group = [c]
        used.add(i)
        words_i = word_sets[i]
        if len(words_i) >= DUPLICATE_MIN_SHARED_WORDS:
            for j in range(i + 1, len(text_candidates)):
                if j in used or len(group) >= MAX_SYNTHESIS_CLUSTER_SIZE:
                    continue
                if text_candidates[j]["source_name"] == c["source_name"]:
                    continue  # same outlet twice isn't multi-source
                words_j = word_sets[j]
                if len(words_j) < DUPLICATE_MIN_SHARED_WORDS:
                    continue
                shared = words_i & words_j
                union = words_i | words_j
                if len(shared) >= DUPLICATE_MIN_SHARED_WORDS and union and \
                        len(shared) / len(union) >= DUPLICATE_SIMILARITY_THRESHOLD:
                    group.append(text_candidates[j])
                    used.add(j)
        clusters.append(group)

    clusters.extend([c] for c in video_candidates)
    return clusters


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
    # Walla (and others) leave their own "last updated" page-metadata line
    # inside the scraped body text - not part of the actual article prose
    r'עודכן לאחרונה\s*:\s*\d{1,2}\.\d{1,2}\.\d{4}\s*/\s*\d{1,2}:\d{2}',
    # Confirmed recurring native-ad/cross-promo/widget boilerplate (found by
    # frequency-counting standalone lines across the whole corpus - each of
    # these repeats across dozens to hundreds of otherwise-unrelated
    # articles, unlike genuine reporting text which never repeats verbatim
    # like this) - never real article content, always safe to remove
    r'עדכונים שוטפים בערוץ הוואטסאפ של i24NEWS',
    r'לצפייה בכתבות וניהול הנושאים, יש ללחוץ על כפתור בסרגל העליון',
    r'השאלון שיעשה לכם סדר\s*-\s*מי המפלגה שהכי מתאימה לעמדות שלכם\??',
    r'סקירת המסחר: דיווחים שוטפים, מגמות, מדדים, שערי מניות, אג"ח, מט"ח וסחורות והמלצות אנליסטים',
    r'רנו קפצ.ר החדשה: קטנה במידות, גדולה באופי',
    r'עקבו אחרינו באינסטגרם\s*:\s*/\s*i24news_he',
    r'הלוואה לחינוך: איך להשקיע בעתיד הילדים בלי להיכנס לסחרור כלכלי\??',
    r'3 מנויים ב-75 שקלים וגם חודש חינם! וואלה מובייל חוסכת המון',
    r'מתוך המהדורה המרכזית, ערוץ 15 בשלט',
    r'המסחר חוזר לצעירים: בנק הפועלים מקל על הצעד הראשון ומציג מהלך חדש בשוק ההון',
    r'רוצים להנות מאינטרנט מהיר וחבילת טלווזיה בזול\? זה אפשרי!',
    r'הצטרפו לוואלה [Ff]iber ושדרגו את חווית הגלישה והטלוויזיה בזול!',
    r'המהפכה של וואלה Fiber שתחסוך לכם בעלויות הטלוויזיה והאינטרנט',
    r'הצטרפו לוואלה פייבר ותהנו מאינטרנט וטלוויזיה במחיר שלא הכרתם',
    r'עוברים עכשיו לוואלה מובייל ונהנים מ-3 מנויים ב-\s*75 שקלים',
    r'חווית גלישה וטלוויזיה איכותית בזול\? עכשיו זה אפשרי!',
    r'איזו תוכנית לתואר שני במנהל עסקים מציעה הכי הרבה קורסי בחירה\??',
    r'איך נראה עתיד ההשקעות בנדל"ן: להצליח בשוק משתנה בעידן של חוסר ודאות',
    r'שוקלים לקחת הלוואה אך מפחדים\? המדריך לצעדים פיננסים חכמים',
    r'נלחמים ביוקר הנדל"ן: כך תוסיפו לבית חדר ביום אחד',
    r'גיל המעבר: התקופה שמגיעה בלי הוראות הפעלה',
    r'הצלחה אמיתית: שביעות רצון של למעלה מ-?94% בטיפולי הרזיה',
    r"האזינו ל[^:\n]{0,70}ב'קול חי':?",
    r'מוזמנים לבקר באתר שלנו:?',
    r'עקבו אחרינו גם בפלטפורמות הנוספות שלנו',
    r'מתוך מגזין השבת, ערוץ 15 בשלט',
    r'קאר ניוז ליווי וייעוץ בתהליכי רכישת רכב, קנייה ומכירה, ופתרונות מימון\.\s*[\d\-]+',
    # Two GENERAL structural patterns, not tied to one source's exact
    # wording - found via a real article ("ההאקר הישראלי של אילון מאסק",
    # Geektime) that alone contained four leaked-widget lines the exact-
    # phrase patterns above would never catch, since every source phrases
    # its own widgets differently. These match the STRUCTURE instead:
    #
    # 1) A photo caption that leaked in as its own plain paragraph, not
    # wrapped in <figcaption> (FIGCAPTION_RE above only catches the HTML-
    # tagged case) - e.g. "יוני רמון. תמונה באדיבות המצולם",
    # "המערכת של Pi. צילום מסך", "גיא ארזי (ימין) ויוני רמון. תמונה: Rona
    # Bar & Ofek Avshalom". Verified against a 5000-article sample (71,095
    # lines) before relying on this: 59 matches, all genuine photo credits,
    # zero false positives - the tight anchoring (marker within the first
    # 80 chars of the line, short line overall) is what keeps a metaphorical
    # use of the same word ("התמונה הכלכלית מדאיגה") from matching, since
    # real prose using it that way doesn't look like a short standalone
    # caption line.
    r'^.{0,80}(תמונה\s*:|תמונה\s+באדיבות|צילום\s*:|צילום\s+מסך)\s*.{0,50}$',
    # 2) A related-headlines teaser widget rendered as one line with 2+
    # "●" bullet separators (e.g. "● פשיטות הרגל בגרמניה בשיא... ● החברות
    # הגדולות חוזרות לגייס עובדים..."), confirmed on Globes across
    # completely unrelated topics (health, tech, finance, real estate) -
    # real Hebrew news prose essentially never uses "●" inline, so 2+ on
    # one line is a reliable signal this is the widget, not article text.
    r'[^\n]*●[^\n]*●[^\n]*',
    # Source-specific widget/CTA text, found via two real articles
    # (Globes tech, Geektime) this same night - not generalizable the way
    # the two patterns above are, but still safe, confirmed-exact matches.
    r'לחיצה על הנושא תוסיף אותו לרשימת "הנושאים שמעניינים אותי", שם ניתן לקרוא ולנהל את ההתראות כשמתפרסמת כתבה בנושא\.',
    r'הצטרפו עכשיו לערוץ הטלגרם של \S+ כדי לא לפספס עוד כתבות כאלו',
    r'תנו לזה לשקוע:[^\n]*',
]
JUNK_PHRASE_RE = re.compile("|".join(JUNK_PHRASE_PATTERNS), re.MULTILINE)

# No raw links are ever allowed inside a published article body - the only
# link we show is the single, explicit "read the full article at the source"
# line _write_article_file appends itself. Scraped content sometimes drags in
# whole lines of promotional/tracking links instead (social-media handles, app
# download shorteners, channel homepage) - especially YouTube video
# descriptions, which are often *entirely* this kind of boilerplate with no
# real synopsis at all. Any full line containing a URL is dropped outright.
URL_IN_LINE_RE = re.compile(r'https?://\S+|bit\.ly/\S+|goo\.gl/\S+')


def strip_link_lines(text):
    if not text:
        return text
    lines = [ln for ln in text.splitlines() if not URL_IN_LINE_RE.search(ln)]
    cleaned = "\n".join(lines)
    return re.sub(r'\n{3,}', '\n\n', cleaned).strip()


# A video's YouTube description is frequently just channel-handle/social-link
# boilerplate (see strip_link_lines above) with zero real synopsis of the
# story. Once link-lines are stripped, what's left has to clear this low bar
# - low because a real one-line video caption is naturally much shorter than
# a full article - or the video is rejected outright rather than published
# with a content-free stub. This is the "fully clean it or don't publish"
# rule applied to video/social-sourced items: since there's no real text left
# to clean, and we never fabricate a synopsis via AI (risk of inventing
# facts), reject is the only honest option.
MIN_VIDEO_CONTENT_LEN = 30


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
# The site's fixed category set (must match build_site.py's DESK_BY_CATEGORY/
# category pages exactly - not TV_CATEGORY, which is assigned separately by
# the video/live-broadcast branch, never by this general RSS path)
VALID_CATEGORIES = [
    "חדשות", "ספורט", "כלכלה", "טכנולוגיה", "בריאות", "רכב",
    "תרבות ובידור", "בישול ומתכונים", "חרדים",
]

# Objective, non-AI check for whether a "rewrite" actually got reworded, or
# just came back as the source text with a few words swapped. Trusting the
# model's own self-report isn't enough - this measures it directly: build
# 6-word sliding-window shingles from both texts and see what fraction of
# the output's windows also appear verbatim in the source. A genuine
# independent rewrite shares almost no 6-word sequences with the original
# (near 0); a copy with light synonym-swapping still shares most of them
# (most windows are untouched between edits) - tested against mock verbatim/
# rewritten/lightly-edited text before relying on this in production.
def _word_shingles(text, n=6):
    words = re.findall(r'[\w֐-׿]+', text)
    if len(words) < n:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


REWRITE_SIMILARITY_THRESHOLD = 0.30


def is_too_similar_to_source(output_text, source_text):
    out_shingles = _word_shingles(output_text)
    if not out_shingles:
        return True  # empty output is never an acceptable rewrite
    src_shingles = _word_shingles(source_text)
    overlap = len(out_shingles & src_shingles) / len(out_shingles)
    return overlap > REWRITE_SIMILARITY_THRESHOLD

AI_ENRICH_SYSTEM_PROMPT = (
    "אתה עורך תוכן לאתר חדשות ישראלי. תקבל כותרת וגוף כתבה אמיתית שנשאבה "
    "ממקור חדשות (הקטגוריה המוצעת נקבעת כרגע לפי המקור עצמו, ולכן עלולה "
    "להיות שגויה אם המקור מפרסם גם תוכן שאינו בנושא הרגיל שלו). בצע חמש "
    "משימות, אך ורק על סמך העובדות שמופיעות בטקסט עצמו - ללא הוספת פרטים, "
    "השערות, או דעות שאינם מופיעים בו, וללא ניסוח שמציג את התוצר כאילו הוא "
    "הכתבה המקורית או כאילו אתה מקור הידיעה:\n"
    "1. rewritten_content - אל תנסח מחדש משפט-אחר-משפט לפי הסדר שבמקור. "
    "בחר נקודת כניסה וזווית ארגון שונות לגמרי מהמקור - למשל: אם המקור פותח "
    "בהסבר מוסדי/טכני, פתח אתה במשמעות המעשית לקורא; אם המקור בנוי "
    "כרונולוגית, ארגן אתה לפי חשיבות או לפי 'למה זה משנה'; שקול מבנה כמו "
    "'מה קרה / מה זה אומר בפועל / מה השלב הבא' במקום לחקות את זרימת המקור. "
    "כל העובדות חייבות להישאר אותן עובדות בדיוק - זו סינתזה מחדש של אותו "
    "חומר גלם במבנה עצמאי, לא תוספת של מידע חדש. זהו כלל-הברזל: חובה לשמר במדויק "
    "את כל העובדות - שמות, תאריכים, מספרים, נתונים ומיקומים - בדיוק כפי "
    "שהם, בלי לשנות אף אחד מהם. ציטוטים ישירים (בתוך מירכאות) חייבים "
    "להישאר מדויקים מילה-במילה ומיוחסים לאותו דובר בדיוק - אסור לשנות, "
    "לקצר או להמציא ציטוט. אסור בתכלית האיסור להוסיף עובדה, פרט, נתון "
    "או משפט שאינו נובע ישירות מהטקסט המקורי. אסור לקצר משמעותית את "
    "הכתבה או להשמיט מידע מהותי - האורך הכולל צריך להישאר דומה למקור. "
    "אם אינך בטוח שתוכל לנסח מחדש בלי לסכן דיוק עובדתי, החזר את הטקסט "
    "המקורי ללא שינוי במקום להמציא או לנחש.\n"
    "2. takeaways - רשימה של 3-4 משפטים קצרים (עיקרי הדברים), כל אחד עובדה "
    "בודדת מתוך הטקסט.\n"
    "3. tags - רשימה של 3-4 מילות מפתח סמנטיות (שמות אנשים, ארגונים, "
    "מקומות, או נושאים ספציפיים המוזכרים בכתבה בפועל).\n"
    "4. verified_category - הקטגוריה שהכי מתאימה לתוכן בפועל, מהרשימה "
    "הסגורה הבאה בדיוק: " + ", ".join(VALID_CATEGORIES) + ". לדוגמה: כתבה "
    "על סקר תחלואה של משרד הבריאות ששייכת קטגורית מקור 'חרדים' רק בגלל "
    "שהמקור הוא אתר חרדי - שייכת בפועל ל'בריאות'.\n"
    "5. hero_worthy - true אך ורק אם זו ידיעת חדשות מבזקת אמיתית, על אירוע "
    "קונקרטי שקרה/נחשף עכשיו, באחד מהנושאים הבאים: ביטחון/צבא, פשע חמור "
    "(רצח, טרור, פיגוע), ספורט משמעותי, סלבריטאים/תרבות ובידור, או כלכלה "
    "משמעותית (כמו החלטת ריבית, קריסת שוק, פיטורים המוניים - לא טיפים "
    "כלליים). false בכל מקרה אחר, במפורש כולל: תוכן טיפים/מדריך/הסבר "
    "כללי-לאורך-זמן (כגון 'איך לתכנן פרישה', 'כך תחסכו במס') גם אם הקטגוריה "
    "היא כלכלה - זה תוכן ירוק-לנצח, לא ידיעה מבזקת, גם אם הכותרת מנוסחת "
    "כשאלה או כהצעת ערך. false גם עבור בריאות, מתכונים, רכב, טכנולוגיה, "
    "ותוכן חדשותי כללי/שגרתי שאינו מבזק אמיתי.\n"
    'השב אך ורק ב-JSON תקני: {"rewritten_content": "...", "takeaways": '
    '["...", "..."], "tags": ["...", "..."], "verified_category": "...", '
    '"hero_worthy": false}'
)


def enrich_article_with_ai(title, content):
    if not GROQ_API_KEY:
        return {"rewrite_succeeded": False}
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

        rewritten = re.sub(r'\s+', ' ', (parsed.get("rewritten_content") or "")).strip()
        # safety net: compare against what the model actually saw (input is
        # capped at 6000 chars below), not the full original - a long source
        # article naturally makes a shorter rewrite look "truncated" if
        # measured against the untruncated original. A rewrite that comes
        # back far shorter or longer than what it was given almost always
        # means truncation, garbling, or unwanted summarizing - fall back to
        # the original text rather than trust a suspicious result.
        source_len = len(content[:6000])
        length_ok = rewritten and 0.6 * source_len <= len(rewritten) <= 1.5 * source_len
        # objective check, not just a length heuristic: does the "rewrite"
        # actually share large verbatim chunks with the source? Catches the
        # case a pure length check misses - a right-sized output that's
        # still mostly copied with light synonym-swapping.
        rewrite_succeeded = bool(length_ok and not is_too_similar_to_source(rewritten, content[:6000]))
        # legal directive (2026-08-02): a rewrite that fails these checks must
        # NEVER fall back to publishing the original scraped text - that fail-
        # open behavior is exactly the fact pattern found to be copyright
        # infringement in Israeli case law (Mor v. Azoulay, T.A. 26386-09-09 -
        # a news article republished on another site without a genuine
        # rewrite). content_out is left empty here; the caller rejects the
        # article entirely when rewrite_succeeded is False instead of
        # publishing anything derived from the raw source text.
        content_out = rewritten if rewrite_succeeded else ""

        # each item forced single-line for the same frontmatter-safety reason
        # as the summary field used to be - see the note further down where
        # these get written into the file
        takeaways = [re.sub(r'\s+', ' ', str(t)).strip() for t in (parsed.get("takeaways") or [])]
        takeaways = [t for t in takeaways if t][:4]
        tags = [re.sub(r'\s+', ' ', str(t)).strip().strip(',') for t in (parsed.get("tags") or [])]
        tags = [t for t in tags if t and ',' not in t][:4]

        verified_category = parsed.get("verified_category")
        if verified_category not in VALID_CATEGORIES:
            verified_category = None
        hero_worthy = bool(parsed.get("hero_worthy") is True)

        return {
            "content": content_out, "takeaways": takeaways, "tags": tags,
            "verified_category": verified_category, "hero_worthy": hero_worthy,
            "rewrite_succeeded": rewrite_succeeded,
        }
    except Exception as e:
        # legal directive (2026-08-02): previously fell back to publishing
        # the article anyway on any AI failure (rate limit, API outage,
        # network error) - meaning the raw scraped text went out unrewritten.
        # rewrite_succeeded=False here forces the caller to reject instead.
        print(f"העשרת AI נכשלה (הכתבה תידחה - אין פרסום בלי שכתוב מאומת): {e}")
        return {"rewrite_succeeded": False}


# Genuine multi-source synthesis for when cluster_candidates_by_story finds
# the same story covered by 2-3 different approved outlets in one scrape
# batch - real added value (the same reason wire-rewrite desks exist),
# not a device for disguising a single source. Every fact must still trace
# back to one of the given sources; nothing is invented to fill gaps, and
# if the sources disagree on a detail both versions are kept rather than
# one being picked arbitrarily.
AI_SYNTHESIS_SYSTEM_PROMPT = (
    "אתה עורך תוכן לאתר חדשות ישראלי. תקבל את אותו סיפור חדשותי כפי שדווח "
    "בנפרד על ידי מספר מקורות אמיתיים (מסומנים למטה). כתוב כתבה אחת "
    "מסונתזת שמשלבת את העובדות מכל המקורות יחד, בזווית ארגון ומבנה עצמאיים "
    "- לא העתקה או פרפרזה של אף אחד מהמקורות בנפרד. חוקי ברזל, ללא יוצא "
    "מן הכלל:\n"
    "- כל עובדה בתוצר חייבת להופיע בפועל באחד המקורות הנתונים. אסור "
    "להוסיף עובדה, פרט, נתון, הקשר או דעה שלא מופיעים באף אחד מהם.\n"
    "- אם מקור מסוים תורם עובדה שלא מופיעה באחרים, אפשר לציין זאת בקצרה "
    "בגוף הטקסט (למשל 'לפי דיווח נוסף...') לשקיפות כלפי הקורא.\n"
    "- אם המקורות סותרים זה את זה בפרט כלשהו, הצג את שתי הגרסאות בנפרד "
    "במקום לבחור אחת מהן באופן שרירותי.\n"
    "- ציטוטים ישירים חייבים להישאר מדויקים מילה-במילה ומיוחסים לדובר "
    "הנכון בדיוק כפי שמופיע במקור המקורי.\n"
    "- כתוב כותרת חדשה ועצמאית, שונה מהכותרת של כל אחד מהמקורות.\n"
    "- אורך יעד: כ-450 מילה לפחות אם יש בסיס עובדתי מספיק בין המקורות "
    "- אל תמלא בחזרות או ניסוחים ריקים רק כדי להגיע לאורך.\n"
    "בנוסף לכתבה עצמה, בצע: takeaways (3-4 עובדות מרכזיות), tags (3-4 "
    "מילות מפתח), verified_category (מהרשימה הסגורה: " +
    ", ".join(VALID_CATEGORIES) + "), ו-hero_worthy (true אך ורק אם זו "
    "ידיעה מבזקת אמיתית בביטחון/צבא, פשע חמור, ספורט משמעותי, סלבריטאים/"
    "תרבות ובידור, או כלכלה משמעותית (לא טיפים/מדריך כללי) - false בכל "
    "מקרה אחר).\n"
    'השב אך ורק ב-JSON תקני: {"title": "...", "content": "...", '
    '"takeaways": ["...", "..."], "tags": ["...", "..."], '
    '"verified_category": "...", "hero_worthy": false}'
)


def synthesize_from_sources_ai(members):
    """members: list of {"source_name", "title", "content"} dicts, each
    already the real full-text (not just an RSS teaser) of one outlet's
    coverage of the same story. Returns None on any failure or if the
    result reads as too close to any single input source - synthesis is
    strictly better-than-single-source or the story doesn't get this
    treatment at all, never a degraded fallback that fabricates to fill
    gaps in the sources."""
    if not GROQ_API_KEY:
        return None
    try:
        sources_block = "\n\n".join(
            f"--- מקור {i + 1}: {m['source_name']} ---\nכותרת: {m['title']}\n\n{m['content'][:4000]}"
            for i, m in enumerate(members)
        )
        payload = json.dumps({
            "model": GROQ_MODEL,
            "response_format": {"type": "json_object"},
            "temperature": 0.4,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": AI_SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": sources_block[:11000]},
            ],
        }).encode("utf-8")
        req = urllib.request.Request(
            GROQ_API_URL, data=payload,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        raw = result["choices"][0]["message"]["content"]
        parsed = json.loads(raw)

        title = re.sub(r'\s+', ' ', str(parsed.get("title") or "")).strip()
        content = re.sub(r'\s+', ' ', str(parsed.get("content") or "")).strip()
        if not title or len(content) < MIN_CONTENT_LEN:
            return None
        # must not be a near-copy of any single source it was built from -
        # the whole point of clustering is to produce something none of the
        # individual sources already are
        for m in members:
            if is_too_similar_to_source(content, m["content"][:4000]):
                return None

        takeaways = [re.sub(r'\s+', ' ', str(t)).strip() for t in (parsed.get("takeaways") or [])]
        takeaways = [t for t in takeaways if t][:4]
        tags = [re.sub(r'\s+', ' ', str(t)).strip().strip(',') for t in (parsed.get("tags") or [])]
        tags = [t for t in tags if t and ',' not in t][:4]
        verified_category = parsed.get("verified_category")
        if verified_category not in VALID_CATEGORIES:
            verified_category = None
        hero_worthy = bool(parsed.get("hero_worthy") is True)

        return {
            "title": title, "content": content, "takeaways": takeaways, "tags": tags,
            "verified_category": verified_category, "hero_worthy": hero_worthy,
        }
    except Exception as e:
        print(f"סינתזה רב-מקורית נכשלה (מדלג, יתבצע ניסיון חד-מקורי רגיל): {e}")
        return None


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

# IndexNow: a real, free protocol that Bing/Yandex/Seznam actually consume
# for near-immediate crawling (Google does NOT participate in IndexNow -
# there is no equivalent free/instant push mechanism for Google itself;
# Google's own Indexing API is restricted by its terms to JobPosting/
# BroadcastEvent content, not general news articles, so it isn't used
# here). The key below just needs to match the content of a static file
# hosted at INDEXNOW_KEY + ".txt" on the site root - build_site.py writes
# that file every build. One key, generated once, reused for every ping.
INDEXNOW_KEY = "bc07a11788f80a9c2808e9a360684a3a"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"


def ping_indexnow(slugs):
    if not slugs:
        return
    try:
        url_list = [f"{SITE_URL}/article/{slug}.html" for slug in slugs]
        payload = json.dumps({
            "host": SITE_URL.replace("https://", "").replace("http://", ""),
            "key": INDEXNOW_KEY,
            "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt",
            "urlList": url_list,
        }).encode("utf-8")
        req = urllib.request.Request(
            INDEXNOW_ENDPOINT, data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"IndexNow: {len(url_list)} כתובות נשלחו (סטטוס {resp.status})")
    except Exception as e:
        print(f"IndexNow נכשל (מדלג, לא חוסם פרסום): {e}")


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


VIDEO_ENRICH_SYSTEM_PROMPT = (
    "אתה עוזר עריכה לאתר חדשות ישראלי. תקבל כותרת גולמית ותיאור גולמי של "
    "סרטון מערוץ יוטיוב רשמי (דוברות ממשלתית/צבאית, קבוצת ספורט, וכו') - "
    "לא כתבה שכתב עיתונאי. הכותרת עשויה להיות לא מתארת (למשל תאריך גרידא), "
    "או בשפה שאינה עברית. המשימה שלך: "
    "1. headline - כותרת עברית תקנית, קצרה, אמיתית ומתארת בפועל את תוכן "
    "הסרטון, אך ורק על סמך העובדות שמופיעות בכותרת/תיאור הגולמיים - אם "
    "המקור באנגלית, תרגם ותנסח בעברית; לעולם אל תמציא פרט שלא מופיע במקור. "
    "2. synopsis - פסקה קצרה (2-4 משפטים) בעברית תקנית שמסבירה מה רואים "
    "בסרטון, מבוססת אך ורק על העובדות שבתיאור הגולמי. "
    "3. is_promotional - true אם זהו בעיקרו תוכן פרסומי/שיווקי/מיתוגי (למשל "
    "השקת מוצר, שיתוף פעולה עם מותג מסחרי, קמפיין פרסומי קליל) ולא ידיעה "
    "חדשותית אמיתית - false אחרת. "
    "4. insufficient_content - true אם התיאור הגולמי כה דל שאין ממנו מספיק "
    "מידע עובדתי אמיתי לבנות כותרת ותקציר משמעותיים (למשל רק לינקים "
    "לרשתות חברתיות, או תאריך בלבד) - false אחרת. "
    "5. hero_worthy - true אך ורק אם זו ידיעת חדשות מבזקת אמיתית באחד "
    "מהנושאים הבאים: ביטחון/צבא, פשע חמור (רצח, טרור, פיגוע), ספורט "
    "משמעותי (תוצאה/העברה/הכרזה משמעותית, לא אימון או תוכן שגרתי), "
    "סלבריטאים/תרבות ובידור, או כלכלה משמעותית. false בכל מקרה אחר. "
    'השב אך ורק ב-JSON תקני: {"headline": "...", "synopsis": "...", '
    '"is_promotional": false, "insufficient_content": false, '
    '"hero_worthy": false}'
)


def enrich_video_with_ai(title, content, source_name):
    if not GROQ_API_KEY:
        return None
    try:
        payload = json.dumps({
            "model": GROQ_MODEL,
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": VIDEO_ENRICH_SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"ערוץ מקור: {source_name}\nכותרת גולמית: {title}\n\n"
                    f"תיאור גולמי:\n{content[:2000]}"
                )},
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
        parsed = json.loads(result["choices"][0]["message"]["content"])

        if parsed.get("insufficient_content") or parsed.get("is_promotional"):
            return None
        headline = re.sub(r'\s+', ' ', str(parsed.get("headline") or "")).strip()
        synopsis = re.sub(r'\s+', ' ', str(parsed.get("synopsis") or "")).strip()
        if not headline or not synopsis:
            return None
        return {"title": headline, "content": synopsis, "hero_worthy": bool(parsed.get("hero_worthy") is True)}
    except Exception as e:
        # fails CLOSED (unlike enrich_article_with_ai) - a video whose raw
        # title/description we can't verify or rewrite must not publish
        # as-is per the owner's explicit rule that every primary-source item
        # goes through the bot's rewrite, never a raw embed
        print(f"נפסל (וידאו - העשרת AI נכשלה, לא מפרסמים גולמי): {e}")
        return None


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


def save_article(title, link, content, image_url, source_name, category, video_id="", recent_titles=None, tags_index=None, image_hashes=None, published_slugs=None, author=""):
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
        # YouTube's own URL scheme distinguishes a Short from a regular
        # upload (/shorts/ID vs /watch?v=ID) - real, reliable signal (not a
        # guess) for vertical/portrait-format social-style video content,
        # shown in its own compact section rather than mixed into the
        # regular video listing (owner directive: "חדשות עומדות")
        is_short = "/shorts/" in link
        if not image_url:
            image_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        image_chunk = _fetch_image_chunk(image_url)
        if is_low_quality_image(image_chunk):
            print(f"נפסל (וידאו - תמונה לא נטענת/איכות נמוכה מדי): {title}")
            return
        # duplicate-thumbnail hashing is skipped here (unlike regular
        # articles) - many auto-generated YouTube thumbnails from the same
        # channel legitimately look similar (same on-air graphics template),
        # which would false-positive as "duplicate" far more than it would
        # for real news photos
        if is_blurry_image(_fetch_full_image(image_url)):
            print(f"נפסל (וידאו - תמונה מטושטשת): {title}")
            return
        content = strip_link_lines(strip_known_junk_phrases(content))
        if len(content) < MIN_VIDEO_CONTENT_LEN:
            print(f"נפסל (וידאו - אין תיאור אמיתי, רק קישורים/בוילרפלייט): {title}")
            return

        # A video's raw title/description is whatever the uploader typed -
        # not a journalist's headline - and is frequently non-Hebrew, a bare
        # date, or otherwise not something the site can publish as-is. Every
        # primary-source video is rewritten through the same bot editing
        # pass a regular article gets (real Hebrew headline, real synopsis),
        # never just an embed with the raw scraped title (owner directive).
        enrichment = enrich_video_with_ai(title, content, source_name)
        if not enrichment:
            print(f"נפסל (וידאו - נכשל בשכתוב/לא חדשותי מספיק): {title}")
            return
        final_title = enrichment["title"]
        final_content = enrichment["content"]
        hero_worthy = enrichment.get("hero_worthy", False)

        # Checked for every video regardless of category - not just TV/live
        # broadcasts - a station bug/logo baked into the thumbnail is exactly
        # as unwanted on a regular news clip as it is on a live broadcast one.
        has_watermark = detect_tv_watermark(image_url)
        time.sleep(1)  # brief pacing between Groq calls, same margin as the text enrichment call
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _write_article_file(filename, final_title, date_str, source_name, image_url, link, video_category,
                             final_content, video_id, has_watermark=has_watermark, hero_worthy=hero_worthy,
                             is_short=is_short)
        if recent_titles is not None:
            recent_titles.append(normalize_title_words(final_title))
        video_slug = slugify(final_title, sanitize_filename(final_title))
        if published_slugs is not None:
            published_slugs.append(video_slug)
        notify_telegram(final_title, source_name, video_category, video_slug)
        return

    # Filter 1: a real, reachable, non-trivial image is mandatory - try the
    # RSS image first, then the article page's og:image. Previously this
    # only checked that a URL *string* existed, never that it actually
    # resolved to real image bytes - a dead link or a tracking-pixel-sized
    # stub would still pass and publish. Now the image is genuinely
    # fetched once and verified before the article is allowed through.
    if not image_url:
        image_url = fetch_og_image(link)
    if not image_url:
        print(f"נפסל (אין תמונה איכותית): {title}")
        return
    image_chunk = _fetch_image_chunk(image_url)
    if is_low_quality_image(image_chunk):
        print(f"נפסל (תמונה לא נטענת/איכות נמוכה מדי): {title}")
        return

    # A banner/strip-shaped image (not a normal photo) doesn't get rejected
    # outright - it's downgraded to the compact "quick" card style instead
    # of the large hero/bento treatment, similar to how a short news-in-brief
    # item is handled
    quick_image = is_bad_image_aspect(image_chunk)

    # Real pixel-level quality checks (blur, duplicate, on-image watermark) -
    # only run on candidates that already cleared the cheap chunk-based gates
    # above, since each of these needs the full image and/or a Groq call.
    full_image_bytes = _fetch_full_image(image_url)
    if is_blurry_image(full_image_bytes):
        print(f"נפסל (תמונה מטושטשת): {title}")
        return
    new_hash = image_ahash(full_image_bytes)
    if image_hashes is not None:
        dup_title = find_duplicate_image(new_hash, image_hashes)
        if dup_title:
            print(f"נפסל (תמונה כפולה - כבר שימשה בכתבה '{dup_title}'): {title}")
            return
    # station bug/logo baked into a regular news photo, not just video
    # thumbnails - same real vision check, same placeholder-swap-not-reject
    # treatment build_site.py already applies via the has_watermark flag
    has_watermark = detect_tv_watermark(image_url)
    time.sleep(1)  # same Groq rate-limit pacing margin used elsewhere
    if image_hashes is not None and new_hash:
        image_hashes[new_hash] = {"title": title, "ts": time.time()}

    # Filter 2: need the full article body, not just a short RSS teaser.
    # Always attempt the real full-text fetch first (an RSS teaser is
    # rarely as complete as the actual article, even when it happens to
    # clear MIN_CONTENT_LEN on its own). Three outcomes, not two: a real
    # full-length fetch is a normal article; real prose that's genuinely
    # shorter than that (early/developing coverage) is published honestly
    # as a bulletin instead of being discarded; only actual junk/nothing
    # gets rejected.
    is_bulletin = False
    full_text = fetch_full_article_text(link)
    if full_text and len(full_text) >= MIN_CONTENT_LEN:
        content = full_text
    elif full_text and len(full_text) >= MIN_BULLETIN_LEN:
        content = full_text
        is_bulletin = True
    elif len(content) < MIN_CONTENT_LEN:
        print(f"נפסל (לא נמצאה כתבה מלאה, רק תקציר קצר מדי): {title}")
        return

    content = strip_link_lines(strip_known_junk_phrases(content))

    if is_gibberish_or_broken(content):
        print(f"נפסל (תוכן שבור/גיבריש/קישורים שיוריים): {title}")
        return

    # re-check after pulling the full article body - sponsorship disclosure
    # is often buried lower in the text, not in the short RSS teaser
    if is_sponsored_content(title, link, content):
        print(f"נפסל (תוכן ממומן חשוד - זוהה בגוף הכתבה): {title}")
        return

    enrichment = enrich_article_with_ai(title, content)
    if GROQ_API_KEY:
        time.sleep(2)  # free-tier rate-limit safety margin between Groq calls
    # legal directive (2026-08-02): a verified original rewrite is mandatory
    # for every article, not best-effort polish - publishing the raw scraped
    # text (what used to happen here on any AI failure) is exactly the fact
    # pattern found to be copyright infringement in Israeli case law. No
    # genuine rewrite means no publish, full stop - this will publish fewer
    # articles whenever Groq is down/rate-limited, and that is the correct
    # tradeoff, not a regression to work around.
    if not enrichment.get("rewrite_succeeded"):
        print(f"נפסל (לא הופק שכתוב מקורי מאומת - אין פרסום תוכן שנשאב כלשונו): {title}")
        return
    content = enrichment.get("content", content)
    takeaways = enrichment.get("takeaways", [])
    tags = enrichment.get("tags", [])
    # a source's mapped category is a default, not a guarantee - e.g. a
    # Haredi-affiliated source occasionally publishing a general public-
    # health item is really a בריאות story, not a חרדים one. Only overridden
    # when the AI is confident enough to name one of the site's real
    # categories; otherwise the source-based default stands unchanged.
    category = enrichment.get("verified_category") or category
    # owner directive: the homepage's most prominent slots (hero/bento) are
    # reserved for real breaking news in a fixed set of topics - security/
    # military, serious crime, major sports, celebrity/entertainment, or
    # significant economic news - never decided by category label alone.
    # Defaults to False (not eligible) when enrichment isn't available,
    # same conservative default as any other AI-only signal on this path.
    hero_worthy = enrichment.get("hero_worthy", False)

    if tags_index is not None:
        content = auto_link_internal_tags(content, tags_index)

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_article_file(filename, title, date_str, source_name, image_url, link, category, content,
                         takeaways=takeaways, tags=tags, quick_image=quick_image, hero_worthy=hero_worthy,
                         has_watermark=has_watermark, is_bulletin=is_bulletin, author=author)
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
    if published_slugs is not None:
        published_slugs.append(slug_guess)
    notify_telegram(title, source_name, category, slug_guess)


def save_synthesized_article(cluster, recent_titles=None, tags_index=None, image_hashes=None, published_slugs=None):
    """cluster: 2-3 candidates (from cluster_candidates_by_story) that are
    the same story from different approved sources. Runs real multi-source
    synthesis instead of publishing only the first candidate and silently
    discarding the rest as duplicates. Falls back to the normal single-
    source pipeline (never just drops the story) if synthesis isn't
    possible or doesn't clear its quality bar."""
    primary = cluster[0]

    def fall_back_to_single_source():
        save_article(primary["title"], primary["link"], primary["content"], primary["image_url"],
                     primary["source_name"], primary["category"], recent_titles=recent_titles,
                     tags_index=tags_index, image_hashes=image_hashes, published_slugs=published_slugs,
                     author=primary.get("author", ""))

    if recent_titles is not None and is_duplicate_of_recent(primary["title"], recent_titles):
        print(f"נפסל (סינתזה - הסיפור כבר פורסם ממקור קודם): {primary['title']}")
        return
    if is_sponsored_content(primary["title"], primary["link"], primary["content"]):
        print(f"נפסל (סינתזה - תוכן ממומן חשוד): {primary['title']}")
        return

    # need each member's real full-text, not just an RSS teaser - same
    # reasoning as Filter 2 in save_article
    members = []
    for cand in cluster:
        full_text = fetch_full_article_text(cand["link"])
        text = full_text if full_text else cand["content"]
        text = strip_link_lines(strip_known_junk_phrases(text))
        if len(text) >= MIN_CONTENT_LEN // 2:
            members.append({"source_name": cand["source_name"], "title": cand["title"], "content": text})

    if len(members) < 2:
        # lost enough members along the way that this isn't really
        # multi-source anymore - don't lose the story, just publish it the
        # normal single-source way
        fall_back_to_single_source()
        return

    synthesis = synthesize_from_sources_ai(members)
    if not synthesis:
        fall_back_to_single_source()
        return
    if is_gibberish_or_broken(synthesis["content"]):
        print(f"נפסל (סינתזה - תוכן שבור/גיבריש): {synthesis['title']}")
        return

    final_title = synthesis["title"]
    filename = f"{sanitize_filename(final_title)}.md"
    exists = any(os.path.exists(os.path.join(d, filename)) for d in [LIVE_DIR, PENDING_DIR, ARCHIVE_DIR])
    if exists:
        return

    image_url = primary["image_url"] or fetch_og_image(primary["link"])
    if not image_url:
        print(f"נפסל (סינתזה - אין תמונה איכותית): {final_title}")
        return
    image_chunk = _fetch_image_chunk(image_url)
    if is_low_quality_image(image_chunk):
        print(f"נפסל (סינתזה - תמונה לא נטענת/איכות נמוכה מדי): {final_title}")
        return
    quick_image = is_bad_image_aspect(image_chunk)
    full_image_bytes = _fetch_full_image(image_url)
    if is_blurry_image(full_image_bytes):
        print(f"נפסל (סינתזה - תמונה מטושטשת): {final_title}")
        return
    new_hash = image_ahash(full_image_bytes)
    if image_hashes is not None:
        dup_title = find_duplicate_image(new_hash, image_hashes)
        if dup_title:
            print(f"נפסל (סינתזה - תמונה כפולה, כבר שימשה ב-'{dup_title}'): {final_title}")
            return
    has_watermark = detect_tv_watermark(image_url)
    if image_hashes is not None and new_hash:
        image_hashes[new_hash] = {"title": final_title, "ts": time.time()}

    content = synthesis["content"]
    if tags_index is not None:
        content = auto_link_internal_tags(content, tags_index)

    source_display = " + ".join(m["source_name"] for m in members)
    category = synthesis["verified_category"] or primary["category"]
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_article_file(filename, final_title, date_str, source_display, image_url, primary["link"],
                         category, content, takeaways=synthesis["takeaways"], tags=synthesis["tags"],
                         quick_image=quick_image, hero_worthy=synthesis["hero_worthy"],
                         has_watermark=has_watermark)

    if recent_titles is not None:
        # register every member's ORIGINAL title, not just the new
        # synthesized headline - future scrape batches will see the same
        # outlets' own headlines again, not this one
        for m in cluster:
            recent_titles.append(normalize_title_words(m["title"]))
    slug_guess = slugify(final_title, sanitize_filename(final_title))
    if tags_index is not None and synthesis["tags"]:
        for tag in synthesis["tags"]:
            tags_index[tag] = {"slug": slug_guess, "title": final_title}
    if published_slugs is not None:
        published_slugs.append(slug_guess)
    notify_telegram(final_title, source_display, category, slug_guess)


def _write_article_file(filename, title, date_str, source_name, image_url, link, category, content,
                         video_id="", takeaways=None, tags=None, quick_image=False, has_watermark=False,
                         hero_worthy=False, is_short=False, is_bulletin=False, author=""):
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
    hero_worthy_line = '\nhero_worthy: "1"' if hero_worthy else ""
    is_short_line = '\nis_short: "1"' if is_short else ""
    is_bulletin_line = '\nis_bulletin: "1"' if is_bulletin else ""
    # Individual byline credit - Israeli moral rights (זכות מוסרית) attach to
    # the actual creator, not the publisher, so this is separate from and in
    # addition to the "source" outlet name above, not a replacement for it.
    author_line = f'\nauthor: "{author.replace(chr(34), chr(39))}"' if author else ""

    md_content = f"""---
title: >-
  {title}
date: "{date_str}"
source: "{source_name}"
image: "{image_url}"
link: "{link}"
category: "{category}"{video_line}{takeaways_line}{tags_line}{quick_image_line}{has_watermark_line}{hero_worthy_line}{is_short_line}{is_bulletin_line}{author_line}
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
    image_hashes = load_recent_image_hashes()
    trending_keywords = fetch_trending_keywords()
    print(f"נטענו {len(recent_titles)} כותרות מ-{DUPLICATE_LOOKBACK_HOURS} השעות האחרונות לבדיקת כפילויות")
    print(f"נטען אינדקס תגיות עם {len(tags_index)} תגיות לקישור פנימי אוטומטי")
    print(f"נטען אינדקס תמונות עם {len(image_hashes)} טביעות אצבע מ-{IMAGE_DEDUPE_LOOKBACK_HOURS} השעות האחרונות")
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
            # Individual byline credit, when the feed actually provides one -
            # Israeli moral rights (זכות מוסרית) attach to the actual creator,
            # not the publisher, so "מקור: גלובס" alone doesn't satisfy
            # attribution when the source names an author. Confirmed via a
            # real feed check: ynet/Walla's RSS never include this field
            # (author stays blank for them - can't credit what isn't given),
            # Globes' does (real names came back, e.g. "חזי שטרנליכט").
            author = entry.get('author', '').strip()[:100]
            candidates.append({
                "title": title, "link": link, "content": content, "image_url": image_url,
                "source_name": source_name, "category": category, "video_id": "", "author": author,
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
                "source_name": source_name, "category": category, "video_id": video_id, "author": "",
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

    # Group same-story candidates from different sources BEFORE saving -
    # previously the second/third outlet's coverage of a story already
    # published this run just silently hit Filter 0 ("already published")
    # and was discarded. Clustering first means that coverage gets used for
    # real multi-source synthesis instead of thrown away.
    clusters = cluster_candidates_by_story(candidates)
    multi_source_count = sum(1 for group in clusters if len(group) > 1)
    if multi_source_count:
        print(f"{multi_source_count} סיפורים זוהו במספר מקורות - יעברו סינתזה רב-מקורית")

    published_slugs = []
    for group in clusters:
        if len(group) > 1:
            save_synthesized_article(group, recent_titles=recent_titles, tags_index=tags_index,
                                      image_hashes=image_hashes, published_slugs=published_slugs)
        else:
            c = group[0]
            save_article(c["title"], c["link"], c["content"], c["image_url"], c["source_name"], c["category"],
                         video_id=c["video_id"], recent_titles=recent_titles, tags_index=tags_index,
                         image_hashes=image_hashes, published_slugs=published_slugs, author=c.get("author", ""))

    save_tags_index(tags_index)
    save_image_hashes(image_hashes)
    ping_indexnow(published_slugs)


if __name__ == "__main__":
    fetch_news()
