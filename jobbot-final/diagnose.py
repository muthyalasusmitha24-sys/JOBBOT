"""Tries ONE real application form and tells you exactly what happens, step by step.

    python diagnose.py "<apply page URL>" "<path to resume.pdf>"            (fills the form, does NOT submit)
    python diagnose.py "<apply page URL>" "<path to resume.pdf>" --live     (really submits)
    add --headless to hide the browser window

Paste the whole output back to the developer: it shows which fields were found, what was filled, and why it stopped.
"""
import os
import sys
import tempfile

import jb_applier as A
import jb_pipeline as P


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        return
    url, resume = args[0], args[1]
    live = "--live" in sys.argv
    headless = "--headless" in sys.argv
    out = tempfile.mkdtemp(prefix="jobbot_diag_")
    cfg = P.make_cfg(out, resume, {"dry_run": not live, "headed": not headless, "captcha_wait": 90,
                                   "candidate": {"city": "India"}})
    prof = P.build_profile(cfg)
    print(f"Resume: {prof['name']} | {prof['email']} | phone {prof['phone']}")
    print(f"Mode: {'LIVE (will submit)' if live else 'DRY RUN (will not submit)'} | window: {'hidden' if headless else 'visible'}\n")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = A._launch(pw, headless=headless)
        page = b.new_context(viewport={"width": 1366, "height": 900}, user_agent=A.UA).new_page()
        page.set_default_timeout(15000)
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(4000)
        print("Page title:", page.title())
        fields = page.evaluate(A.FIELDS_JS)
        print(f"\nFound {len(fields)} form fields:")
        v = A.candidate_values(prof, cfg, {}, "cover")
        for f in fields:
            kind, val = A.decide(f, v, cfg)
            lab = (f["label"] or f["name"] or f["placeholder"] or f["id"])[:55].replace("\n", " ")
            print(f"  [{f['type']:<8}] {'REQ' if f['required'] else '   '} {lab:<55} -> {kind}{(': ' + str(val)[:25]) if val else ''}")
        txt = A.page_text(page)
        print("\nCAPTCHA words on page:", [k for k in A.BLOCKERS if k in txt] or "none visible yet")
        b.close()

    job = {"key": "diag", "company": "Test", "title": "Test", "apply_url": url, "url": url, "description": ""}
    res = []
    print("\nRunning the real apply routine ...")
    A.apply_all([(job, resume, "I am excited about this role and believe my skills are a strong fit.")], prof, cfg,
                lambda j, s, r, sh: res.append((s, r, sh)), print)
    s, r, sh = res[0]
    print(f"\n=== RESULT: {s} ===\n{r}")
    shots = os.path.join(out, "screenshots")
    print("Screenshots folder:", shots if os.path.isdir(shots) else "(none)")


if __name__ == "__main__":
    main()
