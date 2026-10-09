# subbus

Kunst og kultur utenfor allfarvei i Stavanger, samlet i én kronologisk feed.

## Slik virker det

Tre ganger om dagen henter GitHub Actions programmet fra kildene i `subbus/sources.py`, bygger siden og publiserer den på GitHub Pages.

- Kilder merket `auto` i `config.yml` publiseres direkte.
- Kilder merket `review` havner i saken **«subbus: til godkjenning»** under Issues. Kryss av det som skal med. Siden oppdateres et par minutter etter.
- `alltid_ja` og `alltid_nei` i `config.yml` sorterer automatisk på tittel, så lista blir kortere over tid.

## Filer

| | |
|---|---|
| `config.yml` | kilder og regler, det eneste du normalt trenger å endre |
| `subbus/sources.py` | én funksjon per kilde |
| `subbus/run.py` | henter, sorterer og bygger siden |
| `subbus/review.py` | godkjenningslista i GitHub |
| `template.html` | utseendet |
| `data/godkjent.json` | id-er du har godkjent |

## Kjøre lokalt

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m subbus.run
open site/index.html
```

Lokalt skrives godkjenningslista til `data/godkjenning.md` i stedet for til GitHub.
