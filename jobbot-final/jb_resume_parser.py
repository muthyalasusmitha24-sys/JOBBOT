"""Reads the resume PDF -> structured profile (name, contact, skills, sections, experience years)."""
import datetime
import re

from pypdf import PdfReader

HEADS = [
    "ACHIEVEMENTS & CERTIFICATIONS", "CAREER OBJECTIVE", "WORK EXPERIENCE", "PROFESSIONAL EXPERIENCE",
    "INTERNSHIP EXPERIENCE", "PROFESSIONAL SUMMARY", "EDUCATIONAL QUALIFICATIONS", "ACADEMIC QUALIFICATIONS",
    "TECHNICAL SKILLS", "KEY SKILLS", "CORE SKILLS", "ACADEMIC PROJECTS", "PERSONAL PROJECTS",
    "ACHIEVEMENTS", "CERTIFICATIONS", "CERTIFICATES", "AWARDS", "DECLARATION", "EDUCATION", "EXPERIENCE",
    "INTERNSHIPS", "OBJECTIVE", "PROJECTS", "SUMMARY", "PROFILE", "SKILLS",
]
HEAD_MAP = {
    "CAREER OBJECTIVE": "objective", "OBJECTIVE": "objective", "SUMMARY": "objective",
    "EDUCATION": "education", "SKILLS": "skills",
    "WORK EXPERIENCE": "experience", "PROFESSIONAL EXPERIENCE": "experience", "EXPERIENCE": "experience",
    "PROJECTS": "projects", "ACHIEVEMENTS & CERTIFICATIONS": "achievements",
    "ACHIEVEMENTS": "achievements", "CERTIFICATIONS": "achievements", "DECLARATION": "declaration",
    "INTERNSHIP EXPERIENCE": "experience", "INTERNSHIPS": "experience", "PROFESSIONAL SUMMARY": "objective",
    "PROFILE": "objective", "EDUCATIONAL QUALIFICATIONS": "education", "ACADEMIC QUALIFICATIONS": "education",
    "TECHNICAL SKILLS": "skills", "KEY SKILLS": "skills", "CORE SKILLS": "skills",
    "ACADEMIC PROJECTS": "projects", "PERSONAL PROJECTS": "projects", "CERTIFICATES": "achievements",
    "AWARDS": "achievements",
}
_ALT = "|".join(re.escape(h) for h in sorted(HEADS, key=len, reverse=True))
HEAD_RE = re.compile(r"^[\d\s]*(" + _ALT + r")\b\s*(.*)$")          # UPPERCASE headings (text may be glued after)
HEAD_ANY_RE = re.compile(r"^(" + _ALT + r")\s*:?\s*$", re.I)         # standalone Title/lower-case headings

# canonical skill -> aliases (all matched case-insensitively with word boundaries)
SKILLS = {
    "Python": ["python"], "Java": ["java"], "C++": ["c++"], "SQL": ["sql", "mysql"],
    "Machine Learning": ["machine learning", "ml"], "Deep Learning": ["deep learning"],
    "NLP": ["nlp", "natural language processing"], "LLMs": ["llm", "llms", "large language model", "large language models"],
    "RAG": ["rag", "retrieval-augmented generation", "retrieval augmented generation"],
    "Generative AI": ["generative ai", "gen ai", "genai"], "Prompt Engineering": ["prompt engineering", "prompting"],
    "Transformers": ["transformer", "transformers"], "LangChain": ["langchain"],
    "Multimodal AI": ["multimodal"], "PyTorch": ["pytorch"], "TensorFlow": ["tensorflow"],
    "Scikit-learn": ["scikit-learn", "sklearn"], "CNN": ["cnn", "cnns"], "Transfer Learning": ["transfer learning"],
    "BERT": ["bert", "roberta"], "ChromaDB": ["chromadb"], "FAISS": ["faiss"], "Embeddings": ["embedding", "embeddings"],
    "Vector Databases": ["vector database", "vector databases", "vector storage"],
    "Hugging Face": ["hugging face", "huggingface"], "Streamlit": ["streamlit"], "NLTK": ["nltk"],
    "TF-IDF": ["tf-idf", "tfidf"], "Feature Engineering": ["feature engineering"],
    "Computer Vision": ["computer vision", "image classification", "cnn"],
    "GANs": ["gan", "gans"], "Diffusion Models": ["diffusion"], "Classification": ["classification"],
    "Regression": ["regression"], "Clustering": ["clustering", "unsupervised"],
    "Sentiment Analysis": ["sentiment analysis"], "NER": ["named entity recognition", "ner"],
    "LLaMA": ["llama", "llama-3"], "Data Science": ["data science"],
}
# skills NOT in the resume but commonly co-listed are never added (no fabrication).

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def read_pdf_text(path):
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    text = "\n".join(parts)
    if len(text.strip()) < 100:
        raise ValueError("Could not read text from the resume PDF (is it a scanned image?).")
    return text


