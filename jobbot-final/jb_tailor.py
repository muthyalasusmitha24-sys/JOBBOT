"""Tailors the resume for each job WITHOUT inventing anything:
 - re-orders skills so the ones the job asks for come first
 - re-orders bullets inside each project/experience entry by relevance
 - rewrites the summary using only skills that are really in the resume
 - (optional) Gemini rewrites the summary/cover note, constrained to resume facts; falls back to template.
Falls back to the original PDF if anything looks off."""
import json
import os
import re
import shutil
from xml.sax.saxutils import escape

import requests
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

BULLET = "\u2022"


def safe(s):
    s = (s or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u2011", "-")
    return escape(s.encode("cp1252", "ignore").decode("cp1252"))


def slug(s, n=40):
    return re.sub(r"[^A-Za-z0-9]+", "_", s or "").strip("_")[:n] or "x"


def group_entries(lines):
    """Turn raw lines of experience/projects into [(heading_lines, [bullets])]."""
    entries, cur = [], None
    bullet_open = False
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith(BULLET):
            if cur is None:
                cur = {"head": [], "bullets": []}
                entries.append(cur)
            cur["bullets"].append(ln.lstrip(BULLET).strip())
            bullet_open = True
            continue
        if bullet_open and cur and cur["bullets"]:
            last = cur["bullets"][-1]
            if not last.endswith((".", ";")) or ln[:1].islower():
                cur["bullets"][-1] = last + " " + ln  # wrapped line continuation
                continue
            cur = {"head": [ln], "bullets": []}
            entries.append(cur)
            bullet_open = False
            continue
        if cur is None or cur["bullets"]:
            cur = {"head": [], "bullets": []}
            entries.append(cur)
        cur["head"].append(ln)
        bullet_open = False
    return entries


def merge_wrapped_heads(entries):
    """A company/role heading that wrapped onto 2 lines stays together as one heading line."""
    for e in entries:
        if len(e["head"]) >= 2 and not e["bullets"]:
            continue
    return entries


def rank_terms(job_text):
    words = set(re.findall(r"[a-z][a-z0-9+#.\-]{1,}", job_text.lower()))
    return words


def relevance(text, words):
    toks = set(re.findall(r"[a-z][a-z0-9+#.\-]{1,}", text.lower()))
    return len(toks & words)


def reorder_skill_line(line, words, job_text_l):
    if ":" not in line:
        return line
    label, items = line.split(":", 1)
    parts = [p.strip() for p in re.split(r",(?![^(]*\))", items) if p.strip()]
    if len(parts) < 2:
        return line
    def hit(p):
        pl = p.lower()
        return 1 if (pl in job_text_l or any(w in words for w in re.findall(r"[a-z][a-z0-9+#.\-]+", pl))) else 0
    parts_sorted = sorted(parts, key=lambda p: -hit(p))  # stable: keeps original order within group
    return f"{label.strip()}: " + ", ".join(parts_sorted)


def template_summary(profile, job, matched):
    obj = " ".join(profile["sections"].get("objective", []))
    obj = re.sub(r"\s+", " ", obj).strip()
    first = re.split(r"(?<=[a-z\)])\.\s+(?=[A-Z])|\.\s+Skilled", obj)[0].strip().rstrip(".")
    if len(first) < 30:
        first = "Motivated candidate with hands-on project experience"
    top = [s for s in matched][:7] or profile["skills"][:7]
    sk = ", ".join(top)
    return (f"{first}. Skilled in {sk}. Seeking the {job['title']} role at {job['company']} "
            f"to build practical, data-driven AI solutions.")


def template_cover(profile, job, matched):
    sk = ", ".join(matched[:6]) or "machine learning and generative AI"
    obj = re.sub(r"\s+", " ", " ".join(profile["sections"].get("objective", []))).strip()
    intro = re.split(r"(?<=[a-z\)])\.\s+(?=[A-Z])|\.\s+Skilled", obj)[0].strip().rstrip(".")
    intro = (intro + ". ") if len(intro) >= 30 else ""
    return (f"Dear Hiring Team at {job['company']},\n\nI am applying for the {job['title']} position. "
            f"{intro}"
            f"My skills include {sk}, which align with your "
            f"requirements. I would welcome the opportunity to contribute and learn with your team.\n\n"
            f"Regards,\n{profile['name']}\n{profile['email']}")


def llm_text(profile, job, matched, cfg):
    """Optional. Returns (summary, cover) or (None, None)."""
    gkey, mkey = os.environ.get("GROQ_API_KEY"), os.environ.get("GEMINI_API_KEY")
    if not (gkey or mkey):
        return None, None
    prompt = (
        "You write job-application text. Use ONLY facts present in the RESUME. Never invent employers, tools, "
        "numbers or degrees. Return strict JSON with keys summary (max 55 words, first person omitted, resume-style) "
        "and cover (max 110 words, plain text, no placeholders).\n\n"
        f"RESUME:\n{profile['raw_text'][:6000]}\n\nJOB TITLE: {job['title']}\nCOMPANY: {job['company']}\n"
        f"JOB DESCRIPTION:\n{job['description'][:3500]}\n\nSkills from resume matching the job: {', '.join(matched)}"
    )
    try:
        llm = cfg.get("llm", {})
        if gkey:  # Groq (OpenAI-compatible API)
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {gkey}"},
                json={"model": llm.get("groq_model", "llama-3.3-70b-versatile"), "temperature": 0.3,
                      "response_format": {"type": "json_object"},
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=60)
            r.raise_for_status()
            txt = r.json()["choices"][0]["message"]["content"]
        else:  # Gemini
            model = llm.get("model", "gemini-2.5-flash")
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": mkey},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}},
                timeout=60)
            r.raise_for_status()
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        d = json.loads(re.sub(r"^```json|```$", "", txt.strip()).strip())
        s, c = str(d.get("summary", "")).strip(), str(d.get("cover", "")).strip()
        return (s or None), (c or None)
    except Exception:
        return None, None


