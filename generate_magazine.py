import glob
import json
import os
import re
from datetime import datetime, timedelta

CONTENT_DIR = "content/news"
MAGAZINE_DIR = "content/magazine"
RECIPE_CATEGORY = "בישול ומתכונים"
TV_CATEGORY = "טלוויזיה ושידורים חיים"
MAX_PER_CATEGORY = 5
LOOKBACK_DAYS = 7


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


def load_recent_articles():
    cutoff = datetime.now() - timedelta(days=LOOKBACK_DAYS)
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
        date_str = data.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        if dt < cutoff:
            continue
        if not data.get("image"):
            continue  # magazine is visual - text-only stubs don't belong
        articles.append({
            "title": data.get("title", ""),
            "date": date_str,
            "dt": dt,
            "source": data.get("source", ""),
            "image": data.get("image", ""),
            "link": data.get("link", ""),
            "category": data.get("category", "חדשות"),
            "video_id": data.get("video_id", ""),
            "body": body,
        })
    articles.sort(key=lambda a: a["dt"], reverse=True)
    return articles


def build_issue(articles):
    by_category = {}
    for a in articles:
        if a["category"] == TV_CATEGORY:
            continue  # live broadcasts don't belong in a written magazine
        by_category.setdefault(a["category"], []).append(a)

    sections = []
    for category, items in by_category.items():
        picked = items[:MAX_PER_CATEGORY]
        sections.append({
            "category": category,
            "articles": [
                {
                    "title": a["title"],
                    "source": a["source"],
                    "image": a["image"],
                    "link": a["link"],
                    "date": a["date"],
                    "dek": first_sentence(a["body"]),
                }
                for a in picked
            ],
        })
    # order: news first, then everything else alphabetically-ish stable by volume
    sections.sort(key=lambda s: (-len(s["articles"])))

    cover = None
    for a in articles:
        if a["category"] not in (TV_CATEGORY, RECIPE_CATEGORY) and a["image"]:
            cover = a
            break
    if not cover and articles:
        cover = articles[0]

    return sections, cover


def first_sentence(body_text, max_len=160):
    for line in body_text.split("\n"):
        line = line.strip()
        if len(line) < 15:
            continue
        if len(line) > max_len:
            line = line[:max_len].rsplit(" ", 1)[0] + "…"
        return line
    return ""


def main():
    os.makedirs(MAGAZINE_DIR, exist_ok=True)
    week_id = datetime.now().strftime("%Y-W%V")
    out_path = os.path.join(MAGAZINE_DIR, f"{week_id}.json")
    if os.path.exists(out_path):
        print(f"גיליון {week_id} כבר קיים, מדלג.")
        return

    articles = load_recent_articles()
    if len(articles) < 5:
        print(f"לא מספיק כתבות ({len(articles)}) ליצירת גיליון השבוע.")
        return

    sections, cover = build_issue(articles)
    issue = {
        "week_id": week_id,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cover": {
            "title": cover["title"],
            "image": cover["image"],
            "category": cover["category"],
            "source": cover["source"],
        } if cover else None,
        "sections": sections,
        "article_count": sum(len(s["articles"]) for s in sections),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(issue, f, ensure_ascii=False, indent=2)
    print(f"נוצר גיליון {week_id} עם {issue['article_count']} כתבות ב-{len(sections)} מדורים.")


if __name__ == "__main__":
    main()
