"""Browser auto-fill + submit for Greenhouse / Lever / Ashby application forms (Playwright).

Outcomes (status):
  applied       confirmation page/text detected
  unconfirmed   Submit was clicked but no confirmation was seen (often still submitted - verify)
  blocked       CAPTCHA / e-mail verification code stopped it
  manual_needed a required question the bot cannot answer, or form not recognised
  ready         dry run: form filled, not submitted
  skipped       job closed
  failed        unexpected error
"""
import os
import random
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor

FIELDS_JS = """
() => {
  const out = []; let i = 0;
  document.querySelectorAll('[data-jb]').forEach(e => e.removeAttribute('data-jb'));
  for (const el of document.querySelectorAll('input, textarea, select')) {
    const type = (el.getAttribute('type') || el.tagName).toLowerCase();
    if (['hidden','submit','button','image','reset'].includes(type)) continue;
    const st = window.getComputedStyle(el);
    const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && st.visibility !== 'hidden';
    if (!visible && type !== 'file') continue;
    let label = '';
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) label = l.innerText; }
    if (!label) { const p = el.closest('label'); if (p) label = p.innerText; }
    if (!label) { const lb = el.getAttribute('aria-labelledby'); if (lb) { const n = document.getElementById(lb.split(' ')[0]); if (n) label = n.innerText; } }
    if (!label) { let c = el.parentElement; for (let k = 0; k < 3 && c && !label; k++) { const l = c.querySelector('label'); if (l && !l.contains(el)) label = l.innerText; c = c.parentElement; } }
    let group = '';
    if (type === 'radio' || type === 'checkbox') {
      const g = el.closest('fieldset, [role="radiogroup"], [role="group"]');
      if (g) { const lg = g.querySelector('legend'); group = (lg ? lg.innerText : (g.getAttribute('aria-label') || (g.firstElementChild ? g.firstElementChild.innerText : ''))) || ''; }
    }
    const combo = el.getAttribute('role') === 'combobox' || el.getAttribute('aria-haspopup') === 'listbox' || el.getAttribute('aria-autocomplete') === 'list';
    el.setAttribute('data-jb', String(i));
    out.push({i, tag: el.tagName.toLowerCase(), type, label: (label || '').trim(), group: group.trim(), combo,
      name: el.name || '', id: el.id || '', placeholder: el.placeholder || '', aria: el.getAttribute('aria-label') || '',
      required: !!(el.required || el.getAttribute('aria-required') === 'true' || /\\*/.test(label || '')),
      value: el.value || '', checked: !!el.checked,
      options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => o.text) : []});
    i++;
  }
  return out;
}
"""

ERRORS_JS = """
() => Array.from(document.querySelectorAll('[role="alert"], .error, .errors, [class*="error" i], [aria-invalid="true"]'))
  .map(e => (e.innerText || '').trim()).filter(t => t && t.length < 160).slice(0, 4)
"""

SUCCESS = ["application has been submitted", "thank you for applying", "thanks for applying",
           "application received", "successfully submitted", "thank you for your application",
           "we've received your application", "we have received your application", "application submitted",
           "your application was sent", "thanks for your interest", "application was submitted",
           "we'll be in touch", "we will be in touch"]
BLOCKERS = {"captcha": "CAPTCHA", "verify you are human": "CAPTCHA", "i'm not a robot": "CAPTCHA",
            "security code": "an e-mail verification code", "verification code": "an e-mail verification code",
            "confirm you're a human": "CAPTCHA"}
CLOSED = ("no longer available", "no longer accepting", "job not found", "page not found",
          "position has been filled", "this job is closed", "job posting is no longer")
LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
JOB_DEADLINE = 170  # seconds per application


# ------------------------------------------------------------------ field decisions
def desc_of(f):
    return " ".join([f["label"], f["name"], f["id"], f["placeholder"], f["aria"]]).lower()


