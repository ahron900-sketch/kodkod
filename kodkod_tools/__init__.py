"""kodkod_tools - the editorial toolkit behind the bot.

Separate, independently testable modules rather than more logic piled into
idf_scraper.py:

    memory   learns from every rejected item so the same doomed candidate
             isn't fetched, rewritten and rejected again every 15 minutes
    images   quality scoring and enhancement for images the site is
             actually entitled to use
    style    a style profile derived from the site's own published corpus,
             so new articles read like the ones that worked
    seo      structured-data and discoverability helpers

Design rules for everything in here:
  * No module may make an article publishable that the safety gates in
    idf_scraper.py would reject. These tools raise quality; they never
    lower a bar.
  * Every module fails open. A tool that errors must never block the bot.
  * Nothing here removes, obscures or defeats a rights marking on someone
    else's work. Watermark handling is detection-only, and detection
    results are used to REJECT an image, never to clean it for reuse.
"""

__all__ = ["memory", "images", "style", "seo"]
