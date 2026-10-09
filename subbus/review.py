"""Godkjenningslista ligger i en GitHub-sak (issue) med avkrysningsbokser.
Kryss av = publiser. Fjern krysset = fjern fra siden igjen.

Uten GITHUB_TOKEN (lokalt) skrives lista til data/godkjenning.md i stedet.
"""
import os
import re
from datetime import date
from pathlib import Path

import requests

LABEL = "godkjenning"
TITLE = "subbus: til godkjenning"
DAYS = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]
LINE = re.compile(r"^- \[([ xX])\] .*<!-- id:(\w+) -->", re.M)
INTRO = ("Kryss av det som skal med på subbus. Siden oppdateres et par minutter etter at du har krysset av.\n"
         "Fjerner du et kryss, forsvinner arrangementet fra siden igjen. Det du ikke krysser av, vises aldri.\n\n"
         "Regler for hva som alltid eller aldri skal med, står i `config.yml`.\n")


def body(candidates, approved):
    out, cur = [INTRO], None
    for e in candidates:
        if e["date"] != cur:
            cur = e["date"]
            d = date.fromisoformat(cur)
            out.append(f"\n### {DAYS[d.weekday()]} {d:%d.%m}")
        box = "x" if e["id"] in approved else " "
        t = f"{e['t']} " if e["t"] else ""
        out.append(f"- [{box}] {t}**{e['title']}** · {e['venue']} · [lenke]({e['url']}) <!-- id:{e['id']} -->")
    text = "\n".join(out)
    return text[:64000]


def sync(approved, events, classify_plain, today):
    seen, candidates = set(), []
    for e in events:
        if classify_plain(e) == "venter" and e["id"] not in seen:
            seen.add(e["id"]); candidates.append(e)

    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        Path(__file__).resolve().parent.parent.joinpath("data", "godkjenning.md").write_text(body(candidates, approved))
        return approved

    api = f"https://api.github.com/repos/{repo}"
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    issues = requests.get(f"{api}/issues", headers=h, params={"labels": LABEL, "state": "open"}, timeout=30).json()
    issue = issues[0] if issues else None

    if issue:
        for box, eid in LINE.findall(issue.get("body") or ""):
            (approved.add if box.lower() == "x" else approved.discard)(eid)

    new_body = body(candidates, approved)
    if issue:
        if new_body != issue.get("body"):
            requests.patch(f"{api}/issues/{issue['number']}", headers=h, json={"body": new_body}, timeout=30).raise_for_status()
    else:
        requests.post(f"{api}/labels", headers=h, json={"name": LABEL, "color": "000000"}, timeout=30)
        requests.post(f"{api}/issues", headers=h, json={"title": TITLE, "body": new_body, "labels": [LABEL]},
                      timeout=30).raise_for_status()
    return approved
