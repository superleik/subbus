"""Henter arrangementer fra hver kilde. Hver funksjon returnerer en liste med dict-er:
date (YYYY-MM-DD), t (HH:MM eller ""), title, venue, actor, cat, url, img, desc
Utstillinger kan i tillegg ha 'until' (YYYY-MM-DD).
"""
import html
import json
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

OSL = ZoneInfo("Europe/Oslo")
UA = {"User-Agent": "Mozilla/5.0 (subbus.no event aggregator)"}
MONTHS_EN = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}
MONTHS_NO = {m: i + 1 for i, m in enumerate("januar februar mars april mai juni juli august september oktober november desember".split())}


def get(url, **kw):
    r = requests.get(url, headers=UA, timeout=30, **kw)
    r.raise_for_status()
    return r


def text_lines(page):
    """Gjør HTML om til linjer med tekst, lenker som [url] og bilder som {img url}."""
    s = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", "", page)
    s = re.sub(r'(?i)<a [^>]*href="([^"]+)"[^>]*>', r"\n[\1]\n", s)
    s = re.sub(r'(?i)<img [^>]*src="([^"]+)"[^>]*>', r"\n{img \1}\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "\n", s))
    return [l.strip() for l in s.splitlines() if l.strip()]


def guess_year(month, day, today=None):
    """Datoer uten år: anta inneværende år, eller neste år hvis datoen er mer enn to måneder bak oss."""
    today = today or date.today()
    return today.year + 1 if (today - date(today.year, month, day)).days > 60 else today.year


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


# --- Tou: åpen JSON fra nettsiden deres -------------------------------------
def tou():
    data = get("https://www.touofficial.com/api/eventsEdge").json()
    items = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    out = []
    for e in items:
        dt = datetime.fromisoformat(e["start_time"].replace("Z", "+00:00")).astimezone(OSL)
        tags = " ".join(e.get("tags") or []).lower()
        cat = ("scene" if re.search(r"dans/teater|scenekunst", tags) else
               "kunst" if "exhibition" in tags else
               "klubb" if "klubb" in tags else
               "konsert" if re.search(r"rock|pop|jazz|hiphop|indie|folk|musikk|kor|punk|metal|elektron", tags) else "annet")
        img = None
        for k in ("imagekit", "photo"):
            if isinstance(e.get(k), dict) and e[k].get("url"):
                img = e[k]["url"]; break
        paras = re.sub(r"[*#_]", "", e.get("details") or "").split("\n\n")
        desc = next((p for p in paras if len(p) > 60), "")[:300]
        slug = re.sub(r"[^a-z0-9]+", "-", e["name"].lower()).strip("-")
        out.append(dict(date=dt.date().isoformat(), t=dt.strftime("%H:%M"), title=e["name"], venue="Tou",
                        actor="Tou Scene", cat=cat, url=f"https://www.touofficial.com/events/{slug}/{e['id']}",
                        img=img, desc=desc, tags=tags))
    return out


# --- Folken (og Strømklang, som holder til der) -------------------------------
def folken():
    s = get("https://www.folken.no/folken/").text
    cats = {"Konsert": "konsert", "Film": "film", "Teater": "scene", "Comedy": "scene"}
    out = []
    pat = re.compile(r"""<li class="list-item" data-type='([^']*)'>\s*<div class="image" style="background-image:url\(([^)]*)\);">.*?"""
                     r"""<div class="title"><a href="([^"]+)">(.*?)</a>.*?fa-calendar-o[^>]*></i>\s*([^<]+?)\s*</div>"""
                     r"""(?:(?:(?!list-item).)*?fa-clock-o[^>]*></i>\s*([^<]*?)\s*</div>)?""", re.S)
    for typ, img, url, title, ds, tm in pat.findall(s):
        p = ds.split()
        month, day = MONTHS_EN[p[1].lower()], int(p[0])
        year = int(p[2]) if len(p) > 2 else guess_year(month, day)
        title = html.unescape(title)
        actor = "Strømklang" if "strømklang" in title.lower() else "Folken"
        out.append(dict(date=date(year, month, day).isoformat(), t=tm.strip(), title=title, venue="Folken",
                        actor=actor, cat=cats.get(typ, "annet"), url=url, img=img, desc="", tags=typ.lower()))
    return out


# --- Litteraturhuset: Squarespace-kalender med JSON ---------------------------
def litteraturhuset():
    data = get("https://www.litthusstvg.no/program?format=json").json()
    out = []
    for e in data.get("upcoming", []):
        dt = datetime.fromtimestamp(e["startDate"] / 1000, OSL)
        out.append(dict(date=dt.date().isoformat(), t=dt.strftime("%H:%M"), title=clean(e["title"]),
                        venue="Litteraturhuset", actor="Stavanger Litteraturhus", cat="ord",
                        url="https://www.litthusstvg.no" + e["fullUrl"], img=e.get("assetUrl"),
                        desc=clean(re.sub("<[^>]+>", " ", html.unescape(e.get("excerpt") or "")))[:300], tags=""))
    return out


# --- Kunsthall Stavanger: arrangementer og utstillinger fra nettsiden ---------
def kunsthall():
    out = []
    lines = text_lines(get("https://kunsthallstavanger.no/en/events/upcoming").text)
    for i, l in enumerate(lines):
        m = re.match(r"\[(https://kunsthallstavanger.no/en/events/[^\]?]+)\]$", l)
        if not m or i + 3 >= len(lines) or not lines[i + 1].startswith("{img"):
            continue
        dm = re.match(r"\w+ (\d+) (\w+) (\d{4}),? (\d\d:\d\d)?", lines[i + 3])
        if not dm:
            continue
        d = date(int(dm[3]), MONTHS_EN[dm[2].lower()], int(dm[1]))
        out.append(dict(date=d.isoformat(), t=dm[4] or "", title=lines[i + 2], venue="Kunsthall Stavanger",
                        actor="Kunsthall Stavanger", cat="kunst", url=m[1], img=lines[i + 1][5:-1].split("?")[0] + "?width=400",
                        desc="", tags=""))
    lines = text_lines(get("https://kunsthallstavanger.no/en/exhibitions").text)
    for i, l in enumerate(lines):
        m = re.match(r"\[(https://kunsthallstavanger.no/en/exhibitions/[^\]?]+)\]$", l)
        if not m or i + 3 >= len(lines) or not lines[i + 1].startswith("{img"):
            continue
        dm = re.match(r"(\d+) (\w+)(?: (\d{4}))? – (\d+) (\w+) (\d{4})", lines[i + 3])
        if not dm:
            continue
        start = date(int(dm[3] or dm[6]), MONTHS_EN[dm[2].lower()], int(dm[1]))
        until = date(int(dm[6]), MONTHS_EN[dm[5].lower()], int(dm[4]))
        out.append(dict(date=start.isoformat(), until=until.isoformat(), t="", title=lines[i + 2],
                        venue="Kunsthall Stavanger", actor="Kunsthall Stavanger", cat="kunst", url=m[1],
                        img=lines[i + 1][5:-1].split("?")[0] + "?width=400", desc="", tags="exhibition"))
    return out


# --- RISK (Rimi/Imir Scenekunst): forsiden lister sesongens program ------------
def risk():
    lines = text_lines(get("https://www.rimi-imir.no/").text)
    out, seen = [], set()
    for i, l in enumerate(lines):
        m = re.match(r"\[(https://www.rimi-imir.no/[^\]]+/)\]$", l)
        if not m or i + 1 >= len(lines) or not lines[i + 1].startswith("{img") or m[1] in seen:
            continue
        seen.add(m[1])
        img = lines[i + 1][5:-1]
        block = []
        for x in lines[i + 2:i + 14]:
            if x == "TICKETS" or x.startswith("{img"):
                break
            if not x.startswith("["):
                block.append(x.strip("‘’' "))
        block = [b for b in block if b]
        if not block:
            continue
        dm = re.match(r"(\d+)(?:\s*\+\s*(\d+))?\.?\s+(\w+)", block[-1])
        if not dm or dm[3].lower() not in MONTHS_NO:
            continue
        month = MONTHS_NO[dm[3].lower()]
        title = re.sub(r"//\s*/\s*", "//", " / ".join(clean(b) for b in block[:-1]))
        for day in filter(None, (dm[1], dm[2])):
            d = date(guess_year(month, int(day)), month, int(day))
            out.append(dict(date=d.isoformat(), t="", title=title, venue="RISK", actor="RISK",
                            cat="scene", url=m[1], img=img, desc="", tags=""))
    return out


# --- Galleri Opdahl: Sanity-databasen bak nettsiden --------------------------
def opdahl():
    q = '*[_type=="exhibition" && closingDate >= now()]{_id, exhibitionTitle, title, exhibitionSubTitle, openingDate, startDate, closingDate, "img": exhibitionImages[0].image.asset->url, artists[]->{name}}'
    res = get("https://3tt2t14f.apicdn.sanity.io/v2021-06-07/data/query/production", params={"query": q}).json()["result"]
    out = []
    for e in res:
        names = ", ".join(a["name"] for a in (e.get("artists") or []) if a and a.get("name"))
        title = clean(e.get("exhibitionTitle") or e.get("title") or names)
        sub = clean(e.get("exhibitionSubTitle"))
        start = e.get("openingDate") or e.get("startDate")
        if not start:
            continue
        out.append(dict(date=start[:10], until=e["closingDate"][:10], t="",
                        title=" / ".join(x for x in (names or title, sub) if x), venue="Galleri Opdahl",
                        actor="Galleri Opdahl", cat="kunst", url="https://www.galleriopdahl.no/",
                        img=(e.get("img") or "") + "?w=400" if e.get("img") else None, desc="", tags="exhibition"))
    return out


SOURCES = {"tou": tou, "folken": folken, "litteraturhuset": litteraturhuset,
           "kunsthall": kunsthall, "risk": risk, "opdahl": opdahl}
