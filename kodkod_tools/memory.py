"""Failure memory: don't make the same mistake twice.

The bot runs every 15 minutes over feeds that change slowly, so the same
candidate is seen again and again. Before this module, a story that failed
was re-fetched, re-sent to the AI and re-rejected on every single run -
burning the AI quota that working stories need, and guaranteeing the
failure repeated forever.

This records what failed and why, and lets the bot skip candidates whose
outcome is already known. Two distinct kinds of knowledge, deliberately
kept apart because they age differently:

  permanent  the item itself can never work - it is structurally too thin,
             or its page yields no text. Re-trying is pure waste.
  transient  the failure was environmental (AI unreachable, rate limited).
             The item may be perfectly fine; retry it later.

Storage is a plain JSON file in data/, committed by the bot workflow like
the other state files, so the memory survives across runs and machines.
"""

import json
import os
import time

MEMORY_PATH = os.path.join("data", "failure_memory.json")

# A permanently-failed item is remembered for this long. Not forever: a
# source can rewrite its page template, and a story too thin today can be
# expanded tomorrow. Long enough to stop the churn, short enough that the
# bot re-checks eventually.
PERMANENT_TTL_SECONDS = 14 * 24 * 3600
# Environmental failures clear fast - the AI being down for one run says
# nothing about the item.
TRANSIENT_TTL_SECONDS = 6 * 3600
# After this many transient failures the item is treated as permanent:
# something about it, not the environment, is the problem.
TRANSIENT_ESCALATION_COUNT = 5

# Which outcomes mean "this item is the problem" vs "the world was the
# problem". Anything unknown is treated as transient, because wrongly
# forgetting is cheaper than wrongly banning a good story forever.
PERMANENT_OUTCOMES = {
    "rejected_under_min_words",
    "text_rejected_no_source_text",
    "rejected_gibberish",
    "rejected_sponsored",
    "rejected_no_image",
}
TRANSIENT_OUTCOMES = {
    "text_rejected_no_verified_rewrite",
    "video_rejected_enrich_failed_or_not_newsworthy",
    "ai_unavailable",
}


def _now():
    return time.time()


def load(path=MEMORY_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("items"), dict):
            return data
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"זיכרון כשלונות לא נקרא (מתחיל מחדש): {e}")
    return {"items": {}}


def save(mem, path=MEMORY_PATH):
    try:
        prune(mem)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"שמירת זיכרון כשלונות נכשלה (לא חוסם): {e}")


def _key(link):
    return (link or "").strip()


def record_failure(mem, link, outcome, title=""):
    """Remember that this item failed, and how."""
    key = _key(link)
    if not key:
        return
    entry = mem["items"].get(key) or {"count": 0, "title": title[:120]}
    entry["count"] = entry.get("count", 0) + 1
    entry["outcome"] = outcome
    entry["ts"] = _now()
    kind = "permanent" if outcome in PERMANENT_OUTCOMES else "transient"
    # repeated environmental failures on the same item stop being credible
    # as environmental - treat the item itself as the problem
    if kind == "transient" and entry["count"] >= TRANSIENT_ESCALATION_COUNT:
        kind = "permanent"
    entry["kind"] = kind
    mem["items"][key] = entry


def record_success(mem, link):
    """Clear any memory of an item that has now published, so a previously
    failing story that later succeeded doesn't stay tarred."""
    mem["items"].pop(_key(link), None)


def should_skip(mem, link):
    """True if this candidate is known to be a waste of a run."""
    entry = mem["items"].get(_key(link))
    if not entry:
        return False
    age = _now() - entry.get("ts", 0)
    ttl = PERMANENT_TTL_SECONDS if entry.get("kind") == "permanent" else TRANSIENT_TTL_SECONDS
    return age < ttl


def prune(mem):
    """Drop entries whose TTL has expired, so the file can't grow forever."""
    now = _now()
    keep = {}
    for key, entry in mem["items"].items():
        ttl = PERMANENT_TTL_SECONDS if entry.get("kind") == "permanent" else TRANSIENT_TTL_SECONDS
        if now - entry.get("ts", 0) < ttl:
            keep[key] = entry
    mem["items"] = keep


def stats(mem):
    perm = sum(1 for e in mem["items"].values() if e.get("kind") == "permanent")
    trans = len(mem["items"]) - perm
    return {"remembered": len(mem["items"]), "permanent": perm, "transient": trans}