def candidate_values(profile, cfg, job, cover):
    c = cfg.get("candidate", {})
    cc = c.get("phone_country_code", "+91")
    phone = profile.get("phone", "")
    return {
        "first": profile["first_name"], "last": profile["last_name"], "full": profile["name"],
        "email": profile["email"], "phone": f"{cc}{phone}" if phone else "", "phone_plain": phone,
        "linkedin": c.get("linkedin", ""), "github": c.get("github", ""),
        "website": c.get("website", "") or c.get("github", "") or c.get("linkedin", ""),
        "city": c.get("city", ""), "company": c.get("current_company", ""),
        "years": str(c.get("years_experience", "1")), "notice": c.get("notice_period", ""),
        "expected": c.get("expected_ctc", ""), "current": c.get("current_ctc", ""),
        "authorized": c.get("work_authorized_india", "Yes"), "sponsor": c.get("needs_sponsorship", "No"),
        "relocate": c.get("willing_to_relocate", "Yes"), "cover": cover,
        "grad_year": str(c.get("graduation_year", "")), "degree": c.get("degree", ""),
        "university": c.get("university", ""), "cgpa": str(c.get("cgpa", "")),
        "onsite": c.get("onsite_ok", "Yes"), "pref_loc": c.get("preferred_location", "") or c.get("city", ""),
    }


def yes_no_for(q, v):
    q = q.lower()
    if "sponsor" in q:
        return v["sponsor"]
    if any(w in q for w in ("authorized", "authorised", "legally", "eligible to work", "right to work")):
        return v["authorized"]
    if "relocat" in q:
        return v["relocate"]
    if any(w in q for w in ("18 years", "above 18", "over 18")):
        return "Yes"
    if any(w in q for w in ("onsite", "on-site", "in-office", "in office", "hybrid", "work from office")):
        return v["onsite"]
    return None


def decide(f, v, cfg):
    """-> ('text'|'select'|'check'|'file'|'skip'|'unknown', value). A <select> never gets a 'text' action."""
    kind, val = _decide(f, v, cfg)
    if kind == "text" and f["tag"] == "select":
        kind = "select"
    return kind, val


def _decide(f, v, cfg):
    d = desc_of(f) + " " + f["group"].lower()
    t = f["type"]
    for ca in cfg.get("custom_answers", []) or []:
        if str(ca.get("match", "")).strip() and str(ca["match"]).lower() in d:
            return ("select" if t == "select" else "text"), str(ca.get("answer", ""))
    if t == "file":
        if "cover" in d:
            return "skip", ""
        return "file", ""
    if t == "checkbox":
        if any(w in d for w in ("agree", "consent", "privacy", "terms", "acknowledge", "confirm", "certify", "accurate")):
            return "check", ""
        return "skip", ""
    if t == "radio":
        a = yes_no_for(d, v)
        return ("text", a) if a else ("unknown", "")
    if any(w in d for w in ("gender", "race", "ethnic", "veteran", "disabilit", "pronoun", "sexual", "orientation", "lgbt")):
        return ("select" if (t == "select" or f.get("combo")) else "skip"), "decline"
    rules = [
        (("first name", "first_name", "firstname", "given name"), "first"),
        (("last name", "last_name", "lastname", "surname", "family name"), "last"),
        (("full name", "your name", "legal name"), "full"),
        (("email",), "email"),
        (("phone", "mobile", "contact number"), "phone"),
        (("linkedin",), "linkedin"), (("github",), "github"),
        (("portfolio", "website", "personal site", "url"), "website"),
        (("current company", "current employer", "employer", "organization", "organisation"), "company"),
        (("current location", "location", "city", "where are you based", "residence"), "city"),
        (("cover letter", "why do you want", "why are you interested", "additional information", "tell us about"), "cover"),
        (("notice",), "notice"),
        (("graduation", "passing year", "year of passing"), "grad_year"),
        (("highest degree", "degree", "qualification"), "degree"),
        (("university", "college", "institution", "school"), "university"),
        (("cgpa", "gpa", "percentage", "grade"), "cgpa"),
        (("preferred location", "preferred city", "location preference"), "pref_loc"),
    ]
    for keys, name in rules:
        if any(k in d for k in keys):
            return ("select" if t == "select" else "text"), v[name]
    if "expected" in d and any(w in d for w in ("ctc", "salary", "compensation", "pay")):
        return "text", v["expected"]
    if "current" in d and any(w in d for w in ("ctc", "salary", "compensation")):
        return "text", v["current"]
    if "year" in d and "experience" in d:
        return "text", v["years"]
    if f["label"].lower().strip(" *") == "name" or f["name"].lower() == "name":
        return "text", v["full"]
    a = yes_no_for(d, v)
    if a:
        return ("select" if t == "select" else "text"), a
    return "unknown", ""


