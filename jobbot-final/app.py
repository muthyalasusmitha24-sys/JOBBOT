import csv
import hashlib
import html
import io
import os
import sys
import time

import altair as alt
import pandas as pd
import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

st.set_page_config(page_title="JobBot - AI Career Copilot", page_icon="🚀", layout="wide",
                   initial_sidebar_state="expanded")

_REQUIRED = ["jb_applier.py", "jb_config.py", "jb_dashboard.py", "jb_db.py", "jb_matcher.py", "jb_pipeline.py",
             "jb_resume_parser.py", "jb_sources.py", "jb_tailor.py", "jb_ui_style.py", "jb_mail.py", "companies.yaml", "config.yaml"]
_missing = [f for f in _REQUIRED if not os.path.exists(os.path.join(HERE, f))]
if _missing:
    st.error("These files are missing from your GitHub repo (upload them next to app.py): " + ", ".join(_missing))
    st.stop()

import jb_applier as applier  # noqa: E402
import jb_dashboard as dashboard  # noqa: E402
import jb_pipeline as pipeline  # noqa: E402
from jb_config import load_config  # noqa: E402
from jb_ui_style import CSS  # noqa: E402

st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)

BASE = load_config()
STATUS = {  # key: (label, colour)
    "applied": ("Applied", "#059669"), "unconfirmed": ("Submitted - verify", "#0891b2"),
    "blocked": ("Blocked (CAPTCHA/code)", "#d97706"), "manual_needed": ("Needs your input", "#ea580c"),
    "ready": ("Dry run OK", "#2563eb"), "found": ("Matched", "#4f46e5"),
    "failed": ("Failed", "#dc2626"), "skipped": ("Closed", "#94a3b8"),
}
AV = ["#4f46e5", "#7c3aed", "#0891b2", "#059669", "#d97706", "#db2777", "#2563eb", "#0d9488"]


# ---------------------------------------------------------------- helpers
def E(x):
    return html.escape(str(x if x is not None else "")).replace("$", "&#36;")


def secret(name):
    try:
        v = st.secrets.get(name)
    except Exception:
        v = None
    return v or os.environ.get(name)


for _k in ("GROQ_API_KEY", "GEMINI_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY"):
    _v = secret(_k)
    if _v:
        os.environ[_k] = str(_v)


def avcol(name):
    return AV[sum(ord(c) for c in (name or "?")) % len(AV)]


def score_color(s):
    return "#059669" if s >= 75 else "#4f46e5" if s >= 60 else "#d97706" if s >= 45 else "#94a3b8"


def chips(items, limit=8):
    return "".join(f'<span class="chip">{E(i)}</span>' for i in list(items)[:limit] if i)


def kpi(label, value, sub="", color="#4f46e5"):
    return (f'<div class="kpi" style="--c:{color}"><div class="v">{E(value)}</div>'
            f'<div class="l">{E(label)}</div><div class="s">{E(sub)}</div></div>')


def badge(status):
    lab, col = STATUS.get(status, (status, "#64748b"))
    return f'<span class="badge" style="background:{col}1a;color:{col};border:1px solid {col}55">{E(lab)}</span>'


def link(url, text, alt=False):
    if not url or not str(url).lower().startswith("http"):
        return ""
    return f'<a class="lnk{" alt" if alt else ""}" href="{E(url)}" target="_blank" rel="noopener">{E(text)}</a>'


def read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None


def feed_row(r):
    note = r["reason"] or ""
    lk = link(r["apply_url"] or r["url"], "Open", alt=True).replace('class="lnk alt"', 'class="lnk alt" style="margin:0"')
    return (f'<div class="feed"><div class="av" style="background:{avcol(r["company"])}">{E((r["company"] or "?")[:1].upper())}</div>'
            f'<div class="t">{E(r["company"])} · {E(r["title"])}<small>{E(note[:140])} &nbsp;·&nbsp; {E(r["updated_at"])}</small></div>'
            f'{badge(r["status"])}{lk}</div>')


# ---------------------------------------------------------------- session
ss = st.session_state
if "ws" not in ss:
    ss.ws = pipeline.new_workspace()
    ss.db = pipeline.open_db(ss.ws)
    ss.cache, ss.covers = {}, {}
    ss.runner = pipeline.Runner()
    ss.profile, ss.rhash, ss.resume_path = None, None, None
    ss.live_active, ss.last_snap, ss.live_mode = False, None, ""
    ss.browser_state = None