def render_pdf(path, profile, summary, skills_lines, exp_entries, proj_entries, edu_lines, ach_lines):
    styles = getSampleStyleSheet()
    navy = colors.HexColor("#2c3e50")
    h_name = ParagraphStyle("n", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=navy,
                            alignment=TA_CENTER, spaceAfter=2)
    contact = ParagraphStyle("c", parent=styles["Normal"], fontName="Helvetica", fontSize=9, alignment=TA_CENTER)
    h_sec = ParagraphStyle("s", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11, textColor=navy,
                           spaceBefore=5, spaceAfter=1)
    body = ParagraphStyle("b", parent=styles["Normal"], fontName="Helvetica", fontSize=8.6, leading=10.4)
    bold = ParagraphStyle("bb", parent=body, fontName="Helvetica-Bold")
    bul = ParagraphStyle("bu", parent=body, leftIndent=10, bulletIndent=1)

    story = [Paragraph(safe(profile["name"]), h_name)]
    bits = [b for b in (profile.get("city"), profile["email"], profile.get("phone_disp")) if b]
    story.append(Paragraph(safe("  |  ".join(bits)), contact))

    def section(title):
        story.append(Paragraph(title, h_sec))
        story.append(HRFlowable(width="100%", thickness=0.7, color=navy, spaceAfter=3))

    section("CAREER OBJECTIVE")
    story.append(Paragraph(safe(summary), body))
    section("SKILLS")
    for ln in skills_lines:
        if ":" in ln:
            a, b = ln.split(":", 1)
            story.append(Paragraph(f"<b>{safe(a)}:</b>{safe(b)}", body))
        else:
            story.append(Paragraph(safe(ln), body))
    for title, entries in (("WORK EXPERIENCE", exp_entries), ("PROJECTS", proj_entries)):
        if not entries:
            continue
        section(title)
        for e in entries:
            for h in e["head"]:
                story.append(Paragraph(safe(h), bold))
            for b in e["bullets"]:
                story.append(Paragraph(safe(b), bul, bulletText=BULLET))
            story.append(Spacer(1, 2))
    section("EDUCATION")
    for i, ln in enumerate(edu_lines):
        story.append(Paragraph(safe(ln), bold if BULLET not in ln else body))
    if ach_lines:
        section("ACHIEVEMENTS & CERTIFICATIONS")
        for ln in ach_lines:
            story.append(Paragraph(safe(ln), bul, bulletText=BULLET))

    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=9 * mm,
                            bottomMargin=9 * mm, title=f"{profile['name']} - Resume", author=profile["name"])
    doc.build(story)