def pick_option(options, wanted):
    w = (wanted or "").lower()
    opts = [o for o in options if o.strip() and not re.match(r"^(select|choose|please)", o.strip().lower())]
    if w == "decline":
        for o in opts:
            if re.search(r"decline|prefer not|don't wish|do not wish|not to (say|answer|disclose)", o.lower()):
                return o
        return None
    for o in opts:
        if o.lower().strip() == w:
            return o
    if re.fullmatch(r"\d+(\.\d+)?", w):  # numeric answer -> option whose range contains it ("0-1", "1-3", "3+")
        n = float(w)
        for o in opts:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to|–)\s*(\d+(?:\.\d+)?)", o)
            if m and float(m.group(1)) <= n <= float(m.group(2)):
                return o
            m = re.search(r"(\d+(?:\.\d+)?)\s*\+", o)
            if m and n >= float(m.group(1)):
                return o
    for o in opts:
        if w and (w in o.lower() or o.lower() in w):
            return o
    if "hear" in w or w == "company website":
        for o in opts:
            if re.search(r"website|other|career|job board|linkedin", o.lower()):
                return o
    return None


# ------------------------------------------------------------------ page helpers
def page_text(page):
    try:
        return page.inner_text("body", timeout=5000).lower()
    except Exception:
        return ""


def pause(page, lo=80, hi=240):
    try:
        page.wait_for_timeout(random.randint(lo, hi))
    except Exception:
        pass


def fill_combo(page, loc, val):
    """React-select style dropdowns (input role=combobox). Returns True if an option was chosen."""
    loc.click(timeout=4000)
    if val and val != "decline":
        loc.fill(val, timeout=4000)
    page.wait_for_timeout(500)
    opts = page.locator('[role="option"]')
    n = min(opts.count(), 60)
    texts = [opts.nth(i).inner_text().strip() for i in range(n)]
    pick = pick_option(texts, val)
    if pick is None and val not in ("decline",) and n == 1:
        pick = texts[0]
    if pick is None:
        loc.press("Escape")
        return False
    opts.nth(texts.index(pick)).click(timeout=4000)
    return True


RADIO_JS = ("(n) => Array.from(document.querySelectorAll('input[type=radio]')).filter(e => e.name === n)"
            ".map(e => { const l = e.id ? document.querySelector('label[for=\"' + CSS.escape(e.id) + '\"]') : null;"
            " return {jb: e.getAttribute('data-jb'), t: ((l ? l.innerText : (e.closest('label') ? e.closest('label').innerText : e.value)) || '').trim()}; })")


def guess_text(f, v, cfg):
    """Last-resort answer for an unknown REQUIRED text field (can be switched off in settings)."""
    if not cfg.get("guess_unknown", True):
        return None
    d = desc_of(f) + " " + f["group"].lower()
    if f["tag"] == "textarea":
        return (v["cover"] or "Please refer to my resume for details.")[:900]
    if any(w in d for w in ("ctc", "salary", "compensation", "pay")):
        return v["expected"] or "Negotiable"
    if any(w in d for w in ("linkedin", "github", "portfolio", "website", "url", "link")):
        return v["website"] or "N/A"
    if "year" in d or f["type"] in ("number", "tel"):
        return v["years"]
    return "N/A"


