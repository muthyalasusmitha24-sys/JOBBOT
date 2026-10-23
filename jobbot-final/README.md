---
title: JobBot
emoji: 🚀
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# 🚀 JobBot — AI Career Copilot

Upload a resume → JobBot scans **150+ AI & tech company career boards** (Greenhouse · Lever · Ashby), ranks every
opening against your skills, builds a **tailored resume per job**, **applies automatically** and shows every result in a
**live dashboard** (Applied · Submitted-verify · Blocked · Needs input).

## ⚡ Quick start (the way that really applies)
1. Install Python (python.org, tick *Add Python to PATH*).  2. Unzip this repo.  3. Double-click **`start_windows.bat`**
(Mac/Linux: `./start_mac_linux.sh`).  The app opens in your browser: upload your resume, fill *Common application answers*,
choose **Auto-apply – LIVE**, press **Run**.  Applications appear on the dashboard as they complete.

* **Show the browser window** (on by default locally) – if a site shows a CAPTCHA you can solve it and JobBot continues.
* **E-mail codes** – add a Gmail *app password* in the sidebar so JobBot can read Greenhouse security codes.
* **Unknown questions** – answered from your resume by AI (add a free `GROQ_API_KEY`), otherwise safe defaults.

**Google Colab:** open `JobBot_Colab.ipynb` in Colab and run the cells top to bottom (headless, no CAPTCHA solving).

**Something not working?** Run `python diagnose.py "<job apply URL>" "<resume.pdf>"` – it tries one real form and prints exactly what happened.

## Files (all in the repo root; only `.streamlit/` is a folder)
`app.py` · `jb_*.py` (10 files) · `companies.yaml` · `config.yaml` · `requirements.txt` · `packages.txt` · `Dockerfile` · `.streamlit/config.toml`

## Why a browser is needed
Applying means opening the company's form, filling it and clicking Submit. That needs a headless Chromium.
The plain Streamlit Cloud image has none, so JobBot could only show links. This repo fixes that three ways:

| Where | Auto-apply | How |
|---|---|---|
| **Your own computer** (best success rate – your home IP) | ✅ | see *Run locally* |
| **Hugging Face Space (Docker)** | ✅ | see *Deploy on Hugging Face* |
| **Streamlit Community Cloud** | ⚠️ best effort | `packages.txt` installs Chromium; if the server can't start it the app says so |

## Run locally (recommended for LIVE applying)
**Windows:** install Python from python.org (tick *Add Python to PATH*), then double-click `start_windows.bat`.
**Mac/Linux:** `./start_mac_linux.sh`.  Or manually:
```bash
pip install -r requirements.txt
playwright install chromium
streamlit run app.py
```

## Deploy on Hugging Face (free, full auto-apply)
1. Create a free account at huggingface.co → **New Space** → name `jobbot` → SDK **Docker → Blank** → Public.
2. **Files → Add file → Upload files**: upload everything from this repo (including `Dockerfile`, `README.md`, `.streamlit/config.toml`).
3. Wait for the build (~5-8 min). Your app opens at `https://huggingface.co/spaces/<you>/jobbot`.
4. Optional: Space **Settings → Secrets** (name = key name, value = your key): `GROQ_API_KEY` or `GEMINI_API_KEY`
   (better summaries/cover notes – NOT required for applying), `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`.

**Hugging Face troubleshooting**
- SDK must be **Docker** (not Streamlit/Gradio). Wrong SDK = no browser.
- Uploading in the website needs **no token**. If you use `git push`, use a token with **Write** permission as the password.
- Never paste keys into the code – only into Settings → Secrets.
- If the Space shows an error, open the Space → **Logs** (Build / Container) and read the last 20 lines.

## Deploy on Streamlit Community Cloud
share.streamlit.io → Create app → repo, branch `main`, file `app.py` → Advanced → Python 3.11 → Deploy.
If the build log complains about `packages.txt`, delete that file (the app still works for matching + tailoring).

## How to use
1. Upload your resume, fill **Your details** (LinkedIn, expected CTC …).
2. Add more companies: paste any career-page URL in **Add company career pages**.
3. Run **Find & tailor only** → check matches → **Dry run** (forms filled, nothing sent) → **LIVE**.
4. Watch the live panel; then use **Applications** and **Export** (keep `applications.csv`, import it next time).

## Honest limits
- Auto-submit covers Greenhouse / Lever / Ashby. Some companies add a CAPTCHA or e-mail code: those are marked **Blocked** with a link.
- **Applied** = confirmation detected. **Submitted – verify** = Submit clicked, no confirmation shown.
- LinkedIn, Naukri, Indeed are not automated (their terms ban it and accounts get blocked).
- Hosted servers forget data between sessions – download the CSV.
