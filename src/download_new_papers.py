# download_new_papers.py
# encoding: utf-8
import os, json, datetime, pytz, urllib.request, tqdm
from bs4 import BeautifulSoup as bs

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

        paper_id   = dt.text.strip().split(" ")[2].split(":")[-1]
        main_page  = _ARXIV_BASE + paper_id
        pdf_link   = main_page.replace("abs", "pdf")
        title      = dd.find("div", {"class": "list-title"}).text \
                       .replace("Title:", "").strip()
        authors    = dd.find("div", {"class": "list-authors"}).text \
                       .replace("Authors:", "").replace("\n", "").strip()
        subjects   = dd.find("div", {"class": "list-subjects"}).text \
                       .replace("Subjects:", "").strip()
        abstract   = dd.find("p", {"class": "mathjax"}).text \
                       .replace("\n", " ").strip()

        # submission date appears in the comment line, e.g. "(submitted 3 Jul 2024)"
        comment = dd.find("div", {"class": "list-comments"})
        if comment and "(submitted" in comment.text:
            date_str = comment.text.split("(submitted")[1].split(")")[0].strip()
            sub_date = datetime.datetime.strptime(date_str, "%d %b %Y").date()
        else:
            sub_date = _timestamp_ny()  # fallback to 'today' if missing

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
