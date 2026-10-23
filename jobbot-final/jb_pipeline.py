"""High-level steps used by the Streamlit app. The whole run happens in a background thread (Runner),
so long auto-apply sessions keep going even if the browser tab sleeps or reloads."""
import os
import tempfile
import threading
import time
import zipfile

import jb_applier as applier
import jb_matcher as matcher
import jb_sources as sources
from jb_config import _merge, load_companies, load_config
from jb_db import DB
from jb_resume_parser import parse_resume
from jb_tailor import answer_question, tailor_resume

SUPPORTED_APPLY = ("greenhouse", "lever", "ashby")


def new_workspace():
    return tempfile.mkdtemp(prefix="jobbot_")


def make_cfg(data_dir, resume_path, overrides=None):
    cfg = _merge(load_config(), overrides or {})
    cfg["data_dir"] = data_dir
    cfg["resume_abs"] = resume_path
    os.makedirs(data_dir, exist_ok=True)
    return cfg


def build_profile(cfg):
    p = parse_resume(cfg["resume_abs"])
    yrs = cfg.get("candidate", {}).get("years_experience")
    if yrs not in (None, ""):
        try:
            p["years_experience"] = float(yrs)
        except ValueError:
            pass
    return p


def platform_of(url):
    u = (url or "").lower()
    for name, dom in (("greenhouse", "greenhouse.io"), ("lever", "lever.co"), ("ashby", "ashbyhq.com")):
        if dom in u:
            return name
    return ""


def open_db(data_dir):
    return DB(os.path.join(data_dir, "jobbot.db"))


def merged_companies(extra_lines=None, log=print):
    comp = load_companies()
    if extra_lines:
        extra = sources.discover_boards(extra_lines, log)
        for k in ("greenhouse", "lever", "ashby", "try_all"):
            comp[k] = list(dict.fromkeys(comp.get(k, []) + extra.get(k, [])))
    return comp


def search(cfg, profile, db, companies, log=print):
    """Fetch -> filter -> score -> save new matches. Returns (summary, {key: (job, matched)})."""
    src_stats = {}
    cfg = dict(cfg)
    cfg["priority_slugs"] = [s.lower() for s in companies.get("priority", [])]
    raw = sources.fetch_all(cfg, companies, log, src_stats)
    seen, found, filtered = set(), {}, {}
    for j in raw:
        if j["key"] in seen:
            continue
        seen.add(j["key"])
        ok, score, matched, why = matcher.evaluate(j, profile, cfg)
        if not ok:
            filtered[why] = filtered.get(why, 0) + 1
            continue
        if db.has(j["key"]):
            filtered["already tracked"] = filtered.get("already tracked", 0) + 1
            continue
        db.add_found(j, score, matched)
        found[j["key"]] = (j, matched)
    summary = {"raw": len(raw), "unique": len(seen), "new": len(found), "filtered": filtered, "sources": src_stats}
    return summary, found


def tailor_top(cfg, profile, db, cache, limit, apply_only=False, progress=None):
    """Tailor resumes for the best pending jobs. Returns {key: cover_text}."""
    keys = db.pending_keys(limit, apply_only=apply_only, per_company=int(cfg.get("max_per_company", 0) or 0))
    covers, out_dir = {}, os.path.join(cfg["data_dir"], "resumes")
    for n, k in enumerate(keys, 1):
        row = db.get(k)
        if k in cache:
            job, matched = cache[k]
        else:
            job = {"key": k, "source": row["source"], "company": row["company"], "title": row["title"],
                   "location": row["location"], "url": row["url"], "apply_url": row["apply_url"],
                   "description": "", "salary": row["salary"]}
            matched = [m for m in (row["matched"] or "").split(", ") if m]
            cache[k] = (job, matched)
        try:
            path, cover = tailor_resume(profile, job, matched, cfg, out_dir)
        except Exception:
            path, cover = cfg["resume_abs"], ""
        db.update(k, resume_path=path)
        covers[k] = cover
        if progress:
            progress(n, len(keys), job)
    return covers


