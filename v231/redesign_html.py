"""Replaces only CSS sections and Google Fonts links in the three HTML templates."""
import re

SRC = "D:/boticifane/v231/server_v2.py"

with open(SRC, "r", encoding="utf-8") as f:
    content = f.read()

NEW_FONTS_SINGLE = (
    "https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800"
    "&family=JetBrains+Mono:wght@400;500&display=swap"
)
NEW_FONTS_ADMIN = NEW_FONTS_SINGLE  # same for all three

# ─────────────────────────────────────────────────────
# CSS blocks
# ─────────────────────────────────────────────────────

LOGIN_CSS = """:root{--bg:#04060c;--surface:#090d18;--surface2:#0e1422;--surface3:#141c2e;--border:rgba(0,229,255,.07);--border2:rgba(0,229,255,.16);--text:#d8e8ff;--muted:#4a6080;--accent:#00e5ff;--accent2:#38f5c0;--green:#00ff87;--yellow:#ffc107;--red:#ff3b6b;--blue:#4d9dff;--cyan:#00e5ff}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Space Grotesk',sans-serif;background:var(--bg);background-image:radial-gradient(rgba(0,229,255,.06) 1px,transparent 1px);background-size:28px 28px;color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center}
.box{background:var(--surface);border:1px solid var(--border2);border-radius:16px;padding:36px 32px;width:340px;box-shadow:0 0 60px rgba(0,229,255,.06)}
.logo{text-align:center;margin-bottom:28px}
.logo-icon{font-size:36px;display:block;margin-bottom:8px}
.logo h1{font-size:18px;font-weight:800;color:var(--text)}
.logo p{font-size:12px;color:var(--muted);margin-top:3px}
label{display:block;font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px}
input{width:100%;background:#060a14;border:1px solid var(--border2);border-radius:9px;padding:11px 14px;color:var(--text);font-size:14px;font-family:inherit;outline:none;transition:.15s}
input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(0,229,255,.1)}
.field{margin-bottom:20px}
button{width:100%;background:var(--accent);border:none;border-radius:9px;color:var(--bg);padding:12px;font-size:14px;font-weight:700;font-family:inherit;cursor:pointer;transition:.15s;letter-spacing:.02em}
button:hover{background:#19eeff;transform:translateY(-1px)}
button:active{transform:translateY(0)}
.err{background:rgba(255,59,107,.1);border:1px solid rgba(255,59,107,.2);border-radius:8px;color:var(--red);font-size:13px;padding:10px 12px;margin-bottom:16px;text-align:center}"""

