"""Run JobBot in Google Colab (no Streamlit needed). Used by JobBot_Colab.ipynb."""
import os
import shutil
import time

import jb_dashboard
import jb_pipeline as P


def run(resume_path, mode="dry", candidate=None, max_apps=15, min_score=40, max_years=1, extra_boards="",
        mail_user="", mail_pass="", pause=(10, 20), per_company=2, guess=True, groq_key="", gemini_key="",
        include_remote=True, out_dir="/content/jobbot_out", log=print):
    """mode: 'find' (only match+tailor) | 'dry' (fill forms, don't submit) | 'live' (submit)."""
    if groq_key:
        os.environ["GROQ_API_KEY"] = groq_key
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key
    os.makedirs(out_dir, exist_ok=True)
    cfg = P.make_cfg(out_dir, resume_path, {
        "min_match_score": min_score, "max_required_years": max_years, "allow_remote": include_remote,
        "enabled_sources": ["greenhouse", "lever", "ashby"], "dry_run": mode != "live",
        "max_applications_per_run": max_apps, "max_per_company": per_company,
        "delay_between_applications": [pause[0], pause[1]], "headed": False, "captcha_wait": 0,
        "guess_unknown": guess, "mail": {"user": mail_user.strip(), "password": mail_pass.replace(" ", "")},
        "candidate": dict(candidate or {}),
    })
    profile = P.build_profile(cfg)
    log(f"Resume: {profile['name']} | {profile['email']} | {len(profile['skills'])} skills | mode={mode}")
    db, cache, covers = P.open_db(out_dir), {}, {}
    runner = P.Runner()
    runner.start(P.run_job, cfg, profile, db, cache, covers, [x for x in extra_boards.splitlines() if x.strip()],
                 mode in ("dry", "live"))
    shown = 0
    while True:
        snap = runner.snapshot()
        for line in snap["log"][shown:]:
            log(line)
        shown = len(snap["log"])
        if not runner.running:
            break
        time.sleep(3)
    for line in runner.snapshot()["log"][shown:]:
        log(line)
    snap = runner.snapshot()
    if snap["error"]:
        log("ERROR: " + snap["error"])
    if snap.get("browser") is False:
        log("Browser could not start: " + str(snap.get("browser_error")))
    path = jb_dashboard.write_dashboard(db.all(), out_dir)
    P.zip_resumes(out_dir)
    counts = {}
    for r in db.all():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    log(f"\nDONE. Totals: {counts}")
    return db, out_dir


def show(out_dir):
    from IPython.display import HTML, display
    with open(os.path.join(out_dir, "dashboard.html"), encoding="utf-8") as f:
        display(HTML(f.read()))


def download(out_dir):
    from google.colab import files
    shutil.make_archive("/content/jobbot_results", "zip", out_dir)
    files.download("/content/jobbot_results.zip")
