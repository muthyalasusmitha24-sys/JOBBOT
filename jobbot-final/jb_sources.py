"""Job sources. Only public/free APIs that allow reading - no login-wall scraping."""
import html
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from jb_db import make_key

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


def strip_html(s):
    s = html.unescape(s or "")
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def get_json(url, params=None, retries=2, timeout=25):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code in (400, 401, 403, 404):
                return None
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            time.sleep(1)
    return None


def make_job(source, company, title, location, url, apply_url, description, salary="", platform=""):
    company, title, location = (company or "").strip(), (title or "").strip(), (location or "").strip()
    return {
        "key": make_key(company, title, location), "source": source, "company": company, "title": title,
        "location": location, "url": url or apply_url or "", "apply_url": apply_url or url or "",
        "description": strip_html(description), "salary": salary or "", "platform": platform,
    }


PRETTY = {
    "openai": "OpenAI", "deepmind": "Google DeepMind", "scaleai": "Scale AI", "xai": "xAI", "togetherai": "Together AI",
    "anthropic": "Anthropic", "mistral": "Mistral AI", "cohere": "Cohere", "perplexity": "Perplexity AI",
    "wandb": "Weights & Biases", "gleanwork": "Glean", "elevenlabs": "ElevenLabs", "huggingface": "Hugging Face",
    "cerebrassystems": "Cerebras", "snorkelai": "Snorkel AI", "runwayml": "Runway", "sambanovasystems": "SambaNova",
    "razorpaysoftwareprivatelimited": "Razorpay", "dreamplug": "CRED", "appliedintuition": "Applied Intuition",
    "characterai": "Character.AI", "stabilityai": "Stability AI", "adobe": "Adobe", "nvidia": "NVIDIA",
}


def pretty(slug):
    return PRETTY.get(slug.lower()) or slug.replace("-", " ").replace("_", " ").title()


def fetch_greenhouse(slug):
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", {"content": "true"})
    out = []
    for j in (data or {}).get("jobs", []) or []:
        loc = (j.get("location") or {}).get("name", "")
        out.append(make_job(f"greenhouse:{slug}", j.get("company_name") or pretty(slug), j.get("title"), loc, j.get("absolute_url"),
                            f"https://job-boards.greenhouse.io/{slug}/jobs/{j.get('id')}",
                            j.get("content", ""), platform="greenhouse"))
    return out


def fetch_lever(slug):
    data = get_json(f"https://api.lever.co/v0/postings/{slug}", {"mode": "json"})
    out = []
    if not isinstance(data, list):
        return out
    for j in data:
        cats = j.get("categories") or {}
        loc = cats.get("location") or ""
        if cats.get("allLocations"):
            loc = "; ".join(cats["allLocations"])
        desc = (j.get("descriptionPlain") or "") + "\n"
        for lst in j.get("lists") or []:
            desc += (lst.get("text") or "") + "\n" + strip_html(lst.get("content", "")) + "\n"
        desc += j.get("additionalPlain") or ""
        sal = ""
        sr = j.get("salaryRange")
        if isinstance(sr, dict) and sr.get("min"):
            sal = f"{sr.get('currency','')} {sr.get('min')}-{sr.get('max')} {sr.get('interval','')}".strip()
        hosted = j.get("hostedUrl") or ""
        out.append(make_job(f"lever:{slug}", pretty(slug), j.get("text"), loc, hosted,
                            j.get("applyUrl") or (hosted + "/apply"), desc, sal, platform="lever"))
    return out


def fetch_ashby(slug):
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", {"includeCompensation": "true"})
    out = []
    for j in (data or {}).get("jobs", []) or []:
        if j.get("isListed") is False:
            continue
        loc = j.get("location") or ""
        sec = [s.get("location") if isinstance(s, dict) else str(s) for s in j.get("secondaryLocations") or []]
        loc = "; ".join([x for x in [loc] + sec if x])
        comp = (j.get("compensation") or {}).get("compensationTierSummary", "") or ""
        out.append(make_job(f"ashby:{slug}", pretty(slug), j.get("title"), loc, j.get("jobUrl"),
                            j.get("applyUrl") or j.get("jobUrl"),
                            j.get("descriptionPlain") or j.get("descriptionHtml", ""), comp, platform="ashby"))
    return out


def fetch_remotive(query):
    data = get_json("https://remotive.com/api/remote-jobs", {"search": query, "limit": 100})
    out = []
    for j in (data or {}).get("jobs", []) or []:
        out.append(make_job("remotive", j.get("company_name"), j.get("title"),
                            j.get("candidate_required_location") or "Remote", j.get("url"), j.get("url"),
                            j.get("description", ""), j.get("salary") or ""))
    return out


