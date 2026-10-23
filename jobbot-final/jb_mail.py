"""Reads verification codes (e.g. Greenhouse 'security code') from your mailbox via IMAP.
Use a Gmail *App Password* (Google Account > Security > 2-Step Verification > App passwords)."""
import email
import email.utils
import imaplib
import re
import time
from email.header import decode_header, make_header


def _decode(s):
    try:
        return str(make_header(decode_header(s or "")))
    except Exception:
        return s or ""


def _body(msg):
    parts = []
    for p in (msg.walk() if msg.is_multipart() else [msg]):
        if p.get_content_type() in ("text/plain", "text/html"):
            try:
                raw = p.get_payload(decode=True) or b""
                t = raw.decode(p.get_content_charset() or "utf-8", "ignore")
            except Exception:
                continue
            if p.get_content_type() == "text/html":
                t = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", t)
                t = re.sub(r"<[^>]+>", " ", t)
            parts.append(t)
    return " ".join(parts)


def extract_code(text):
    """First token (6-10 chars, containing a digit) after the word 'code'."""
    t = re.sub(r"\s+", " ", text or "")
    i = t.lower().find("code")
    tail = t[i:] if i >= 0 else t
    for m in re.finditer(r"(?<![A-Za-z0-9])([A-Za-z0-9]{6,10})(?![A-Za-z0-9])", tail):
        tok = m.group(1)
        if re.search(r"\d", tok) and not re.fullmatch(r"(19|20)\d\d", tok):
            return tok
    return None


def fetch_code(user, password, since_ts, timeout=90, host="imap.gmail.com", log=print):
    """Polls the mailbox until a fresh message with a code arrives. Returns the code or None."""
    if not (user and password):
        return None
    end = time.time() + timeout
    while time.time() < end:
        try:
            M = imaplib.IMAP4_SSL(host)
            M.login(user, password)
            for folder in ("INBOX", "[Gmail]/Spam"):
                typ, _ = M.select(f'"{folder}"' if " " in folder or "[" in folder else folder, readonly=True)
                if typ != "OK":
                    continue
                typ, data = M.search(None, "ALL")
                ids = (data[0] or b"").split()[-12:]
                for i in reversed(ids):
                    typ, md = M.fetch(i, "(RFC822)")
                    msg = email.message_from_bytes(md[0][1])
                    try:
                        ts = email.utils.parsedate_to_datetime(msg["Date"]).timestamp()
                    except Exception:
                        ts = time.time()
                    if ts < since_ts - 120:
                        continue
                    text = _decode(msg["Subject"]) + " " + _body(msg)
                    if "code" in text.lower():
                        code = extract_code(text)
                        if code:
                            M.logout()
                            return code
            M.logout()
        except Exception as e:
            log(f"mail check failed: {type(e).__name__}: {str(e)[:80]}")
        time.sleep(5)
    return None