def split_sections(text):
    sections, cur = {"header": []}, "header"
    for raw in text.splitlines():
        # PDFs often glue the header phone number onto another line; drop it from body lines
        line = re.sub(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)", " ", raw) if cur != "header" else raw
        line = line.strip()
        if not line:
            continue
        m = HEAD_RE.match(line)
        if m:
            cur = HEAD_MAP[m.group(1)]
            sections.setdefault(cur, [])
            rest = m.group(2).strip()
            if rest:
                sections[cur].append(rest)
            continue
        m2 = HEAD_ANY_RE.match(line)
        if m2:
            cur = HEAD_MAP[m2.group(1).upper()]
            sections.setdefault(cur, [])
            continue
        sections.setdefault(cur, []).append(line)
    return sections


def _has(text, alias):
    return re.search(r"(?<![A-Za-z0-9+])" + re.escape(alias) + r"(?![A-Za-z0-9+])", text, re.I) is not None


def extract_skills(text):
    found = []
    for canon, aliases in SKILLS.items():
        if any(_has(text, a) for a in aliases):
            found.append(canon)
    return found


def _ym(mon, yr):
    return int(yr) * 12 + MONTHS[mon[:3].lower()]


def estimate_years(text):
    today = datetime.date.today()
    pat = re.compile(r"([A-Za-z]{3,9})\s+(20\d\d)\s*[-\u2013\u2014to ]+\s*([A-Za-z]{3,9})\s*(20\d\d)?", re.I)
    spans = []
    for m in pat.finditer(text):
        a, ay, b, by = m.groups()
        if a[:3].lower() not in MONTHS:
            continue
        s = _ym(a, ay)
        if b.lower().startswith("pres"):
            e = today.year * 12 + today.month
        elif by and b[:3].lower() in MONTHS:
            e = _ym(b, by)
        else:
            continue
        if e >= s:
            spans.append((s, e))
    if not spans:
        return 0.0
    return round((max(e for _, e in spans) - min(s for s, _ in spans)) / 12.0, 1)


def parse_resume(path):
    text = read_pdf_text(path)
    sections = split_sections(text)
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    phone = re.search(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{9})(?!\d)", text)
    header = sections.get("header", [])
    name = next((l for l in header if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{2,40}", l) and len(l.split()) <= 4), "")
    if not name and email:
        name = email.group(0).split("@")[0]
    parts = name.split()
    exp_text = "\n".join(sections.get("experience", []))
    return {
        "name": name.title() if name.isupper() else name,
        "first_name": parts[0] if parts else "",
        "last_name": " ".join(parts[1:]) if len(parts) > 1 else (parts[0] if parts else ""),
        "email": email.group(0) if email else "",
        "phone": phone.group(1) if phone else "",
        "skills": extract_skills(text),
        "sections": sections,
        "years_experience": estimate_years(exp_text or text),
        "raw_text": text,
    }
