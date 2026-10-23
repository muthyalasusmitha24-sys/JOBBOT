"""Filter + score jobs against the resume profile."""
import re

INDIA_TERMS = [
    "india", "bengaluru", "bangalore", "hyderabad", "chennai", "pune", "mumbai", "delhi", "gurgaon",
    "gurugram", "noida", "kolkata", "ahmedabad", "kochi", "cochin", "coimbatore", "trivandrum",
    "thiruvananthapuram", "jaipur", "indore", "chandigarh", "mysuru", "mysore", "nagpur", "lucknow",
    "bhubaneswar", "vadodara", "surat", "visakhapatnam", "vizag", "mohali", "navi mumbai", "thane",
]
RESTRICTED = [
    "united states", "usa", "u.s.", "us only", "canada", "united kingdom", "uk only", "europe", "emea",
    "germany", "france", "netherlands", "spain", "poland", "latam", "brazil", "mexico", "australia",
    "new zealand", "singapore", "japan", "israel", "north america", "eu only", "ireland", "london",
    "new york", "san francisco", "toronto", "berlin", "dublin", "sydney",
]
FRESHER_TERMS = ["fresher", "freshers", "entry level", "entry-level", "new grad", "new graduate",
                 "recent graduate", "graduate engineer", "campus", "0-1 year", "0-2 year", "0 to 1 year",
                 "0 - 1 year", "no experience required", "early career", "early-career", "associate"]


def _word_in(text, w):
    return re.search(r"(?<![a-z0-9])" + re.escape(w.lower()) + r"(?![a-z0-9])", text) is not None


def title_excluded(title, cfg):
    t = title.lower()
    if any(_word_in(t, w) for w in cfg["exclude_title_words"]):
        return True
    return re.search(r"\b(ii|iii|iv|v)\b\s*$", t) is not None or re.search(r"\b(level|l)\s?[3-9]\b", t) is not None


def title_score(title, cfg):
    t = title.lower()
    if any(k.lower() in t for k in cfg["strong_title_keywords"]):
        return 40
    if any(k.lower() in t for k in cfg["weak_title_keywords"]):
        return 20
    return 0


def location_ok(loc, desc, cfg):
    l = (loc or "").lower()
    terms = INDIA_TERMS + [x.lower() for x in cfg.get("countries_terms", [])]
    if any(_word_in(l, t) for t in terms):
        return "india"
    remote = any(w in l for w in ("remote", "anywhere", "worldwide", "work from home", "global", "apac", "asia"))
    if remote and cfg.get("allow_remote", True):
        if any(r in l for r in RESTRICTED):
            return ""
        return "remote"
    if not l and cfg.get("allow_unknown_location", False):
        return "unknown"
    return ""


def min_required_years(text):
    """Smallest 'N years' style requirement found; None if not stated."""
    vals = []
    for m in re.finditer(r"(\d{1,2})\s*(?:\+|plus)?\s*(?:-|to|–)?\s*(\d{1,2})?\s*\+?\s*(?:years|yrs|year)\b", text.lower()):
        a = int(m.group(1))
        if a <= 20:
            vals.append(a)
    if not vals:
        return None
    return min(vals)  # lenient: boilerplate like '10 years of history' must not reject a good job


def salary_lpa(s):
    """Best-effort INR salary parse -> annual LPA of the lower bound; None if unknown/non-INR."""
    s = (s or "").lower()
    if "inr" not in s and "₹" not in s and "lpa" not in s and "lakh" not in s:
        return None
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", s)]
    if not nums:
        return None
    n = nums[0]
    return n / 100000.0 if n > 1000 else n


def evaluate(job, profile, cfg):
    """Return (ok, score, matched_skills, reason)."""
    title, desc = job["title"], job["description"]
    if not title:
        return False, 0, [], "no title"
    if title_excluded(title, cfg):
        return False, 0, [], "senior/irrelevant title"
    ts = title_score(title, cfg)
    if ts == 0:
        return False, 0, [], "title not relevant"
    loc = location_ok(job["location"], desc, cfg)
    if not loc:
        return False, 0, [], "location not suitable"
    need = min_required_years(desc)
    if need is not None and need > cfg["max_required_years"]:
        return False, 0, [], f"needs {need}+ years"
    sal = salary_lpa(job.get("salary"))
    if cfg.get("min_salary_lpa") and sal is not None and sal < cfg["min_salary_lpa"]:
        return False, 0, [], "salary below minimum"

    text = f"{title}\n{desc}".lower()
    matched = [s for s in profile["skills"] if _word_in(text, s.lower())]
    from jb_resume_parser import SKILLS
    for s in profile["skills"]:
        if s not in matched and any(_word_in(text, a) for a in SKILLS.get(s, [])):
            matched.append(s)
    skill_pts = min(len(matched), 10) / 10.0 * 40
    low = desc.lower()
    bonus = 10 if any(t in low or t in title.lower() for t in FRESHER_TERMS) else (
        5 if need == 1 else (3 if need is None else 0))
    loc_pts = 10 if loc == "india" else 6
    slug = (job.get("source") or "").split(":")[-1].lower()
    prio = 6 if slug and slug in set(cfg.get("priority_slugs") or []) else 0
    score = round(min(100, ts + skill_pts + bonus + loc_pts + prio), 1)
    if score < cfg["min_match_score"]:
        return False, score, matched, "score below threshold"
    return True, score, matched, "ok"