def fetch_remoteok(_query=None):
    data = get_json("https://remoteok.com/api")
    out = []
    if not isinstance(data, list):
        return out
    for j in data:
        if not isinstance(j, dict) or not j.get("position"):
            continue
        sal = f"USD {j['salary_min']}-{j['salary_max']}" if j.get("salary_min") else ""
        out.append(make_job("remoteok", j.get("company"), j.get("position"), j.get("location") or "Remote",
                            j.get("url"), j.get("apply_url") or j.get("url"), j.get("description", ""), sal))
    return out


def fetch_adzuna(query):
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return []
    out = []
    for page in (1, 2):
        data = get_json(f"https://api.adzuna.com/v1/api/jobs/in/search/{page}",
                        {"app_id": app_id, "app_key": app_key, "results_per_page": 50, "what": query,
                         "max_days_old": 21, "content-type": "application/json"})
        for j in (data or {}).get("results", []) or []:
            sal = ""
            if j.get("salary_min"):
                sal = f"INR {int(j['salary_min']):,}-{int(j.get('salary_max') or j['salary_min']):,} / yr"
            out.append(make_job("adzuna", (j.get("company") or {}).get("display_name"), j.get("title"),
                                (j.get("location") or {}).get("display_name", "India"), j.get("redirect_url"),
                                j.get("redirect_url"), j.get("description", ""), sal))
    return out


def fetch_all(cfg, companies, log=print, stats_out=None):
    tasks, seen_t = [], set()
    fns = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}

    def add(kind, slug):
        if (kind, slug) not in seen_t:
            seen_t.add((kind, slug))
            tasks.append((kind, slug, fns[kind]))
    for kind in fns:
        for slug in companies.get(kind, []):
            add(kind, slug)
    for slug in companies.get("try_all", []):  # we don't know which ATS the company uses -> try all three
        for kind in fns:
            add(kind, slug)
    tasks.append(("remoteok", "-", fetch_remoteok))
    for q in cfg["search_queries"]:
        tasks.append(("remotive", q, fetch_remotive))
        tasks.append(("adzuna", q, fetch_adzuna))

    enabled = cfg.get("enabled_sources")
    if enabled:
        tasks = [t for t in tasks if t[0] in enabled]

    def run(t):
        kind, arg, fn = t
        try:
            return t, fn(arg)
        except Exception as e:  # never let one source kill the run
            return t, []

    jobs, stats = [], {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        for (kind, arg, _), res in ex.map(run, tasks):
            stats.setdefault(kind, {"boards_with_jobs": 0, "jobs": 0})
            if res:
                stats[kind]["boards_with_jobs"] += 1
                stats[kind]["jobs"] += len(res)
            jobs.extend(res)
    if stats_out is not None:
        stats_out.update(stats)
    for k, v in stats.items():
        log(f"  source {k:<11} boards/queries with results: {v['boards_with_jobs']:>3}  jobs: {v['jobs']}")
    return jobs


# ------------------------------------------------------------------ board discovery from pasted career URLs
BOARD_PATTERNS = [
    ("greenhouse", r"greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)"),
    ("greenhouse", r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([A-Za-z0-9_-]+)"),
    ("lever", r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)"),
]
BAD_SLUGS = {"embed", "v1", "jobs", "api", "static", "assets", "js", "css"}


def find_boards(text):
    found = []
    for kind, pat in BOARD_PATTERNS:
        for m in re.finditer(pat, text or "", re.I):
            slug = m.group(1).strip(".")
            if slug.lower() not in BAD_SLUGS and (kind, slug) not in found:
                found.append((kind, slug))
    return found


def discover_boards(lines, log=print):
    """User pastes career-page URLs (or ATS links, or plain slugs). Returns {'greenhouse': [...], ...}."""
    out = {"greenhouse": [], "lever": [], "ashby": [], "try_all": []}
    for raw in (lines or []):
        line = raw.strip()
        if not line:
            continue
        hits = find_boards(line)
        if not hits and line.lower().startswith("http"):
            try:
                r = requests.get(line, headers=UA, timeout=15)
                hits = find_boards(r.text)
            except Exception:
                hits = []
        if hits:
            for kind, slug in hits:
                if slug not in out[kind]:
                    out[kind].append(slug)
            log(f"  found career board(s) for {line[:60]}: " + ", ".join(f"{k}/{s}" for k, s in hits))
        elif re.fullmatch(r"[A-Za-z0-9_-]{2,40}", line):
            out["try_all"].append(line)
            log(f"  will try '{line}' on Greenhouse, Lever and Ashby")
        else:
            log(f"  could not find a supported career board in: {line[:70]} (needs Greenhouse/Lever/Ashby)")
    return out