def fill_form(page, profile, cfg, job, cover, resume_path, deadline):
    """Returns (filled_count, unknown_required_labels)."""
    fields = page.evaluate(FIELDS_JS)
    v = candidate_values(profile, cfg, job, cover)
    filled, unknown, radio_done = 0, [], set()

    def ask(question, options):
        fn = cfg.get("answerer")
        if not fn:
            return None
        try:
            return fn(profile, job, question, options)
        except Exception:
            return None
    for f in fields:
        if time.time() > deadline:
            unknown.append("(timed out filling form)")
            break
        loc = page.locator(f'[data-jb="{f["i"]}"]')
        kind, val = decide(f, v, cfg)
        label = f["label"] or f["name"] or f["placeholder"] or kind
        try:
            if kind == "file":
                loc.set_input_files(resume_path, timeout=8000)
                filled += 1
            elif f["type"] == "radio" and kind == "text":
                if f["name"] in radio_done:
                    continue
                opts = page.evaluate(RADIO_JS, f["name"])
                hit = next((o for o in opts if o["t"].lower().startswith(val.lower())), None)
                if hit:
                    page.locator(f'[data-jb="{hit["jb"]}"]').check(force=True, timeout=4000)
                    radio_done.add(f["name"]); filled += 1
                elif f["required"]:
                    unknown.append(f["group"] or label)
            elif kind in ("text", "select") and f.get("combo"):
                if not val and f["required"]:
                    unknown.append(label)
                elif val:
                    if fill_combo(page, loc, val):
                        filled += 1
                    elif f["required"]:
                        unknown.append(label + " (option not found)")
            elif kind == "text":
                if not val:
                    if f["required"]:
                        unknown.append(label)
                    continue
                loc.fill(val, timeout=6000)
                filled += 1
                pause(page)
            elif kind == "select":
                if f["tag"] == "select":
                    opt = pick_option(f["options"], val)
                    if opt:
                        loc.select_option(label=opt, timeout=5000); filled += 1
                    elif f["required"]:
                        unknown.append(label)
                elif val and val != "decline":
                    loc.fill(val, timeout=6000); filled += 1
            elif kind == "check":
                loc.check(force=True, timeout=4000); filled += 1
            elif kind == "unknown":
                if not f["required"]:
                    continue
                if f["type"] == "radio":
                    if f["name"] in radio_done:
                        continue
                    opts = page.evaluate(RADIO_JS, f["name"])
                    ans = ask(f["group"] or label, [o["t"] for o in opts])
                    hit = None
                    if ans:
                        pick = pick_option([o["t"] for o in opts], ans)
                        hit = next((o for o in opts if o["t"] == pick), None)
                    if hit:
                        page.locator(f'[data-jb="{hit["jb"]}"]').check(force=True, timeout=4000)
                        radio_done.add(f["name"]); filled += 1
                    else:
                        unknown.append(f["group"] or label)
                elif f["tag"] == "select":
                    ans = ask(label, [o for o in f["options"] if o.strip()])
                    pick = pick_option(f["options"], ans) if ans else None
                    if pick:
                        loc.select_option(label=pick, timeout=5000); filled += 1
                    else:
                        unknown.append(label)
                elif f.get("combo"):
                    unknown.append(label)
                elif not (f["value"] or "").strip() and not f["checked"]:
                    ans = ask(label, None) or guess_text(f, v, cfg)
                    if ans:
                        loc.fill(ans[:1500], timeout=6000); filled += 1; pause(page)
                    else:
                        unknown.append(label)
        except Exception:
            if f["required"] or kind == "file":
                unknown.append(label + " (could not fill)")
    seen, uniq = set(), []
    for u in unknown:
        u = re.sub(r"\s+", " ", (u or "").strip())[:80]
        if u and u not in seen:
            seen.add(u); uniq.append(u)
    return filled, uniq