ADMIN_DASH_CSS = """:root{--bg:#04060c;--surface:#090d18;--surface2:#0e1422;--surface3:#141c2e;--border:rgba(0,229,255,.07);--border2:rgba(0,229,255,.16);--text:#d8e8ff;--muted:#4a6080;--accent:#00e5ff;--accent2:#38f5c0;--green:#00ff87;--yellow:#ffc107;--red:#ff3b6b;--blue:#4d9dff;--cyan:#00e5ff}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
::-webkit-scrollbar{width:5px;height:5px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:rgba(0,229,255,.25);border-radius:3px}
body{font-family:'Space Grotesk',-apple-system,sans-serif;background:var(--bg);background-image:radial-gradient(rgba(0,229,255,.06) 1px,transparent 1px);background-size:28px 28px;color:var(--text);min-height:100vh;font-size:14px;line-height:1.5}
.hdr{position:sticky;top:0;z-index:100;backdrop-filter:blur(12px);background:var(--bg);border-bottom:1px solid var(--border2);box-shadow:0 1px 30px rgba(0,229,255,.04);display:flex;align-items:center;padding:0 24px;height:52px;gap:16px}
.brand{font-weight:800;font-size:15px;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;white-space:nowrap;display:flex;align-items:center;gap:8px}
.brand-dot{width:8px;height:8px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent)}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:16px}
.live{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.live-dot{width:7px;height:7px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(0,255,135,.4)}70%{box-shadow:0 0 0 6px rgba(0,255,135,0)}100%{box-shadow:0 0 0 0 rgba(0,255,135,0)}}
.hdr-time{font-size:12px;color:var(--muted);font-family:'JetBrains Mono',monospace}
.btn-logout{font-size:12px;color:var(--muted);background:none;border:1px solid var(--border2);border-radius:20px;padding:5px 14px;cursor:pointer;font-family:inherit;text-decoration:none;transition:.2s}
.btn-logout:hover{color:var(--accent);border-color:var(--accent)}
.export-btn{display:inline-block;padding:6px 14px;background:rgba(0,229,255,.08);border:1px solid rgba(0,229,255,.2);border-radius:8px;color:var(--accent);font-size:12px;font-weight:600;text-decoration:none;transition:.15s;font-family:inherit}
.export-btn:hover{background:rgba(0,229,255,.14);text-decoration:none}
.ref-card{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:16px;margin-bottom:10px}
.ref-user{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.ref-badge{display:inline-block;padding:2px 8px;border-radius:6px;font-size:10px;font-weight:700}
.ref-list{display:flex;flex-wrap:wrap;gap:6px}
.wrap{padding:24px;max-width:1700px;margin:0 auto}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:24px}
@keyframes fadeInUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:18px 20px;transition:all .2s ease;animation:fadeInUp .4s ease both}
.card:hover{border-color:rgba(0,229,255,.22);box-shadow:0 0 28px rgba(0,229,255,.07);transform:translateY(-2px)}
.card:nth-child(1){animation-delay:.1s}.card:nth-child(2){animation-delay:.2s}.card:nth-child(3){animation-delay:.3s}.card:nth-child(4){animation-delay:.4s}.card:nth-child(5){animation-delay:.45s}.card:nth-child(6){animation-delay:.5s}
.card-label{font-size:10.5px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px}
.card-val{font-size:30px;font-weight:800;line-height:1}
.card-val.accent{color:var(--accent2)}.card-val.green{color:var(--green)}.card-val.yellow{color:var(--yellow)}.card-val.blue{color:var(--blue)}.card-val.red{color:var(--red)}
.section-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.section-title{font-size:13px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.btn-refresh{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:20px;border:1px solid var(--border2);background:none;color:var(--muted);font-size:12px;font-family:inherit;cursor:pointer;text-decoration:none;transition:.2s}
.btn-refresh:hover{color:var(--accent);border-color:var(--accent)}
.tbl-wrap{overflow-x:auto;border-radius:14px;border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;background:var(--surface);font-size:12.5px}
thead tr{background:linear-gradient(180deg,var(--surface2),var(--surface))}
th{padding:10px 12px;text-align:left;font-size:10px;color:var(--accent);font-weight:700;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid var(--border);white-space:nowrap;font-family:'Space Grotesk',sans-serif}
td{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:middle;color:#7a9abf}
tr:last-child td{border-bottom:none}
tr.clickable:hover td{background:rgba(0,229,255,.03);cursor:pointer}
.badge{display:inline-flex;align-items:center;gap:4px;padding:2px 9px;border-radius:20px;font-size:10.5px;font-weight:700;letter-spacing:.03em}
.b-on{background:rgba(0,255,135,.1);color:var(--green)}.b-off{background:rgba(74,96,128,.1);color:#4a6080}.b-rev{background:rgba(255,59,107,.1);color:var(--red)}
.mono{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted)}
.name{font-weight:600;color:var(--text)}
.tg-link{color:#38f5c0;text-decoration:none;font-size:12px;font-weight:500}.tg-link:hover{text-decoration:underline}
.r-yellow{color:var(--yellow);font-weight:700}.r-faint{color:#a07c04;font-weight:500}
.btn-rev{background:none;border:1px solid rgba(255,59,107,.25);color:rgba(255,59,107,.7);padding:3px 10px;border-radius:6px;cursor:pointer;font-size:11px;font-family:inherit;transition:.15s}
.btn-rev:hover{background:rgba(255,59,107,.1);border-color:var(--red);color:var(--red)}
form.inl{display:inline}
.footer{margin-top:14px;font-size:11px;color:#1a2840;text-align:right}
.tabs{display:flex;gap:6px;margin-bottom:20px;flex-wrap:wrap}
.tab{padding:7px 18px;font-size:12px;font-weight:600;color:var(--muted);background:var(--surface);border:1px solid var(--border);border-radius:20px;cursor:pointer;font-family:inherit;transition:.2s}
.tab:hover{color:var(--text);border-color:var(--border2)}.tab.active{color:var(--bg);background:var(--accent);border-color:var(--accent);font-weight:700}
.tab-panel{display:none}.tab-panel.active{display:block}
.modal-overlay{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.75);z-index:200;align-items:center;justify-content:center;padding:20px}
.modal-overlay.open{display:flex}
.modal{background:var(--bg);border:1px solid var(--border2);border-radius:20px;width:100%;max-width:900px;max-height:85vh;overflow-y:auto;padding:28px;box-shadow:0 0 80px rgba(0,229,255,.08),0 40px 80px rgba(0,0,0,.6)}
.modal-hdr{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}
.modal-hdr h2{font-size:18px;font-weight:800}
.modal-close{width:32px;height:32px;border-radius:8px;border:1px solid var(--border2);background:none;color:var(--muted);font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center}
.modal-close:hover{background:rgba(0,229,255,.06);color:var(--text)}
.modal-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:20px}
.ms{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px;text-align:center}
.ms-val{font-size:22px;font-weight:800}.ms-lbl{font-size:9px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:2px}
.ilog{max-height:400px;overflow-y:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:12px}
.ilog-row{display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid var(--border);font-size:11.5px}
.ilog-row:last-child{border-bottom:none}
.ilog-time{font-family:'JetBrains Mono',monospace;color:var(--muted);font-size:10px;min-width:70px;flex-shrink:0}
.ilog-icon{min-width:16px;text-align:center}
.ilog-body{flex:1;color:var(--text)}
.ilog-target{color:var(--accent2);font-weight:600}
.ilog-reply{color:var(--cyan);font-style:italic}
.ilog-event{color:var(--muted);font-size:10px;margin-left:4px}
.ilog-ago{color:var(--muted);font-size:10px;flex-shrink:0;margin-left:auto}
.filter-bar{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}
.filter-bar select,.filter-bar input{background:var(--surface2);border:1px solid var(--border);color:var(--text);border-radius:8px;padding:6px 10px;font-size:11px;font-family:inherit}
.filter-bar select:focus,.filter-bar input:focus{border-color:var(--accent);outline:none}
.sess-list{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:12px;max-height:250px;overflow-y:auto}
.sess-item{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border);font-size:11px;color:var(--muted)}
.sess-item:last-child{border-bottom:none}
.sess-dur{font-family:'JetBrains Mono',monospace;color:var(--text);font-weight:600;min-width:60px}
.sess-stat{font-family:'JetBrains Mono',monospace}
.sess-r{color:var(--yellow);font-weight:600}
@media(max-width:900px){.cards{grid-template-columns:repeat(3,1fr)}}
@media(max-width:600px){.cards{grid-template-columns:repeat(2,1fr)}}"""

