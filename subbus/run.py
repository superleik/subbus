"""Henter alle kilder, sorterer ut hva som skal publiseres, synkroniserer godkjenningslista
med GitHub og bygger nettsiden til site/.

Kjør lokalt:  python -m subbus.run
"""
import hashlib
import io
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import yaml
from PIL import Image

from . import review
from .sources import OSL, SOURCES, UA

ROOT = Path(__file__).resolve().parent.parent
DATA, SITE, CACHE = ROOT / "data", ROOT / "site", ROOT / ".cache" / "img"
DAYS = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]


def event_id(e):
    key = f"{e['actor']}|{e['date']}|{e['t']}|{e['title']}".lower()
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def fetch_all(cfg):
    """Henter hver kilde. Feiler en kilde, brukes forrige vellykkede resultat."""
    cache_file = DATA / "kilder.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    for name in cfg["kilder"]:
        try:
            cache[name] = SOURCES[name]()
            print(f"{name}: {len(cache[name])} arrangementer")
        except Exception as x:
            print(f"{name}: FEIL ({x}), bruker forrige resultat", file=sys.stderr)
    cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    events = []
    for name, items in cache.items():
        if name in cfg["kilder"]:
            for e in items:
                e["source"] = name
                e["id"] = event_id(e)
                events.append(e)
    return events


def classify(e, cfg, approved):
    title = e["title"].lower()
    if any(re.search(p, title) for p in cfg["alltid_nei"]):
        return "nei"
    if any(re.search(p, title) for p in cfg["alltid_ja"]):
        return "ja"
    if cfg["kilder"][e["source"]] == "auto":
        return "ja"
    return "ja" if e["id"] in approved else "venter"


def thumbnail(e):
    """Laster ned bildet og klipper det til et kvadrat på 160 px."""
    if not e.get("img"):
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    name = hashlib.sha1(e["img"].encode()).hexdigest()[:12] + ".jpg"
    cached = CACHE / name
    if not cached.exists():
        try:
            raw = requests.get(e["img"], headers=UA, timeout=30).content
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            side = min(im.size)
            left, top = (im.width - side) // 2, (im.height - side) // 2
            im.crop((left, top, left + side, top + side)).resize((160, 160), Image.LANCZOS).save(cached, quality=72)
        except Exception as x:
            print(f"bilde feilet: {e['img']} ({x})", file=sys.stderr)
            return None
    (SITE / "img").mkdir(parents=True, exist_ok=True)
    (SITE / "img" / name).write_bytes(cached.read_bytes())
    return "img/" + name


def main():
    cfg = yaml.safe_load((ROOT / "config.yml").read_text())
    today = datetime.now(OSL).date()
    horizon = today + timedelta(days=cfg.get("dager_frem", 90))

    events = fetch_all(cfg)
    events = [e for e in events if today <= date.fromisoformat(e["date"]) <= horizon
              or (e.get("until") and date.fromisoformat(e["date"]) <= today <= date.fromisoformat(e["until"]))]
    events.sort(key=lambda e: (e["date"], e["t"] or "99", e["title"]))

    approved_file = DATA / "godkjent.json"
    approved = set(json.loads(approved_file.read_text())) if approved_file.exists() else set()
    approved = review.sync(approved, events, lambda e: classify(e, cfg, set()), today)
    approved_file.write_text(json.dumps(sorted(approved), indent=1))

    published = [e for e in events if classify(e, cfg, approved) == "ja"]
    print(f"{len(published)} publisert, {sum(classify(e, cfg, approved) == 'venter' for e in events)} venter på godkjenning")

    SITE.mkdir(exist_ok=True)
    feed, ongoing, seen = [], [], set()
    for e in published:
        if e.get("until"):
            if date.fromisoformat(e["date"]) <= today:
                ongoing.append(dict(title=e["title"], venue=e["venue"], url=e["url"],
                                    until=date.fromisoformat(e["until"]).strftime("%d.%m")))
                continue
            e = dict(e, title="Åpning: " + e["title"])
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        feed.append(dict(date=e["date"], t=e["t"], title=e["title"], venue=e["venue"], actor=e["actor"],
                         cat=e["cat"], url=e["url"], desc=e.get("desc", ""), img=thumbnail(e)))

    now = datetime.now(OSL)
    data = dict(events=feed, ongoing=ongoing,
                updated=f"{DAYS[now.weekday()]} {now:%d.%m %H:%M}")
    page = (ROOT / "template.html").read_text().replace("/*DATA*/", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (SITE / "index.html").write_text(page)
    print(f"bygget site/index.html med {len(feed)} arrangementer")


if __name__ == "__main__":
    main()
