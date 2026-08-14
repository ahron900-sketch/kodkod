"""The masthead's editorial identity, in one place.

Voice rules were scattered across prompt strings inside idf_scraper.py,
which meant the paper's character was defined by whichever prompt was
edited last. This centralises it so the bot writes consistently, and so
the rules can be changed once rather than in four places.

Written to match what this specific newsroom is: an automated desk that
rewrites official-source material into Hebrew. That constrains the voice
in ways a human newsroom's would not - it cannot claim to have been
somewhere, interviewed anyone, or verified anything independently, and
the voice guide has to say so out loud, because a confident tone plus no
first-hand reporting is exactly how automated news starts overclaiming.
"""

SITE_NAME = "קודקוד חדשות"
TAGLINE = "חדשות ועדכונים ממקורות רשמיים"

# Section desks, used for the byline line on articles.
DESKS = {
    "חדשות": "דסק חדשות",
    "כלכלה": "דסק כלכלה",
    "ספורט": "דסק ספורט",
    "טכנולוגיה": "דסק טכנולוגיה",
    "בריאות": "דסק בריאות",
    "תרבות ובידור": "דסק תרבות",
    "רכב": "דסק רכב",
    "חרדים": "דסק חברה",
    "בישול ומתכונים": "דסק אוכל",
}


def byline(category):
    desk = DESKS.get(category)
    return f"מערכת {SITE_NAME.split()[0]} | {desk}" if desk else f"מערכת {SITE_NAME.split()[0]}"


# --- editorial voice -------------------------------------------------------

# Hebrew news register: plain, current, neither tabloid nor bureaucratic.
# Phrased as instructions to the writing model.
VOICE_RULES = [
    "כתוב בעברית עיתונאית עכשווית ותקנית - לא מליצית, לא סלנג, ולא תרגומית.",
    "משפטים קצרים. רעיון אחד למשפט, פסקאות של 2-3 משפטים.",
    "פתח בעובדה המרכזית, לא ברקע ולא בהקדמה כללית. הקורא צריך לדעת מה קרה כבר במשפט הראשון.",
    "גוף שלישי. אין 'אנחנו', אין פנייה ישירה לקורא, אין שאלות רטוריות.",
    "מספרים, תאריכים ושמות - במדויק כפי שנמסרו. אל תעגל ואל תשנה סדר גודל.",
    "אל תכתוב הערכות, ניתוחים או פרשנות שלא הופיעו במקור.",
    "אל תשתמש בתארים דרמטיים ('מזעזע', 'חסר תקדים') אלא אם המקור עצמו השתמש בהם.",
]

# Things this newsroom must never imply, because they are not true of it.
INTEGRITY_RULES = [
    "אל תכתוב שהמערכת נכחה במקום, ראתה, שמעה או ראיינה מישהו.",
    "אל תייחס לעצמך אימות עצמאי של עובדות - הן מבוססות על מה שנמסר במקור.",
    "אל תציג את הכתבה כסקופ, כבלעדי או כחשיפה של המערכת.",
    "אל תמציא ציטוט, ואל תשנה ציטוט קיים. ציטוט מיוחס בדיוק לדובר שאמר אותו.",
]


def voice_prompt():
    """The block appended to writing prompts. One source of truth."""
    lines = ["סגנון הכתיבה של המערכת:"]
    lines += [f"- {rule}" for rule in VOICE_RULES]
    lines.append("כללי יושרה עיתונאית (מחייבים):")
    lines += [f"- {rule}" for rule in INTEGRITY_RULES]
    return "\n".join(lines)


# --- headline discipline ---------------------------------------------------

# Patterns that make a headline read as clickbait. Used to score, not to
# rewrite - a headline that trips these is a signal the story was written
# to bait rather than inform.
CLICKBAIT_MARKERS = [
    "לא תאמינו", "תתפלאו", "הסוד ש", "מה שקרה אחר כך", "כולם מדברים על",
    "אתם חייבים", "זה מה שקורה כש", "הסיבה תפתיע",
]


def headline_warnings(title):
    """Returns the reasons a headline reads as weak, or an empty list."""
    problems = []
    text = title or ""
    for marker in CLICKBAIT_MARKERS:
        if marker in text:
            problems.append(f"ניסוח קליקבייט: '{marker}'")
    if len(text) > 95:
        problems.append(f"ארוכה מדי ({len(text)} תווים) - תיחתך בתוצאות החיפוש")
    if len(text) < 20:
        problems.append(f"קצרה מדי ({len(text)} תווים) - לא מספרת מה קרה")
    if text.count("?") > 1 or text.endswith("???"):
        problems.append("ריבוי סימני שאלה")
    if text.count("!") >= 1:
        problems.append("סימן קריאה בכותרת חדשותית")
    return problems