USER_DASH_CSS = """:root{--bg:#04060c;--surface:#090d18;--surface2:#0e1422;--surface3:#141c2e;--border:rgba(0,229,255,.07);--border2:rgba(0,229,255,.16);--text:#d8e8ff;--muted:#4a6080;--accent:#00e5ff;--accent2:#38f5c0;--green:#00ff87;--yellow:#ffc107;--red:#ff3b6b;--blue:#4d9dff;--cyan:#00e5ff}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
::-webkit-scrollbar{width:5px;height:5px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:rgba(0,229,255,.25);border-radius:3px}
body{font-family:'Space Grotesk',-apple-system,sans-serif;background:var(--bg);background-image:radial-gradient(rgba(0,229,255,.06) 1px,transparent 1px);background-size:28px 28px;color:var(--text);min-height:100vh;font-size:14px;line-height:1.5}
a{color:var(--accent2);text-decoration:none}a:hover{text-decoration:underline}

/* Header */
.hdr{position:sticky;top:0;z-index:100;backdrop-filter:blur(16px);background:var(--bg);border-bottom:1px solid var(--border2);box-shadow:0 1px 30px rgba(0,229,255,.04);display:flex;align-items:center;padding:0 24px;height:56px;gap:16px}
.brand{font-weight:900;font-size:16px;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;white-space:nowrap;display:flex;align-items:center;gap:10px}
.brand-icon{width:32px;height:32px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:16px}
.hdr-badge{font-size:10px;font-weight:700;background:rgba(0,229,255,.1);color:var(--accent);padding:3px 10px;border-radius:20px;letter-spacing:.05em}
.hdr-right{margin-left:auto;display:flex;align-items:center;gap:12px}
.hdr-time{font-size:11px;color:var(--muted);font-family:'JetBrains Mono',monospace}

/* Layout */
.wrap{padding:24px;max-width:1200px;margin:0 auto}

/* Hero section */
.hero{background:linear-gradient(135deg,rgba(0,229,255,.06),rgba(56,245,192,.04));border:1px solid rgba(0,229,255,.12);border-radius:20px;padding:32px;margin-bottom:24px;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;top:-50%;right:-20%;width:300px;height:300px;background:radial-gradient(circle,rgba(0,229,255,.06),transparent 70%);pointer-events:none}
.hero-row{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.hero-avatar{width:56px;height:56px;border-radius:14px;background:var(--surface2);border:2px solid var(--border2);display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:800;color:var(--accent2)}
.hero-info h2{font-size:22px;font-weight:800;margin-bottom:2px}
.hero-info p{font-size:13px;color:var(--muted)}
.hero-status{margin-left:auto;display:flex;flex-direction:column;align-items:flex-end;gap:6px}
.status-pill{display:inline-flex;align-items:center;gap:6px;padding:5px 14px;border-radius:20px;font-size:11px;font-weight:700}
.s-active{background:rgba(0,255,135,.08);color:var(--green);border:1px solid rgba(0,255,135,.2)}
.s-trial{background:rgba(255,193,7,.08);color:var(--yellow);border:1px solid rgba(255,193,7,.2)}
.s-expired{background:rgba(255,59,107,.08);color:var(--red);border:1px solid rgba(255,59,107,.2)}
.key-type{font-size:10px;color:var(--muted);font-family:'JetBrains Mono',monospace}

/* Stats cards */
@keyframes fadeInUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:24px}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px;position:relative;overflow:hidden;transition:all .2s ease;animation:fadeInUp .4s ease both}
.stat:hover{border-color:rgba(0,229,255,.22);box-shadow:0 0 28px rgba(0,229,255,.07);transform:translateY(-2px)}
.stat:nth-child(1){animation-delay:.1s}.stat:nth-child(2){animation-delay:.2s}.stat:nth-child(3){animation-delay:.3s}.stat:nth-child(4){animation-delay:.4s}.stat:nth-child(5){animation-delay:.5s}
.stat::after{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.stat.purple::after{background:linear-gradient(90deg,var(--accent),transparent)}
.stat.green::after{background:linear-gradient(90deg,var(--green),transparent)}
.stat.yellow::after{background:linear-gradient(90deg,var(--yellow),transparent)}
.stat.blue::after{background:linear-gradient(90deg,var(--blue),transparent)}
.stat.cyan::after{background:linear-gradient(90deg,var(--cyan),transparent)}
.stat-label{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}
.stat-val{font-size:28px;font-weight:800;line-height:1}
.stat-val.purple{color:var(--accent2)}
.stat-val.green{color:var(--green)}
.stat-val.yellow{color:var(--yellow)}
.stat-val.blue{color:var(--blue)}
.stat-val.cyan{color:var(--cyan)}
.stat-sub{font-size:11px;color:var(--muted);margin-top:4px}

/* Sections */
.section{margin-bottom:24px}
.section-hdr{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.section-title{font-size:13px;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}
.section-count{font-size:11px;color:var(--accent2);background:rgba(0,229,255,.08);padding:2px 10px;border-radius:12px;font-weight:700}

/* Account cards */
.acc-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}
.acc-card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px;transition:.2s}
.acc-card:hover{border-color:rgba(0,229,255,.22);box-shadow:0 0 28px rgba(0,229,255,.07);transform:translateY(-2px)}
.acc-head{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.acc-dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.acc-dot.on{background:var(--green);box-shadow:0 0 8px rgba(0,255,135,.4);animation:pulse-dot 2s infinite}
@keyframes pulse-dot{0%,100%{box-shadow:0 0 8px rgba(0,255,135,.4)}50%{box-shadow:0 0 14px rgba(0,255,135,.6)}}
.acc-dot.off{background:#1a2840}
.acc-name{font-weight:700;font-size:15px}
.acc-uid{font-size:11px;color:var(--muted);font-family:'JetBrains Mono',monospace}
.acc-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.acc-stat{text-align:center;padding:12px 6px;background:var(--surface2);border-radius:10px;border:1px solid var(--border)}
.acc-stat-val{font-size:18px;font-weight:800;color:var(--text)}
.acc-stat-lbl{font-size:9px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:4px}
.acc-conv{margin-top:12px;padding:10px 14px;background:var(--surface2);border-radius:10px;border:1px solid var(--border)}
.acc-conv-bar{height:6px;background:var(--surface3);border-radius:3px;overflow:hidden;margin-top:6px}
.acc-conv-fill{height:100%;border-radius:3px;transition:width .3s}
.acc-sessions{margin-top:14px}
.acc-sessions summary{font-size:11px;font-weight:700;color:var(--muted);cursor:pointer;text-transform:uppercase;letter-spacing:.06em;padding:6px 0;transition:color .2s}
.acc-sessions summary:hover{color:var(--text)}
.sess-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--border);font-size:11px;color:var(--muted)}
.sess-dur{font-family:'JetBrains Mono',monospace;color:var(--text);font-weight:600;min-width:60px}
.sess-stat{font-family:'JetBrains Mono',monospace}
.sess-r{color:var(--yellow);font-weight:600}

/* Analytics */
.an-grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
.an-card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px}
.an-title{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:14px}
.an-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}
.an-sum-item{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:12px;text-align:center}
.an-sum-val{font-size:22px;font-weight:800;line-height:1}
.an-sum-lbl{font-size:9px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-top:4px}
@media(max-width:768px){.an-grid2{grid-template-columns:1fr}}

/* Guide section */
.guide{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:28px;margin-bottom:24px}
.guide h3{font-size:16px;font-weight:800;margin-bottom:16px;display:flex;align-items:center;gap:10px}
.guide-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.guide-card{background:var(--surface2);border:1px solid var(--border);border-radius:14px;padding:20px}
.guide-card h4{font-size:14px;font-weight:700;margin-bottom:8px;display:flex;align-items:center;gap:8px}
.guide-card p{font-size:12.5px;color:var(--muted);line-height:1.6}
.guide-card .step{display:flex;gap:10px;margin-top:10px;padding:8px 0;border-top:1px solid var(--border)}
.guide-card .step-num{width:22px;height:22px;background:rgba(0,229,255,.1);color:var(--accent);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;flex-shrink:0}
.guide-card .step-text{font-size:12px;color:#7a9abf;line-height:1.5}
.guide-link{display:inline-flex;align-items:center;gap:6px;margin-top:12px;padding:8px 16px;background:rgba(0,229,255,.08);border:1px solid rgba(0,229,255,.16);border-radius:10px;color:var(--accent);font-size:12px;font-weight:600;transition:.15s}
.guide-link:hover{background:rgba(0,229,255,.14);text-decoration:none}

/* Device info */
.device-info{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:14px 18px;margin-top:16px;display:flex;align-items:center;gap:12px;font-size:12px}
.device-icon{font-size:18px}
.device-text{color:var(--muted)}
.device-text strong{color:var(--text)}

/* Footer */
.footer{text-align:center;padding:24px;font-size:11px;color:#1a2840}

/* Responsive */
@media(max-width:768px){
    .hero-row{flex-direction:column;align-items:flex-start}
    .hero-status{margin-left:0;align-items:flex-start}
    .stats{grid-template-columns:repeat(2,1fr)}
    .acc-grid{grid-template-columns:1fr}
    .guide-grid{grid-template-columns:1fr}
}"""

