import csv
import html
import os

STATUS_LABEL = {"applied": "Applied", "unconfirmed": "Submitted - verify", "blocked": "Blocked (CAPTCHA/code)",
                "manual_needed": "Needs your input", "ready": "Dry run OK", "found": "Matched",
                "failed": "Failed", "skipped": "Closed"}
COLORS = {"applied": "#059669", "unconfirmed": "#0891b2", "blocked": "#d97706", "manual_needed": "#ea580c",
          "ready": "#2563eb", "found": "#4f46e5", "failed": "#dc2626", "skipped": "#94a3b8"}


def write_dashboard(rows, data_dir):
    e = lambda s: html.escape(str(s if s is not None else ""))
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    cards = "".join(
        f'<div class="card" style="border-top:4px solid {COLORS.get(k, "#64748b")}"><div class="n">{counts.get(k, 0)}</div>'
        f'<div class="l">{STATUS_LABEL[k]}</div></div>' for k in STATUS_LABEL)
    body = []
    for r in rows:
        res = os.path.relpath(r["resume_path"], data_dir) if r.get("resume_path") else ""
        shot = os.path.relpath(r["screenshot"], data_dir) if r.get("screenshot") else ""
        links = f'<a href="{e(r["url"])}" target="_blank">job</a>'
        if r["apply_url"] and r["apply_url"] != r["url"]:
            links += f' &middot; <a href="{e(r["apply_url"])}" target="_blank">apply</a>'
        if res:
            links += f' &middot; <a href="{e(res)}" target="_blank">resume</a>'
        if shot:
            links += f' &middot; <a href="{e(shot)}" target="_blank">proof</a>'
        st = r["status"]
        body.append(
            f'<tr data-s="{e(st)}"><td><span class="b" style="background:{COLORS.get(st, "#64748b")}">{e(STATUS_LABEL.get(st, st))}</span></td>'
            f'<td>{e(r["score"])}</td><td>{e(r["company"])}</td><td>{e(r["title"])}</td><td>{e(r["location"])}</td>'
            f'<td>{e(r["salary"] or "not listed")}</td><td>{e(r["matched"])}</td><td>{links}</td>'
            f'<td>{e(r["reason"])}</td><td>{e(r["updated_at"])}</td></tr>')
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JobBot Dashboard</title><style>
body{{font-family:system-ui,Arial,sans-serif;margin:0;background:#f8fafc;color:#0f172a}}
header{{padding:18px 24px;background:#0f172a;color:#fff}} h1{{margin:0;font-size:20px}}
.wrap{{padding:18px 24px}} .cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}}
.card{{background:#fff;padding:10px 18px;border-radius:8px;box-shadow:0 1px 3px #0002;min-width:110px}}
.n{{font-size:26px;font-weight:700}} .l{{font-size:12px;color:#475569}}
input,select{{padding:7px;border:1px solid #cbd5e1;border-radius:6px;margin-right:8px}}
.tw{{overflow-x:auto;background:#fff;border-radius:8px;box-shadow:0 1px 3px #0002;margin-top:10px}}
table{{border-collapse:collapse;width:100%;font-size:13px}} th,td{{padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:left;vertical-align:top}}
th{{background:#f1f5f9;position:sticky;top:0}} .b{{color:#fff;padding:2px 8px;border-radius:10px;font-size:11px;white-space:nowrap}}
a{{color:#2563eb;text-decoration:none}}
</style></head><body><header><h1>JobBot - applications dashboard</h1></header><div class="wrap">
<div class="cards">{cards}<div class="card"><div class="n">{len(rows)}</div><div class="l">Total tracked</div></div></div>
<input id="q" placeholder="Search company / title / skill..." oninput="f()">
<select id="s" onchange="f()"><option value="">All statuses</option>{''.join(f'<option value="{k}">{v}</option>' for k, v in STATUS_LABEL.items())}</select>
<div class="tw"><table id="t"><thead><tr><th>Status</th><th>Score</th><th>Company</th><th>Title</th><th>Location</th><th>Salary</th>
<th>Matched skills</th><th>Links</th><th>Note</th><th>Updated</th></tr></thead><tbody>{''.join(body)}</tbody></table></div></div>
<script>function f(){{var q=document.getElementById('q').value.toLowerCase(),s=document.getElementById('s').value;
document.querySelectorAll('#t tbody tr').forEach(function(r){{r.style.display=((!s||r.dataset.s===s)&&r.innerText.toLowerCase().indexOf(q)>-1)?'':'none'}})}}</script>
</body></html>"""
    path = os.path.join(data_dir, "dashboard.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    cols = ["job_key", "status", "score", "company", "title", "location", "salary", "matched", "url", "apply_url", "reason", "resume_path", "updated_at"]
    with open(os.path.join(data_dir, "applications.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])
    return path