def tailor_resume(profile, job, matched, cfg, out_dir):
    """Returns (resume_pdf_path, cover_text). Never raises; falls back to the original resume."""
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{slug(profile['name'])}_{slug(job['company'])}_{slug(job['title'])}_{job['key'][:6]}.pdf")
    cover = template_cover(profile, job, matched)
    try:
        sec = profile["sections"]
        if not sec.get("skills") or not (sec.get("experience") or sec.get("projects")) or not sec.get("education"):
            raise ValueError("resume sections not recognised")
        jt = f"{job['title']} {job['description']}"
        words, jt_l = rank_terms(jt), jt.lower()
        summary, cover_llm = llm_text(profile, job, matched, cfg)
        summary = summary or template_summary(profile, job, matched)
        cover = cover_llm or cover

        skills_lines, buf = [], ""
        for ln in sec["skills"]:  # re-join wrapped skill lines
            if re.match(r"^[A-Za-z][A-Za-z /&()\-]{2,45}:", ln):
                if buf:
                    skills_lines.append(buf)
                buf = ln
            else:
                buf += " " + ln
        if buf:
            skills_lines.append(buf)
        skills_lines = [reorder_skill_line(l, words, jt_l) for l in skills_lines]

        def prep(lines):
            ents = group_entries(lines)
            for e in ents:
                e["bullets"] = sorted(e["bullets"], key=lambda b: -relevance(b, words))
            return ents
        exp_entries, proj_entries = prep(sec.get("experience", [])), prep(sec.get("projects", []))
        edu = [re.sub(r"\s+", " ", l) for l in sec["education"]]
        ach = [l for l in sec.get("achievements", [])]
        prof = dict(profile)
        prof["city"] = cfg["candidate"].get("city", "")
        prof["phone_disp"] = profile.get("phone", "")
        if not any(e["bullets"] for e in exp_entries + proj_entries):
            raise ValueError("no bullet structure recognised")
        render_pdf(out, prof, summary, skills_lines, exp_entries, proj_entries, edu, ach)
        if not os.path.exists(out) or os.path.getsize(out) < 1500:
            raise ValueError("render produced an empty file")
        return out, cover
    except Exception:
        fallback = os.path.join(out_dir, f"{slug(profile['name'])}_Resume.pdf")
        shutil.copy(cfg["resume_abs"], fallback)
        return fallback, cover


def llm_raw(prompt, cfg):
    """One plain-text LLM call (Groq or Gemini). Returns text or None."""
    gkey, mkey = os.environ.get("GROQ_API_KEY"), os.environ.get("GEMINI_API_KEY")
    try:
        llm = cfg.get("llm", {})
        if gkey:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                              headers={"Authorization": f"Bearer {gkey}"},
                              json={"model": llm.get("groq_model", "llama-3.3-70b-versatile"), "temperature": 0.2,
                                    "messages": [{"role": "user", "content": prompt}]}, timeout=45)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        if mkey:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{llm.get('model', 'gemini-2.5-flash')}:generateContent",
                params={"key": mkey}, json={"contents": [{"parts": [{"text": prompt}]}],
                                            "generationConfig": {"temperature": 0.2}}, timeout=45)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None
    return None


def answer_question(profile, job, question, options, cfg):
    """Answer an application question using ONLY resume facts + the candidate's saved answers. None if no LLM."""
    c = cfg.get("candidate", {})
    facts = "\n".join(f"{k}: {v}" for k, v in c.items() if v)
    opt = ("\nChoose EXACTLY one of these options and reply with only that option text:\n- " + "\n- ".join(options)) if options else \
          "\nAnswer in at most 60 words, plain text, first person, no placeholders."
    prompt = ("You fill a job application for the candidate below. Use ONLY facts from the RESUME and CANDIDATE DETAILS; "
              "never invent employers, degrees, numbers or tools. If something is unknown, answer honestly and briefly "
              f"(for yes/no pick the safest truthful option).\n\nRESUME:\n{profile['raw_text'][:5000]}\n\n"
              f"CANDIDATE DETAILS:\n{facts}\n\nJOB: {job.get('title','')} at {job.get('company','')}\n"
              f"QUESTION: {question}{opt}")
    txt = llm_raw(prompt, cfg)
    return re.sub(r"^[\"'`\s]+|[\"'`\s]+$", "", txt) if txt else None
