# download_new_papers.py
# encoding: utf-8
import os, json, datetime, pytz, urllib.request, tqdm
from bs4 import BeautifulSoup as bs
from typing import Optional
import re, html, urllib.request, xml.etree.ElementTree as ET

_DATA_DIR = "./data"
_ARXIV_BASE = "https://arxiv.org/abs/"

# ──────────────────────────────────────────────────────────────────────────────
def _ensure_data_dir():
    if not os.path.exists(_DATA_DIR):
        os.makedirs(_DATA_DIR, exist_ok=True)

def _timestamp_ny():
    return datetime.datetime.now(
        tz=pytz.timezone("America/New_York")
    ).date()  # returns YYYY-MM-DD

# ──────────────────────────────────────────────────────────────────────────────
def _scrape_page(url: str):
    page = urllib.request.urlopen(url)
    soup = bs(page, "html.parser")
    content = soup.body.find("div", {"id": "content"})

    dt_list = content.dl.find_all("dt")
    dd_list = content.dl.find_all("dd")
    assert len(dt_list) == len(dd_list)

    papers = []

    for i in tqdm.tqdm(range(len(dt_list))):
        dt, dd = dt_list[i], dd_list[i]
    
        # 1️⃣ robust ID & URL
        abs_a = dt.find("a", attrs={"title": "Abstract"})
        paper_id  = abs_a["href"].split("/")[-1]          # 2407.01234
        main_page = "https://arxiv.org" + abs_a["href"]   # full /abs/ URL
        pdf_link  = main_page.replace("abs", "pdf")
    
        # 2️⃣ core metadata from list page
        title_div   = dd.find("div", {"class": "list-title"})
        authors_div = dd.find("div", {"class": "list-authors"})
        subject_div = dd.find("div", {"class": "list-subjects"})
        title    = title_div.get_text(" ", strip=True).replace("Title:", "").strip()
        authors  = authors_div.get_text(" ", strip=True).replace("Authors:", "").strip()
        subjects = subject_div.get_text(" ", strip=True).replace("Subjects:", "").strip()
    
        # 3️⃣ abstract: first try list page, else pull from API
        abs_par = dd.find("p", {"class": "mathjax"})
        if abs_par:
            abstract = abs_par.get_text(" ", strip=True)
        else:
            api_url  = f'https://export.arxiv.org/api/query?id_list={paper_id}&max_results=1'
            api_xml  = urllib.request.urlopen(api_url).read().decode()
            m = re.search(r'<summary>(.*?)</summary>', api_xml, re.S)
            abstract = html.unescape(m.group(1).strip()) if m else ""
    
        # 4️⃣ submission date (leave as before) …
        # ------------------------------------------------------------------------
    
        papers.append(
            dict(
                id=paper_id,
                main_page=main_page,
                pdf=pdf_link,
                title=title,
                authors=authors,
                subjects=subjects,
                abstract=abstract,
                submitted=sub_date.isoformat(),
            )
        )
    return papers

# ──────────────────────────────────────────────────────────────────────────────
def _save_jsonl(fname: str, items):
    with open(fname, "w") as f:
        for p in items:
            f.write(json.dumps(p) + "\n")

def _load_jsonl(fname: str):
    with open(fname) as f:
        return [json.loads(line) for line in f]

# ──────────────────────────────────────────────────────────────────────────────
def get_papers(field_abbr: str, days: int = 1, limit: Optional[int] = None):
    """
    Return a list of arXiv papers for `field_abbr`.

    Parameters
    ----------
    field_abbr : str
        e.g. "q-fin" or "cs"
    days : int, optional
        1  → today's `/new` page (default, legacy behaviour)  
        >1 → scrape `/pastweek` (up to 1000 items) and return only those
              submitted in the last `days` 24-hour windows.
    limit : int, optional
        If provided, truncate the returned list to `limit` entries.
    """
    _ensure_data_dir()

    today_str = _timestamp_ny().strftime("%Y-%m-%d")

    # 1️⃣ decide which URL & cache file to use
    if days == 1:
        url  = f"https://arxiv.org/list/{field_abbr}/new"
        fname = f"{_DATA_DIR}/{field_abbr}_{today_str}_new.jsonl"
    else:
        url  = f"https://arxiv.org/list/{field_abbr}/pastweek?show=1000"
        fname = f"{_DATA_DIR}/{field_abbr}_{today_str}_pastweek.jsonl"

    # 2️⃣ scrape if cache missing
    if not os.path.exists(fname):
        papers = _scrape_page(url)
        _save_jsonl(fname, papers)

    papers = _load_jsonl(fname)

    # 3️⃣ filter by look-back window
    if days > 1:
        cutoff = _timestamp_ny() - datetime.timedelta(days=days)
        papers = [p for p in papers if datetime.date.fromisoformat(p["submitted"]) >= cutoff]

    if limit:
        papers = papers[:limit]

    return papers
