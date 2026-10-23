CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{--bg:#f5f7fb;--card:#ffffff;--line:#e6e9f2;--ink:#0f172a;--mut:#64748b;--pri:#4f46e5;--pri2:#7c3aed;--acc:#0891b2;
--ok:#059669;--warn:#d97706;--bad:#dc2626;--shadow:0 1px 2px rgba(15,23,42,.05),0 8px 24px rgba(15,23,42,.06);}
html,body,[class*="css"],.stApp{font-family:'Inter',system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink);}
.stApp{background:var(--bg);}
#MainMenu,footer,header [data-testid="stToolbar"]{visibility:hidden;}
.block-container{padding-top:1.4rem;padding-bottom:3rem;max-width:1240px;}
section[data-testid="stSidebar"]{background:#ffffff;border-right:1px solid var(--line);}
section[data-testid="stSidebar"] .block-container{padding-top:1rem;}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:1.3rem;letter-spacing:-.02em;margin-bottom:.4rem;}
.brand .logo{width:36px;height:36px;border-radius:11px;display:grid;place-items:center;color:#fff;font-size:1.05rem;
background:linear-gradient(135deg,var(--pri),var(--pri2));box-shadow:0 6px 16px rgba(79,70,229,.35);}
.sbh{font-size:.7rem;font-weight:700;letter-spacing:.12em;color:var(--mut);text-transform:uppercase;margin:.9rem 0 .2rem;}
.hero{position:relative;overflow:hidden;border-radius:24px;padding:34px 38px;margin-bottom:22px;color:#fff;
background:linear-gradient(120deg,#3730a3 0%,#6d28d9 52%,#0e7490 100%);box-shadow:0 18px 44px rgba(79,70,229,.28);}
.hero:after{content:"";position:absolute;right:-90px;top:-110px;width:340px;height:340px;border-radius:50%;
background:radial-gradient(circle,rgba(255,255,255,.22),transparent 68%);}
.hero .tag{display:inline-block;padding:4px 12px;border-radius:999px;font-size:.7rem;font-weight:700;letter-spacing:.14em;
background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.28);}
.hero h1{color:#fff;font-size:2.35rem;font-weight:800;letter-spacing:-.03em;margin:.55rem 0 .25rem;padding:0;line-height:1.1;}
.hero p{color:rgba(255,255,255,.88);font-size:1.02rem;max-width:720px;margin:0 0 14px;}
.hero .hp{display:inline-block;margin:4px 8px 0 0;padding:5px 12px;border-radius:999px;font-size:.78rem;font-weight:600;
background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.22);}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px 20px;box-shadow:var(--shadow);}
.card h4{margin:0 0 .35rem;font-size:1rem;font-weight:700;}
.card p{margin:0;color:var(--mut);font-size:.9rem;line-height:1.5;}
.step{display:flex;gap:14px;align-items:flex-start;}
.step .n{flex:0 0 36px;height:36px;border-radius:11px;display:grid;place-items:center;font-weight:800;color:#fff;
background:linear-gradient(135deg,var(--pri),var(--pri2));}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:15px 18px;box-shadow:var(--shadow);
position:relative;overflow:hidden;}
.kpi:before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--c,var(--pri));}
.kpi .v{font-size:1.9rem;font-weight:800;letter-spacing:-.02em;line-height:1.1;}
.kpi .l{color:var(--mut);font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.09em;margin-top:3px;}
.kpi .s{color:#94a3b8;font-size:.74rem;margin-top:2px;}
.sec{font-size:1.08rem;font-weight:800;letter-spacing:-.01em;margin:1.3rem 0 .6rem;}
.jcard{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px 18px;box-shadow:var(--shadow);
min-height:205px;transition:transform .18s,box-shadow .18s,border-color .18s;}
.jcard:hover{transform:translateY(-3px);border-color:#c7d2fe;box-shadow:0 14px 34px rgba(79,70,229,.16);}
.jtop{display:flex;gap:12px;align-items:flex-start;}
.av{flex:0 0 42px;height:42px;border-radius:12px;display:grid;place-items:center;color:#fff;font-weight:800;font-size:1.05rem;}
.jtx{flex:1;min-width:0;}
.jco{color:var(--mut);font-size:.74rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;}
.jti{font-size:1rem;font-weight:700;line-height:1.25;margin:2px 0 4px;}
.jmeta{color:var(--mut);font-size:.8rem;margin:6px 0 2px;}
.ring{position:relative;flex:0 0 48px;height:48px;}
.ring:before{content:"";position:absolute;inset:0;border-radius:50%;
background:conic-gradient(var(--c) calc(var(--p)*1%),#e8ebf4 0);-webkit-mask:radial-gradient(farthest-side,transparent 66%,#000 68%);
mask:radial-gradient(farthest-side,transparent 66%,#000 68%);}
.ring b{position:absolute;inset:0;display:grid;place-items:center;font-size:.86rem;font-weight:800;}
.chip{display:inline-block;margin:6px 5px 0 0;padding:3px 10px;border-radius:999px;font-size:.72rem;font-weight:600;
background:#eef2ff;color:#4338ca;border:1px solid #e0e7ff;}
.badge{display:inline-block;padding:3px 11px;border-radius:999px;font-size:.72rem;font-weight:700;white-space:nowrap;}
.lnk{display:inline-block;margin:10px 8px 0 0;padding:6px 13px;border-radius:10px;font-size:.8rem;font-weight:700;
text-decoration:none!important;color:#fff!important;background:linear-gradient(135deg,var(--pri),var(--pri2));}
.lnk.alt{background:#fff;color:var(--pri)!important;border:1px solid #c7d2fe;}
.feed{display:flex;gap:12px;align-items:center;padding:11px 14px;border:1px solid var(--line);border-radius:14px;background:#fff;
margin-bottom:8px;box-shadow:0 1px 2px rgba(15,23,42,.04);}
.feed .t{flex:1;min-width:0;font-weight:600;font-size:.92rem;}
.feed .t small{display:block;color:var(--mut);font-weight:500;font-size:.78rem;margin-top:1px;}
.live{display:flex;align-items:center;gap:10px;font-weight:700;}
.dot{width:10px;height:10px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 0 rgba(5,150,105,.6);animation:pulse 1.6s infinite;}
@keyframes pulse{70%{box-shadow:0 0 0 10px rgba(5,150,105,0);}100%{box-shadow:0 0 0 0 rgba(5,150,105,0);}}
.logbox{background:#0f172a;color:#cbd5e1;border-radius:14px;padding:12px 14px;font-family:ui-monospace,Menlo,Consolas,monospace;
font-size:.76rem;line-height:1.55;max-height:210px;overflow:auto;white-space:pre-wrap;}
.stButton>button[kind="primary"],.stButton>button[data-testid="stBaseButton-primary"]{border:0;border-radius:12px;font-weight:700;
background:linear-gradient(135deg,var(--pri),var(--pri2));box-shadow:0 8px 20px rgba(79,70,229,.32);}
.stDownloadButton>button{border-radius:11px;font-weight:600;}
.stTabs [data-baseweb="tab-list"]{gap:4px;border-bottom:1px solid var(--line);}
.stTabs [data-baseweb="tab"]{padding:9px 16px;font-weight:600;}
div[data-testid="stExpander"]{border:1px solid var(--line);border-radius:14px;background:#fff;}
.foot{text-align:center;color:#94a3b8;font-size:.78rem;margin:34px 0 6px;}
"""
CSS = "\n".join(l for l in CSS.splitlines() if l.strip())