def click_submit(page):
    for sel in ['button[type="submit"]', 'input[type="submit"]',
                'button:has-text("Submit application")', 'button:has-text("Submit Application")',
                'button:has-text("Submit")', 'button:has-text("Apply")']:
        try:
            b = page.locator(sel).last
            if b.count() and b.is_visible():
                b.scroll_into_view_if_needed(timeout=3000)
                b.click(timeout=8000)
                return True
        except Exception:
            continue
    return False


def wait_for_outcome(page, seconds=14):
    """Polls for a confirmation message after Submit."""
    end = time.time() + seconds
    while time.time() < end:
        txt = page_text(page)
        if any(s in txt for s in SUCCESS) or re.search(r"/(confirmation|thanks|thank-you|submitted)", page.url.lower()):
            return True, txt
        page.wait_for_timeout(1000)
    return False, page_text(page)


CODE_HINTS = ("security code", "verification code", "enter the code", "8-character code", "confirm your email")


def enter_code(page, code):
    """Types a verification code into 6-10 single-character boxes, or one code input."""
    try:
        boxes = page.locator('input[maxlength="1"]')
        if boxes.count() >= 6:
            boxes.first.click()
            page.keyboard.type(code, delay=90)
            return True
        for sel in ['input[autocomplete="one-time-code"]', 'input[name*="code" i]', 'input[id*="code" i]',
                    'input[id*="security" i]', 'input[name*="security" i]']:
            loc = page.locator(sel).first
            if loc.count():
                loc.fill(code, timeout=4000)
                return True
    except Exception:
        pass
    return False


def apply_one(page, job, profile, cfg, resume_path, cover, shot_dir):
    """-> (status, reason, screenshot_path)"""
    deadline = time.time() + JOB_DEADLINE
    page.goto(job["apply_url"], wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3500)
    if len(page.evaluate(FIELDS_JS)) < 3:  # maybe an 'Apply' button must be clicked first
        for sel in ['a:has-text("Apply for this job")', 'button:has-text("Apply for this job")',
                    'a:has-text("Apply now")', 'button:has-text("Apply now")', 'a:has-text("Apply")',
                    'button:has-text("Apply")']:
            try:
                if page.locator(sel).first.count():
                    page.locator(sel).first.click(timeout=5000)
                    page.wait_for_timeout(3000)
                    break
            except Exception:
                continue
    txt = page_text(page)
    if any(w in txt for w in CLOSED):
        return "skipped", "job closed / page not found", ""
    filled, unknown = fill_form(page, profile, cfg, job, cover, resume_path, deadline)
    if filled < 3:
        return "manual_needed", "could not recognise the application form", ""
    if unknown:
        return "manual_needed", "needs your answer: " + "; ".join(unknown[:6]), ""
    shot = os.path.join(shot_dir, f"{job['key']}.png")
    if cfg.get("dry_run", True):
        try:
            page.screenshot(path=shot, full_page=True)
        except Exception:
            shot = ""
        return "ready", f"form filled ({filled} fields); NOT submitted (dry run)", shot
    if not click_submit(page):
        return "manual_needed", "submit button not found", ""
    t_submit = time.time()
    ok, txt = wait_for_outcome(page, 12)
    mail = cfg.get("mail") or {}
    if not ok and any(k in txt for k in CODE_HINTS):
        if mail.get("user") and mail.get("password"):
            from jb_mail import fetch_code
            code = fetch_code(mail["user"], mail["password"], t_submit, timeout=90)
            if code and enter_code(page, code):
                page.wait_for_timeout(600)
                click_submit(page)
                ok, txt = wait_for_outcome(page, 15)
        else:
            return "blocked", "needs an e-mail verification code - add your Gmail + app password in the sidebar", ""
    if not ok and cfg.get("captcha_wait", 0) > 0 and cfg.get("headed"):
        ok, txt = wait_for_outcome(page, int(cfg["captcha_wait"]))  # you can solve a CAPTCHA in the open window
    try:
        page.screenshot(path=shot, full_page=True)
    except Exception:
        shot = ""
    if ok:
        return "applied", "submitted - confirmation detected", shot
    for k, why in BLOCKERS.items():
        if k in txt:
            return "blocked", f"stopped by {why} - finish manually via the link", shot
    try:
        errs = [e for e in page.evaluate(ERRORS_JS) if e]
    except Exception:
        errs = []
    if errs:
        return "manual_needed", "form rejected: " + " | ".join(errs)[:150], shot
    return "unconfirmed", "submit clicked, no confirmation shown (a CAPTCHA may have blocked it) - verify via the link", shot


