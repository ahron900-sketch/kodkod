"""Discoverability helpers - classic search and AI answer engines.

Built from an audit of the live site rather than from a generic checklist.
What the audit actually found:

  article pages   already strong - NewsArticle schema with headline,
                  datePublished, dateModified, author, publisher, image,
                  description, articleSection, inLanguage and keywords,
                  plus BreadcrumbList, Organization and WebPage, and one
                  correct H1. Left alone.
  homepage        no <h1> at all. Every heading was an <h2>, because the
                  only H1 lived inside a hero slide - so when the hero had
                  nothing fresh to show, the front page shipped with no
                  top-level heading.
  whole site      no hreflang, and no speakable annotations.

Everything here is a pure function returning markup or a dict. No network
calls, no state.
"""

# --- language targeting ----------------------------------------------------

def hreflang_tags(canonical_url):
    """Israeli Hebrew must be declared he-IL, not bare he: the country code
    is what google.co.il geo-targets on. The site is Hebrew-only, so the
    same URL is also the x-default."""
    if not canonical_url:
        return ""
    return (
        f'<link rel="alternate" hreflang="he-IL" href="{canonical_url}">\n'
        f'<link rel="alternate" hreflang="x-default" href="{canonical_url}">'
    )


# --- AI answer-engine extraction ------------------------------------------

def speakable_spec(selectors=None):
    """Marks the parts of a page an assistant should read aloud or quote.

    Pointed at the headline, the standfirst and the AI takeaways box, since
    those are the passages written to stand alone - which is exactly what a
    voice answer or a cited snippet needs."""
    return {
        "@type": "SpeakableSpecification",
        "cssSelector": selectors or ["h1", ".article-dek", ".ai-summary"],
    }


def with_speakable(article_schema, selectors=None):
    """Return a copy of a NewsArticle schema with speakable added."""
    if not isinstance(article_schema, dict):
        return article_schema
    enriched = dict(article_schema)
    enriched["speakable"] = speakable_spec(selectors)
    return enriched


def with_reading_signals(article_schema, body_text=""):
    """Add the two fields the audit found missing from an otherwise
    complete NewsArticle: wordCount, and an explicit free-to-read flag.

    isAccessibleForFree matters more than it looks for a news site - it is
    how Google is told there is no paywall, which is a precondition for
    some news surfaces."""
    if not isinstance(article_schema, dict):
        return article_schema
    enriched = dict(article_schema)
    enriched["isAccessibleForFree"] = True
    words = len((body_text or "").split())
    if words:
        enriched["wordCount"] = words
    return enriched


# --- homepage structure ----------------------------------------------------

def homepage_h1(site_name="קודקוד חדשות", tagline="חדשות ועדכונים ממקורות רשמיים"):
    """A homepage H1 that exists unconditionally.

    Visually hidden rather than displayed: the page's visual hierarchy
    already starts with the hero, and adding a second large heading above
    it would look wrong. Hidden with a clip rect, NOT display:none - screen
    readers skip display:none, and a heading no assistive tech can reach is
    not a heading. This is the standard visually-hidden pattern."""
    return f'<h1 class="visually-hidden">{site_name} - {tagline}</h1>'