# ─────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────

def replace_style_block(text, template_start_marker, new_css):
    """Replace <style>...</style> inside the template that contains template_start_marker."""
    # Find the template variable assignment start
    idx = text.find(template_start_marker)
    if idx == -1:
        raise ValueError(f"Marker not found: {template_start_marker!r}")
    # Find <style> after marker
    style_open = text.find("<style>", idx)
    if style_open == -1:
        raise ValueError(f"<style> not found after {template_start_marker!r}")
    style_close = text.find("</style>", style_open)
    if style_close == -1:
        raise ValueError("</style> not found")
    # Replace content between <style> and </style> (exclusive of tags)
    return text[:style_open + len("<style>")] + "\n" + new_css + "\n" + text[style_close:]


def replace_font_link(text, template_start_marker, new_url):
    """Replace the Google Fonts href in the template."""
    idx = text.find(template_start_marker)
    if idx == -1:
        raise ValueError(f"Marker not found: {template_start_marker!r}")
    # Find next fonts.googleapis.com link after marker
    fonts_idx = text.find("fonts.googleapis.com", idx)
    if fonts_idx == -1:
        raise ValueError("fonts.googleapis.com not found")
    # Walk back to find the opening quote
    q_open = text.rfind('"', idx, fonts_idx)
    q_close = text.find('"', fonts_idx)
    if q_open == -1 or q_close == -1:
        raise ValueError("Could not find href quotes")
    return text[:q_open + 1] + new_url + text[q_close:]


# ─────────────────────────────────────────────────────
# Apply replacements
# ─────────────────────────────────────────────────────

# 1. _ADMIN_LOGIN_HTML
content = replace_font_link(content, "_ADMIN_LOGIN_HTML", NEW_FONTS_SINGLE)
content = replace_style_block(content, "_ADMIN_LOGIN_HTML", LOGIN_CSS)

# 2. _ADMIN_DASH_HTML
content = replace_font_link(content, "_ADMIN_DASH_HTML", NEW_FONTS_ADMIN)
content = replace_style_block(content, "_ADMIN_DASH_HTML", ADMIN_DASH_CSS)

# 3. _USER_DASH_HTML
content = replace_font_link(content, "_USER_DASH_HTML", NEW_FONTS_ADMIN)
content = replace_style_block(content, "_USER_DASH_HTML", USER_DASH_CSS)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(content)

print("Done.")
