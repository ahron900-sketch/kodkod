"""Daily Google Search Console health check.

Runs read-only checks against the real Search Console API (verified against
Google's own documentation - no fabricated endpoints):
  - webmasters v3 (www.googleapis.com/webmasters/v3): searchAnalytics.query
    for per-page performance, sitemaps.submit to nudge a recrawl.
  - searchconsole v1 (searchconsole.googleapis.com/v1): urlInspection.index.inspect
    for per-URL indexing status.

What this deliberately does NOT do, and why:
  - There is no Google API to "force reindex" an arbitrary content URL.
    The Indexing API (indexing.googleapis.com) is scoped by Google's own
    terms to JobPosting/BroadcastEvent structured data only - using it for
    regular news articles violates its terms of use, not a shortcut.
  - It does not auto-rewrite article text to "trick" indexing. A page not
    getting indexed is a real quality/duplication/thin-content signal, not
    something to paper over - the actual fix is the content-length and
    dedup work already shipped elsewhere in this repo.
The realistic, legitimate lever this script pulls: flag what's stuck so a
human can look at it, and resubmit the sitemap (a real, supported action)
so Google's crawler has a fresh nudge to work with.

Setup (owner, one-time):
  1. console.cloud.google.com -> new project -> enable "Search Console API"
  2. Create a service account, download its JSON key
  3. In Search Console (search.google.com/search-console) -> Settings ->
     Users and permissions -> add the service account's email as a user
     (Full or Restricted is enough for these read + sitemap-submit calls)
  4. Store the full JSON key content as a repo secret named
     GSC_SERVICE_ACCOUNT_JSON, and set GSC_SITE_URL (e.g.
     "sc-domain:kodkodnews.co.il" for a domain property, or the exact
     "https://kodkodnews.co.il/" URL-prefix property, matching whichever
     property type actually exists in Search Console)
Until those exist, this script exits immediately without error - same
fail-open pattern as every other optional integration in this repo.
"""
import glob
import json
import os
import re
from datetime import datetime, timedelta

GSC_SERVICE_ACCOUNT_JSON = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "")
GSC_SITE_URL = os.environ.get("GSC_SITE_URL", "")
SITE_URL = "https://kodkodnews.co.il"
REPORT_PATH = "data/gsc_report.json"
STUCK_AFTER_HOURS = 48


def load_recent_article_urls(days=3):
    """Slug + publish date for articles saved in the last N days, read
    straight from the frontmatter already on disk - no need to hit the
    live site or guess, this file is the source of truth build_site.py
    itself reads from."""
    cutoff = datetime.now() - timedelta(days=days)
    urls = []
    for path in glob.glob("content/news/*.md"):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        m_date = re.search(r'^date:\s*"([^"]+)"', text, re.M)
        if not m_date:
            continue
        try:
            dt = datetime.strptime(m_date.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if dt < cutoff:
            continue
        slug = os.path.splitext(os.path.basename(path))[0]
        urls.append((f"{SITE_URL}/article/{slug}.html", dt))
    return urls


def main():
    if not GSC_SERVICE_ACCOUNT_JSON or not GSC_SITE_URL:
        print("GSC_SERVICE_ACCOUNT_JSON/GSC_SITE_URL לא הוגדרו - מדלג (השבתה מכוונת עד שיוגדרו).")
        return

    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_info = json.loads(GSC_SERVICE_ACCOUNT_JSON)
    scopes = ["https://www.googleapis.com/auth/webmasters"]
    credentials = service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)

    webmasters = build("webmasters", "v3", credentials=credentials)
    search_console = build("searchconsole", "v1", credentials=credentials)

    # 1. Per-page performance over the last 7 full days - flags pages with
    # real impressions but a suspiciously low click-through rate
    today = datetime.now().date()
    start = (today - timedelta(days=8)).isoformat()
    end = (today - timedelta(days=1)).isoformat()
    try:
        analytics = webmasters.searchAnalytics().query(
            siteUrl=GSC_SITE_URL,
            body={
                "startDate": start,
                "endDate": end,
                "dimensions": ["page"],
                "rowLimit": 500,
            },
        ).execute()
    except Exception as e:
        print(f"שאילתת searchAnalytics נכשלה: {e}")
        analytics = {}

    low_ctr_pages = []
    for row in analytics.get("rows", []):
        impressions = row.get("impressions", 0)
        clicks = row.get("clicks", 0)
        if impressions >= 20 and clicks == 0:
            low_ctr_pages.append({"url": row["keys"][0], "impressions": impressions})

    # 2. Indexing status for recently-published articles, via the real URL
    # Inspection API - flags anything still not indexed after the cutoff
    recent = load_recent_article_urls(days=3)
    stuck = []
    now = datetime.now()
    for url, published_at in recent:
        age_hours = (now - published_at).total_seconds() / 3600
        if age_hours < STUCK_AFTER_HOURS:
            continue
        try:
            result = search_console.urlInspection().index().inspect(
                body={"inspectionUrl": url, "siteUrl": GSC_SITE_URL}
            ).execute()
            coverage = result.get("inspectionResult", {}).get("indexStatusResult", {}).get("coverageState", "")
        except Exception as e:
            coverage = f"שגיאת בדיקה: {e}"
        if "Indexed" not in coverage and "indexed" not in coverage.lower():
            stuck.append({"url": url, "age_hours": round(age_hours), "coverage": coverage})

    # 3. A real, supported nudge - resubmit the sitemap. Does not force
    # reindexing of specific URLs, just tells Google there's fresh content
    # worth another crawl pass.
    try:
        webmasters.sitemaps().submit(siteUrl=GSC_SITE_URL, feedpath=f"{SITE_URL}/sitemap.xml").execute()
        sitemap_resubmitted = True
    except Exception as e:
        print(f"הגשת sitemap נכשלה: {e}")
        sitemap_resubmitted = False

    report = {
        "generated_at": now.isoformat(),
        "low_ctr_pages": low_ctr_pages[:50],
        "stuck_not_indexed": stuck,
        "sitemap_resubmitted": sitemap_resubmitted,
    }
    os.makedirs("data", exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"נמצאו {len(low_ctr_pages)} עמודים עם הופעות ללא קליקים, {len(stuck)} כתבות תקועות מחוץ לאינדוקס.")


if __name__ == "__main__":
    main()