running = ss.runner.running

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown('<div class="brand"><div class="logo">🚀</div>JobBot</div>', unsafe_allow_html=True)
    up = st.file_uploader("Upload your resume (PDF)", type=["pdf"], help="Used for this session only.")

    with st.expander("👤 Your details (used to fill forms)"):
        linkedin = st.text_input("LinkedIn URL")
        github = st.text_input("GitHub URL")
        website = st.text_input("Portfolio / website")
        city = st.text_input("Current location", "India")
        org = st.text_input("Current / last organisation", "")
        c1, c2 = st.columns(2)
        pcode = c1.text_input("Phone code", "+91")
        notice = c2.text_input("Notice period", "Immediate")
        c3, c4 = st.columns(2)
        exp_ctc = c3.text_input("Expected CTC", "", placeholder="8 LPA")
        cur_ctc = c4.text_input("Current CTC", "", placeholder="optional")
        years = st.number_input("Years of experience", 0.0, 5.0, 1.0, 0.5)

    with st.expander("📝 Common application answers (saves 'needs input')"):
        grad = st.text_input("Graduation year", "")
        degree = st.text_input("Highest degree", "", placeholder="M.Sc Computer Science")
        univ = st.text_input("University / college", "")
        cgpa = st.text_input("CGPA / percentage", "")
        pref = st.text_input("Preferred job location", "", placeholder="Bengaluru, Hyderabad, Remote")
        a1, a2 = st.columns(2)
        auth = a1.selectbox("Authorized to work in India?", ["Yes", "No"])
        sponsor = a2.selectbox("Need visa sponsorship?", ["No", "Yes"])
        a3, a4 = st.columns(2)
        reloc = a3.selectbox("Willing to relocate?", ["Yes", "No"])
        onsite = a4.selectbox("OK with on-site / hybrid?", ["Yes", "No"])
        guess = st.toggle("Let JobBot answer unknown questions", True,
                          help="Uses AI (if you added a Groq/Gemini key) and your resume; otherwise safe defaults.")

    with st.expander("📧 E-mail for verification codes (optional)"):
        st.caption("Some Greenhouse forms e-mail a security code. JobBot can read it from Gmail. Use a Google "
                   "**App Password** (Google Account → Security → 2-Step Verification → App passwords), not your normal password.")
        mail_user = st.text_input("Gmail address", "")
        mail_pass = st.text_input("Gmail app password", "", type="password")

    with st.expander("🎯 Search preferences", expanded=True):
        min_score = st.slider("Minimum match score", 20, 90, 40, 5)
        max_years = st.select_slider("Max experience the job may require (yrs)", options=[0, 1, 2, 3], value=1)
        allow_remote = st.toggle("Include remote roles", True)
        incl_intern = st.toggle("Include internships", False)
        min_sal = st.number_input("Minimum salary (LPA, only if listed)", 0, 100, 0)
        queries = st.text_area("Role keywords for job feeds (one per line)", "\n".join(BASE["search_queries"]), height=110)

    with st.expander("🏢 Add company career pages"):
        extra = st.text_area("Paste career-page URLs or company names (one per line)",
                             placeholder="https://jobs.lever.co/mistral\nhttps://boards.greenhouse.io/anthropic\nhttps://company.com/careers",
                             height=110, help="JobBot detects Greenhouse / Lever / Ashby boards automatically.")

    with st.expander("🌐 Job sources"):
        s_gh = st.checkbox("Greenhouse company boards", True)
        s_lv = st.checkbox("Lever company boards", True)
        s_ab = st.checkbox("Ashby company boards", True)
        st.caption("Feeds below only give links (no auto-apply):")
        s_rm = st.checkbox("Remotive", False)
        s_ro = st.checkbox("RemoteOK", False)
        has_adz = bool(os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY"))
        s_az = st.checkbox("Adzuna India", False, disabled=not has_adz, help="Needs ADZUNA keys in secrets.")

    st.markdown('<div class="sbh">Mode</div>', unsafe_allow_html=True)
    mode = st.radio("mode", ["Find & tailor only", "Auto-apply - dry run (fill, don't submit)",
                             "Auto-apply - LIVE (submit)"], label_visibility="collapsed")
    max_n = st.slider("Applications this run", 5, 60, 20, 5)
    pause = st.slider("Pause between applications (sec)", 5, 60, (10, 20))
    per_co = st.select_slider("Max per company", options=[1, 2, 3], value=2)
    local_ok = os.name == "nt" or sys.platform == "darwin" or bool(os.environ.get("DISPLAY"))
    headed = False
    cwait = 0
    if local_ok:
        headed = st.toggle("Show the browser window", True,
                           help="Lets you watch, and solve a CAPTCHA yourself if one appears.")
        if headed:
            cwait = st.slider("Wait for me to solve a CAPTCHA (sec)", 0, 180, 60, 15)
    live_ok = True
    if "LIVE" in mode:
        live_ok = st.checkbox("I understand real applications will be submitted")
    auto = mode.startswith("Auto-apply")
    if auto and ss.browser_state is None:
        with st.spinner("Checking that a browser can start on this server ..."):
            ss.browser_state = applier.browser_check()
    bs = ss.browser_state
    browser_block = bool(auto and bs and not bs[0])
    if auto and bs and bs[0]:
        st.caption("✅ Browser ready – JobBot can apply from here.")
    run = st.button("▶  Run JobBot", type="primary",
                    disabled=(up is None or not live_ok or running or browser_block))
    if running and st.button("⏹  Stop after current job"):
        ss.runner.stop()

# ---------------------------------------------------------------- hero
st.markdown(
    '<div class="hero"><span class="tag">AI CAREER COPILOT</span><h1>Find. Tailor. Apply.</h1>'
    '<p>Upload your resume once. JobBot scans 150+ AI &amp; tech company career boards, ranks every opening against your skills, '
    'builds a tailored resume for each match, applies automatically and tracks every application live.</p>'
    '<span class="hp">Greenhouse</span><span class="hp">Lever</span><span class="hp">Ashby</span>'
    '<span class="hp">Tailored resume per job</span><span class="hp">Live dashboard</span></div>', unsafe_allow_html=True)

if browser_block:
    _root_has = os.path.exists(os.path.join(os.getcwd(), "packages.txt"))
    _app_has = os.path.exists(os.path.join(HERE, "packages.txt"))
    _where = ("packages.txt found at the top of your repo ✓ (then check Manage app → logs for apt errors)" if _root_has else
              "packages.txt is NOT at the top level of your repo ✗ - move ALL files to the top level (app.py, packages.txt, requirements.txt side by side)"
              if _app_has else "packages.txt is missing from your repo ✗ - upload it")
    st.markdown(
        f'<div class="card" style="border-color:#fde68a;background:#fffbeb"><h4>🔧 Fix for hosted apply</h4>'
        f'<p><b>{E(_where)}</b></p></div>', unsafe_allow_html=True)
    st.write("")
    st.markdown(
        '<div class="card" style="border-color:#fecaca;background:#fff7f7"><h4>🚫 This server cannot apply automatically</h4>'
        f'<p>Applying needs a real browser and this hosted server does not have one ({E((bs[1] or "")[:160])}). '
        'Run JobBot on your own computer instead – it takes about 5 minutes:<br>'
        '<b>1.</b> Install Python from python.org (tick “Add Python to PATH”) &nbsp; '
        '<b>2.</b> Download this repo as a ZIP and unzip it &nbsp; '
        '<b>3.</b> Double-click <b>start_windows.bat</b> (Mac/Linux: <b>start_mac_linux.sh</b>). '
        'The same app opens on your computer and applies for real.</p></div>', unsafe_allow_html=True)
    st.write("")

# ---------------------------------------------------------------- resume parse
if up is not None:
    data = up.getvalue()
    h = hashlib.md5(data).hexdigest()
    if h != ss.rhash:
        path = os.path.join(ss.ws, "resume.pdf")
        with open(path, "wb") as f:
            f.write(data)
        try:
            ss.profile = pipeline.build_profile(pipeline.make_cfg(ss.ws, path))
            ss.rhash, ss.resume_path = h, path
        except Exception as e:
            ss.profile, ss.rhash = None, None
            st.error(f"Could not read this resume: {e}")
else:
    if not running:
        ss.profile, ss.rhash = None, None
prof = ss.profile

# ---------------------------------------------------------------- landing
if prof is None:
    cols = st.columns(3)
    steps = [("1", "Upload", "Drop your resume PDF in the sidebar. Skills, contact details and experience are read automatically."),
             ("2", "Choose a mode", "Start with <b>Find &amp; tailor only</b>, then a <b>dry run</b>, then <b>LIVE</b> applying."),
             ("3", "Watch it work", "JobBot applies in the background and your dashboard updates live with every result.")]
    for c, (n, t, d) in zip(cols, steps):
        c.markdown(f'<div class="card step"><div class="n">{n}</div><div><h4>{t}</h4><p>{d}</p></div></div>', unsafe_allow_html=True)
    st.write("")
    cols = st.columns(4)
    for c, (t, d) in zip(cols, [("🔎 Smart matching", "Scores titles, skills, seniority, location and company."),
                                ("📝 Honest tailoring", "Reorders and highlights - never invents experience."),
                                ("🤖 Auto-apply", "Fills and submits Greenhouse, Lever and Ashby forms."),
                                ("📊 Live dashboard", "Applied, verify, blocked - with proof screenshots.")]):
        c.markdown(f'<div class="card"><h4>{t}</h4><p>{d}</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="foot">Upload a resume in the sidebar to begin.</div>', unsafe_allow_html=True)
    st.stop()

# ---------------------------------------------------------------- profile card
p1, p2 = st.columns([2, 3])
p1.markdown(f'<div class="card"><h4>👋 {E(prof["name"] or "Candidate")}</h4><p>{E(prof["email"])} &nbsp;·&nbsp; {E(prof["phone"])}</p>'
            f'<p style="margin-top:6px">Experience detected: <b>~{E(prof["years_experience"])} yrs</b></p></div>', unsafe_allow_html=True)
p2.markdown(f'<div class="card"><h4>🧠 {len(prof["skills"])} skills detected</h4>{chips(prof["skills"], 18)}</div>', unsafe_allow_html=True)
st.write("")

# ---------------------------------------------------------------- start a run (background thread)
if run:
    excl = [w for w in BASE["exclude_title_words"] if not (incl_intern and w == "intern")]
    enabled = [n for n, on in (("greenhouse", s_gh), ("lever", s_lv), ("ashby", s_ab), ("remotive", s_rm),
                               ("remoteok", s_ro), ("adzuna", s_az)) if on]
    do_apply = mode.startswith("Auto-apply")
    cfg = pipeline.make_cfg(ss.ws, ss.resume_path, {
        "min_match_score": min_score, "max_required_years": max_years, "allow_remote": allow_remote,
        "min_salary_lpa": min_sal, "exclude_title_words": excl, "enabled_sources": enabled,
        "search_queries": [q.strip() for q in queries.splitlines() if q.strip()] or BASE["search_queries"],
        "dry_run": "LIVE" not in mode, "max_applications_per_run": max_n, "max_per_company": per_co,
        "delay_between_applications": [pause[0], pause[1]],
        "headed": headed, "captcha_wait": cwait, "guess_unknown": guess,
        "mail": {"user": mail_user.strip(), "password": mail_pass.replace(" ", "")},
        "candidate": {"graduation_year": grad, "degree": degree, "university": univ, "cgpa": cgpa,
                      "preferred_location": pref, "work_authorized_india": auth, "needs_sponsorship": sponsor,
                      "willing_to_relocate": reloc, "onsite_ok": onsite,
                     "linkedin": linkedin, "github": github, "website": website, "city": city,
                      "current_company": org, "phone_country_code": pcode or "+91", "notice_period": notice,
                      "expected_ctc": exp_ctc, "current_ctc": cur_ctc, "years_experience": str(years)},
    })
    profile_now = pipeline.build_profile(cfg)
    ss.profile = profile_now
    ss.live_active, ss.live_mode = True, mode
    ss.runner.start(pipeline.run_job, cfg, profile_now, ss.db, ss.cache, ss.covers,
                    [x for x in extra.splitlines() if x.strip()], do_apply)
    st.rerun()


# ---------------------------------------------------------------- live view while the thread works
def counts_now():
    rows_ = ss.db.all()
    c = {}
    for r in rows_:
        c[r["status"]] = c.get(r["status"], 0) + 1
    return rows_, c


def live_view():
    snap = ss.runner.snapshot()
    rows_, c = counts_now()
    stage = {"scan": "Scanning company career boards", "tailor": "Tailoring resumes", "apply": "Applying to jobs",
             "starting": "Starting", "done": "Finishing"}.get(snap["stage"], "Working")
    st.markdown(f'<div class="card"><div class="live"><span class="dot"></span>{E(stage)} ...</div>'
                f'<p style="margin-top:6px">{E(snap["msg"])}</p></div>', unsafe_allow_html=True)
    st.progress(min(max(float(snap["pct"]), 0.0), 1.0))
    k = st.columns(4)
    for col, (lab, key, colr) in zip(k, [("Applied", "applied", "#059669"), ("Submitted - verify", "unconfirmed", "#0891b2"),
                                         ("Blocked", "blocked", "#d97706"), ("Needs input", "manual_needed", "#ea580c")]):
        col.markdown(kpi(lab, c.get(key, 0), "this session", colr), unsafe_allow_html=True)
    recent = [r for r in rows_ if r["status"] not in ("found",)][:6]
    if recent:
        st.markdown('<div class="sec">Latest results</div>' + "".join(feed_row(r) for r in recent), unsafe_allow_html=True)
    st.markdown('<div class="sec">Activity log</div><div class="logbox">' + E("\n".join(snap["log"][-14:])) + "</div>",
                unsafe_allow_html=True)
    if not ss.runner.running:
        st.rerun()


if ss.live_active:
    if ss.runner.running:
        st.fragment(run_every=2)(live_view)()
        st.stop()
    ss.live_active = False
    ss.last_snap = ss.runner.snapshot()

# ---------------------------------------------------------------- after-run banner
snap = ss.last_snap
if snap:
    if snap.get("error"):
        st.error(f"The run stopped with an error: {snap['error']} (results so far are saved below).")
    elif snap.get("browser") is False:
        st.warning("This server could not start a browser, so forms were not filled. Matches and tailored resumes are below. "
                   f"Reason: {snap.get('browser_error') or 'unknown'}. "
                   "Fix: run JobBot on your own computer (double-click start_windows.bat) or deploy with the Dockerfile.")
    elif snap.get("summary"):
        sm = snap["summary"]
        st.success(f"Run complete: {sm['raw']} postings scanned → {sm['new']} new matches.")

# ---------------------------------------------------------------- results
rows = ss.db.all()
if not rows:
    st.markdown('<div class="card"><h4>Ready when you are</h4><p>Choose your preferences in the sidebar and press <b>Run JobBot</b>. '
                'Start with “Find &amp; tailor only” to preview matches safely.</p></div>', unsafe_allow_html=True)
    st.stop()

df = pd.DataFrame(rows)
df["Status"] = df["status"].map(lambda s: STATUS.get(s, (s, ""))[0])
cnt = df["status"].value_counts().to_dict()
tabs = st.tabs(["📊 Overview", "📨 Applications", "💼 Jobs", "📄 Resumes", "⬇️ Export & Help"])

# ---- Overview
with tabs[0]:
    k = st.columns(6)
    vals = [("Applied", cnt.get("applied", 0), "confirmed submitted", "#059669"),
            ("Submitted - verify", cnt.get("unconfirmed", 0), "no confirmation seen", "#0891b2"),
            ("Blocked", cnt.get("blocked", 0), "CAPTCHA / code", "#d97706"),
            ("Needs input", cnt.get("manual_needed", 0), "open the link", "#ea580c"),
            ("Matches", len(df), "jobs tracked", "#4f46e5"),
            ("Tailored", int((df["resume_path"] != "").sum()), "resumes built", "#7c3aed")]
    for c, (l, v, s, colr) in zip(k, vals):
        c.markdown(kpi(l, v, s, colr), unsafe_allow_html=True)
    st.write("")
    a, b = st.columns(2)
    with a:
        st.markdown('<div class="sec" style="margin-top:.2rem">Pipeline status</div>', unsafe_allow_html=True)
        sdf = pd.DataFrame({"Status": [STATUS.get(s, (s, ""))[0] for s in cnt], "Count": list(cnt.values())})
        st.altair_chart(alt.Chart(sdf).mark_arc(innerRadius=62).encode(
            theta="Count:Q", color=alt.Color("Status:N", scale=alt.Scale(domain=[v[0] for v in STATUS.values()],
                                                                         range=[v[1] for v in STATUS.values()])),
            tooltip=["Status", "Count"]).properties(height=260))
    with b:
        st.markdown('<div class="sec" style="margin-top:.2rem">Top companies by matches</div>', unsafe_allow_html=True)
        top = df["company"].value_counts().head(8).reset_index()
        top.columns = ["Company", "Matches"]
        st.altair_chart(alt.Chart(top).mark_bar(cornerRadiusEnd=6, color="#4f46e5").encode(
            x="Matches:Q", y=alt.Y("Company:N", sort="-x"), tooltip=["Company", "Matches"]).properties(height=260))
    done_rows = [r for r in rows if r["status"] in ("applied", "unconfirmed", "blocked", "manual_needed", "ready", "failed")][:6]
    if done_rows:
        st.markdown('<div class="sec">Latest application activity</div>' + "".join(feed_row(r) for r in done_rows),
                    unsafe_allow_html=True)
    st.markdown('<div class="sec">🏆 Top picks for you</div>', unsafe_allow_html=True)
    picks = df.sort_values("score", ascending=False).head(6).to_dict("records")
    for i in range(0, len(picks), 3):
        cols = st.columns(3)
        for c, r in zip(cols, picks[i:i + 3]):
            with c:
                st.markdown(
                    f'<div class="jcard"><div class="jtop"><div class="av" style="background:{avcol(r["company"])}">'
                    f'{E((r["company"] or "?")[:1].upper())}</div><div class="jtx"><div class="jco">{E(r["company"])}</div>'
                    f'<div class="jti">{E(r["title"])}</div></div>'
                    f'<div class="ring" style="--p:{int(r["score"])};--c:{score_color(r["score"])}"><b>{int(r["score"])}</b></div></div>'
                    f'<div class="jmeta">📍 {E(r["location"] or "-")} &nbsp;·&nbsp; 💰 {E(r["salary"] or "not listed")}</div>'
                    f'<div>{chips([x for x in (r["matched"] or "").split(", ") if x], 5)}</div>'
                    f'<div style="margin-top:8px">{badge(r["status"])}</div>'
                    f'<div>{link(r["url"], "View job")}{link(r["apply_url"] if r["apply_url"] != r["url"] else "", "Apply page", True)}</div></div>',
                    unsafe_allow_html=True)
                if r["resume_path"]:
                    d = read_bytes(r["resume_path"])
                    if d:
                        st.download_button("Tailored resume", d, file_name=os.path.basename(r["resume_path"]),
                                           mime="application/pdf", key=f"pick_{r['job_key']}")

# ---- Applications
with tabs[1]:
    act = df[df["status"].isin(["applied", "unconfirmed", "blocked", "manual_needed", "ready", "failed"])]
    if act.empty:
        st.info("No application attempts yet. Choose an Auto-apply mode in the sidebar and run again.")
    else:
        sel_a = st.multiselect("Show", [STATUS[k][0] for k in ("applied", "unconfirmed", "blocked", "manual_needed", "ready", "failed")],
                               default=[STATUS["applied"][0], STATUS["unconfirmed"][0], STATUS["blocked"][0],
                                        STATUS["manual_needed"][0], STATUS["ready"][0]], key="app_sel")
        view = act[act["Status"].isin(sel_a)] if sel_a else act
        st.markdown("".join(feed_row(r) for r in view.head(60).to_dict("records")), unsafe_allow_html=True)
        st.caption(f"{len(view)} applications")
        shots = view[view["screenshot"] != ""].head(6)
        if not shots.empty:
            with st.expander("📸 Proof screenshots"):
                for _, r in shots.iterrows():
                    st.caption(f'{r["company"]} - {r["title"]} ({r["Status"]})')
                    if os.path.exists(r["screenshot"]):
                        st.image(r["screenshot"])

# ---- Jobs
with tabs[2]:
    f1, f2, f3 = st.columns([2, 2, 1])
    q = f1.text_input("Search company, title or skill", "", key="jq")
    sel = f2.multiselect("Status", [v[0] for v in STATUS.values()], default=[], key="js")
    mins = f3.number_input("Min score", 0, 100, 0, key="jm")
    v = df[df["score"] >= mins]
    if sel:
        v = v[v["Status"].isin(sel)]
    if q:
        hay = (v["company"] + " " + v["title"] + " " + v["matched"] + " " + v["location"]).str.lower()
        v = v[hay.str.contains(q.lower(), regex=False)]
    show = v.sort_values("score", ascending=False)[["Status", "score", "company", "title", "location", "salary", "matched", "apply_url"]]
    st.dataframe(show, hide_index=True, column_config={
        "score": st.column_config.ProgressColumn("Match", min_value=0, max_value=100, format="%d"),
        "company": "Company", "title": "Role", "location": "Location", "salary": "Salary", "matched": "Matched skills",
        "apply_url": st.column_config.LinkColumn("Link", display_text="Open ↗")})
    st.caption(f"{len(show)} jobs shown")

# ---- Resumes
with tabs[3]:
    rr = df[df["resume_path"] != ""].sort_values("score", ascending=False)
    if rr.empty:
        st.info("Tailored resumes will appear here after a run.")
    else:
        zdata = read_bytes(pipeline.zip_resumes(ss.ws))
        if zdata:
            st.download_button("⬇️ Download all tailored resumes (ZIP)", zdata, "tailored_resumes.zip",
                               mime="application/zip", type="primary")
        for _, r in rr.head(30).iterrows():
            c1, c2 = st.columns([5, 1])
            c1.markdown(f'**{E(r["company"])}** - {E(r["title"])} &nbsp; {badge(r["status"])}', unsafe_allow_html=True)
            d = read_bytes(r["resume_path"])
            if d:
                c2.download_button("PDF", d, file_name=os.path.basename(r["resume_path"]), mime="application/pdf",
                                   key=f"rs_{r['job_key']}")
        cv = [(k2, t) for k2, t in ss.covers.items() if t]
        if cv:
            with st.expander("✉️ Cover notes"):
                for k2, t in cv[:15]:
                    job = ss.cache.get(k2, ({"company": "", "title": ""},))[0]
                    st.markdown(f'**{E(job["company"])} - {E(job["title"])}**')
                    st.code(t, language=None)

# ---- Export & Help
with tabs[4]:
    e1, e2 = st.columns(2)
    dpath = dashboard.write_dashboard(ss.db.all(), ss.ws)
    e1.download_button("📄 Standalone HTML dashboard", read_bytes(dpath), "jobbot_dashboard.html", mime="text/html")
    e2.download_button("📊 Applications CSV (keep this!)", read_bytes(os.path.join(ss.ws, "applications.csv")),
                       "applications.csv", mime="text/csv")
    st.markdown("##### Restore previous history")
    st.caption("Hosted apps forget data between sessions. Upload your last exported CSV so JobBot never re-applies to the same job.")
    hist = st.file_uploader("applications.csv", type=["csv"], key="hist")
    if hist is not None and st.button("Import history"):
        try:
            n = ss.db.import_history(list(csv.DictReader(io.StringIO(hist.getvalue().decode("utf-8", "ignore")))))
            st.success(f"Imported {n} records.")
        except Exception as e:
            st.error(f"Could not import: {e}")
    st.markdown("##### Good to know")
    st.markdown(
        "- Auto-apply covers **Greenhouse, Lever and Ashby** forms (the career pages of most AI companies).\n"
        "- **Applied** = a confirmation was detected. **Submitted - verify** = Submit was clicked but no confirmation was shown.\n"
        "- **CAPTCHA, e-mail codes and unusual required questions** can't be automated: those are flagged with a link.\n"
        "- Keep this tab open during a run and download the CSV afterwards.\n"
        "- LinkedIn, Naukri and Indeed are not automated (terms of service / account bans).")

st.markdown('<div class="foot">JobBot · review your applications · built with Streamlit</div>', unsafe_allow_html=True)
