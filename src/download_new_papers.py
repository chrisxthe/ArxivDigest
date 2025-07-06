# src/download_new_papers.py
# encoding: utf-8
"""
Lightweight arXiv scraper + cache.

Features
--------
* `get_papers(field_abbr, days=1, limit=None)`  ← public entry point  
    - days = 1   → today’s `/new` list (legacy behaviour)  
    - days > 1   → `/pastweek?show=1000` and keep only submissions
                   from the last `days` × 24 h.
* Caches every scrape to ./data/ so repeated calls are instant.
* Robust to rows that lack an abstract or list‐comments block.
* Works on Python 3.8 (no PEP-604 syntax).

Dependencies
------------
beautifulsoup4, tqdm, pytz  (all already in requirements.txt)
"""

import os, json, re, html, datetime, urllib.request, tqdm
from typing import Optional
import pytz
from bs4 import BeautifulSoup as BS

_DATA_DIR   = "./data"
_ABS_BASE   = "https://arxiv.org/abs/"
_PASTWEEK_Q = "?show=1000"              # grab up to 1 000 rows in one go


# ──────────────────────────────────────────────────────────────────────────────
def _ensure_dir() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)


def _today_ny() -> datetime.date:
    """Return today's date in America/New_York."""
    return datetime.datetime.now(
        tz=pytz.timezone("America/New_York")
    ).date()


# ──────────────────────────────────────────────────────────────────────────────
def _scrape_page(url: str):
    """Return list[dict] with id, title, authors, subjects, abstract, submitted."""
    soup  = BS(urllib.request.urlopen(url), "html.parser")
    dl    = soup.body.find("div", id="content").dl
    dt_ls = dl.find_all("dt")
    dd_ls = dl.find_all("dd")

    assert len(dt_ls) == len(dd_ls)
    papers = []

    for dt, dd in tqdm.tqdm(zip(dt_ls, dd_ls), total=len(dt_ls), unit="paper"):
        # --- id & links -------------------------------------------------------
        abs_a    = dt.find("a", title="Abstract")
        paper_id = abs_a["href"].split("/")[-1]           # e.g. 2407.01234
        main_url = "https://arxiv.org" + abs_a["href"]
        pdf_url  = main_url.replace("/abs/", "/pdf/")

        # --- title / authors / subjects --------------------------------------
        title = dd.find("div", class_="list-title")
        title = title.get_text(" ", strip=True).replace("Title:", "").strip()

        authors = dd.find("div", class_="list-authors")
        authors = authors.get_text(" ", strip=True).replace("Authors:", "").strip()

        subjects = dd.find("div", class_="list-subjects")
        subjects = subjects.get_text(" ", strip=True).replace("Subjects:", "").strip()

        # --- abstract ---------------------------------------------------------
        abs_par = dd.find("p", class_="mathjax")
        if abs_par:
            abstract = abs_par.get_text(" ", strip=True)
        else:  # fall back to API (≈150 ms)
            api_xml = urllib.request.urlopen(
                f"https://export.arxiv.org/api/query?id_list={paper_id}&max_results=1"
            ).read().decode()
            m = re.search(r"<summary>(.*?)</summary>", api_xml, re.S)
            abstract = html.unescape(m.group(1).strip()) if m else ""

        # --- submission date --------------------------------------------------
        comment = dd.find("div", class_="list-comments")
        if comment and "(submitted" in comment.text:
            date_str = comment.text.split("(submitted")[1].split(")")[0].strip()
            sub_date = datetime.datetime.strptime(date_str, "%d %b %Y").date()
        else:
            sub_date = _today_ny()

        papers.append(
            dict(
                id=paper_id,
                main_page=main_url,
                pdf=pdf_url,
                title=title,
                authors=authors,
                subjects=subjects,
                abstract=abstract,
                submitted=sub_date.isoformat(),
            )
        )
    return papers


# ──────────────────────────────────────────────────────────────────────────────
def _save_jsonl(path: str, rows) -> None:
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _load_jsonl(path: str):
    with open(path) as fh:
        return [json.loads(ln) for ln in fh]


# ──────────────────────────────────────────────────────────────────────────────
def get_papers(field_abbr: str, days: int = 1, limit: Optional[int] = None):
    """
    Parameters
    ----------
    field_abbr : str
        e.g. "q-fin", "cs", "math"
    days : int, default 1
        1  → scrape today's `/new` list
        >1 → scrape `/pastweek` once, filter to last `days`
    limit : int or None
        If set, truncate the result list to `limit` entries.
    """
    _ensure_dir()
    today_str = _today_ny().strftime("%Y-%m-%d")

    if days == 1:
        url   = f"https://arxiv.org/list/{field_abbr}/new"
        cache = f"{_DATA_DIR}/{field_abbr}_{today_str}_new.jsonl"
    else:
        url   = f"https://arxiv.org/list/{field_abbr}/pastweek{_PASTWEEK_Q}"
        cache = f"{_DATA_DIR}/{field_abbr}_{today_str}_pastweek.jsonl"

    if not os.path.exists(cache):
        papers = _scrape_page(url)
        _save_jsonl(cache, papers)

    papers = _load_jsonl(cache)

    if days > 1:
        cutoff = _today_ny() - datetime.timedelta(days=days)
        papers = [
            p for p in papers
            if datetime.date.fromisoformat(p["submitted"]) >= cutoff
        ]

    if limit:
        papers = papers[:limit]

    return papers
