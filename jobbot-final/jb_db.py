import datetime
import hashlib
import os
import sqlite3
import threading

SCHEMA = """CREATE TABLE IF NOT EXISTS jobs(
 job_key TEXT PRIMARY KEY, source TEXT, company TEXT, title TEXT, location TEXT,
 url TEXT, apply_url TEXT, salary TEXT, score REAL, matched TEXT, status TEXT,
 reason TEXT, resume_path TEXT, screenshot TEXT, found_at TEXT, updated_at TEXT)"""

COLUMNS = ["job_key", "source", "company", "title", "location", "url", "apply_url", "salary",
           "score", "matched", "status", "reason", "resume_path", "screenshot", "found_at", "updated_at"]


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def make_key(company, title, location):
    raw = "|".join(str(x or "").strip().lower() for x in (company, title, location))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class DB:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.execute(SCHEMA)
            self.conn.commit()

    def has(self, key):
        with self.lock:
            r = self.conn.execute("SELECT 1 FROM jobs WHERE job_key=?", (key,)).fetchone()
        return r is not None

    def add_found(self, job, score, matched):
        with self.lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO jobs(job_key,source,company,title,location,url,apply_url,salary,"
                "score,matched,status,reason,resume_path,screenshot,found_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job["key"], job["source"], job["company"], job["title"], job["location"], job["url"],
                 job["apply_url"], job["salary"], float(score), ", ".join(matched), "found", "", "", "",
                 now(), now()))
            self.conn.commit()

    def update(self, key, **fields):
        fields = {k: v for k, v in fields.items() if k in COLUMNS and k != "job_key"}
        fields["updated_at"] = now()
        sets = ", ".join(f"{k}=?" for k in fields)
        with self.lock:
            self.conn.execute(f"UPDATE jobs SET {sets} WHERE job_key=?", list(fields.values()) + [key])
            self.conn.commit()

    def all(self):
        with self.lock:
            rows = self.conn.execute("SELECT * FROM jobs ORDER BY updated_at DESC, score DESC").fetchall()
        return [dict(r) for r in rows]

    def pending_keys(self, limit, apply_only=False, per_company=0):
        """Best pending jobs. apply_only -> only sites the bot can auto-apply to. per_company caps spam."""
        with self.lock:
            rows = self.conn.execute(
                "SELECT job_key, company, apply_url FROM jobs WHERE status IN ('found','ready') "
                "ORDER BY score DESC").fetchall()
        keys, per = [], {}
        for r in rows:
            u = (r["apply_url"] or "").lower()
            if apply_only and not any(d in u for d in ("greenhouse.io", "lever.co", "ashbyhq.com")):
                continue
            c = (r["company"] or "").lower()
            if per_company and per.get(c, 0) >= per_company:
                continue
            per[c] = per.get(c, 0) + 1
            keys.append(r["job_key"])
            if len(keys) >= int(limit):
                break
        return keys

    def get(self, key):
        with self.lock:
            r = self.conn.execute("SELECT * FROM jobs WHERE job_key=?", (key,)).fetchone()
        return dict(r) if r else None

    def import_history(self, rows):
        """Re-load a previously exported CSV so already-seen jobs are never re-applied."""
        n = 0
        with self.lock:
            for r in rows:
                key = str(r.get("job_key") or "").strip()
                if not key:
                    continue
                vals = [str(r.get(c, "") or "") for c in COLUMNS]
                vals[COLUMNS.index("job_key")] = key
                try:
                    vals[COLUMNS.index("score")] = float(r.get("score") or 0)
                except ValueError:
                    vals[COLUMNS.index("score")] = 0.0
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO jobs(" + ",".join(COLUMNS) + ") VALUES(" + ",".join("?" * len(COLUMNS)) + ")", vals)
                n += cur.rowcount
            self.conn.commit()
        return n
