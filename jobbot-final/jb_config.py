import copy
import os

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))
# Where DB / dashboard / tailored resumes go. In Colab set JOBBOT_DATA to a Drive folder to keep history.
DATA_DIR = os.environ.get("JOBBOT_DATA") or os.path.join(ROOT, "output")  # overridden per session by the app

DEFAULTS = {
    "resume_path": "",
    "dry_run": True,
    "max_applications_per_run": 25,
    "delay_between_applications": [10, 20],
    "max_per_company": 2,
    "priority_slugs": [],
    "min_match_score": 40,
    "max_required_years": 1,
    "min_salary_lpa": 0,
    "allow_remote": True,
    "allow_unknown_location": False,
    "countries_terms": ["india"],
    "search_queries": ["machine learning engineer", "generative ai engineer", "data scientist"],
    "strong_title_keywords": ["machine learning", "ai engineer", "data scientist", "nlp", "llm"],
    "weak_title_keywords": ["data analyst", "software engineer", "python developer"],
    "exclude_title_words": ["senior", "sr", "lead", "principal", "staff", "manager", "director", "head"],
    "candidate": {},
    "custom_answers": [],
    "llm": {"provider": "gemini", "model": "gemini-2.5-flash"},
}


def _merge(a, b):
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_yaml(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if data is not None else default
    except FileNotFoundError:
        return default


def load_config(path=None):
    cfg = _merge(DEFAULTS, _load_yaml(path or os.path.join(ROOT, "config.yaml"), {}))
    rp = cfg["resume_path"]
    cfg["resume_abs"] = rp if os.path.isabs(rp) else os.path.join(ROOT, rp)  # replaced by the uploaded resume
    cfg["data_dir"] = DATA_DIR
    return cfg


FALLBACK_TRY_ALL = ["anthropic", "openai", "databricks", "scaleai", "stripe", "cohere", "mistral", "perplexity",
                    "xai", "deepmind", "cloudflare", "datadog", "mongodb", "figma", "vercel", "notion", "ramp"]


def load_companies():
    """Returns {'greenhouse': [...], 'lever': [...], 'ashby': [...], 'try_all': [...], 'priority': [...]}"""
    d = _load_yaml(os.path.join(ROOT, "companies.yaml"), {})
    if not isinstance(d, dict):
        d = {}
    out = {k: [str(x).strip() for x in (d.get(k) or []) if str(x).strip()]
           for k in ("greenhouse", "lever", "ashby", "try_all", "priority")}
    if not (out["greenhouse"] or out["lever"] or out["ashby"] or out["try_all"]):
        out["try_all"] = list(FALLBACK_TRY_ALL)
    return out