# ------------------------------------------------------------------ browser management
def chromium_path():
    for n in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        p = shutil.which(n)
        if p:
            return p
    return None


def _launch(pw, headless=True):
    try:
        return pw.chromium.launch(headless=headless, args=LAUNCH_ARGS)
    except Exception:
        p = chromium_path()
        if p:
            try:
                return pw.chromium.launch(executable_path=p, headless=headless, args=LAUNCH_ARGS)
            except Exception:
                pass
        if not headless:  # no display available -> fall back to headless
            return _launch(pw, True)
        raise


def _check():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = _launch(pw)
        b.close()
    return True


def _try_check():
    with ThreadPoolExecutor(max_workers=1) as ex:
        ex.submit(_check).result(timeout=120)


def _install_chromium():
    """Last resort on hosts without a system chromium: download Playwright's own copy."""
    import subprocess
    import sys
    try:
        p = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                           capture_output=True, text=True, timeout=600)
        return p.returncode == 0, " ".join((p.stderr or p.stdout or "").split())[-200:]
    except Exception as e:
        return False, str(e)[:200]


def browser_check():
    """-> (ok, reason). Launches a headless browser once to prove it works; reason explains a failure."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False, "the 'playwright' Python package is not installed (check requirements.txt)"
    try:
        _try_check()
        return True, ""
    except Exception as e:
        first = " ".join(str(e).split())[:260] or type(e).__name__
    if "Executable doesn't exist" in first or "playwright install" in first:
        ok, info = _install_chromium()
        if ok:
            try:
                _try_check()
                return True, ""
            except Exception as e2:
                first = " ".join(str(e2).split())[:260] or type(e2).__name__
        else:
            first = f"Chromium is missing and could not be downloaded ({info})"
    return False, first


def browser_available():
    return browser_check()[0]


def _batch(items, profile, cfg, on_result, log, stop=None):
    from playwright.sync_api import sync_playwright
    shot_dir = os.path.join(cfg["data_dir"], "screenshots")
    os.makedirs(shot_dir, exist_ok=True)
    with sync_playwright() as pw:
        browser = _launch(pw, headless=not cfg.get("headed", False))
        for n, (job, resume_path, cover) in enumerate(items, 1):
            if stop is not None and stop():
                log("stopped by user")
                break
            ctx = browser.new_context(viewport={"width": 1366, "height": 900}, locale="en-IN", user_agent=UA)
            page = ctx.new_page()
            page.set_default_timeout(15000)
            try:
                status, reason, shot = apply_one(page, job, profile, cfg, resume_path, cover, shot_dir)
            except Exception as e:
                status, reason, shot = "failed", f"error: {str(e)[:120]}", ""
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
            on_result(job, status, reason, shot)
            log(f"[{n}/{len(items)}] {status:<13} {job['company']} - {job['title']} :: {reason[:90]}")
            if n < len(items) and not cfg.get("dry_run", True):
                lo, hi = cfg.get("delay_between_applications", [10, 20])
                time.sleep(random.uniform(lo, hi))
        browser.close()


def apply_all(items, profile, cfg, on_result, log=print, stop=None):
    """Runs Playwright in a worker thread so it also works inside Jupyter/Streamlit event loops."""
    if not items:
        return
    with ThreadPoolExecutor(max_workers=1) as ex:
        ex.submit(_batch, items, profile, cfg, on_result, log, stop).result()