def zip_resumes(data_dir):
    src = os.path.join(data_dir, "resumes")
    out = os.path.join(data_dir, "tailored_resumes.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        if os.path.isdir(src):
            for f in sorted(os.listdir(src)):
                z.write(os.path.join(src, f), f)
    return out


# ------------------------------------------------------------------ background runner
class Runner:
    """Holds live progress of a run. Thread-safe; the UI only reads snapshot()."""

    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.stop_flag = False
        self.reset()

    def reset(self):
        with self.lock:
            self.s = {"stage": "idle", "pct": 0.0, "msg": "", "log": [], "finished": False, "error": "",
                      "started": 0.0, "summary": None, "browser": None, "applied_now": 0, "total_apply": 0}

    def set(self, **kw):
        with self.lock:
            self.s.update(kw)

    def log(self, m):
        with self.lock:
            self.s["log"].append(time.strftime("%H:%M:%S") + "  " + str(m))
            self.s["log"] = self.s["log"][-300:]

    def snapshot(self):
        with self.lock:
            d = dict(self.s)
            d["log"] = list(self.s["log"])
        return d

    @property
    def running(self):
        return bool(self.thread and self.thread.is_alive())

    def stop(self):
        self.stop_flag = True

    def start(self, fn, *args):
        self.stop_flag = False
        self.reset()
        self.set(stage="starting", started=time.time())
        self.thread = threading.Thread(target=self._run, args=(fn,) + args, daemon=True)
        self.thread.start()

    def _run(self, fn, *args):
        try:
            fn(self, *args)
        except Exception as e:  # never die silently
            self.set(error=f"{type(e).__name__}: {e}")
            self.log(f"ERROR: {type(e).__name__}: {e}")
        finally:
            self.set(finished=True, stage="done")


def run_job(runner, cfg, profile, db, cache, covers, extra_lines, do_apply):
    """Everything: scan -> filter -> tailor -> (apply). Executed inside the Runner thread."""
    log = runner.log
    runner.set(stage="scan", pct=0.02, msg="Scanning company career boards ...")
    comp = merged_companies(extra_lines, log)
    n_boards = sum(len(comp.get(k, [])) for k in ("greenhouse", "lever", "ashby")) + 3 * len(comp.get("try_all", []))
    log(f"Checking about {n_boards} company boards ...")
    summary, found = search(cfg, profile, db, comp, log)
    cache.update(found)
    runner.set(summary=summary, pct=0.30)
    log(f"{summary['raw']} postings scanned, {summary['new']} new relevant matches")

    runner.set(stage="tailor", msg="Tailoring resumes ...")

    def tprog(n, t, j):
        runner.set(pct=0.30 + 0.25 * n / max(t, 1), msg=f"Tailoring resume {n}/{t}: {j['company']}")
    covers.update(tailor_top(cfg, profile, db, cache, cfg["max_applications_per_run"], apply_only=do_apply, progress=tprog))
    log(f"{len(covers)} tailored resumes ready")
    if not covers:
        log("No new jobs to process (try lower match score / more companies).")
        return
    if not do_apply:
        runner.set(pct=1.0, msg="Done")
        return

    runner.set(stage="apply", msg="Starting browser ...", pct=0.57)
    log("Checking headless browser ...")
    ok, why = applier.browser_check()
    runner.set(browser=ok, browser_error=why)
    if not ok:
        log(f"NO BROWSER on this server -> cannot auto-apply here. Reason: {why}")
        for k in covers:  # keep them as 'Matched' - they were NOT attempted
            db.update(k, reason="not applied: this server has no browser - run JobBot on your computer")
        return
    if os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        cfg["answerer"] = lambda p, j, q, o: answer_question(p, j, q, o, cfg)  # AI answers custom questions
    items = []
    for k in covers:
        job, _ = cache[k]
        if platform_of(job["apply_url"]) in SUPPORTED_APPLY:
            items.append((job, db.get(k)["resume_path"] or cfg["resume_abs"], covers.get(k, "")))
        else:
            db.update(k, status="manual_needed", reason="not a Greenhouse/Lever/Ashby page - open the link")
    runner.set(total_apply=len(items))
    done = {"n": 0}

    def on_result(job, status, reason, shot):
        db.update(job["key"], status=status, reason=reason, screenshot=shot or "")
        done["n"] += 1
        runner.set(pct=0.57 + 0.43 * done["n"] / max(len(items), 1), applied_now=done["n"],
                   msg=f"Applied to {done['n']}/{len(items)}: {job['company']} -> {status}")

    log(f"Auto-applying to {len(items)} jobs ({'LIVE' if not cfg['dry_run'] else 'dry run'}) ...")
    applier.apply_all(items, profile, cfg, on_result, log, stop=lambda: runner.stop_flag)
    runner.set(pct=1.0, msg="Done")
