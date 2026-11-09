# NGO Darpan Directory Scraper

Extracts the public directory of **Indian NGOs / voluntary organisations** from
[NGO Darpan](https://ngodarpan.gov.in) (NITI Aayog) — tens of thousands of
records across all 36 states & UTs — into a single clean, de-duplicated CSV.

NGO Darpan publishes its registry only as a **paginated, captcha-guarded search
form**: no export, no API docs, one small page at a time. This project turns it
into an analysis-ready dataset with one command.

```
unique_id,ngo_name,state,sectors,address
KL/2020/0245678,Green Kerala Foundation,Kerala,Environment; Rural Development,"Kochi, Kerala"
...
```

> This is the classic **directory / listing extraction** problem — the single
> most common type of web-scraping work: turning a search-only portal into a
> structured spreadsheet (lead lists, registries, contact directories).

## The hard parts (and how it handles them)

| Challenge | Approach |
|-----------|----------|
| **Captcha on search** | requests-first for speed; **Playwright fallback** lets a human clear the captcha once, then harvests every page |
| **Scale** (36 states × many pages) | Iterates **state-by-state** so each query is small, resumable, and easy to rate-limit |
| **Markup drift** (table vs. cards) | Parser prefers a `<table>` but falls back to positional parsing — survives redesigns |
| **Duplicates** | Single identity key (`unique_id`, else `name|state`) — avoids the NaN-equality trap that silently merges id-less rows |
| **Trust** | **pandera** schema validates every record before anything is written |

## Architecture

```
scrape()  ─ state-by-state, paginated ─┐
  ├─ fetch_via_requests (AJAX POST)     │
  └─ fetch_via_browser  (captcha)       ├─► clean() ─► validate() ─► CSV
       raw rows                         │   normalise    pandera
                                        │   + de-dup     schema
```

## Install

```bash
git clone https://github.com/HemanthM005/ngo-darpan-scraper
cd ngo-darpan-scraper
pip install -r requirements.txt
playwright install chromium   # optional, for the captcha fallback
```

## Usage

```bash
# all states
python -m ngo_darpan_scraper --out data/ngos.csv

# a subset
python -m ngo_darpan_scraper --states "Telangana,Kerala" --out data/south.csv

# requests only, no browser
python -m ngo_darpan_scraper --no-browser
```

```python
from ngo_darpan_scraper import scrape, clean, validate
df = validate(clean(scrape(states=("Goa",))))
```

## Output schema

| column | description |
|--------|-------------|
| `unique_id` | NGO Darpan registration id (e.g. `TS/2019/0012345`) |
| `ngo_name` | registered name |
| `state` | state / UT |
| `sectors` | sectors of work, `; `-separated |
| `address` | published address |

> `data/sample_output/ngos_SAMPLE.csv` is an **illustrative** sample of the
> output schema. Run the scraper to pull the live directory.

## Tests

```bash
pip install pytest
PYTHONPATH=src pytest -q
```

## Tech
Python · requests · BeautifulSoup · Playwright · pandas · pandera

## Responsible scraping
Collects only **public** registry data, sends a descriptive User-Agent,
rate-limits and backs off politely, and never bypasses the captcha
programmatically (a human solves it in the fallback browser).

## License
MIT © 2026 Manikala Hemanth
