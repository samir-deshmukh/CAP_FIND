"""Render CETFind administrative pages and their browser-side interface helpers.

backend.main owns authentication, API routes and database operations. It calls
these page builders to combine shared CSS/JavaScript with the selected admin
page; browser actions then call the protected endpoints in backend.main.
"""

from __future__ import annotations

import json
import re
from html import escape


# Shared stylesheet used by every page rendered through _shell().
CSS = r'''
:root{--bg:#FFFBF4;--panel:#FFFBF4;--ink:#11120D;--muted:#11120D;--line:#D8CFBC;--red:#11120D;--blue:#11120D;--green:#11120D;--amber:#D8CFBC;--purple:#11120D;--shadow:0 8px 28px rgba(17,18,13,.06);--sidebar:250px}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}a{color:inherit;text-decoration:none}button,input,select,textarea{font:inherit}button{cursor:pointer;border:0}.side{position:fixed;z-index:20;inset:0 auto 0 0;width:var(--sidebar);background:#FFFBF4;border-right:1px solid var(--line);padding:18px 14px}.brand{display:flex;gap:12px;align-items:center;padding:4px 10px 22px}.mark{width:30px;color:var(--red);font-size:31px;font-weight:900}.brand-tortoise{width:34px;height:auto;display:block;overflow:visible}.brand b{display:block;font-size:18px}.brand span{font-size:12px;color:var(--muted)}.nav{display:grid;gap:5px}.nav a{padding:11px 13px;border-radius:9px;color:#11120D;font-size:14px;transition:background .2s,transform .2s,color .2s}.nav a:hover{background:#D8CFBC;color:var(--red);transform:translateX(2px)}.nav a.active{background:#D8CFBC;color:var(--red);font-weight:700}.sidefoot{position:absolute;left:26px;bottom:22px;color:var(--muted);font-size:11px;line-height:1.7}.online{color:#11120D}.main{margin-left:var(--sidebar);min-height:100vh}.top{position:sticky;top:0;z-index:10;height:64px;background:rgba(255,255,255,.94);backdrop-filter:blur(12px);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 26px}.search{width:min(530px,52vw);height:36px;background:#D8CFBC;border:1px solid #D8CFBC;border-radius:9px;display:flex;align-items:center;gap:10px;padding:0 13px;color:var(--muted);font-size:13px}.user{display:flex;align-items:center;gap:12px;font-size:13px}.avatar{width:30px;height:30px;border-radius:50%;background:#11120D;color:#FFFBF4;display:grid;place-items:center;font-size:11px}.content{padding:27px 26px 40px;max-width:1550px}.title{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:23px}.title h1{margin:0;font-size:31px;letter-spacing:-1px}.title p{margin:5px 0;color:var(--muted);font-size:14px}.live{font-size:12px;color:#11120D;display:flex;align-items:center;gap:7px}.dot{width:7px;height:7px;border-radius:50%;background:#11120D;box-shadow:0 0 0 0 rgba(16,185,129,.5);animation:pulse 1.8s infinite}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);transition:transform .2s,box-shadow .2s,border-color .2s}.card:hover{transform:translateY(-1px);box-shadow:0 12px 32px rgba(20,33,61,.08)}.kpi{padding:18px 19px;min-height:125px}.khead{display:flex;align-items:center;gap:12px;color:#11120D;font-size:13px}.ki{width:42px;height:42px;border-radius:50%;display:grid;place-items:center;font-size:19px}.sky{background:#D8CFBC;color:#11120D}.rose{background:#D8CFBC;color:#e11d2e}.mint{background:#D8CFBC;color:#0a9c70}.lav{background:#D8CFBC;color:#11120D}.num{font-size:28px;font-weight:800;margin:6px 0 0 55px;transition:color .25s}.trend{font-size:12px;margin-left:55px}.up{color:#11120D}.warn{color:#11120D}.layout{display:grid;grid-template-columns:minmax(0,2.2fr) minmax(300px,.8fr);gap:14px}.panel{padding:18px}.panel h2{font-size:15px;margin:0}.toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}.muted{color:var(--muted)}.small{font-size:12px}.pipeline{display:flex;gap:3px;overflow:auto;padding:4px 0}.stage{min-width:85px;flex:1;text-align:center;position:relative}.stage:not(:last-child):after{content:'→';position:absolute;right:-4px;top:10px;color:#D8CFBC}.si{width:42px;height:42px;margin:auto;border-radius:50%;background:#D8CFBC;color:#11120D;display:grid;place-items:center;transition:transform .25s,box-shadow .25s}.stage.active .si{animation:floatPulse 1.5s infinite;box-shadow:0 0 0 5px rgba(37,99,235,.08)}.stage.done .si{background:#D8CFBC;color:#0a9c70}.stage.warn .si{background:#FFFBF44dc;color:#11120D}.stage.review .si{background:#D8CFBC;color:#e11d2e}.stage.publish .si{background:#D8CFBC;color:#0a9c70}.stage b{display:block;font-size:10px;margin-top:8px;color:#11120D;line-height:1.25}.stage small{font-size:10px;color:var(--muted)}.recent{margin-top:14px}.tablewrap{overflow:auto}.table{width:100%;border-collapse:collapse;font-size:12px}.table th{background:#FFFBF4;color:#11120D;text-align:left;padding:10px 9px;position:sticky;top:0}.table td{padding:11px 9px;border-bottom:1px solid var(--line);color:#11120D}.table tbody tr{transition:background .15s}.table tbody tr:hover{background:#FFFBF4}.status{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:999px;font-size:10px;font-weight:800;white-space:nowrap}.status:before{content:'';width:6px;height:6px;border-radius:50%;background:currentColor}.status.loading:before{animation:statusSpin .8s linear infinite;box-shadow:0 0 0 2px currentColor}.pdfspin{display:inline-block;width:11px;height:11px;margin-right:7px;border:2px solid #D8CFBC;border-top-color:#11120D;border-radius:50%;vertical-align:-1px;animation:pdfSpin .75s linear infinite}.processbtn{width:34px;height:34px;padding:0;border:1px solid #D8CFBC;background:#FFFBF4;color:#11120D;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:15px}.processbtn:hover{background:#D8CFBC}.processbtn.stop{border-color:#f1c8cd;background:#FFFBF47f8;color:#11120D}.processbtn.retry{border-color:#bfe5d5;background:#FFFBF4;color:#11120D}.activityspin{display:inline-block;width:15px;height:15px;border:2px solid #D8CFBC;border-top-color:#11120D;border-right-color:#11120D;border-radius:50%;animation:pdfSpin .8s linear infinite;vertical-align:-3px}.red{background:#D8CFBC;color:#11120D}.green{background:#e4f8ef;color:#11120D}.blue{background:#D8CFBC;color:#11120D}.purple{background:#D8CFBC;color:#11120D}.amber{background:#FFFBF44dc;color:#11120D}.gray{background:#D8CFBC;color:#11120D}.sidepanel{display:grid;gap:14px}.trendbox{height:220px;display:flex;flex-direction:column}.bars{flex:1;display:flex;align-items:flex-end;gap:9px;padding:15px 8px 4px;border-bottom:1px solid var(--line)}.barcol{flex:1;height:100%;display:flex;align-items:flex-end;gap:4px}.bar{width:50%;border-radius:5px 5px 0 0;background:#D8CFBC;transition:height .7s cubic-bezier(.2,.7,.2,1)}.bar.g{background:#11120D}.health{display:grid}.hr{display:grid;grid-template-columns:32px 1fr auto;align-items:center;gap:9px;padding:11px 0;border-bottom:1px solid var(--line);font-size:12px}.hr:last-child{border-bottom:0}.hi{width:30px;height:30px;border-radius:8px;background:#D8CFBC;display:grid;place-items:center}.healthy{color:#11120D}.danger{color:#11120D}.warning{color:#11120D}.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;border-radius:8px;padding:9px 13px;font-size:12px;font-weight:700;transition:transform .15s,box-shadow .15s,opacity .15s}.btn:hover{transform:translateY(-1px)}.btn:disabled{opacity:.5;cursor:not-allowed;transform:none}.primary{background:var(--red);color:#FFFBF4;box-shadow:0 4px 12px rgba(225,29,46,.18)}.secondary{background:#D8CFBC;color:#11120D}.success{background:#e4f8ef;color:#11120D}.dangerbtn{background:#D8CFBC;color:#11120D}.ghost{background:transparent;color:#11120D;border:1px solid var(--line)}.filters{display:flex;gap:9px;flex-wrap:wrap}.rowactions{display:inline-flex;align-items:center;gap:4px;white-space:nowrap}.action-placeholder{display:inline-block;width:34px;height:34px;flex:0 0 34px}.dashboard-imports .rowactions .iconbtn,.dashboard-imports .rowactions .trashbtn{width:34px;height:34px;min-width:34px}.upload-quick{min-width:0}.upload-quick h2{font-size:14px;margin:0}.upload-quick input[type=file]{max-width:100%}.iconbtn{width:27px;height:27px;min-width:27px;padding:0;display:inline-flex;align-items:center;justify-content:center;border:1px solid #D8CFBC;border-radius:6px;background:#FFFBF4;color:#11120D;font-size:13px;font-weight:700;line-height:1}.iconbtn:hover{background:#D8CFBC}.iconbtn:disabled{opacity:.4;cursor:not-allowed}.status-detail{margin-top:5px;white-space:normal;line-height:1.35}.upload-layout{grid-template-columns:minmax(0,1fr)}.runtime-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}.extraction-mini{min-width:0}.extract-live{display:flex;align-items:center;gap:7px;margin-top:5px;min-height:17px}.extract-progress{font-size:17px!important;white-space:nowrap}.extract-file{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}.commit-progress{padding:8px 2px}.commit-progress-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.commit-progress-head strong{margin-left:auto;font-size:24px}.commit-track{height:12px;border-radius:999px;overflow:hidden;background:#D8CFBC;margin:18px 0 10px}.commit-bar{height:100%;width:0;background:#11120D;transition:width .25s ease}.commit-progress-stats{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;font-size:12px;font-weight:700}.commit-progress .muted{margin-top:12px;line-height:1.5}.import-queue th:last-child,.import-queue td:last-child{width:1%;white-space:nowrap}.openbtn{min-width:58px}.trashbtn{width:34px;height:34px;display:inline-flex;align-items:center;justify-content:center;border:1px solid #D8CFBC;background:#FFFBF47f8;color:#11120D;border-radius:8px;font-size:15px}.trashbtn:hover{background:#D8CFBC}.trashbtn:disabled{opacity:.35;cursor:not-allowed;background:#FFFBF4;border-color:var(--line);color:#11120D}.input,.select{height:37px;border:1px solid var(--line);background:#FFFBF4;border-radius:8px;padding:0 10px;color:#11120D;outline:none}.input:focus,.select:focus{border-color:#D8CFBC;box-shadow:0 0 0 3px rgba(37,99,235,.08)}.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric{padding:16px}.metric .label{font-size:11px;color:var(--muted)}.metric .value{font-size:25px;font-weight:800;margin-top:4px}.pagegrid{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:14px}.notice{padding:12px 14px;border-radius:9px;background:#FFFBF4;border:1px solid var(--line);font-size:12px;color:#11120D}.issue{padding:12px 14px;border-left:4px solid var(--amber);background:#FFFBF4af0;border-radius:8px;margin-bottom:8px;font-size:12px}.issue.good{border-left-color:var(--green);background:#FFFBF4}.skeleton{position:relative;overflow:hidden;background:#D8CFBC;border-radius:6px;color:transparent!important}.skeleton:after{content:'';position:absolute;inset:0;transform:translateX(-100%);background:linear-gradient(90deg,transparent,rgba(255,255,255,.75),transparent);animation:shimmer 1.25s infinite}.empty{text-align:center;padding:42px 18px;color:var(--muted);font-size:13px}.modalback{position:fixed;inset:0;z-index:50;background:rgba(10,20,35,.42);backdrop-filter:blur(3px);display:none;align-items:center;justify-content:center;padding:18px}.modalback.show{display:flex;animation:fadeIn .18s ease}.modal{width:min(760px,100%);max-height:90vh;overflow:auto;background:#FFFBF4;border-radius:14px;box-shadow:0 25px 80px rgba(0,0,0,.2);animation:modalIn .2s ease}.modalhead{padding:18px 20px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}.modalbody{padding:20px}.modalfoot{padding:15px 20px;border-top:1px solid var(--line);display:flex;justify-content:flex-end;gap:8px}.close{background:#D8CFBC;border-radius:50%;width:32px;height:32px;color:#11120D}.toastbox{position:fixed;right:18px;bottom:18px;z-index:100;display:grid;gap:8px}.toast{background:#11120D;color:#FFFBF4;border-radius:9px;padding:11px 14px;font-size:12px;box-shadow:0 10px 30px rgba(0,0,0,.18);animation:toastIn .25s ease}.toast.ok{background:#11120D}.toast.err{background:#11120D}.timeline{display:grid;gap:0}.event{display:grid;grid-template-columns:20px 1fr;gap:10px;position:relative;padding:0 0 17px}.event:before{content:'';position:absolute;left:8px;top:18px;bottom:0;width:2px;background:#D8CFBC}.event:last-child:before{display:none}.eventdot{width:16px;height:16px;border-radius:50%;background:#D8CFBC;border:4px solid #FFFBF4;box-shadow:0 0 0 1px #D8CFBC;z-index:1}.event.active .eventdot{background:var(--blue);box-shadow:0 0 0 5px rgba(37,99,235,.1);animation:pulse 1.6s infinite}.event h4{margin:0;font-size:12px}.event p{margin:3px 0 0;font-size:11px;color:var(--muted)}pre.json{background:#0f172a;color:#d7e1ef;padding:13px;border-radius:9px;overflow:auto;font-size:11px;max-height:300px}
.admin-locked .main{display:none}.admin-tab-lock{position:fixed;inset:0;z-index:9999;display:none;align-items:center;justify-content:center;background:#FFFBF4;padding:24px}.admin-tab-lock.show{display:flex}.admin-tab-lock-card{width:min(440px,100%);background:#FFFBF4;border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:28px;text-align:center}.admin-tab-lock-card h2{margin:0 0 8px;font-size:20px}.admin-tab-lock-card p{margin:0 0 18px;color:var(--muted);font-size:13px;line-height:1.55}.admin-tab-lock-card button{background:var(--ink);color:#FFFBF4;border-radius:8px;padding:10px 16px;font-weight:700}.admin-tab-lock-card small{display:block;margin-top:12px;color:var(--muted)}@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(16,185,129,.45)}70%{box-shadow:0 0 0 8px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}@keyframes statusSpin{0%,100%{transform:scale(.75);opacity:.55}50%{transform:scale(1.15);opacity:1}}@keyframes pdfSpin{to{transform:rotate(360deg)}}@keyframes floatPulse{50%{transform:translateY(-3px)}}@keyframes shimmer{100%{transform:translateX(100%)}}@keyframes fadeIn{from{opacity:0}to{opacity:1}}@keyframes modalIn{from{opacity:0;transform:translateY(8px) scale(.99)}to{opacity:1;transform:none}}@keyframes toastIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@media(max-width:1050px){.cards,.grid4{grid-template-columns:repeat(2,1fr)}.layout,.pagegrid{grid-template-columns:1fr}}@media(max-width:720px){.side{display:none}.main{margin-left:0}.content{padding:20px 14px}.top{padding:0 14px}.search{width:55%}.title h1{font-size:25px}.cards,.grid4{grid-template-columns:1fr}.pipeline{min-width:800px}.table{min-width:760px}.pagegrid{grid-template-columns:1fr}.top .user b{display:none}}

/* Final CETFind palette override: every admin surface uses only the three approved colors. */
:root{--bg:#FFFBF4;--panel:#FFFBF4;--ink:#11120D;--muted:#11120D;--line:#D8CFBC;--red:#11120D;--blue:#11120D;--green:#11120D;--amber:#D8CFBC;--purple:#11120D}
body,.main{background:#FFFBF4;color:#11120D}.side,.top,.card,.panel,.modal,.admin-tab-lock,.admin-tab-lock-card{background:#FFFBF4;border-color:#D8CFBC}.top{box-shadow:0 1px 0 #D8CFBC}.search{background:#FFFBF4;border-color:#D8CFBC;color:#11120D}.nav a{color:#11120D}.nav a:hover,.nav a.active{background:#D8CFBC;color:#11120D}.sidefoot,.muted,.title p,.stage small,.metric .label,.empty,.event p{color:#11120D}.online,.live,.healthy,.danger,.warning{color:#11120D}.dot{background:#11120D}.ki,.si,.hi,.secondary,.dangerbtn,.gray,.blue,.purple,.red,.rose,.mint,.sky,.lav,.green,.success,.amber{background:#D8CFBC!important;color:#11120D!important}.primary,.toast,.toast.ok,.toast.err{background:#11120D!important;color:#FFFBF4!important}.btn.ghost,.ghost{background:#FFFBF4;color:#11120D;border-color:#D8CFBC}.input,.select{background:#FFFBF4;color:#11120D;border-color:#D8CFBC}.input:focus,.select:focus{border-color:#11120D;box-shadow:0 0 0 3px rgba(216,207,188,.55)}.table th{background:#D8CFBC;color:#11120D}.table td{color:#11120D;border-color:#D8CFBC}.table tbody tr:hover{background:#D8CFBC}.processbtn,.trashbtn{background:#FFFBF4;color:#11120D;border-color:#D8CFBC}.processbtn:hover,.trashbtn:hover,.close{background:#D8CFBC;color:#11120D}.stage.active .si,.event.active .eventdot{box-shadow:0 0 0 4px rgba(216,207,188,.65)}.bar{background:#D8CFBC!important}.bar.g{background:#11120D!important}.skeleton{background:#D8CFBC}.modalback{background:rgba(17,18,13,.42)}.timeline .event:before{background:#D8CFBC}.eventdot{background:#D8CFBC;border-color:#FFFBF4;box-shadow:0 0 0 1px #D8CFBC}.admin-close-btn{border-color:#D8CFBC!important}
/* White-led refinement: beige is reserved for borders, selection and subtle highlights. */
body,.side,.top,.content,.card,.panel,.modal,.admin-tab-lock,.admin-tab-lock-card{background:#FFFBF4!important}
.search,.ki,.si,.hi,.secondary,.dangerbtn,.gray,.blue,.purple,.red,.rose,.mint,.sky,.lav,.green,.success,.amber,.table th,.table tbody tr:hover,.processbtn:hover,.trashbtn:hover,.close{background:#FFFBF4!important;color:#11120D!important}
.ki,.si,.hi,.secondary,.dangerbtn,.gray,.blue,.purple,.red,.rose,.mint,.sky,.lav,.green,.success,.amber{border:1px solid #D8CFBC}
.nav a.active{background:#D8CFBC!important;color:#11120D!important}

/* Premium monochrome admin theme */
:root{
  --bg:#F4F4F4;--panel:#FFFFFF;--ink:#111111;--muted:#5F5F5F;
  --line:#DEDEDE;--red:#050505;--blue:#111111;--green:#111111;
  --amber:#BDBDBD;--purple:#111111;--shadow:0 8px 28px rgba(0,0,0,.055)
}
html,body,.main,.content{background:#F4F4F4!important;color:#111111!important}
.side{background:#080808!important;border-right:1px solid #252525!important;color:#FFFFFF!important}
.brand b,.brand span,.brand .mark,.sidefoot,.online{color:#FFFFFF!important}
.brand span,.sidefoot{opacity:.72}
.nav a{color:#C9C9C9!important;background:transparent!important;border:1px solid transparent}
.nav a:hover{background:#1B1B1B!important;color:#FFFFFF!important;border-color:#303030;transform:translateX(2px)}
.nav a.active{background:#FFFFFF!important;color:#080808!important;border-color:#FFFFFF;font-weight:800}
.top{background:rgba(255,255,255,.96)!important;border-bottom:1px solid #DEDEDE!important;box-shadow:0 3px 16px rgba(0,0,0,.035)!important}
.search{background:#F6F6F6!important;border:1px solid #E0E0E0!important;color:#555!important}
.avatar{background:#080808!important;color:#FFFFFF!important}
.card,.panel,.modal,.admin-tab-lock-card{background:#FFFFFF!important;border:1px solid #E1E1E1!important;box-shadow:0 7px 24px rgba(0,0,0,.045)!important}
.card:hover{box-shadow:0 12px 30px rgba(0,0,0,.075)!important}
.title h1,.title p,.khead,.stage b,.stage small,.table td,.metric .label,.metric .value,.muted,.small,.event p,.sidefoot{color:inherit}
.title p,.muted,.metric .label,.stage small,.event p{color:#666666!important}
.live,.online,.healthy,.danger,.warning{color:#222222!important}
.dot{background:#111111!important;box-shadow:0 0 0 4px rgba(0,0,0,.07)!important}
.ki,.si,.hi{background:#F0F0F0!important;color:#111111!important}
.stage.done .si,.stage.warn .si,.stage.review .si,.stage.publish .si{background:#E8E8E8!important;color:#111111!important}
.stage.active .si{background:#111111!important;color:#FFFFFF!important;box-shadow:0 0 0 5px rgba(0,0,0,.09)!important}
.table th{background:#F0F0F0!important;color:#111111!important;border-bottom:1px solid #DCDCDC}
.table td{color:#222222!important;border-color:#E7E7E7!important}
.table tbody tr:hover{background:#F7F7F7!important}
.status{background:#EFEFEF!important;color:#222222!important}
.primary,.toast,.toast.ok,.toast.err{background:#080808!important;color:#FFFFFF!important;box-shadow:0 4px 12px rgba(0,0,0,.13)!important}
.secondary,.dangerbtn,.success,.red,.green,.blue,.purple,.amber,.gray{background:#EEEEEE!important;color:#111111!important}
.btn.ghost,.ghost{background:#FFFFFF!important;color:#111111!important;border:1px solid #D5D5D5!important}
.btn.success{background:#111111!important;color:#FFFFFF!important}
.btn.dangerbtn{background:#F0F0F0!important;color:#111111!important;border:1px solid #D8D8D8}
.input,.select,textarea{background:#FFFFFF!important;color:#111111!important;border:1px solid #D8D8D8!important}
.input:focus,.select:focus,textarea:focus{border-color:#111111!important;box-shadow:0 0 0 3px rgba(0,0,0,.08)!important}
.processbtn,.iconbtn,.trashbtn{background:#FFFFFF!important;color:#111111!important;border:1px solid #D8D8D8!important}
.processbtn:hover,.iconbtn:hover,.trashbtn:hover,.close{background:#111111!important;color:#FFFFFF!important;border-color:#111111!important}
.pdfspin,.activityspin{border-color:#D6D6D6!important;border-top-color:#111111!important;border-right-color:#111111!important}
.commit-track{background:#E8E8E8!important}.commit-bar{background:#111111!important}
.bars{border-color:#E1E1E1!important}.bar{background:#D2D2D2!important}.bar.g{background:#111111!important}
.notice{background:#F7F7F7!important;border-color:#DDDDDD!important;color:#222222!important}
.issue{background:#F5F5F5!important;border-left-color:#777777!important;color:#222222!important}
.skeleton{background:#EAEAEA!important}
.modalback{background:rgba(0,0,0,.58)!important;backdrop-filter:blur(5px)}
.modalhead,.modalfoot{border-color:#E5E5E5!important}
.close{background:#F0F0F0!important;color:#111111!important}
.timeline .event:before{background:#E0E0E0!important}.eventdot{background:#DADADA!important;border-color:#FFFFFF!important;box-shadow:0 0 0 1px #DADADA!important}
.event.active .eventdot{background:#111111!important;box-shadow:0 0 0 5px rgba(0,0,0,.08)!important}
.admin-tab-lock{background:#F4F4F4!important}
.admin-tab-lock-card button{background:#080808!important;color:#FFFFFF!important}
pre.json{background:#111111!important;color:#F1F1F1!important}
/* Soft pearl theme with restrained color and a subtle raised-card depth. */
:root{--bg:#F2F4F7;--panel:#FFFFFF;--ink:#263244;--muted:#697586;--line:#E0E5EC;--red:#355D91;--blue:#4777B7;--green:#32866D;--amber:#B58A45;--purple:#7768A8;--shadow:0 2px 4px rgba(32,48,70,.035),0 9px 22px rgba(32,48,70,.065),inset 0 1px 0 rgba(255,255,255,.95)}
html,body,.main,.content{background:#F2F4F7!important;color:#263244!important}
.side{background:linear-gradient(180deg,#FFFFFF 0%,#F5F7FA 100%)!important;color:#344256!important;border-right:1px solid #E0E5EC!important;box-shadow:3px 0 14px rgba(32,48,70,.035)}
.brand b,.brand span,.brand .mark,.sidefoot,.online{color:#344256!important}.brand span,.sidefoot{opacity:.8}
.nav a{color:#59677A!important;background:transparent!important;border:1px solid transparent}
.nav a:hover{background:#EAF0F8!important;color:#315C91!important;border-color:#DCE6F4;transform:translateX(2px)}
.nav a.active{background:linear-gradient(180deg,#E7EFFA,#DCE8F8)!important;color:#315C91!important;border-color:#D3E0F2!important;box-shadow:inset 0 1px 0 #FFFFFF,0 2px 5px rgba(55,92,145,.08);font-weight:800}
.top{background:rgba(255,255,255,.94)!important;border-bottom:1px solid #E0E5EC!important;box-shadow:0 3px 14px rgba(32,48,70,.04)!important}
.search{background:#F7F9FC!important;border:1px solid #E1E7EF!important;color:#697586!important}
.avatar{background:#E4ECF7!important;color:#355D91!important;border:1px solid #D6E1F0}
.card,.panel,.modal,.admin-tab-lock-card{background:linear-gradient(145deg,#FFFFFF 0%,#FCFDFE 100%)!important;border:1px solid #E0E5EC!important;box-shadow:0 2px 4px rgba(32,48,70,.035),0 9px 22px rgba(32,48,70,.065),inset 0 1px 0 rgba(255,255,255,.98)!important;transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease}
.card:hover{transform:translateY(-2px);border-color:#D5DFEC!important;box-shadow:0 4px 8px rgba(32,48,70,.045),0 14px 28px rgba(32,48,70,.085),inset 0 1px 0 #FFFFFF!important}
.kpi{position:relative;overflow:hidden}.kpi:before{content:"";position:absolute;inset:0 0 auto;height:3px;background:linear-gradient(90deg,#C8D9EF,#E7EDF6);opacity:.9}
.title h1{color:#263244!important}.title p,.muted,.metric .label,.stage small,.event p{color:#697586!important}
.live,.online{color:#3F7D69!important}.dot{background:#4A9B7B!important;box-shadow:0 0 0 4px rgba(74,155,123,.12)!important}
.ki,.si,.hi{background:linear-gradient(145deg,#F4F7FB,#E8EEF6)!important;color:#47668E!important;border:1px solid #DFE7F1;box-shadow:inset 0 1px 0 #FFFFFF,0 2px 4px rgba(32,48,70,.04)}
.khead{color:#526176!important}.num,.metric .value{color:#263244!important}
.table th{background:#F2F5F9!important;color:#526176!important;border-bottom:1px solid #E0E5EC}.table td{color:#354256!important;border-color:#E8ECF1!important}.table tbody tr:hover{background:#F7F9FC!important}
.status{background:#EEF2F7!important;color:#526176!important}.status.loading{background:#EAF1FB!important;color:#426DA8!important}
.primary,.toast,.toast.ok,.toast.err{background:#355D91!important;color:#FFFFFF!important;box-shadow:0 4px 10px rgba(53,93,145,.18)!important}
.secondary,.dangerbtn,.success,.red,.green,.blue,.purple,.amber,.gray{background:#EDF2F8!important;color:#45658D!important;border:1px solid #DDE6F1!important}
.btn.ghost,.ghost{background:#FFFFFF!important;color:#53647A!important;border:1px solid #DDE4ED!important}
.btn.success{background:#E8F4EF!important;color:#2F7D65!important;border:1px solid #D3E9DF!important}
.btn.dangerbtn{background:#F7F1ED!important;color:#986747!important;border:1px solid #EDE0D6!important}
.input,.select,textarea{background:#FFFFFF!important;color:#344256!important;border:1px solid #DCE3EC!important;box-shadow:inset 0 1px 2px rgba(32,48,70,.025)}
.input:focus,.select:focus,textarea:focus{border-color:#9DB6D8!important;box-shadow:0 0 0 3px rgba(100,143,196,.13)!important}
.processbtn,.iconbtn,.trashbtn{background:linear-gradient(180deg,#FFFFFF,#F5F7FA)!important;color:#53647A!important;border:1px solid #DCE3EC!important;box-shadow:0 1px 2px rgba(32,48,70,.04),inset 0 1px 0 #FFFFFF}
.processbtn:hover,.iconbtn:hover,.trashbtn:hover,.close{background:#EAF0F8!important;color:#355D91!important}
.commit-track{background:#E8EDF4!important}.commit-bar{background:linear-gradient(90deg,#5F86BA,#355D91)!important}
.bars{border-color:#E0E5EC!important}.bar{background:#C8D8EA!important}.bar.g{background:#5F86BA!important}
.notice{background:#F7F9FC!important;border-color:#E0E6EF!important;color:#526176!important}.issue{background:#FBF8F5!important;border-left-color:#C5A27D!important;color:#655448!important}
.skeleton{background:#EDF1F6!important}.modalback{background:rgba(43,57,77,.28)!important;backdrop-filter:blur(5px)}.modalhead,.modalfoot{border-color:#E5EAF0!important}.close{background:#EEF2F7!important;color:#526176!important}
.timeline .event:before{background:#E0E7F0!important}.eventdot{background:#DCE6F2!important;border-color:#FFFFFF!important;box-shadow:0 0 0 1px #D5DFEC!important}.event.active .eventdot{background:#5F86BA!important;box-shadow:0 0 0 5px rgba(95,134,186,.13)!important}
.admin-tab-lock{background:#F2F4F7!important}.admin-tab-lock-card button{background:#355D91!important;color:#FFFFFF!important}pre.json{background:#354256!important;color:#F4F7FB!important}
.dashboard-imports{min-height:260px}.dashboard-imports .toolbar{margin-bottom:18px}.dashboard-imports .table{font-size:13px}.dashboard-imports .table th{padding:13px 11px}.dashboard-imports .table td{padding:13px 11px}
@media(max-width:720px){.side{display:none!important}.dashboard-imports .toolbar{align-items:flex-start}}

/* Refinement: warm neutral accents, downward-only card depth, consistent badges. */
:root{--bg:#F3F1EC;--panel:#FFFEFB;--ink:#383832;--muted:#77766F;--line:#E4E0D7;--red:#8C8272;--blue:#8C8272;--green:#7C8875;--amber:#9A8B6E;--purple:#8C8272;--shadow:0 5px 8px rgba(54,49,39,.035),0 13px 24px rgba(54,49,39,.075)}
html,body,.main,.content{background:#F3F1EC!important;color:#383832!important}
.side{background:linear-gradient(180deg,#FFFEFB,#F6F4EF)!important;color:#4A4942!important;border-right:1px solid #E4E0D7!important;box-shadow:3px 0 12px rgba(54,49,39,.035)!important}
.nav a{color:#68675F!important}.nav a:hover,.nav a.active{background:#EAE5DA!important;color:#514D42!important;border-color:#E1DACC!important;box-shadow:0 3px 7px rgba(54,49,39,.06)!important}
.top{box-shadow:0 4px 10px rgba(54,49,39,.045)!important;border-color:#E4E0D7!important}
.card,.panel,.modal,.admin-tab-lock-card{background:linear-gradient(150deg,#FFFEFC 0%,#FBFAF6 100%)!important;border:1px solid #E4E0D7!important;box-shadow:0 4px 7px rgba(54,49,39,.035),0 12px 24px rgba(54,49,39,.075)!important;transition:transform .2s ease,box-shadow .2s ease,border-color .2s ease}
.card:hover{transform:translateY(-1px);border-color:#DCD5C8!important;box-shadow:0 6px 10px rgba(54,49,39,.04),0 16px 29px rgba(54,49,39,.09)!important}
/* Remove the top-edge highlight; depth is cast below each card. */
.card,.panel,.modal,.admin-tab-lock-card,.ki,.si,.hi,.btn,.processbtn,.iconbtn,.trashbtn{inset:auto;}
.card,.panel,.modal,.admin-tab-lock-card{box-shadow:0 4px 7px rgba(54,49,39,.035),0 12px 24px rgba(54,49,39,.075)!important}
.kpi:before{background:linear-gradient(90deg,#D9D1C2,#ECE7DD)!important}
.avatar,.ki,.si,.hi{background:#EEEAE1!important;color:#77705F!important;border-color:#E2DCCE!important;box-shadow:0 2px 4px rgba(54,49,39,.045)!important}
.primary,.toast,.toast.ok,.toast.err{background:#777D6B!important;color:#FFFFFF!important;box-shadow:0 5px 10px rgba(79,87,68,.15)!important}
.secondary,.dangerbtn,.success,.red,.green,.blue,.purple,.amber,.gray,.rose,.mint,.sky,.lav{background:#F0EDE6!important;color:#716B5E!important;border:1px solid #E3DED3!important}
.btn.success{background:#E9EDE5!important;color:#66745D!important;border:1px solid #DCE3D5!important}
.btn.dangerbtn{background:#F3ECE6!important;color:#8C7562!important;border:1px solid #E8DCD1!important}
.status,.status.loading,.status.green,.status.red,.status.purple,.status.blue,.status.amber,.status.gray,.status.rose,.status.mint,.status.sky,.status.lav{background:#F0EDE6!important;color:#6E695E!important;border:1px solid #E4DFD5!important;box-shadow:none!important}
.status.loading{background:#F5F1E7!important;color:#8B7957!important;border-color:#EAE2D1!important}
.status.green{background:#EDF0E9!important;color:#69745F!important;border-color:#DEE5D7!important}
.status.red{background:#F3ECE6!important;color:#8C7562!important;border-color:#E8DCD1!important}
.status.purple,.status.blue,.status.amber,.status.gray{background:#F0EDE6!important;color:#6E695E!important;border-color:#E4DFD5!important}
.table th{background:#F1EEE7!important;color:#6E6B62!important}.table tbody tr:hover{background:#FAF8F3!important}
.commit-track{background:#E8E3D9!important}.commit-bar{background:linear-gradient(90deg,#A5AA98,#7C8875)!important}
.bars{border-color:#E4E0D7!important}.bar{background:#D6D0C3!important}.bar.g{background:#8E9781!important}
.processbtn,.iconbtn,.trashbtn{background:linear-gradient(180deg,#FFFEFC,#F5F2EB)!important;color:#6F6A5F!important;border:1px solid #E2DDD2!important;box-shadow:0 3px 6px rgba(54,49,39,.055)!important}
.processbtn:hover,.iconbtn:hover,.trashbtn:hover,.close{background:#EEE9DF!important;color:#625C4F!important}
.notice{background:#F7F4ED!important;border-color:#E7E0D2!important;color:#6E695E!important}.issue{background:#F8F3ED!important;border-left-color:#B9A58A!important;color:#6D5D4C!important}
.eventdot{background:#DCD7CB!important;box-shadow:0 0 0 1px #DCD7CB!important}.event.active .eventdot{background:#8E9781!important;box-shadow:0 0 0 5px rgba(142,151,129,.14)!important}
.modalback{background:rgba(49,47,40,.30)!important}
.admin-tab-lock-card button{background:#777D6B!important;color:#FFFFFF!important}


/* Statuses are plain text, not badges: remove pill shape, fill, border and status dot. */
.status{
  display:inline;
  padding:0!important;
  border:0!important;
  border-radius:0!important;
  background:transparent!important;
  box-shadow:none!important;
  font-size:11px!important;
  font-weight:600!important;
  line-height:inherit;
  white-space:nowrap;
}
.status:before{display:none!important;content:none!important}


/* Complete admin panel: bright white surfaces, restrained grey borders, soft downward shadows. */
:root{--bg:#FFFFFF;--panel:#FFFFFF;--ink:#171717;--muted:#666666;--line:#E7E7E7;--red:#171717;--blue:#171717;--green:#171717;--amber:#EEEEEE;--purple:#171717;--shadow:0 10px 26px rgba(0,0,0,.06)}
html,body,.main,.content,.side,.top,.card,.panel,.modal,.modalhead,.modalbody,.modalfoot,.admin-tab-lock,.admin-tab-lock-card,.notice,.issue,.search,.input,.select,textarea,.table th,.table td,.metric,.kpi,.toolbar,.filters,.health,.hr,.event,.runtime-metrics,.extraction-mini,.commit-progress,.pagegrid,.layout,.sidepanel,.tablewrap{background-color:#FFFFFF!important;color:#171717!important}
.side{border-right:1px solid #E7E7E7!important}
.top{border-bottom:1px solid #E7E7E7!important;box-shadow:0 3px 14px rgba(0,0,0,.035)!important}
.brand b,.brand span,.brand .mark,.sidefoot,.online{color:#171717!important;opacity:1}
.nav a{color:#333333!important;background:#FFFFFF!important;border-color:transparent!important}
.nav a:hover,.nav a.active{background:#F2F2F2!important;color:#111111!important;border-color:#E5E5E5!important}
.card,.panel,.modal,.admin-tab-lock-card{border:1px solid #E7E7E7!important;box-shadow:0 9px 24px rgba(0,0,0,.06)!important}
.card:hover{box-shadow:0 13px 28px rgba(0,0,0,.075)!important}
.title h1,.title p,.khead,.stage b,.stage small,.table td,.table th,.metric .label,.metric .value,.muted,.small,.event p,.live,.healthy,.danger,.warning{color:#171717!important}
.title p,.muted,.metric .label,.stage small,.event p,.sidefoot{color:#666666!important}
.search,.input,.select,textarea{border:1px solid #E2E2E2!important;box-shadow:none}
.input:focus,.select:focus,textarea:focus{border-color:#AFAFAF!important;box-shadow:0 0 0 3px rgba(0,0,0,.045)!important}
.table th{background:#F8F8F8!important;border-bottom:1px solid #E7E7E7!important}
.table td{border-color:#EEEEEE!important}
.table tbody tr:hover{background:#FAFAFA!important}
.ki,.si,.hi,.stage.done .si,.stage.warn .si,.stage.review .si,.stage.publish .si{background:#F5F5F5!important;color:#222222!important;border:1px solid #EAEAEA}
.stage.active .si{background:#222222!important;color:#FFFFFF!important;box-shadow:0 4px 10px rgba(0,0,0,.12)!important}
.primary,.btn.primary,.toast,.toast.ok,.toast.err{background:#171717!important;color:#FFFFFF!important;border-color:#171717!important}
.secondary,.success,.dangerbtn,.btn.ghost,.ghost,.processbtn,.iconbtn,.trashbtn,.close{background:#FFFFFF!important;color:#171717!important;border:1px solid #E0E0E0!important}
.secondary:hover,.success:hover,.dangerbtn:hover,.ghost:hover,.processbtn:hover,.iconbtn:hover,.trashbtn:hover,.close:hover{background:#F5F5F5!important}
.status{display:inline!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;color:#222222!important;font-size:11px!important;font-weight:600!important}
.status:before{display:none!important;content:none!important}
.red,.green,.blue,.purple,.amber,.gray{background:transparent!important;color:#222222!important}
.notice,.issue{border:1px solid #E8E8E8!important;border-radius:8px}
.commit-track{background:#EEEEEE!important}
.commit-bar{background:#222222!important}
.skeleton{background:#EEEEEE!important}
.modalback{background:rgba(0,0,0,.28)!important}
pre.json{background:#F7F7F7!important;color:#222222!important;border:1px solid #E7E7E7}


/* Clean enterprise light UI: white working surfaces on a soft neutral canvas. */
:root{
  --bg:#F5F7FA;--panel:#FFFFFF;--ink:#17191C;--muted:#68717D;
  --line:#E4E8ED;--red:#17191C;--blue:#17191C;--green:#17191C;
  --amber:#ECEFF2;--purple:#17191C;--shadow:0 2px 5px rgba(20,28,38,.025),0 8px 22px rgba(20,28,38,.045)
}
html,body{background:#F5F7FA!important;color:#17191C!important}
.main,.content{background:#F5F7FA!important;color:#17191C!important}
.side,.top{background:#FFFFFF!important;color:#17191C!important}
.side{border-right:1px solid #E5E9EE!important}
.top{border-bottom:1px solid #E5E9EE!important;box-shadow:0 2px 7px rgba(20,28,38,.025)!important}
.brand b,.brand .mark,.brand span,.sidefoot,.online{color:#17191C!important}
.brand span,.sidefoot{color:#78818C!important}
.nav{gap:4px!important}
.nav a{background:transparent!important;color:#515B67!important;border:1px solid transparent!important;border-radius:7px!important;padding:10px 12px!important;font-weight:500!important}
.nav a:hover{background:#F5F7F9!important;color:#17191C!important;border-color:#EEF0F3!important;transform:none!important}
.nav a.active{position:relative;background:#F1F3F5!important;color:#17191C!important;border-color:#E8EBEF!important;font-weight:650!important}
.nav a.active:before{content:"";position:absolute;left:-1px;top:7px;bottom:7px;width:3px;background:#17191C;border-radius:0 3px 3px 0}
.search{background:#F7F8FA!important;border:1px solid #E4E8ED!important;color:#68717D!important;border-radius:8px!important}
.avatar{background:#17191C!important;color:#FFFFFF!important}
.content{padding-top:30px!important}
.title{margin-bottom:25px!important}
.title h1{font-size:29px!important;letter-spacing:-.7px!important;font-weight:650!important;color:#17191C!important}
.title p{font-size:13px!important;line-height:1.55!important;color:#68717D!important}
.card,.panel,.modal,.admin-tab-lock-card{background:#FFFFFF!important;border:1px solid #E4E8ED!important;border-radius:11px!important;box-shadow:var(--shadow)!important}
.card:hover{box-shadow:0 3px 7px rgba(20,28,38,.03),0 11px 25px rgba(20,28,38,.055)!important;transform:translateY(-1px)}
.kpi{padding:19px!important}
.khead{font-size:12px!important;font-weight:550!important;color:#5E6874!important}
.num,.metric .value{font-size:27px!important;font-weight:650!important;letter-spacing:-.45px!important;color:#17191C!important}
.trend{font-size:11px!important;color:#69737F!important}
.ki,.si,.hi{background:#F2F4F6!important;color:#343B44!important;border:1px solid #E9EDF1!important;border-radius:9px!important}
.stage.active .si{background:#17191C!important;color:#FFFFFF!important;box-shadow:0 3px 8px rgba(23,25,28,.12)!important}
.stage b{font-size:10px!important;font-weight:600!important;color:#424B56!important}
.stage small{color:#78818C!important}
.tablewrap{border-radius:8px!important}
.table{font-size:12px!important}
.table th{background:#F7F8FA!important;color:#68717D!important;font-size:10px!important;font-weight:650!important;text-transform:uppercase;letter-spacing:.045em;border-bottom:1px solid #E4E8ED!important;padding:12px 11px!important}
.table td{background:#FFFFFF!important;color:#303741!important;border-bottom:1px solid #EDF0F3!important;padding:12px 11px!important}
.table tbody tr:hover td{background:#FAFBFC!important}
.toolbar h2,.panel h2{font-size:14px!important;font-weight:650!important;color:#252A31!important}
.muted,.small,.metric .label,.event p,.stage small{color:#68717D!important}
.live{color:#4E5864!important;font-weight:550!important}
.dot{background:#4C8A70!important;box-shadow:0 0 0 4px rgba(76,138,112,.10)!important}
.primary,.btn.primary{background:#17191C!important;color:#FFFFFF!important;border:1px solid #17191C!important;box-shadow:0 2px 3px rgba(20,28,38,.08)!important}
.primary:hover,.btn.primary:hover{background:#30343A!important}
.secondary,.success,.dangerbtn,.btn.ghost,.ghost,.processbtn,.iconbtn,.trashbtn,.close{background:#FFFFFF!important;color:#303741!important;border:1px solid #DCE2E8!important;box-shadow:none!important}
.secondary:hover,.success:hover,.dangerbtn:hover,.ghost:hover,.processbtn:hover,.iconbtn:hover,.trashbtn:hover,.close:hover{background:#F5F7F9!important;border-color:#CBD3DC!important}
.btn{border-radius:7px!important;font-weight:600!important}
.input,.select,textarea{background:#FFFFFF!important;color:#252A31!important;border:1px solid #DCE2E8!important;border-radius:7px!important}
.input::placeholder,textarea::placeholder{color:#89929D!important}
.input:focus,.select:focus,textarea:focus{border-color:#8A949F!important;box-shadow:0 0 0 3px rgba(85,98,112,.10)!important}
.status{display:inline!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;color:#4B5561!important;font-size:11px!important;font-weight:600!important}
.status:before{display:none!important;content:none!important}
.red,.green,.blue,.purple,.amber,.gray{background:transparent!important;color:#4B5561!important}
.notice{background:#F8FAFB!important;border:1px solid #E5EAF0!important;color:#4D5864!important;border-radius:8px!important}
.issue{background:#FBF8F3!important;border-left-color:#B6A17D!important;color:#655A49!important}
.commit-track{background:#E9EDF1!important;border-radius:5px!important}
.commit-bar{background:#303943!important}
.skeleton{background:#ECEFF3!important}
.bars{border-color:#E5E9EE!important}
.bar{background:#D9DEE5!important}
.bar.g{background:#65717E!important}
.hr,.event:before{border-color:#E8ECF0!important;background:#E8ECF0!important}
.eventdot{background:#D6DCE3!important;border-color:#FFFFFF!important;box-shadow:0 0 0 1px #D6DCE3!important}
.event.active .eventdot{background:#65717E!important;box-shadow:0 0 0 4px rgba(101,113,126,.12)!important}
.modalback{background:rgba(22,28,35,.34)!important}
.modalhead,.modalfoot{border-color:#E5E9EE!important}
pre.json{background:#F7F9FB!important;color:#303741!important;border:1px solid #E5E9EE!important}
.toast,.toast.ok,.toast.err{background:#17191C!important;color:#FFFFFF!important;box-shadow:0 8px 22px rgba(20,28,38,.16)!important}
@media(max-width:720px){.content{padding:20px 14px 32px!important}.title h1{font-size:25px!important}.card,.panel{border-radius:9px!important}}


/* Strict monochrome finish: black, white, and neutral greys only. */
:root{--bg:#FFFFFF;--panel:#FFFFFF;--ink:#111111;--muted:#666666;--line:#E5E5E5;--red:#111111;--blue:#111111;--green:#111111;--amber:#EAEAEA;--purple:#111111;--shadow:0 2px 5px rgba(0,0,0,.025),0 8px 22px rgba(0,0,0,.045)}
html,body,.main,.content{background:#F5F5F5!important;color:#111111!important}
.side,.top,.card,.panel,.modal,.modalhead,.modalbody,.modalfoot,.admin-tab-lock,.admin-tab-lock-card{background:#FFFFFF!important;color:#111111!important}
.side{border-right:1px solid #E5E5E5!important}
.top{border-bottom:1px solid #E5E5E5!important;box-shadow:0 2px 7px rgba(0,0,0,.03)!important}
.brand b,.brand .mark,.brand span,.sidefoot,.online{color:#111111!important;opacity:1}
.sidefoot,.brand span{color:#666666!important}
.nav a{background:transparent!important;color:#444444!important;border:1px solid transparent!important}
.nav a:hover,.nav a.active{background:#F0F0F0!important;color:#111111!important;border-color:#E5E5E5!important;transform:none!important}
.nav a.active{font-weight:650!important}
.nav a.active:before{content:"";position:absolute;left:-1px;top:7px;bottom:7px;width:3px;background:#111111;border-radius:0 2px 2px 0}
.search{background:#F7F7F7!important;border:1px solid #E5E5E5!important;color:#666666!important}
.avatar{background:#111111!important;color:#FFFFFF!important}
.card,.panel,.modal,.admin-tab-lock-card{border:1px solid #E5E5E5!important;border-radius:10px!important;box-shadow:var(--shadow)!important}
.card:hover{box-shadow:0 3px 7px rgba(0,0,0,.03),0 11px 25px rgba(0,0,0,.055)!important;transform:translateY(-1px)}
.title h1,.khead,.stage b,.table td,.table th,.metric .label,.metric .value,.toolbar h2,.panel h2{color:#111111!important}
.title p,.muted,.small,.metric .label,.stage small,.event p{color:#666666!important}
.live,.healthy,.danger,.warning,.online{color:#333333!important}
.dot{background:#111111!important;box-shadow:0 0 0 4px rgba(0,0,0,.08)!important}
.ki,.si,.hi,.stage.done .si,.stage.warn .si,.stage.review .si,.stage.publish .si{background:#F2F2F2!important;color:#222222!important;border:1px solid #E8E8E8!important}
.stage.active .si{background:#111111!important;color:#FFFFFF!important;box-shadow:0 3px 8px rgba(0,0,0,.12)!important}
.table th{background:#F5F5F5!important;color:#555555!important;border-bottom:1px solid #E5E5E5!important}
.table td{background:#FFFFFF!important;color:#222222!important;border-color:#EEEEEE!important}
.table tbody tr:hover td{background:#FAFAFA!important}
.primary,.btn.primary{background:#111111!important;color:#FFFFFF!important;border:1px solid #111111!important;box-shadow:0 2px 4px rgba(0,0,0,.08)!important}
.primary:hover,.btn.primary:hover{background:#292929!important}
.secondary,.success,.dangerbtn,.btn.ghost,.ghost,.processbtn,.iconbtn,.trashbtn,.close{background:#FFFFFF!important;color:#222222!important;border:1px solid #DDDDDD!important;box-shadow:none!important}
.secondary:hover,.success:hover,.dangerbtn:hover,.ghost:hover,.processbtn:hover,.iconbtn:hover,.trashbtn:hover,.close:hover{background:#F3F3F3!important;border-color:#CCCCCC!important}
.btn{border-radius:7px!important;font-weight:600!important}
.input,.select,textarea{background:#FFFFFF!important;color:#222222!important;border:1px solid #DDDDDD!important;border-radius:7px!important}
.input::placeholder,textarea::placeholder{color:#888888!important}
.input:focus,.select:focus,textarea:focus{border-color:#777777!important;box-shadow:0 0 0 3px rgba(0,0,0,.07)!important}
.status{display:inline!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important;color:#333333!important;font-size:11px!important;font-weight:600!important}
.status:before{display:none!important;content:none!important}
.red,.green,.blue,.purple,.amber,.gray{background:transparent!important;color:#333333!important}
.notice{background:#F8F8F8!important;border:1px solid #E7E7E7!important;color:#444444!important;border-radius:8px!important}
.issue{background:#F7F7F7!important;border-left-color:#777777!important;color:#333333!important}
.commit-track{background:#EAEAEA!important;border-radius:5px!important}
.commit-bar{background:#222222!important}
.skeleton{background:#EEEEEE!important}
.bars{border-color:#E5E5E5!important}
.bar{background:#D5D5D5!important}
.bar.g{background:#666666!important}
.hr,.event:before{border-color:#E8E8E8!important;background:#E8E8E8!important}
.eventdot{background:#D6D6D6!important;border-color:#FFFFFF!important;box-shadow:0 0 0 1px #D6D6D6!important}
.event.active .eventdot{background:#555555!important;box-shadow:0 0 0 4px rgba(0,0,0,.09)!important}
.modalback{background:rgba(0,0,0,.34)!important}
.modalhead,.modalfoot{border-color:#E5E5E5!important}
pre.json{background:#F7F7F7!important;color:#222222!important;border:1px solid #E5E5E5!important}
.toast,.toast.ok,.toast.err{background:#111111!important;color:#FFFFFF!important;box-shadow:0 8px 22px rgba(0,0,0,.16)!important}


/* Strict black-and-white, white-led pass: no beige, grey fills, or tinted shadows. */
:root{--bg:#FFFFFF;--panel:#FFFFFF;--ink:#000000;--muted:#000000;--line:#FFFFFF;--red:#000000;--blue:#000000;--green:#000000;--amber:#000000;--purple:#000000;--shadow:none}
html,body,.main,.content,.side,.top,.card,.panel,.modal,.admin-tab-lock,.admin-tab-lock-card,
.search,.ki,.si,.hi,.sky,.rose,.mint,.lav,.secondary,.dangerbtn,.success,.red,.green,.blue,.purple,.amber,.gray,
.table th,.table tbody tr:hover,.processbtn,.iconbtn,.trashbtn,.close,.notice,.issue,.skeleton,.stage .si,
.commit-track,.bars,.bar,.eventdot,.event:before,.admin-tab-lock-card button,.input,.select,textarea{
  background:#FFFFFF!important;color:#000000!important;border-color:#FFFFFF!important;box-shadow:none!important
}
body,.main,.content,.side,.top,.card,.panel,.modal,.admin-tab-lock,.admin-tab-lock-card{background:#FFFFFF!important}
*{box-shadow:none!important;text-shadow:none!important}
html,body{color:#000000!important}
.brand b,.brand span,.brand .mark,.sidefoot,.online,.nav a,.nav a:hover,.nav a.active,
.title h1,.title p,.khead,.stage b,.stage small,.table th,.table td,.metric .label,.metric .value,
.muted,.small,.event p,.live,.healthy,.danger,.warning,.status,.status-detail,.empty,.search{color:#000000!important}
.nav a{background:#FFFFFF!important;border:0!important;border-radius:0!important}
.nav a:hover,.nav a.active{background:#FFFFFF!important;color:#000000!important;border-bottom:1px solid #000000!important}
.primary,.toast,.toast.ok,.toast.err,.commit-bar{background:#000000!important;color:#FFFFFF!important;border-color:#000000!important}
.btn.ghost,.ghost,.input,.select,textarea,.processbtn,.iconbtn,.trashbtn{background:#FFFFFF!important;color:#000000!important;border:1px solid #000000!important}
.btn.secondary,.btn.success,.btn.dangerbtn,.secondary,.success,.dangerbtn{background:#FFFFFF!important;color:#000000!important;border:1px solid #FFFFFF!important}
.table th,.table td{border-color:#FFFFFF!important}
.status{display:inline!important;padding:0!important;border:0!important;border-radius:0!important;font-weight:600!important}
.status:before{display:none!important}
.dot,.bar.g,.event.active .eventdot{background:#000000!important;box-shadow:none!important}
.bar{background:#000000!important}
.pdfspin,.activityspin{border-color:#000000!important;border-top-color:#FFFFFF!important;border-right-color:#FFFFFF!important}
.skeleton:after{background:linear-gradient(90deg,transparent,rgba(0,0,0,.06),transparent)!important}
.modalback{background:rgba(0,0,0,.35)!important}


/* Final shadow tuning: white-led UI with only subtle neutral black depth. */
:root{--shadow:0 3px 10px rgba(0,0,0,.035)}
.card,.panel,.modal,.admin-tab-lock-card{
  box-shadow:0 3px 10px rgba(0,0,0,.035)!important;
}
.card:hover{
  box-shadow:0 5px 14px rgba(0,0,0,.055)!important;
}
.top{
  box-shadow:0 2px 7px rgba(0,0,0,.025)!important;
}


/* Restore the original blue admin theme; retain current layout and processing UI */
:root{
  --bg:#f6f8fb!important;--panel:#ffffff!important;--ink:#14213d!important;
  --muted:#6b7c93!important;--line:#e5eaf0!important;--red:#e11d2e!important;
  --blue:#2563eb!important;--green:#10b981!important;--amber:#f59e0b!important;
  --purple:#8b5cf6!important;--shadow:0 8px 28px rgba(20,33,61,.06)!important;
}
html,body,.main,.content{background:#f6f8fb!important;color:#14213d!important}
.side{background:#ffffff!important;color:#14213d!important;border-right:1px solid #e5eaf0!important}
.brand b,.brand span,.brand .mark,.sidefoot{color:#14213d!important}
.brand span,.sidefoot,.muted,.title p,.metric .label,.stage small,.event p{color:#6b7c93!important}
.online,.live,.healthy{color:#10a875!important}
.nav a{color:#36506f!important;background:transparent!important;border-color:transparent!important}
.nav a:hover{background:#fff4f5!important;color:#e11d2e!important;border-color:#ffe1e5!important}
.nav a.active{background:#fff0f1!important;color:#e11d2e!important;border-color:#ffe1e5!important}
.top{background:rgba(255,255,255,.96)!important;border-bottom:1px solid #e5eaf0!important;box-shadow:0 3px 16px rgba(20,33,61,.035)!important}
.search{background:#f5f7fa!important;border:1px solid #eef1f5!important;color:#6b7c93!important}
.avatar{background:#14213d!important;color:#ffffff!important}
.card,.panel,.modal,.admin-tab-lock-card{background:#ffffff!important;border:1px solid #e5eaf0!important;box-shadow:0 8px 28px rgba(20,33,61,.06)!important}
.card:hover{box-shadow:0 12px 32px rgba(20,33,61,.08)!important}
.khead,.stage b,.table td,.metric .value,.title h1{color:#14213d!important}
.dot{background:#10b981!important;box-shadow:0 0 0 4px rgba(16,185,129,.10)!important}
.ki,.si,.hi{background:#eef4ff!important;color:#2563eb!important}
.sky,.lav{background:#eaf2ff!important;color:#2563eb!important}
.rose{background:#fff0f1!important;color:#e11d2e!important}
.mint,.stage.done .si,.stage.publish .si{background:#e8fbf3!important;color:#0a9c70!important}
.stage.warn .si{background:#fff7e6!important;color:#b7791f!important}
.stage.review .si{background:#fff0f1!important;color:#e11d2e!important}
.stage.active .si{background:#2563eb!important;color:#ffffff!important;box-shadow:0 0 0 5px rgba(37,99,235,.10)!important}
.table th{background:#f5f7fa!important;color:#36506f!important;border-bottom:1px solid #e5eaf0!important}
.table td{color:#14213d!important;border-color:#edf0f5!important}
.table tbody tr:hover{background:#f6f9ff!important}
.status{background:#eef4ff!important;color:#2563eb!important}
.primary,.toast,.toast.ok{background:#2563eb!important;color:#ffffff!important;box-shadow:0 4px 12px rgba(37,99,235,.18)!important}
.toast.err,.dangerbtn,.red,.danger{background:#fff0f1!important;color:#d92332!important}
.secondary,.gray,.processbtn,.iconbtn,.trashbtn,.btn.ghost,.ghost{background:#ffffff!important;color:#36506f!important;border:1px solid #dbe3ef!important}
.success,.green,.btn.success{background:#e8fbf3!important;color:#087f5b!important}
.blue,.purple{background:#eef4ff!important;color:#2563eb!important}
.amber{background:#fff7e6!important;color:#b7791f!important}
.input,.select,textarea{background:#ffffff!important;color:#14213d!important;border:1px solid #dbe3ef!important}
.input:focus,.select:focus,textarea:focus{border-color:#2563eb!important;box-shadow:0 0 0 3px rgba(37,99,235,.10)!important}
.processbtn:hover,.iconbtn:hover,.trashbtn:hover,.close{background:#2563eb!important;color:#ffffff!important;border-color:#2563eb!important}
.pdfspin,.activityspin{border-color:#dbe3ef!important;border-top-color:#2563eb!important;border-right-color:#2563eb!important}
.commit-track{background:#e5eaf0!important}.commit-bar{background:#2563eb!important}
.bars{border-color:#e5eaf0!important}.bar{background:#cbd8eb!important}.bar.g{background:#10b981!important}
.notice{background:#f5f8ff!important;border-color:#dce7fa!important;color:#36506f!important}
.issue{background:#fff7f7!important;border-left-color:#e11d2e!important;color:#7f1d1d!important}
.skeleton{background:#edf1f7!important}
.modalback{background:rgba(20,33,61,.48)!important}
.modalhead,.modalfoot{border-color:#e5eaf0!important}
.close{background:#f5f7fa!important;color:#36506f!important}
.timeline .event:before{background:#dbe3ef!important}.eventdot{background:#cbd8eb!important;border-color:#ffffff!important;box-shadow:0 0 0 1px #dbe3ef!important}
.event.active .eventdot{background:#2563eb!important;box-shadow:0 0 0 5px rgba(37,99,235,.10)!important}
.admin-tab-lock{background:#f6f8fb!important}
.admin-tab-lock-card button{background:#2563eb!important;color:#ffffff!important}
pre.json{background:#14213d!important;color:#f6f8fb!important}


/* Final palette correction: cool violet + slate; remove blue/red/green accents and warm shadows */
:root{
  --bg:#f7f7fb!important;--panel:#ffffff!important;--ink:#29263d!important;
  --muted:#77758a!important;--line:#e7e6ef!important;--red:#6d5bd0!important;
  --blue:#6d5bd0!important;--green:#6d5bd0!important;--amber:#6d5bd0!important;
  --purple:#6d5bd0!important;--shadow:0 4px 14px rgba(49,46,129,.075)!important;
}
html,body,.main,.content{background:#f7f7fb!important;color:#29263d!important}
.side{background:#ffffff!important;color:#29263d!important;border-right:1px solid #e7e6ef!important}
.brand b,.brand span,.brand .mark,.sidefoot,.khead,.stage b,.table td,.metric .value,.title h1{color:#29263d!important}
.brand span,.sidefoot,.muted,.title p,.metric .label,.stage small,.event p{color:#77758a!important}
.online,.live,.healthy{color:#6d5bd0!important}
.nav a{color:#59566f!important;background:transparent!important;border-color:transparent!important}
.nav a:hover,.nav a.active{background:#f0edff!important;color:#5b4ac4!important;border-color:#e2dcff!important}
.top{background:rgba(255,255,255,.97)!important;border-bottom:1px solid #e7e6ef!important;box-shadow:0 2px 8px rgba(49,46,129,.035)!important}
.search{background:#fafaff!important;border:1px solid #e7e6ef!important;color:#77758a!important}
.avatar{background:#393451!important;color:#ffffff!important}
.card,.panel,.modal,.admin-tab-lock-card{background:#ffffff!important;border:1px solid #e7e6ef!important;box-shadow:0 4px 14px rgba(49,46,129,.075)!important}
.card:hover{box-shadow:0 6px 18px rgba(49,46,129,.10)!important}
.dot{background:#6d5bd0!important;box-shadow:0 0 0 4px rgba(109,91,208,.10)!important}
.ki,.si,.hi,.sky,.lav,.rose,.mint,.stage.done .si,.stage.publish .si,.stage.warn .si,.stage.review .si{
  background:#f0edff!important;color:#5b4ac4!important;
}
.stage.active .si{background:#6d5bd0!important;color:#ffffff!important;box-shadow:0 0 0 5px rgba(109,91,208,.12)!important}
.table th{background:#f8f7fc!important;color:#59566f!important;border-bottom:1px solid #e7e6ef!important}
.table td{color:#29263d!important;border-color:#eeedf4!important}
.table tbody tr:hover{background:#faf9ff!important}
.status,.blue,.purple,.green,.success,.amber,.primary,.toast,.toast.ok,.btn.success{
  background:#f0edff!important;color:#5b4ac4!important;border-color:#e2dcff!important;
}
.toast.err,.dangerbtn,.red,.danger{background:#f0edff!important;color:#5b4ac4!important;border-color:#e2dcff!important}
.secondary,.gray,.processbtn,.iconbtn,.trashbtn,.btn.ghost,.ghost,.close{
  background:#ffffff!important;color:#59566f!important;border:1px solid #e1dfec!important;
}
.input,.select,textarea{background:#ffffff!important;color:#29263d!important;border:1px solid #e1dfec!important}
.input:focus,.select:focus,textarea:focus{border-color:#8b7ce8!important;box-shadow:0 0 0 3px rgba(109,91,208,.10)!important}
.processbtn:hover,.iconbtn:hover,.trashbtn:hover,.close:hover,.primary:hover{
  background:#6d5bd0!important;color:#ffffff!important;border-color:#6d5bd0!important;
}
.pdfspin,.activityspin{border-color:#e1dfec!important;border-top-color:#6d5bd0!important;border-right-color:#6d5bd0!important}
.commit-track{background:#e7e6ef!important}.commit-bar{background:#6d5bd0!important}
.bars{border-color:#e7e6ef!important}.bar,.bar.g{background:#b8afea!important}
.notice{background:#f8f7ff!important;border-color:#e2dcff!important;color:#59566f!important}
.issue{background:#f8f7ff!important;border-left-color:#8b7ce8!important;color:#59566f!important}
.skeleton{background:#eeedf5!important}
.modalback{background:rgba(41,38,61,.38)!important}
.modalhead,.modalfoot{border-color:#e7e6ef!important}
.timeline .event:before{background:#e1dfec!important}
.eventdot{background:#b8afea!important;border-color:#ffffff!important;box-shadow:0 0 0 1px #e1dfec!important}
.event.active .eventdot{background:#6d5bd0!important;box-shadow:0 0 0 5px rgba(109,91,208,.10)!important}
.admin-tab-lock{background:#f7f7fb!important}
.admin-tab-lock-card button{background:#6d5bd0!important;color:#ffffff!important}
pre.json{background:#29263d!important;color:#f7f7fb!important}


/* Strict neutral theme: white, greys, and charcoal only */
:root{
 --bg:#f4f4f4!important;--panel:#ffffff!important;--ink:#262626!important;
 --muted:#707070!important;--line:#dedede!important;
 --red:#666666!important;--blue:#666666!important;--green:#666666!important;
 --amber:#666666!important;--purple:#666666!important;
 --shadow:0 3px 12px rgba(0,0,0,.07)!important;
}
html,body,.main,.content,.admin-tab-lock{background:#f4f4f4!important;color:#262626!important}
.side,.top,.card,.panel,.modal,.admin-tab-lock-card{background:#fff!important;color:#262626!important;border-color:#dedede!important;box-shadow:0 3px 12px rgba(0,0,0,.06)!important}
.brand b,.brand span,.brand .mark,.sidefoot,.khead,.stage b,.table td,.metric .value,.title h1,
.label,.value,h1,h2,h3,strong,b{color:#262626!important}
.brand span,.sidefoot,.muted,.title p,.metric .label,.stage small,.event p,.small{color:#707070!important}
.nav a,.secondary,.gray,.processbtn,.iconbtn,.trashbtn,.btn.ghost,.ghost{color:#555!important;background:#fff!important;border-color:#d6d6d6!important}
.nav a:hover,.nav a.active{background:#e9e9e9!important;color:#222!important;border-color:#d0d0d0!important}
.online,.live,.healthy{color:#555!important}
.avatar,pre.json{background:#333!important;color:#fff!important}
.card:hover{box-shadow:0 5px 15px rgba(0,0,0,.09)!important}
.dot{background:#777!important;box-shadow:0 0 0 4px rgba(0,0,0,.07)!important}
.ki,.si,.hi,.sky,.lav,.rose,.mint,.stage.done .si,.stage.publish .si,.stage.warn .si,.stage.review .si,
.status,.blue,.purple,.green,.success,.amber,.primary,.toast,.toast.ok,.btn.success,.toast.err,.dangerbtn,.red,.danger{
 background:#e9e9e9!important;color:#333!important;border-color:#d2d2d2!important;box-shadow:none!important
}
.stage.active .si,.processbtn:hover,.iconbtn:hover,.trashbtn:hover,.close,.admin-tab-lock-card button{
 background:#555!important;color:#fff!important;border-color:#555!important;box-shadow:none!important
}
.table th{background:#f0f0f0!important;color:#444!important;border-color:#dedede!important}
.table td{color:#292929!important;border-color:#e5e5e5!important}
.table tbody tr:hover{background:#f7f7f7!important}
.input,.select,textarea,.search{background:#fff!important;color:#333!important;border:1px solid #d4d4d4!important}
.input:focus,.select:focus,textarea:focus{border-color:#888!important;box-shadow:0 0 0 2px rgba(0,0,0,.07)!important}
.pdfspin,.activityspin{border-color:#d8d8d8!important;border-top-color:#666!important;border-right-color:#666!important}
.commit-track,.bars{background:#e5e5e5!important;border-color:#d8d8d8!important}
.commit-bar,.bar,.bar.g,.eventdot,.event.active .eventdot{background:#777!important;border-color:#fff!important;box-shadow:none!important}
.notice,.issue,.issue.good{background:#f3f3f3!important;border-color:#d8d8d8!important;border-left-color:#888!important;color:#444!important}
.skeleton{background:#e9e9e9!important}
.modalback{background:rgba(0,0,0,.42)!important}
.modalhead,.modalfoot,.timeline .event:before{border-color:#dedede!important}
.close{background:#eee!important;color:#444!important}
.admin-tab-lock{background:#f4f4f4!important}

/* Consistent compact controls and balanced admin grids */
.runtime-metrics{grid-template-columns:minmax(0,1.65fr) repeat(2,minmax(0,1fr))!important;align-items:stretch}
.runtime-metrics>.upload-quick{min-width:0;display:flex;flex-direction:column;justify-content:flex-start}
.runtime-metrics .resource-metric{padding:10px 12px;min-height:0;align-self:start}
.runtime-metrics .resource-metric .value{font-size:18px;margin-top:2px}
.runtime-metrics .resource-metric .small{font-size:10px;line-height:1.3}
.release-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}
.runtime-metrics .upload-quick form{min-width:0}
.runtime-metrics .upload-quick input[type=file]{width:100%;font-size:12px}
.health-metrics{grid-template-columns:repeat(4,minmax(0,1fr));align-items:stretch}
.detected-issues .value{font-size:22px;margin-top:4px}
.issue-summary{display:block;line-height:1.35;margin-top:5px;overflow-wrap:anywhere}
.derived-grid{grid-template-columns:minmax(0,1fr)}
.derived-build-card{align-self:stretch;padding:14px}
.derived-build-card .toolbar{margin-bottom:10px;align-items:center}
.derived-build-card .filters{display:grid;grid-template-columns:minmax(0,1fr);gap:9px;margin-top:8px!important}
.course-picker{position:relative;width:100%;min-width:0}.course-picker-trigger{width:100%;min-height:38px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 12px;border:1px solid #DEDEDE;border-radius:8px;background:#FFFFFF;color:#111111;text-align:left}.course-picker-trigger:after{content:"";width:8px;height:8px;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;transform:rotate(45deg);margin:0 3px 4px 0;flex:0 0 auto}.course-picker-menu{display:none;position:static;width:100%;max-height:230px;overflow-y:auto;overscroll-behavior:contain;margin-top:6px;background:#FFFFFF;border:1px solid #DEDEDE;border-radius:8px;box-shadow:none;padding:4px;scrollbar-width:thin;scrollbar-color:#999 #EEEEEE}.course-picker.open .course-picker-menu{display:block}.course-picker-option{display:block;width:100%;padding:9px 10px;border:0;border-radius:5px;background:#FFFFFF;color:#222;text-align:left;font-size:13px}.course-picker-option:hover,.course-picker-option[aria-selected="true"]{background:#F0F0F0}.course-picker-menu::-webkit-scrollbar{width:8px}.course-picker-menu::-webkit-scrollbar-thumb{background:#999;border-radius:8px}
.derived-build-card #buildBtn{width:100%;min-height:38px}
.select{appearance:none;-webkit-appearance:none;background-color:#FFFFFF!important;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='m2 4 4 4 4-4' fill='none' stroke='%23111111' stroke-width='1.5'/%3E%3C/svg%3E")!important;background-repeat:no-repeat!important;background-position:right 11px center!important;padding-right:31px!important;border-color:#DEDEDE!important;border-radius:8px!important;color:#111111!important}
.select option{background:#FFFFFF;color:#111111;padding:8px}
.filters .select{min-width:135px}
.resolver-actions{display:grid;grid-template-columns:repeat(2,minmax(106px,1fr));align-items:stretch;gap:6px;width:100%;min-width:0}
.resolver-actions .btn{width:100%;min-width:0;min-height:31px;padding:6px 8px!important;white-space:nowrap;justify-content:center}
.resolver-actions .small{display:flex;align-items:center;justify-content:center;min-height:31px}
.table td{vertical-align:middle}
.feedback-message-box{display:block;width:100%;max-width:520px;max-height:132px;overflow-y:auto;overflow-x:hidden;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;padding:10px 11px;border:1px solid #E1E1E1;border-radius:7px;background:#F8F8F8;color:#222;line-height:1.5;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#999 #EEEEEE}
.feedback-message-box::-webkit-scrollbar{width:8px}
.feedback-message-box::-webkit-scrollbar-track{background:#EEEEEE;border-radius:8px}
.feedback-message-box::-webkit-scrollbar-thumb{background:#999;border-radius:8px}
.feedback-message-box::-webkit-scrollbar-thumb:hover{background:#666}
.feedback-table{table-layout:fixed;min-width:1000px}
.feedback-table th:nth-child(1){width:145px}.feedback-table th:nth-child(2){width:80px}.feedback-table th:nth-child(3){width:40%}.feedback-table th:nth-child(4){width:125px}.feedback-table th:nth-child(5){width:95px}.feedback-table th:nth-child(6){width:135px}
.resolver-table td:last-child{min-width:225px}
@media(max-width:1050px){.derived-grid{grid-template-columns:1fr}.runtime-metrics{grid-template-columns:repeat(3,minmax(0,1fr))!important}.health-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:720px){.runtime-metrics,.health-metrics{grid-template-columns:1fr!important}.derived-build-card .filters{grid-template-columns:1fr}}

/* Keep Upload anchored to the lower-right corner of the upload panel. */
.import-workspace>.upload-quick{display:flex;flex-direction:column}
.import-workspace>.upload-quick form{display:flex;flex:1;flex-direction:column;min-height:0}
.import-workspace>.upload-quick #uploadState{margin-top:auto!important;padding-top:8px}
.import-workspace>.upload-quick #uploadBtn{align-self:flex-end;margin-top:10px}

/* Import workspace: processing sits directly under RAM and CPU, beside upload. */
.build-loading{align-items:center;gap:12px;min-height:68px}
.source-loading{display:flex;align-items:center;gap:10px;min-height:52px}
.build-loading .activityspin{width:23px;height:23px;flex:0 0 23px;border-width:3px}
.import-workspace{display:grid;grid-template-columns:minmax(260px,.82fr) minmax(0,1.6fr);gap:14px;align-items:stretch;margin-bottom:14px}
.import-workspace>.upload-quick{padding:16px;min-width:0;height:100%;align-self:stretch}
.import-runtime-column{display:grid;gap:10px;min-width:0}
.import-runtime-column .runtime-metrics{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:10px;align-items:stretch}
.import-runtime-column .resource-metric{width:100%;height:100%;min-height:104px;display:flex;flex-direction:column;justify-content:center}
.import-runtime-column .resource-metric .value{overflow-wrap:anywhere}
.import-runtime-column .resource-metric{padding:10px 12px;min-width:0}
.import-runtime-column #liveExtractionCard{margin-top:0!important;min-width:0}
.import-source-name{margin-top:4px;overflow-wrap:anywhere;line-height:1.35}
.btn.dangerbtn{background:#111111!important;color:#FFFFFF!important;border:1px solid #111111!important;box-shadow:0 2px 5px rgba(0,0,0,.12)}
.btn.dangerbtn:hover{background:#333333!important;color:#FFFFFF!important;box-shadow:0 4px 9px rgba(0,0,0,.18)}
#clearBuildBtn{background:#FFFFFF!important;color:#111111!important;border:1px solid #777777!important;box-shadow:0 1px 3px rgba(0,0,0,.08)}
#clearBuildBtn:hover{background:#EEEEEE!important;border-color:#111111!important}
@media(max-width:1050px){.import-workspace{grid-template-columns:minmax(0,1fr)}.derived-grid{grid-template-columns:minmax(0,1fr)}}
@media(max-width:720px){.import-runtime-column .runtime-metrics{grid-template-columns:repeat(2,minmax(0,1fr))!important}.import-workspace{grid-template-columns:minmax(0,1fr)}}

/* Make admin controls dependable on touch screens: hover transforms can move
   a target under the user's finger during the first tap in mobile browsers. */
button,a.btn,.nav a{touch-action:manipulation;-webkit-tap-highlight-color:transparent}
@media (hover:none),(pointer:coarse){
  button:hover,.btn:hover,.nav a:hover,.card:hover{transform:none!important}
}

'''


def _custom_select_script() -> str:
    """Build the custom dropdown UI while keeping each original select in sync.

    _shell() includes this script, so the enhancement is shared across admin pages.
    """
    return r'''
<script>
// Enhance native select elements without changing their submitted form values.
(function(){
  const STYLE_ID='cet-custom-select-style';
  if(!document.getElementById(STYLE_ID)){
    const style=document.createElement('style');style.id=STYLE_ID;style.textContent=`
      .cet-select-wrap{position:relative;display:inline-block;vertical-align:middle;min-width:160px;max-width:100%;font-size:12px;color:#111}
      .cet-select-native{position:absolute!important;width:1px!important;height:1px!important;opacity:0!important;pointer-events:none!important;inset:auto!important}
      .cet-select-trigger{display:flex;width:100%;min-height:37px;align-items:center;justify-content:space-between;gap:14px;padding:8px 11px;background:#fff!important;color:#111!important;border:1px solid #d8d8d8!important;border-radius:7px!important;text-align:left;font:inherit;line-height:1.35;cursor:pointer;box-shadow:none!important}
      .cet-select-trigger:focus-visible,.cet-select-wrap.open .cet-select-trigger{outline:2px solid #aaa;outline-offset:1px;border-color:#777!important}
      .cet-select-arrow{width:8px;height:8px;flex:0 0 8px;border-right:1.5px solid #222;border-bottom:1.5px solid #222;transform:rotate(45deg) translateY(-2px);transition:transform .12s}
      .cet-select-wrap.open .cet-select-arrow{transform:rotate(225deg) translate(-1px,-1px)}
      .cet-select-menu{position:absolute;top:calc(100% + 5px);left:0;right:0;min-width:100%;max-height:260px;overflow:auto;display:none;z-index:200;background:#fff!important;color:#111!important;border:1px solid #d6d6d6;border-radius:8px;padding:4px;box-shadow:0 8px 22px rgba(0,0,0,.12)}
      .cet-select-wrap.open .cet-select-menu{display:block}
      .cet-select-option{display:block;width:100%;padding:9px 10px;border:0;border-radius:5px;background:#fff!important;color:#111!important;text-align:left;font:inherit;line-height:1.35;overflow-wrap:anywhere;cursor:pointer}
      .cet-select-option:hover,.cet-select-option:focus-visible{background:#eee!important;outline:none}
      .cet-select-option[aria-selected=true]{background:#e6e6e6!important;font-weight:700}
      .filters .cet-select-wrap{min-width:160px}
      .resolver-table .cet-select-wrap{min-width:118px}
      @media(max-width:720px){.filters .cet-select-wrap{min-width:min(100%,220px)}.cet-select-wrap{max-width:100%}}
    `;document.head.appendChild(style);
  }
  function closeAll(except){document.querySelectorAll('.cet-select-wrap.open').forEach(w=>{if(w!==except){w.classList.remove('open');w.querySelector('.cet-select-trigger')?.setAttribute('aria-expanded','false')}})}
  function enhance(sel){
    // The calculator owns its course picker UI; do not wrap its hidden backing select.
    if(!(sel instanceof HTMLSelectElement)||sel.dataset.cetCustomSelect==='1'||sel.closest('.course-picker'))return;
    sel.dataset.cetCustomSelect='1';
    const wrap=document.createElement('div');wrap.className='cet-select-wrap';
    const width=sel.style.width;if(width)wrap.style.width=width;
    sel.parentNode.insertBefore(wrap,sel);wrap.appendChild(sel);sel.classList.add('cet-select-native');sel.setAttribute('aria-hidden','true');sel.tabIndex=-1;
    const trigger=document.createElement('button');trigger.type='button';trigger.className='cet-select-trigger';trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');
    const label=document.createElement('span');label.className='cet-select-label';label.style.minWidth='0';label.style.overflow='hidden';label.style.textOverflow='ellipsis';label.style.whiteSpace='nowrap';
    const arrow=document.createElement('span');arrow.className='cet-select-arrow';arrow.setAttribute('aria-hidden','true');trigger.append(label,arrow);
    const menu=document.createElement('div');menu.className='cet-select-menu';menu.setAttribute('role','listbox');
    wrap.append(trigger,menu);
    function sync(){
      const chosen=sel.options[sel.selectedIndex];label.textContent=chosen?chosen.textContent.trim():'Select…';
      menu.innerHTML='';
      [...sel.options].forEach((opt,index)=>{
        const item=document.createElement('button');item.type='button';item.className='cet-select-option';item.setAttribute('role','option');item.setAttribute('aria-selected',opt.selected?'true':'false');item.textContent=opt.textContent.trim();item.disabled=opt.disabled;
        item.addEventListener('click',()=>{if(opt.disabled)return;sel.selectedIndex=index;sel.dispatchEvent(new Event('input',{bubbles:true}));sel.dispatchEvent(new Event('change',{bubbles:true}));sync();wrap.classList.remove('open');trigger.setAttribute('aria-expanded','false');trigger.focus()});menu.appendChild(item);
      });
    }
    trigger.addEventListener('click',()=>{const opening=!wrap.classList.contains('open');closeAll(wrap);wrap.classList.toggle('open',opening);trigger.setAttribute('aria-expanded',String(opening));if(opening){const selected=menu.querySelector('[aria-selected=true]');if(selected)selected.scrollIntoView({block:'nearest'})}});
    trigger.addEventListener('keydown',e=>{if(e.key==='ArrowDown'||e.key==='Enter'||e.key===' '){e.preventDefault();closeAll(wrap);wrap.classList.add('open');trigger.setAttribute('aria-expanded','true');(menu.querySelector('[aria-selected=true]')||menu.querySelector('button:not(:disabled)'))?.focus()}else if(e.key==='Escape'){wrap.classList.remove('open');trigger.setAttribute('aria-expanded','false')}});
    menu.addEventListener('keydown',e=>{const items=[...menu.querySelectorAll('button:not(:disabled)')],i=items.indexOf(document.activeElement);if(e.key==='ArrowDown'){e.preventDefault();items[Math.min(items.length-1,i+1)]?.focus()}else if(e.key==='ArrowUp'){e.preventDefault();items[Math.max(0,i-1)]?.focus()}else if(e.key==='Escape'){wrap.classList.remove('open');trigger.setAttribute('aria-expanded','false');trigger.focus()}});
    sel.addEventListener('change',sync);sel.addEventListener('input',sync);
    new MutationObserver(sync).observe(sel,{childList:true,subtree:true,attributes:true,attributeFilter:['selected','disabled']});
    sync();
  }
  function scan(root){if(root.matches?.('select'))enhance(root);root.querySelectorAll?.('select').forEach(enhance)}
  scan(document);
  new MutationObserver(records=>records.forEach(r=>r.addedNodes.forEach(n=>{if(n.nodeType===1)scan(n)}))).observe(document.documentElement,{childList:true,subtree:true});
  document.addEventListener('click',e=>{if(!e.target.closest('.cet-select-wrap'))closeAll(null)});
  document.addEventListener('change',e=>{if(e.target instanceof HTMLSelectElement)enhance(e.target)});
})();
</script>
'''


def _shell(title: str, active: str, body: str, extra_js: str = '') -> str:
    """Wrap page content in the common admin layout and navigation.

    Combines the shared CSS, live indicator, page-specific JavaScript and dropdown script.
    All page builders return their HTML through this function.
    """
    links = [
        ('dashboard','⌂','Dashboard','/admin'),
        ('imports','⇧','Import Center','/admin/imports'),
        ('review','▤','Review Center','/admin/review'),
        ('releases','◉','Releases','/admin/releases'),
        ('derived','▦','CET Data Calculator','/admin/derived-data'),
        ('resolver','⌁','Website Resolver','/admin/resolver'),
        ('health','♡','Data Health','/admin/health'),
        ('feedback','✦','Feedback','/admin/feedback'),
        ('audit','◷','Audit Log','/admin/audit'),
    ]
    nav = ''.join(f'<a class="{"active" if active==k else ""}" href="{href}">{icon} &nbsp; {label}</a>' for k,icon,label,href in links)
    # Standardize the upper-right live indicator across every admin section.
    body = re.sub(r'<div class="live">.*?</div>', '<div class="live"><span class="dot"></span>Live · <span id="lastRefresh" class="admin-live-time">--:--:--</span></div>', body, flags=re.DOTALL)
    return f'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} - CET CAP Admin</title><style>{CSS}</style></head><body class="admin-locked">
<div id="adminTabLock" class="admin-tab-lock"><div class="admin-tab-lock-card"><h2 id="adminTabLockTitle">Checking admin connection</h2><p id="adminTabLockMessage">Verifying the active admin tab with the server.</p><button id="adminTabLockRetry" type="button" onclick="window.__cetAdminTabRetry&&window.__cetAdminTabRetry()">Retry connection</button><small id="adminTabLockHint">A temporary connection failure does not necessarily mean another tab is open.</small></div></div>
<aside class="side"><div class="brand"><div class="mark">╫</div><div><b>CET CAP PORTAL</b></div></div><nav class="nav">{nav}</nav><div class="sidefoot">CET CAP Portal v1.0.0<br>Maharashtra Admissions System<br><span class="online">● System Online</span></div></aside>
<main class="main"><section class="content">{body}</section></main><div id="toastbox" class="toastbox"></div>{extra_js}<script>(function(){{const update=()=>{{const time=new Date().toLocaleTimeString([],{{hour:'2-digit',minute:'2-digit',second:'2-digit'}});document.querySelectorAll('.admin-live-time').forEach(el=>el.textContent=time)}};update();setInterval(update,1000)}})();</script>{_custom_select_script()}
</body></html>'''


def _common_js():
    """Provide shared browser helpers for authenticated admin pages.

    Handles the single-tab session lock, CSRF headers, API requests, status labels and formatting.
    Page-specific scripts use these helpers instead of repeating request and UI logic.
    """
    return r'''<script>
// Shared browser-side helpers used by every authenticated admin page.
const ADMIN_AUTH_KEY='cet-cap-admin-auth-v1';
function displayCourseFamily(value){
  const raw=String(value??'').trim();
  const normalized=raw.toUpperCase().replace(/[.\s]/g,'');
  if(['BE','BTECH','BE/BTECH'].includes(normalized))return 'BE / BTech';
  const labels={BARCH:'B.Architecture',MARCH:'M.Architecture',BPLAN:'B.Planning',MPLAN:'M.Planning',BPHARM:'B.Pharmacy',MPHARM:'M.Pharmacy',PHARMD:'Pharm.D',ME:'M.E.',LLB3:'3-Year LLB',LLB5:'5-Year Law',BED:'B.Ed',BPED:'B.P.Ed',MED:'M.Ed',MPED:'M.P.Ed',HMCT:'HMCT',MHMCT:'MHMCT',BDES:'B.Des',MTECH:'M.Tech'};
  return labels[normalized]||raw;
}
if(sessionStorage.getItem(ADMIN_AUTH_KEY)!=='1'){
  window.location.replace('/admin/login');
  throw new Error('Admin login required for this browser tab.');
}
window.__cetAdminTabReady=false;
window.__cetAdminLockMessage='Admin connection is unavailable. Retry the connection.';
// Coordinate one active admin tab, with the server-side lock as the authority.
(function(){
  const LOCK_KEY='cet-cap-admin-active-tab-v1';
  const TAB_KEY='cet-cap-admin-tab-id-v1';
  const TTL=45000;
  const body=document.body, gate=document.getElementById('adminTabLock');
  const title=document.getElementById('adminTabLockTitle');
  const message=document.getElementById('adminTabLockMessage');
  const retry=document.getElementById('adminTabLockRetry');
  const hint=document.getElementById('adminTabLockHint');
  const newId=()=>crypto.randomUUID?crypto.randomUUID():Date.now().toString(36)+'-'+Math.random().toString(36).slice(2)+'-'+Math.random().toString(36).slice(2);
  const instanceId=newId(); // unique to this live document; never copied with sessionStorage
  let tabId=sessionStorage.getItem(TAB_KEY);
  if(!tabId){tabId=newId();sessionStorage.setItem(TAB_KEY,tabId);}
  function csrf(){const m=document.cookie.match(/(?:^|; )cet_admin_csrf=([^;]+)/);return m?decodeURIComponent(m[1]):'';}
  function readLock(){try{return JSON.parse(localStorage.getItem(LOCK_KEY)||'null')}catch(_){return null}}
  function rotateTabId(){tabId=newId();sessionStorage.setItem(TAB_KEY,tabId);}
  async function resolveClonedTabIdentity(){
    const existing=readLock();
    const fresh=existing&&existing.id===tabId&&Number(existing.ts)>Date.now()-TTL;
    const owner=fresh?(existing.instanceId||null):null;
    if(!('BroadcastChannel' in window)){
      if(owner&&owner!==instanceId)rotateTabId();
      return;
    }
    const peers=new Set();
    let channel;
    try{
      channel=new BroadcastChannel('cet-cap-admin-tab-identity-v1');
      channel.onmessage=event=>{
        const data=event.data||{};
        if(data.tabId!==tabId||data.instanceId===instanceId)return;
        if(data.type==='probe')channel.postMessage({type:'peer',tabId,instanceId});
        if(data.type==='peer')peers.add(data.instanceId);
      };
      channel.postMessage({type:'probe',tabId,instanceId});
      await new Promise(resolve=>setTimeout(resolve,180));
      channel.close();
    }catch(_){
      try{if(channel)channel.close()}catch(__){}
      if(owner&&owner!==instanceId)rotateTabId();
      return;
    }
    // If a live tab owns this copied ID, only the copy rotates. A stale lock
    // without a live peer is retained so the same tab can recover after reload.
    if(owner&&owner!==instanceId&&peers.has(owner)){rotateTabId();return;}
    // Simultaneously opened duplicate tabs elect one deterministic owner.
    if(!owner&&peers.size&&[instanceId,...peers].sort()[0]!==instanceId)rotateTabId();
  }
  function showBlocked(kind='connection'){
    window.__cetAdminTabReady=false;
    body.classList.add('admin-locked');gate.classList.add('show');
    if(kind==='other-tab'){
      title.textContent='Admin panel active in another tab';
      message.textContent='Another browser tab currently holds the admin lock. Close that tab, or wait for its lock to expire, then retry.';
      retry.textContent='Retry admin lock';
      hint.textContent='For security, only one admin tab is allowed at a time.';
      window.__cetAdminLockMessage='Admin panel is active in another tab. Close the other tab or retry the lock.';
    }else{
      title.textContent='Cannot verify admin connection';
      message.textContent='The server did not confirm this tab’s admin lock. This can happen during a temporary outage; it does not prove another tab is open.';
      retry.textContent='Retry connection';
      hint.textContent='Your extraction worker continues independently while this PC remains on.';
      window.__cetAdminLockMessage='Admin server is temporarily unavailable. Retry the connection.';
    }
  }
  async function acquire(){
    // localStorage is only a cross-tab hint and can be stale during navigation.
    // The server-side lock is authoritative; never reject a tab locally first.
    try{
      const r=await fetch('/admin/api/admin-lock/acquire',{method:'POST',headers:{'X-CSRF-Token':csrf(),'X-Admin-Client-ID':tabId},cache:'no-store'});
      if(r.status===401){window.location.replace('/admin/login');return false;}
      if(r.status===409){showBlocked('other-tab');return false;}
      if(!r.ok){showBlocked('connection');return false;}
      try{localStorage.setItem(LOCK_KEY,JSON.stringify({id:tabId,ts:Date.now(),instanceId}));}catch(_){}
      body.classList.remove('admin-locked');gate.classList.remove('show');window.__cetAdminTabReady=true;window.__cetAdminLockMessage='';return true;
    }catch(_){showBlocked('connection');return false;}
  }
  window.__cetAdminTabRetry=acquire;
  const NAVIGATION_KEY='cet-cap-admin-same-tab-navigation-v1';
  let sameTabNavigation=false;
  try{
    sameTabNavigation=sessionStorage.getItem(NAVIGATION_KEY)==='1';
    sessionStorage.removeItem(NAVIGATION_KEY);
  }catch(_){}
  // A marker written by this document's pagehide means this is the next page
  // in the same tab. Preserve its tab ID rather than treating the previous
  // document, briefly alive during navigation, as a duplicated tab.
  window.__cetAdminLockPromise=(sameTabNavigation?Promise.resolve():resolveClonedTabIdentity()).then(acquire);
  // Backpressure is essential: a slow database heartbeat must not spawn a
  // new request every five seconds and worsen pool exhaustion.
  let heartbeatBusy=false;
  setInterval(async function(){
    if(!window.__cetAdminTabReady||heartbeatBusy)return;
    heartbeatBusy=true;
    try{
      const r=await fetch('/admin/api/admin-lock/heartbeat',{method:'POST',headers:{'X-CSRF-Token':csrf(),'X-Admin-Client-ID':tabId},cache:'no-store'});
      if(r.status===401){window.location.replace('/admin/login');return;}
      if(r.status===409){await acquire();return;}
      if(!r.ok){showBlocked('connection');return;}
      try{localStorage.setItem(LOCK_KEY,JSON.stringify({id:tabId,ts:Date.now(),instanceId}));}catch(_){}
    }catch(_){showBlocked('connection');}
    finally{heartbeatBusy=false;}
  },5000);
  // Do not block on storage events: a stale write from a previous page can
  // race with successful server acquisition. The next API/heartbeat response
  // will enforce the single-tab lock using the authoritative database row.
  // Clear only the browser-side ownership marker on page exit. A new document
  // in the same tab must reuse sessionStorage's tab ID, not mistake the old
  // document's instance ID for a duplicated tab. Do not DELETE the server lock
  // here: a keepalive release can race with the next page's acquire request.
  window.addEventListener('pagehide',function(){
    try{sessionStorage.setItem('cet-cap-admin-same-tab-navigation-v1','1');}catch(_){}
    const x=readLock();
    const ownsLock=x&&x.id===tabId&&(!x.instanceId||x.instanceId===instanceId);
    if(ownsLock){try{localStorage.removeItem(LOCK_KEY);}catch(_){}}
  });

})();
// Prevent overlapping refreshes when one API poll takes longer than its interval.
window.__cetAdminPollBusy=false;
window.__cetAdminRunPoll=async function(fn){if(window.__cetAdminPollBusy)return;window.__cetAdminPollBusy=true;try{if(!window.__cetAdminTabReady&&window.__cetAdminLockPromise)await window.__cetAdminLockPromise;if(!window.__cetAdminTabReady)return;await fn()}finally{window.__cetAdminPollBusy=false}};
// Common request, escaping and display helpers shared by page-specific scripts.
const esc=v=>String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const csrfHeaders=(extra={})=>{const m=document.cookie.match(/(?:^|; )cet_admin_csrf=([^;]+)/);return Object.assign({'X-CSRF-Token':m?decodeURIComponent(m[1]):'','X-Admin-Client-ID':sessionStorage.getItem('cet-cap-admin-tab-id-v1')||''},extra)};
async function toast(msg,type=''){const d=document.createElement('div');d.className='toast '+type;d.textContent=msg;document.querySelector('#toastbox').appendChild(d);setTimeout(()=>d.remove(),3500)}
async function api(url,opts={},lockRetry=true){if(window.__cetAdminLockPromise)await window.__cetAdminLockPromise;if(!window.__cetAdminTabReady)throw new Error(window.__cetAdminLockMessage||'Admin connection is unavailable. Retry the connection.');const tabId=sessionStorage.getItem('cet-cap-admin-tab-id-v1')||'';const h=Object.assign({},opts.headers||{},{'X-Admin-Client-ID':tabId});let r=await fetch(url,Object.assign({},opts,{headers:h,cache:opts.cache||'no-store'}));let raw=await r.text();let data=raw;try{data=raw?JSON.parse(raw):null}catch{}if(r.status===401){window.location='/admin/login';throw new Error('Admin session expired. Please sign in again.')}const detail=data&&typeof data==='object'?(data.detail??data.message??data.error??data):data;if(r.status===409&&lockRetry&&typeof detail==='string'&&detail.toLowerCase().includes('admin panel is active in another tab')){const token=document.cookie.match(/(?:^|; )cet_admin_csrf=([^;]+)/);try{const lock=await fetch('/admin/api/admin-lock/acquire',{method:'POST',headers:{'X-CSRF-Token':token?decodeURIComponent(token[1]):'','X-Admin-Client-ID':tabId},cache:'no-store'});if(lock.ok)return await api(url,opts,false)}catch(_){}}if(!r.ok)throw new Error(typeof detail==='string'?detail:JSON.stringify(detail));return data}
// Format server timestamps and resource values consistently across admin pages.
function fmtTime(v){if(!v)return '—';const d=new Date(String(v).replace(' ','T')+'Z');if(Number.isNaN(d.getTime()))return esc(v);return d.toLocaleString([], {dateStyle:'medium',timeStyle:'short'})}
function bytes(value){const n=Number(value);if(!Number.isFinite(n)||n<0)return '—';if(n<1024)return n+' B';const units=['KiB','MiB','GiB','TiB'];let size=n/1024,i=0;while(size>=1024&&i<units.length-1){size/=1024;i++}return size.toFixed(size>=100?0:size>=10?1:2)+' '+units[i]}
function ramMegabytes(used,limit){const u=Number(used),l=Number(limit);if(!Number.isFinite(u)||u<0)return 'n/a';const usedMb=Math.round(u/1048576);return Number.isFinite(l)&&l>0?usedMb.toLocaleString()+'/'+Math.round(l/1048576).toLocaleString()+' MB':usedMb.toLocaleString()+' MB'}
function badge(s){const x=String(s||'').toUpperCase(),c=x.includes('REVIEW')?'red':x.includes('FAIL')||x.includes('QUARANT')?'red':x.includes('PUBLISH')||x.includes('COMPLETE')||x.includes('VALID')?'green':x.includes('STAGED')||x.includes('COMMIT')?'purple':x.includes('RECEIVED')||x.includes('EXTRACT')||x.includes('NORMAL')?'blue':x.includes('WARN')?'amber':'gray';const loading=['RECEIVED','IDENTIFIED','EXTRACTING','NORMALIZING','VALIDATING','COMPARING'].includes(x);const label=(x==='COMMITTING'||x==='COMMITTED')?'DB COMMITTED':x==='CANDIDATE'?'UNVERIFIED':x.replaceAll('_',' ');return `<span class="status ${c}${loading?' loading':''}">${esc(label)}</span>`}
function countUp(el,to){const n=Number(to)||0,from=Number(el.dataset.value||0),start=performance.now(),dur=450;function tick(t){const p=Math.min(1,(t-start)/dur),e=1-Math.pow(1-p,3);el.textContent=Math.round(from+(n-from)*e).toLocaleString();if(p<1)requestAnimationFrame(tick)}el.dataset.value=n;requestAnimationFrame(tick)}
// Reusable import actions; the backend remains responsible for validating each state change.
async function removeImport(id,btn){if(btn?.disabled)return;if(!confirm('Delete this import? The uploaded PDF and all uncommitted import data will be removed.'))return;try{if(btn)btn.disabled=true;await api('/admin/api/imports/'+id,{method:'DELETE',headers:csrfHeaders()});toast('Import deleted','ok');if(typeof load==='function')load()}catch(e){if(btn)btn.disabled=false;toast(e.message,'err')}}
async function retryImport(id,btn){if(btn?.disabled)return;if(!confirm('Retry processing this PDF?'))return;try{if(btn)btn.disabled=true;await api('/admin/api/imports/'+id+'/process',{method:'POST',headers:csrfHeaders()});toast('Processing restarted','ok');if(typeof load==='function')load()}catch(e){if(btn)btn.disabled=false;toast(e.message,'err')}}
async function cancelImport(id,btn){if(btn?.disabled)return;if(!confirm('Stop processing this PDF? The import will be marked Cancelled and can be retried later.'))return;try{if(btn)btn.disabled=true;await api('/admin/api/imports/'+id+'/cancel',{method:'POST',headers:csrfHeaders()});toast('Processing stopped','ok');if(typeof load==='function')load()}catch(e){if(btn)btn.disabled=false;toast(e.message,'err')}}
async function toggleProcess(id,btn){const d=await api('/admin/api/imports/'+id);const s=String(d.job?.status||'');if(['RECEIVED','IDENTIFIED','EXTRACTING','NORMALIZING','VALIDATING','COMPARING'].includes(s)){await cancelImport(id,btn)}else if(s==='CANCELLED'||s==='FAILED'){await retryImport(id,btn)}else{toast('This import is not currently stoppable or retryable','err')}}
</script>'''


def dashboard() -> str:
    """Build the admin overview from analytics, overview and import API responses.

    The page displays project metrics and recent imports; its browser script refreshes them periodically.
    """
    body = '''<div class="title"><div><h1>Dashboard</h1></div><div class="live"><span class="dot"></span>Live · <span id="lastRefresh">updating</span></div></div>
<div class="cards"><div class="card kpi"><div class="khead"><span class="ki sky">⇧</span>Imports Today</div><div class="num" id="today">0</div></div><div class="card kpi"><div class="khead"><span class="ki rose">▤</span>Pending Review</div><div class="num" id="pending">0</div></div><div class="card kpi"><div class="khead"><span class="ki mint">▣</span>Total CAP Records (Cutoffs + Seats)</div><div class="num" id="production">0</div></div><div class="card kpi"><div class="khead"><span class="ki lav">♡</span>Data Health</div><div class="num" id="health">—</div></div></div>
<div class="card panel" style="margin-bottom:14px"><div class="toolbar"><h2>◌ &nbsp;Website Traffic</h2><span class="muted small">last 30 days</span></div><div class="cards" style="grid-template-columns:repeat(4,1fr);margin-top:14px"><div class="card kpi"><div class="khead">Visitors</div><div class="num" id="siteVisitors">—</div></div><div class="card kpi"><div class="khead">Searches</div><div class="num" id="siteSearches">—</div></div><div class="card kpi"><div class="khead">College Opens</div><div class="num" id="siteCollegeOpens">—</div></div><div class="card kpi"><div class="khead">Website Clicks</div><div class="num" id="siteClicks">—</div></div></div></div>
<div class="card panel recent dashboard-imports"><div class="toolbar"><div><h2>Recent Imports</h2></div><a class="btn secondary" href="/admin/review">View All →</a></div><div class="tablewrap"><table class="table"><thead><tr><th>File</th><th>Year</th><th>Round</th><th>Course</th><th>Status</th><th>Updated</th><th></th></tr></thead><tbody id="rows"><tr><td colspan="7" class="skeleton">Loading</td></tr></tbody></table></div></div>'''
    js = _common_js()+r'''<script>

// Load optional website analytics separately so a usage failure does not hide import metrics.
async function loadSiteUsage(){try{const d=await api('/admin/api/analytics/summary?days=30'),t=d.totals||{};for(const [id,key] of [['siteVisitors','visitors'],['siteSearches','searches'],['siteCollegeOpens','college_opens'],['siteClicks','website_clicks']])document.querySelector('#'+id).textContent=Number(t[key]||0).toLocaleString();}catch(e){document.querySelector('#siteUsageDetail').textContent='Usage statistics are temporarily unavailable.'}}
async function load(){loadSiteUsage();try{const [o,j]=await Promise.all([api('/admin/api/overview'),api('/admin/api/imports')]);countUp(document.querySelector('#today'),o.imports_today);countUp(document.querySelector('#pending'),o.pending_review);countUp(document.querySelector('#production'),o.production_rows);document.querySelector('#health').textContent=o.health.ok?'Healthy':'Check';document.querySelector('#lastRefresh').textContent=new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});document.querySelector('#rows').innerHTML=j.slice(0,8).map(x=>`<tr><td>📄 ${esc(x.original_filename)}</td><td>${esc(x.year||'—')}</td><td>${esc(x.round||'—')}</td><td>${esc(displayCourseFamily(x.course_family||'—'))}</td><td>${badge(x.status)}</td><td>${fmtTime(x.updated_at||x.created_at)}</td><td><div class="rowactions">${['RECEIVED','IDENTIFIED','EXTRACTING','NORMALIZING','VALIDATING','COMPARING'].includes(String(x.status||'').toUpperCase())?'<span class="activityspin" title="Processing" aria-label="Processing"></span>':''}${x.status==='FAILED'?'<button class="iconbtn" title="Retry" aria-label="Retry" onclick="retryImport('+x.id+',this)">↻</button>':'<span class="action-placeholder"></span>'}<button class="trashbtn" title="Delete import" aria-label="Delete import" onclick="removeImport(${x.id},this)" ${['RECEIVED','IDENTIFIED','REVIEW_REQUIRED','STAGED','FAILED','CANCELLED','QUARANTINED'].includes(String(x.status||'').toUpperCase())?'':'disabled'}>🗑</button></div></td></tr>`).join('')||'<tr><td colspan="7" class="empty">No imports yet.</td></tr>';}catch(e){toast(e.message,'err')}}window.refreshAdminData=load;window.__cetAdminRunPoll(load);setInterval(()=>window.__cetAdminRunPoll(load),5000);
</script>'''
    return _shell('Dashboard', 'dashboard', body, js)


def import_center() -> str:
    """Build the upload and extraction control page for PDF and CSV imports.

    Its browser script connects to import, local-worker and remote-worker admin APIs to track jobs.
    """
    body = """<div class="title"><div><h1>Import Center</h1></div><div class="live"><span class="dot"></span><span id="localWorkerStatus">Checking extraction worker…</span></div></div>
<div class="import-workspace">
  <div class="card metric upload-quick"><div class="label">Upload files</div><form id="uploadForm" style="margin-top:8px"><input id="file" type="file" accept="application/pdf,.pdf,.csv,text/csv" multiple required style="display:block;margin:0 0 8px"><div id="selectedFiles" class="small muted" style="margin-bottom:8px"></div><div id="uploadMetadata" class="small muted" style="margin-bottom:8px"></div><div id="uploadState" class="small muted" style="margin-top:6px"></div><button class="btn primary" id="uploadBtn">Upload</button></form></div>
  <div class="import-runtime-column">
    <div class="runtime-metrics"><div class="card metric resource-metric"><div class="label">Backend RAM</div><div class="value" id="ramValue">—</div><div class="small muted" id="ramDetail">Reading cgroup metrics</div></div>
    <div class="card metric resource-metric"><div class="label">CPU usage</div><div class="value" id="cpuValue">—</div><div class="small muted" id="cpuDetail">Measured between polls</div></div></div>
    <div class="card panel" id="liveExtractionCard"><div class="toolbar"><h2>Processing</h2><span class="small muted" id="liveExtractionState">Checking worker…</span></div><div id="liveExtractionEmpty" class="small muted">Waiting for an active extraction.</div><div id="liveExtractionDetails" style="display:none"><div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap"><div style="min-width:0;flex:1"><b id="liveExtractionFile" style="overflow-wrap:anywhere">—</b><div class="small muted" id="liveExtractionStep" style="margin-top:5px">—</div></div><b id="liveExtractionPercent" style="font-size:22px;white-space:nowrap">0%</b></div><div class="commit-track" style="margin:12px 0 10px"><div class="commit-bar" id="liveExtractionBar"></div></div><div class="commit-progress-stats"><span id="liveExtractionPages">Pages: —</span><span id="liveExtractionChunks">Chunks: —</span></div></div></div>
  </div>
</div>
<div class="card panel" style="margin-top:14px"><div class="toolbar"><h2>Imports</h2></div><div class="tablewrap"><table class="table import-queue"><thead><tr><th>Metadata</th><th>Status</th><th>Updated</th><th>Controls</th></tr></thead><tbody id="list"></tbody></table></div></div>"""
    js =_common_js()+r'''<script>
const form=document.querySelector('#uploadForm'),fileInput=document.querySelector('#file'),uploadBtn=document.querySelector('#uploadBtn'),uploadState=document.querySelector('#uploadState'),uploadMetadata=document.querySelector('#uploadMetadata');
const LOCAL_WORKER_URL='http://127.0.0.1:8765';let importJobs=[];
// Send commands to the extraction worker running on this same computer.
async function localWorkerRequest(path,opts={}){let response;try{response=await fetch(LOCAL_WORKER_URL+path,Object.assign({cache:'no-store'},opts))}catch(_){throw new Error('Cannot reach the CAPFind worker on this PC. Start it with ./scripts/start_local_worker.sh, then retry. Allow local-network access if the browser asks.')}const raw=await response.text();let data=null;try{data=raw?JSON.parse(raw):null}catch{}if(!response.ok)throw new Error(data?.detail||'Local worker request failed ('+response.status+')');return data}
// Check whether the local extraction worker on this computer is reachable and ready.
async function checkLocalWorker(){const status=document.querySelector('#localWorkerStatus');try{const health=await api('/admin/api/remote-worker/status'),active=(health.workers||[]).find(w=>w.online&&w.active_job_id);if(health.online){status.textContent='PDF extraction worker online';status.title=active?'Processing import #'+active.active_job_id:'Ready for queued PDFs'}else if(!health.configured){status.textContent='Remote PDF extraction needs setup';status.title=health.storage_ready?'Configure the shared worker token on Render and the worker PC. Same-PC local uploads remain available.':'Configure private durable PDF storage and the shared worker token. Same-PC local uploads remain available.'}else{status.textContent='PDF extraction worker offline';status.title='PDF jobs remain queued until the worker PC reconnects'}}catch(e){status.textContent='Could not check extraction worker';status.title=e.message}}
async function sha256File(file){const digest=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());return Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('')}
function parseCsvLine(line){const out=[];let value='',quoted=false;for(let i=0;i<line.length;i++){const ch=line[i];if(ch==='"'&&quoted&&line[i+1]==='"'){value+='"';i++}else if(ch==='"'){quoted=!quoted}else if(ch===','&&!quoted){out.push(value);value=''}else value+=ch}out.push(value);return out}
// Use XMLHttpRequest here because it exposes upload progress, unlike fetch().
function uploadWithProgress(url,data,file,onProgress){
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();xhr.open('POST',url,true);
    const headers=csrfHeaders();for(const [key,value] of Object.entries(headers))xhr.setRequestHeader(key,value);
    xhr.upload.onprogress=e=>{if(e.lengthComputable&&onProgress)onProgress(e.loaded,e.total)};
    xhr.onerror=()=>reject(new Error('Network error while uploading '+file.name+'. Check the connection and retry.'));
    xhr.onabort=()=>reject(new Error('Upload cancelled for '+file.name+'.'));
    xhr.onload=()=>{
      let body=null;try{body=xhr.responseText?JSON.parse(xhr.responseText):null}catch{body=xhr.responseText}
      if(xhr.status===401){window.location='/admin/login';reject(new Error('Admin session expired. Please sign in again.'));return}
      if(xhr.status<200||xhr.status>=300){const detail=body&&typeof body==='object'?(body.detail??body.message??body.error??body):body;reject(new Error(typeof detail==='string'?detail:JSON.stringify(detail)||('Upload failed ('+xhr.status+')')));return}
      resolve(body)
    };
    xhr.send(data)
  })
}
// Infer the canonical import type and course details from the CSV header and source filename.
function detectCsvMetadata(file,header,line){
  const cols=header.map(x=>x.trim().toLowerCase()),values=parseCsvLine(line||'');
  const row={};cols.forEach((k,i)=>row[k]=String(values[i]??'').trim());
  const type=cols.includes('institution_name')&&cols.includes('program_name')&&cols.includes('program_code')?'CUTOFFS':cols.includes('choice_code')&&cols.includes('seats')&&cols.includes('allocation_type')?'SEATS':'';
  const names=(String(row.source_pdf||'')+' '+file.name).toUpperCase();
  const family=/M\s*\.?\s*ARCH(?:ITECTURE)?|MASTER OF ARCHITECTURE/.test(names)?'MARCH':/B\s*\.?\s*ARCH(?:ITECTURE)?|BACHELOR OF ARCHITECTURE/.test(names)?'BARCH':/M\s*\.?\s*PLAN(?:NING)?|MASTER OF PLANNING/.test(names)?'MPLAN':/B\s*\.?\s*PLAN(?:NING)?|BACHELOR OF PLANNING/.test(names)?'BPLAN':/PHARM\s*\.?\s*D|DOCTOR OF PHARMACY/.test(names)?'PHARMD':/M\s*\.?\s*PHARM(?:ACY)?|MASTER OF PHARMACY/.test(names)?'MPHARM':/B\s*\.?\s*PHARM(?:ACY)?|BACHELOR OF PHARMACY/.test(names)?'BPHARM':/\bBCA\b/.test(names)?'BCA':/\bBBA\b|\bBMS\b|\bBBM\b/.test(names)?'BBA':/\bMBA\b|\bMMS\b/.test(names)?'MBA':/\bMCA\b/.test(names)?'MCA':/\bLLB\b/.test(names)?'LLB3':/\bM\s*\.?\s*E\.?\b/.test(names)?'ME':/\bMTECH\b|MASTER OF TECHNOLOGY/.test(names)?'MTECH':(/\bB\.?E\.?\b|(?:^|[_\W])BE(?:[_\W]|$)|BTECH|B\.?TECH|ENGG|SEATMATRIX|SEAT_MATRIX|(?:^|[_\W])SM(?:[_\W]|$)|(?:^|[_\W])FE(?:[_\W]|$)/.test(names)?'BE':'');
  const year=(names.match(/20[0-9]{2}/)||[])[0]||'';
  const m=names.match(/CAP[ _-]*(?:ROUND[ _-]*)?([1-4])|\bC([1-4])\b/),round=m?'C'+(m[1]||m[2]):'';
  return {type,family,year,round,ready:Boolean(type&&family&&year&&(type==='SEATS'||round))};
}
fileInput.addEventListener('change',async()=>{
  const files=[...fileInput.files];document.querySelector('#selectedFiles').textContent=files.length?files.map(f=>f.name+' ('+bytes(f.size)+')').join(' · '):'';
  if(!files.length){uploadMetadata.textContent='';return}
  const details=[];
  for(const f of files){
    if(/\.pdf$/i.test(f.name)){details.push('PDF · '+f.name+' — server extraction');continue}
    if(!/\.csv$/i.test(f.name)){details.push('Unsupported file · '+f.name);continue}
    try{const lines=(await f.slice(0,65536).text()).split(/\r?\n/),header=parseCsvLine((lines[0]||'').replace(/^\uFEFF/,'')),dataLine=lines.find((x,i)=>i>0&&x.trim())||'',m=detectCsvMetadata(f,header,dataLine);details.push('CSV · '+f.name+' — '+(m.ready?m.type+' / '+m.family+' / '+m.year+(m.type==='CUTOFFS'?' / '+m.round:''):'metadata/schema needs correction'))}catch(e){details.push('CSV · '+f.name+' — could not read metadata')}
  }
  uploadMetadata.textContent='';
});
// Validate selected files, create import jobs, then route PDFs/CSVs to their correct intake API.
form.addEventListener('submit',async e=>{
  e.preventDefault();const files=[...fileInput.files];if(!files.length)return;
  const tooLarge=files.find(f=>f.size>(/\.csv$/i.test(f.name)?100:50)*1024*1024);
  if(tooLarge){toast(tooLarge.name+' exceeds the '+(/\.csv$/i.test(tooLarge.name)?'100 MiB CSV':'50 MiB PDF')+' limit.','err');return}
  if(files.some(f=>!(/\.pdf$/i.test(f.name)||/\.csv$/i.test(f.name)))){toast('Select only PDF or canonical CSV files.','err');return}
  uploadBtn.disabled=true;fileInput.disabled=true;let accepted=0;
  try{
    for(let i=0;i<files.length;i++){
      const f=files[i];uploadState.textContent='Processing upload '+(i+1)+' of '+files.length+': '+f.name;
      const data=new FormData();data.append('file',f,f.name);
      let endpoint='/admin/api/imports',kind='PDF';
      if(/\.csv$/i.test(f.name)){
        kind='CSV';const text=await f.slice(0,65536).text(),lines=text.split(/\r?\n/),header=parseCsvLine((lines[0]||'').replace(/^\uFEFF/,'')),line=lines.find((x,n)=>n>0&&x.trim())||'',meta=detectCsvMetadata(f,header,line);
        if(!meta.ready)throw new Error('Could not infer valid type/course/year/round for '+f.name+'. CSVs need canonical columns and a source_pdf filename containing course/year'+(meta.type==='CUTOFFS'?' and CAP round':'')+'.');
        if(!data.get('file'))throw new Error('File attachment missing for '+f.name);
        data.append('data_type',meta.type);data.append('course_family',meta.family);data.append('year',meta.year);data.append('round_name',meta.round);endpoint='/admin/api/imports/csv';
      }
      if(kind==='PDF'){
        let remoteReady=false;try{remoteReady=(await api('/admin/api/remote-worker/status')).configured===true}catch(_){}
        if(remoteReady){endpoint='/admin/api/remote-worker/imports';uploadState.textContent='Uploading PDF to private storage for remote extraction: '+f.name}
        else{
          try{await localWorkerRequest('/health')}catch(_){throw new Error('Remote PDF extraction is not configured yet. Configure private durable PDF storage and the shared worker token on Render and the worker PC; the local fallback only works on this PC.')}
          uploadState.textContent='Preparing local extraction: '+f.name+' · calculating fingerprint';
          const sha256=await sha256File(f);
          const job=await api('/admin/api/local-imports',{method:'POST',headers:csrfHeaders({'Content-Type':'application/json'}),body:JSON.stringify({filename:f.name,size_bytes:f.size,sha256})});
          const localData=new FormData();localData.append('file',f,f.name);localData.append('job_id',String(job.job_id));localData.append('backend_url',location.origin);localData.append('upload_token',job.upload_token);localData.append('expected_sha256',sha256);localData.append('expected_size',String(f.size));
          uploadState.textContent='Transferring '+f.name+' to this PC’s local worker';
          try{await localWorkerRequest('/jobs',{method:'POST',body:localData})}catch(err){try{await api('/admin/api/local-imports/'+job.job_id+'/fail',{method:'POST',headers:{Authorization:'Bearer '+job.upload_token,'Content-Type':'application/json'},body:JSON.stringify({error:'Local worker could not accept the PDF: '+err.message})})}catch(_){}throw new Error('Import #'+job.job_id+' was created but local transfer failed. '+err.message)}
          accepted++;uploadState.textContent='PDF queued for local extraction.';toast('Local extraction queued · job #'+job.job_id,'ok');await load();continue;
        }
      }
      uploadState.textContent='Uploading '+kind+' 0%: '+f.name;
      const result=await uploadWithProgress(endpoint,data,f,(loaded,total)=>{const pct=total?Math.min(100,Math.round(loaded/total*100)):0;uploadState.textContent='Uploading '+kind+' '+pct+'% · '+bytes(loaded)+' / '+bytes(total)+': '+f.name});accepted++;
      uploadState.textContent=kind+' uploaded.';
      toast(kind==='PDF'?'PDF queued for extraction · job #'+(result.job_id||result.id):kind+' submitted: '+f.name+' · job #'+(result.id||result.job_id),'ok');await load();
    }
    uploadState.textContent='Uploaded '+accepted+' file(s).';
    fileInput.value='';document.querySelector('#selectedFiles').textContent='';uploadMetadata.textContent='';
  }catch(err){uploadState.textContent='Upload stopped after '+accepted+' file(s): '+err.message;toast(err.message,'err')}
  finally{uploadBtn.disabled=false;fileInput.disabled=false;await load()}
});
// Route controls to the local worker only while local extraction owns the job.
async function control(id,action){const labels={pause:'Pause processing at the next safe checkpoint?',resume:'Resume this processing?',cancel:'Cancel this import? You can retry it later.'};if(!confirm(labels[action]||'Continue?'))return;try{const job=importJobs.find(x=>Number(x.id)===Number(id)),localExtraction=String(job?.stored_path||'').startsWith('local://')&&!job?.local_artifact_received;if(localExtraction)await localWorkerRequest('/jobs/'+id+'/'+action,{method:'POST'});else await api('/admin/api/imports/'+id+'/'+action,{method:'POST',headers:csrfHeaders()});toast(action==='pause'?'Pause requested':action==='resume'?'Resume requested':'Cancellation requested','ok');await load()}catch(e){toast(e.message,'err')}}
async function removeJob(id){const job=importJobs.find(x=>Number(x.id)===Number(id))||(await api('/admin/api/imports')).find(x=>Number(x.id)===Number(id));const drive=String(job?.stored_path||'').startsWith('gdrive://'),isLocal=String(job?.stored_path||'').startsWith('local://');if(!confirm(isLocal?'Delete this import and its local PDF from this PC?':drive?'Delete this CAPFind import record and its uncommitted staging data? The original PDF will remain in Google Drive.':'Permanently delete this import, its source file and uncommitted staging data?'))return;try{await api('/admin/api/imports/'+id,{method:'DELETE',headers:csrfHeaders()});if(isLocal){try{await localWorkerRequest('/jobs/'+id,{method:'DELETE'})}catch(e){toast('Import removed; local PDF cleanup failed: '+e.message,'err');await load();return}}toast(drive?'Import deleted; original Drive PDF remains':'Import deleted','ok');await load()}catch(e){toast(e.message,'err')}}

async function retryJob(id){if(!confirm('Retry this failed or cancelled import?'))return;try{const job=importJobs.find(x=>Number(x.id)===Number(id));if(String(job?.stored_path||'').startsWith('local://'))await localWorkerRequest('/jobs/'+id+'/retry',{method:'POST'});else await api('/admin/api/imports/'+id+'/process',{method:'POST',headers:csrfHeaders()});toast('Retry started','ok');await load()}catch(e){toast(e.message,'err')}}
// Combine backend runtime metrics with the active extraction progress shown in the UI.
function renderRuntime(d){const m=d.memory||{},c=d.cpu||{},j=d.active_job;window.activeRuntimeJob=j;document.querySelector('#ramValue').textContent=ramMegabytes(m.used_bytes,m.limit_bytes);document.querySelector('#ramDetail').textContent='';document.querySelector('#cpuValue').textContent=c.percent_of_available_capacity==null?'n/a':c.percent_of_available_capacity+'%';document.querySelector('#cpuDetail').textContent=c.quota_cores?'Quota '+c.quota_cores+' CPU core(s)':'CPU quota not exposed';const empty=document.querySelector('#liveExtractionEmpty'),details=document.querySelector('#liveExtractionDetails'),state=document.querySelector('#liveExtractionState');if(!j){empty.style.display='block';details.style.display='none';empty.textContent='No extraction is currently running.';state.textContent='';return}empty.style.display='none';details.style.display='block';const page=Number(j.page||0),total=Number(j.total_pages||0),chunk=Number(j.chunk_count||0),chunks=Number(j.total_chunks||0),isCsv=String(j.filename||'').toLowerCase().endsWith('.csv'),serverStaging=!!j.local_artifact_received;let pct=Number(j.percent||(total?page/total*100:0));document.querySelector('#liveExtractionFile').textContent=(isCsv?'CSV · ':'PDF · ')+(j.filename||'Import #'+j.id);document.querySelector('#liveExtractionStep').textContent=String(j.message||j.status||'Processing').replaceAll('_',' ')+(j.paused_at_checkpoint?' · Paused at safe checkpoint':j.pause_requested?' · Pause requested':'');if(serverStaging){const ep=Number(j.event_progress);if(Number.isFinite(ep)&&ep>=0)pct=ep;const processed=Number(j.rows_processed||0),totalRows=Number(j.total_rows||0);document.querySelector('#liveExtractionPages').textContent='Extracted CSV received · server validation and staging';document.querySelector('#liveExtractionChunks').textContent='Stage: '+String(j.progress_stage||j.event_message||j.status||'Staging extracted CSV')}else if(isCsv){const ep=Number(j.event_progress);if(Number.isFinite(ep)&&ep>=0)pct=ep;const processed=Number(j.rows_processed||0),totalRows=Number(j.total_rows||0);document.querySelector('#liveExtractionPages').textContent='Rows: '+processed.toLocaleString()+(totalRows?' / '+totalRows.toLocaleString():' processed');document.querySelector('#liveExtractionChunks').textContent='Stage: '+String(j.progress_stage||j.event_message||j.status||'Validating CSV');}else{document.querySelector('#liveExtractionPages').textContent='Pages: '+(total?page.toLocaleString()+' / '+total.toLocaleString():'Reading PDF / total not available');document.querySelector('#liveExtractionChunks').textContent=j.local_worker?'Source: this PC · local extraction':'Chunks: '+(chunks?chunk.toLocaleString()+' / '+chunks.toLocaleString():'Preparing chunk plan');}document.querySelector('#liveExtractionPercent').textContent=((isCsv||serverStaging)&&!(Number(j.event_progress)>=0))?'Stage-based':Math.round(pct)+'%';document.querySelector('#liveExtractionBar').style.width=Math.max(0,Math.min(100,pct))+'%';state.textContent=j.paused_at_checkpoint?'Paused':j.pause_requested?'Pause requested':serverStaging?'Server staging':j.local_worker?'This PC':'Live';}
function queueStatusDetail(x,s){const j=window.activeRuntimeJob&&Number(window.activeRuntimeJob.id)===Number(x.id)?window.activeRuntimeJob:null;if(s==='FAILED'&&x.error_message)return 'Failed: '+String(x.error_message).slice(0,220);if(String(x.stored_path||'').startsWith('local://')&&!x.local_artifact_received&&['EXTRACTING','NORMALIZING','VALIDATING','COMPARING','PAUSED'].includes(s)&&!x.local_worker_alive)return 'Local worker heartbeat expired; recovery is marking this extraction retryable.';if((['EXTRACTING','NORMALIZING','VALIDATING','COMPARING'].includes(s)&&(!String(x.stored_path||'').startsWith('local://')||x.local_artifact_received)||s==='PAUSED'&&x.local_artifact_received)&&!x.worker_alive)return 'Worker lease expired; recovering the retained source or local CSV.';if(['EXTRACTING','NORMALIZING','VALIDATING','COMPARING','QUEUED','PAUSED','RECEIVED','IDENTIFIED'].includes(s)){if(j&&s!=='QUEUED'){if(j.local_worker)return 'This PC · '+String(j.message||j.status||'Processing')+(Number(j.total_pages)>0?' · Page '+(j.page??0)+' / '+j.total_pages:'');if(j.local_artifact_received)return 'Server staging · '+String(j.progress_stage||j.event_message||j.status||'Validating extracted CSV')+(Number(j.event_progress)>=0?' · '+Number(j.event_progress)+'%':'');if(String(j.filename||'').toLowerCase().endsWith('.csv'))return 'Stage: '+String(j.event_message||j.status||'Validating CSV')+(Number(j.event_progress)>=0?' · '+Number(j.event_progress)+'%':'');return 'Page '+(j.page??'—')+' / '+(j.total_pages??'—')+' · Chunk '+(j.chunk_count??'—')+' / '+(j.total_chunks??'—');}return s==='QUEUED'?'Waiting for an extraction worker':s==='PAUSED'?'Paused':'Processing'}if(['STAGED','REVIEW_REQUIRED'].includes(s))return 'Staged';if(['COMMITTING','COMMITTED','CANCELLED'].includes(s))return '';if(s==='COMPLETED')return 'Published / verified';return s.replaceAll('_',' ').toLowerCase()}
async function load(){
  try{
    const [jobs,runtime]=await Promise.all([api('/admin/api/imports'),api('/admin/api/runtime')]);
    importJobs=jobs;
    // Render cannot read local:// source files, so its runtime endpoint omits
    // those jobs. Read progress from the PC worker and merge only its active job
    // into the runtime card; worker outages must not hide server-side status.
    let localActive=null;
    try{
      const health=await localWorkerRequest('/health'),id=Number(health.active_job);
      const localImport=jobs.find(x=>Number(x.id)===id&&String(x.stored_path||'').startsWith('local://'));
      if(id&&localImport){
        const progress=await localWorkerRequest('/jobs/'+id),total=Number(progress.total||0),page=Number(progress.page||0);
        localActive={id,filename:localImport.original_filename,status:progress.status,message:progress.message,page,total_pages:total,percent:total?Math.min(100,page/total*100):0,local_worker:true};
      }
    }catch(_){/* The server runtime remains usable when the local worker is offline. */}
    renderRuntime(Object.assign({},runtime,localActive?{active_job:localActive}:{}));
    document.querySelector('#list').innerHTML=jobs.slice(0,50).map(x=>{
      const s=String(x.status||'').toUpperCase();
      const isLocal=String(x.stored_path||'').startsWith('local://');
      const workerStage=['EXTRACTING','NORMALIZING','VALIDATING','COMPARING'].includes(s);
      const serverStage=!isLocal||x.local_artifact_received;
      const workerLost=(serverStage&&workerStage&&!x.worker_alive)||(isLocal&&!x.local_artifact_received&&['EXTRACTING','NORMALIZING','VALIDATING','COMPARING','PAUSED'].includes(s)&&!x.local_worker_alive)||(isLocal&&x.local_artifact_received&&s==='PAUSED'&&!x.worker_alive);
      const active=!workerLost&&(['RECEIVED','IDENTIFIED','QUEUED','PAUSED'].includes(s)||workerStage);
      const canDelete=['RECEIVED','IDENTIFIED','REVIEW_REQUIRED','STAGED','FAILED','CANCELLED','QUARANTINED'].includes(s);
      const isDrive=String(x.stored_path||'').startsWith('gdrive://');
      const kind=String(x.data_type||'').toUpperCase();
      const family=displayCourseFamily(x.course_family||'');
      const meta=[kind,family,x.year,x.round&&kind!=='SEATS'?x.round:null].filter(Boolean).join(' · ');
      const sourceLabel=x.original_filename||'';
      let controls='';
      if(active){
        const pauseState=s==='PAUSED'||(window.activeRuntimeJob&&Number(window.activeRuntimeJob.id)===Number(x.id)&&(window.activeRuntimeJob.pause_requested||window.activeRuntimeJob.paused_at_checkpoint));
        controls+='<button class="iconbtn" title="'+(pauseState?'Resume':'Pause')+'" aria-label="'+(pauseState?'Resume':'Pause')+'" onclick="control('+x.id+',\''+(pauseState?'resume':'pause')+'\')">'+(pauseState?'▶':'Ⅱ')+'</button><button class="iconbtn" title="Cancel" aria-label="Cancel" onclick="control('+x.id+',\'cancel\')">×</button>';
      }else if(s==='FAILED'||s==='CANCELLED'){
        controls+='<button class="iconbtn" title="Retry" aria-label="Retry" onclick="retryJob('+x.id+')">↻</button>';
      }
      if(canDelete)controls+='<button class="iconbtn" title="Delete import and source file" aria-label="Delete import and source file" onclick="removeJob('+x.id+')">🗑</button>';
      const detail=queueStatusDetail(x,s);
      const statusCell=badge(workerLost?'RECOVERING':s)+(detail?'<div class="small muted status-detail">'+esc(detail)+'</div>':'');
      return '<tr><td><b>'+esc(meta||'Awaiting identification')+'</b>'+(sourceLabel?'<div class="small muted import-source-name">'+esc(sourceLabel)+'</div>':'')+'</td><td>'+statusCell+'</td><td>'+fmtTime(x.updated_at||x.created_at)+'</td><td><div class="rowactions">'+controls+'</div></td></tr>';
    }).join('')||'<tr><td colspan="4" class="empty">No imports yet.</td></tr>';
  }catch(e){toast(e.message,'err')}
}
window.refreshAdminData=load;window.__cetAdminRunPoll(load);setInterval(()=>window.__cetAdminRunPoll(load),5000);
</script>'''
    return _shell('Import Center', 'imports', body, js)


def review_center() -> str:
    """Build the staged-import review page.

    The page loads review data and import details through admin APIs before an import is approved or rejected.
    """
    body ='''<div class="title"><div><h1>Review Center</h1></div><div class="live"><span class="dot"></span>Auto-refresh · 5s</div></div>
<div class="grid4"><div class="card metric"><div class="label">Awaiting Review</div><div class="value" id="mReview">0</div></div><div class="card metric"><div class="label">Committing</div><div class="value" id="mCommit">0</div></div><div class="card metric"><div class="label">Staged Rows</div><div class="value" id="mRows">0</div></div><div class="card metric"><div class="label">Validation Issues</div><div class="value" id="mIssues">0</div></div></div>
<div class="card panel" style="margin-top:14px"><div class="toolbar"><div class="filters"><input id="q" class="input" placeholder="Search file, job, course…"><select id="status" class="select"><option value="">All statuses</option><option>STAGED</option><option>REVIEW_REQUIRED</option><option>COMMITTING</option></select><select id="year" class="select"><option value="">All years</option></select></div></div><div class="tablewrap"><table class="table"><thead><tr><th>Metadata</th><th>Rows</th><th>Status</th><th>Updated</th><th>Action</th></tr></thead><tbody id="list"><tr><td colspan="5" class="skeleton">Loading</td></tr></tbody></table></div></div>
<div class="modalback" id="modal"><div class="modal"><div class="modalhead"><b id="modalTitle">Review Import</b><button class="close" onclick="closeModal()">×</button></div><div class="modalbody" id="modalBody"></div><div class="modalfoot" id="modalFoot"></div></div></div>'''
    js =_common_js()+r'''<script>
let jobs=[];const reviewSpinStyle=document.createElement('style');reviewSpinStyle.textContent='@keyframes reviewSpin{to{transform:rotate(360deg)}}';document.head.appendChild(reviewSpinStyle);const q=document.querySelector('#q'),st=document.querySelector('#status'),yr=document.querySelector('#year');[q,st,yr].forEach(x=>x.addEventListener('input',render));
async function load(){try{jobs=await api('/admin/api/review');const years=[...new Set(jobs.map(x=>x.year).filter(Boolean))].sort().reverse();yr.innerHTML='<option value="">All years</option>'+years.map(y=>`<option>${esc(y)}</option>`).join('');document.querySelector('#mReview').textContent=jobs.filter(x=>['STAGED','REVIEW_REQUIRED'].includes(x.status)).length;document.querySelector('#mCommit').textContent=jobs.filter(x=>x.status==='COMMITTING').length;document.querySelector('#mRows').textContent=jobs.reduce((n,d)=>n+Number(d.staging_row_count||0),0).toLocaleString();document.querySelector('#mIssues').textContent=jobs.reduce((n,d)=>n+Number(d.validation_issue_count||0),0).toLocaleString();render()}catch(e){toast(e.message,'err')}}
function render(){const term=q.value.trim().toLowerCase(),sv=st.value,yv=yr.value;const data=jobs.filter(x=>(!sv||x.status===sv)&&(!yv||String(x.year)===yv)&&(!term||[x.job_key,x.original_filename,x.course_family,x.data_type].some(v=>String(v||'').toLowerCase().includes(term))));document.querySelector('#list').innerHTML=data.map(x=>{const kind=String(x.data_type||'').toUpperCase(),family=displayCourseFamily(x.course_family||'');const meta=[kind,family,x.year,x.round&&kind!=='SEATS'?x.round:null].filter(Boolean).join(' · ');return `<tr><td><b>${esc(meta||'Awaiting identification')}</b><div class="small muted import-source-name">${esc(x.original_filename||'')}</div></td><td>${esc(x.staging_row_count??'—')}</td><td>${badge(x.status)}</td><td>${fmtTime(x.updated_at||x.created_at)}</td><td><button class="btn primary" onclick="openReview(${x.id})">Review</button></td></tr>`}).join('')||'<tr><td colspan="5" class="empty">No imports match the current filters.</td></tr>'}
async function openReview(id){const modal=document.querySelector('#modal');const body=document.querySelector('#modalBody');const foot=document.querySelector('#modalFoot');document.querySelector('#modalTitle').textContent='Loading review…';body.innerHTML='<div style="padding:28px 12px;text-align:center"><div class="spinner" style="margin:0 auto 12px;width:28px;height:28px;border:3px solid #D8CFBC;border-top-color:#11120D;border-radius:50%;animation:reviewSpin .8s linear infinite"></div><b>Loading review details…</b><div class="small muted" style="margin-top:6px">Fetching staged records and validation results.</div></div>';foot.innerHTML='<button class="btn secondary" onclick="closeModal()">Cancel</button>';modal.classList.add('show');try{const d=await api('/admin/api/imports/'+id+'/review');const j=d.job;document.querySelector('#modalTitle').textContent=`${j.job_key} · Review`;const allReview=(d.rows||[]).filter(r=>String(r.validation_status||'').toUpperCase()==='REVIEW');const failedFiles=(d.results||[]).filter(r=>String(r.validation_status||'').toUpperCase()!=='PASS');const legacyFileLevel=allReview.length>0&&allReview.every(r=>String(r.validation_message||'').includes('Total issues:'));const reportText=failedFiles.map(r=>{try{return String(JSON.parse(r.summary_json||'{}').validation||'')}catch{return ''}}).join('\n');const unknownCategories=[...reportText.matchAll(/\[([^\]]+)\]\s*:\s*\d+/g)].map(m=>m[1].trim().toUpperCase());const issue=legacyFileLevel?allReview.filter(r=>{try{return unknownCategories.includes(String(JSON.parse(r.normalized_json||'{}').category||'').trim().toUpperCase())}catch{return false}}).map(r=>({...r,validation_message:'Unknown category: '+String(JSON.parse(r.normalized_json||'{}').category||'')})):allReview;const fileReview=(d.rows||[]).filter(r=>String(r.validation_status||'').toUpperCase()==='FILE_REVIEW').length+(legacyFileLevel?allReview.length-issue.length:0);const validationSummary=failedFiles.length?`<div class="issue"><b>File-level validation failed</b><br>${esc(failedFiles.map(r=>{try{const s=JSON.parse(r.summary_json||'{}');return String(s.validation||'').match(/Total issues:\s*\d+[^\n]*/)?.[0]||'See validation report';}catch{return 'See validation report';}}).filter(Boolean).join(' · '))}</div><details style="margin-top:10px"><summary>Full validation report</summary><pre class="json" style="white-space:pre-wrap;max-height:320px;overflow:auto">${esc(failedFiles.map(r=>{try{const s=JSON.parse(r.summary_json||'{}');return String(s.validation||'No validation text stored')}catch{return 'Validation report could not be decoded'}}).join('\n\n---\n\n'))}</pre></details>`:'';document.querySelector('#modalBody').innerHTML=`<div class="grid4" style="grid-template-columns:repeat(3,1fr)"><div class="notice"><b>Source</b><br>${esc(j.original_filename)}</div><div class="notice"><b>Status</b><br>${badge(j.status)}</div><div class="notice"><b>Validation</b><br>${issue.length?issue.length+' row issue(s)':failedFiles.length?'File-level review required':'No issues reported'}</div></div>${validationSummary}${fileReview?`<div class="issue">${fileReview} row(s) are flagged by the file-level validation gate; this is not a count of distinct row errors. Review the validation report before approving.</div>`:''}<h3 style="font-size:13px;margin:20px 0 9px">Staged records (${d.rows?.length||0}${(d.rows?.length||0)>=500?'+':''})</h3>${issue.length?issue.slice(0,20).map(r=>`<div class="issue"><b>${esc(r.result_type||'Record')}</b> · page ${esc(r.source_page||'—')}<br>${esc(r.validation_message||r.validation_status)}</div>`).join(''):'<div class="issue good">No individual row errors detected in the returned staged records.</div>'}`;const legacyMhNeedsRevalidation=j.status==='REVIEW_REQUIRED'&&j.original_filename==='2026BCA_CAP2_MH_CutOff.pdf'&&failedFiles.some(r=>String(r.validation_status||'').toUpperCase()!=='PASS');const canRetryPdf=j.status==='REVIEW_REQUIRED'&&String(j.original_filename||'').toLowerCase().endsWith('.pdf')&&!String(j.stored_path||'').startsWith('local://')&&!j.source_deleted;document.querySelector('#modalFoot').innerHTML=(['STAGED','REVIEW_REQUIRED'].includes(j.status))?(legacyMhNeedsRevalidation?`<button class="btn dangerbtn" onclick="reject(${id})">Reject / Quarantine</button><button class="btn primary" onclick="revalidateLegacyMH(${id})">Revalidate legacy MH mapping</button>`:canRetryPdf&&j.status==='REVIEW_REQUIRED'?`<button class="btn dangerbtn" onclick="reject(${id})">Reject / Quarantine</button><button class="btn secondary" onclick="retryImport(${id},this)">Re-extract &amp; revalidate PDF</button>`:`<button class="btn dangerbtn" onclick="reject(${id})">Reject / Quarantine</button><button class="btn success" onclick="approve(${id})">Approve & Commit</button>`):'<button class="btn secondary" onclick="closeModal()">Close</button>';document.querySelector('#modal').classList.add('show')}catch(e){document.querySelector('#modalTitle').textContent='Unable to load review';body.innerHTML='<div class="issue"><b>Review details could not be loaded.</b><br>'+esc(e.message||'Unknown error')+'</div><p class="small muted">Check your admin connection and try opening this import again.</p>';foot.innerHTML='<button class="btn secondary" onclick="closeModal()">Close</button><button class="btn primary" onclick="openReview('+id+')">Retry</button>';modal.classList.add('show')}}
function closeModal(){document.querySelector('#modal').classList.remove('show')}
async function revalidateLegacyMH(id){if(!confirm('Revalidate the 2026 BCA CAP-2 staged rows against the current MH → MI category rule? This does not commit or publish data.'))return;try{const d=await api('/admin/api/imports/'+id+'/revalidate-legacy-mh',{method:'POST',headers:csrfHeaders({'Content-Type':'application/json'}),body:JSON.stringify({})});toast('Revalidated '+d.rows_revalidated+' staged rows. Review them, then approve and publish separately.','ok');await openReview(id);load()}catch(e){toast(e.message,'err')}}
async function approve(id){
  const notes=prompt('Approval note (optional):','');if(notes===null)return;
  const foot=document.querySelector('#modalFoot'),body=document.querySelector('#modalBody'),title=document.querySelector('#modalTitle');
  const buttons=[...foot.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  let polling=true, postFinished=false, lastProgress=null;
  title.textContent='Committing import #'+id;
  body.innerHTML='<div class="commit-progress"><div class="commit-progress-head"><span class="activityspin"></span><b id="commitStage">Starting commit…</b><strong id="commitPercent">0%</strong></div><div class="commit-track"><div id="commitBar" class="commit-bar"></div></div><div class="commit-progress-stats"><span id="commitRows">Preparing row count…</span><span id="commitUpdated">Waiting for server progress</span></div><p id="commitMessage" class="small muted">Keep this window open. The server is committing staged rows in a database transaction.</p></div>';
  foot.innerHTML='<button class="btn secondary" disabled>Commit in progress…</button>';
  document.querySelector('#modal').classList.add('show');
  const updateProgress=async()=>{
    while(polling){
      try{
        const p=await api('/admin/api/imports/'+id+'/commit-progress');lastProgress=p;
        const pct=Math.max(0,Math.min(100,Number(p.progress)||0));
        const stage=document.querySelector('#commitStage'),percent=document.querySelector('#commitPercent'),bar=document.querySelector('#commitBar'),rows=document.querySelector('#commitRows'),updated=document.querySelector('#commitUpdated'),message=document.querySelector('#commitMessage');
        if(stage)stage.textContent=p.stage||'Preparing commit';
        if(percent)percent.textContent=pct+'%';
        if(bar)bar.style.width=pct+'%';
        if(rows)rows.textContent=(Number(p.processed)||0).toLocaleString()+' / '+(Number(p.total)||0).toLocaleString()+' rows processed';
        if(updated)updated.textContent=p.updated_at?'Updated '+fmtTime(p.updated_at):'Waiting for first progress update';
        if(message)message.textContent=p.message||'Commit is running…';
      }catch(e){
        const updated=document.querySelector('#commitUpdated');
        if(updated)updated.textContent='Reconnecting to progress updates…';
      }
      if(!polling)break;
      await new Promise(resolve=>setTimeout(resolve,800));
    }
  };
  const pollTask=updateProgress();
  try{
    const result=await api('/admin/api/imports/'+id+'/approve',{method:'POST',headers:csrfHeaders({'Content-Type':'application/json'}),body:JSON.stringify({notes})});
    postFinished=true;polling=false;await pollTask;
    body.innerHTML='<div class="notice"><b>Database commit completed.</b><p>'+(Number(result.rows_inserted)||0).toLocaleString()+' rows were committed successfully.</p><p>Release '+esc(result.release_key||'created')+' is awaiting publish. This step does not publish it automatically.</p></div>';
    foot.innerHTML='<button class="btn primary" onclick="closeModal();load()">Close</button>';
    toast('Commit completed; release is awaiting publish','ok');await load();
  }catch(e){
    postFinished=true;polling=false;await pollTask;
    let status='';
    try{const current=await api('/admin/api/imports/'+id);status=String((current.job||current).status||'').toUpperCase()}catch(_){}
    if(lastProgress&&String(lastProgress.status||'').toUpperCase()==='COMPLETED'){
      body.innerHTML='<div class="notice"><b>Database commit completed.</b><p>'+(Number(lastProgress.processed)||0).toLocaleString()+' staged rows processed.</p><p>The release may still need to be published.</p></div>';
      foot.innerHTML='<button class="btn primary" onclick="closeModal();load()">Close</button>';
      toast('Commit completed; refreshing review list','ok');await load();
    }else{
      body.insertAdjacentHTML('beforeend','<div class="issue" style="margin-top:12px"><b>Commit did not complete.</b><br>'+esc(e.message||'Unknown error')+(status==='FAILED'?'<br>The transaction was rolled back.':'')+'</div>');
      foot.innerHTML='<button class="btn secondary" onclick="closeModal()">Close</button><button class="btn primary" onclick="openReview('+id+')">Retry review</button>';
      toast(e.message||'Commit failed','err');await load();
    }
  }
}
async function reject(id){const reason=prompt('Rejection reason (required):');if(!reason)return;try{await api('/admin/api/imports/'+id+'/reject',{method:'POST',headers:csrfHeaders({'Content-Type':'application/json'}),body:JSON.stringify({reason})});toast('Import quarantined','ok');closeModal();load()}catch(e){toast(e.message,'err')}}
window.refreshAdminData=load;window.__cetAdminRunPoll(load);setInterval(()=>window.__cetAdminRunPoll(load),15000);
</script>'''
    return _shell('Review Center', 'review', body, js)


def releases_page(active: str = 'releases', title: str = 'Releases') -> str:
    """Build the release history and management page.

    Loads release and import information from admin APIs and uses the arguments to set its title and active tab.
    """
    body ='''<div class="title"><div><h1>Releases</h1></div><div class="live"><span class="dot"></span>Live state</div></div><div class="grid4 release-metrics"><div class="card metric"><div class="label">Total Releases</div><div class="value" id="total">0</div></div><div class="card metric"><div class="label">Ready to Publish</div><div class="value" id="ready">0</div></div><div class="card metric"><div class="label">Latest Status</div><div class="value" id="latest" style="font-size:18px">—</div></div></div><div class="card panel" style="margin-top:14px"><div class="toolbar"><h2>Release History</h2></div><div class="tablewrap"><table class="table"><thead><tr><th>Metadata</th><th>Status</th><th>Created</th><th>Action</th></tr></thead><tbody id="list"></tbody></table></div></div>'''
    js =_common_js()+r'''<script>
const releaseDeleteState=new Map();
function setDeleteButtonState(button,phase){if(!button)return;button.disabled=true;button.innerHTML='<span class="activityspin" aria-hidden="true"></span>'+(phase==='data'?'Deleting production data…':'Deleting release and source…')}
async function load(){try{const [d,imports]=await Promise.all([api('/admin/api/releases'),api('/admin/api/imports')]);const importById=new Map(imports.map(j=>[Number(j.id),j]));document.querySelector('#total').textContent=d.length;document.querySelector('#ready').textContent=d.filter(x=>x.status==='COMMITTED').length;document.querySelector('#latest').textContent=d[0]?.status||'—';document.querySelector('#list').innerHTML=d.map(x=>{const s=String(x.status||'').toUpperCase(),busy=releaseDeleteState.get(Number(x.id));const action=s==='ROLLED_BACK'?`<button class="btn dangerbtn" onclick="purge(${x.id},this)" ${busy?'disabled':''}>${busy?'<span class="activityspin" aria-hidden="true"></span>Deleting release and source…':'Delete Permanently'}</button>`:['COMMITTED','PUBLISHED'].includes(s)?`<button class="btn dangerbtn" onclick="deleteReleaseData(${x.id},'${esc(x.release_key)}','${s}',this)" ${busy?'disabled':''}>${busy?'<span class="activityspin" aria-hidden="true"></span>'+(busy==='data'?'Deleting production data…':'Deleting release and source…'):'Delete Data'}</button>`:'<span class="muted small">—</span>';const source=importById.get(Number(x.source_job_id))||{};const kind=String(source.data_type||'').toUpperCase(),family=displayCourseFamily(source.course_family||'');const meta=[kind,family,source.year,source.round&&kind!=='SEATS'?source.round:null].filter(Boolean).join(' · ');return `<tr><td><b>${esc(meta||x.release_key)}</b><div class="small muted import-source-name">${esc(source.original_filename||x.release_key)}</div></td><td>${badge(x.status)}</td><td>${fmtTime(x.created_at)}</td><td>${action}</td></tr>`}).join('')||'<tr><td colspan="4" class="empty">No releases yet.</td></tr>'}catch(e){toast(e.message,'err')}}
async function deleteReleaseData(id,key,status,button){if(!confirm(`Delete production data for release ${key} (${status})?\n\nThis will remove its committed production rows. If published, the previous public site will be restored. The source import and release history will then be permanently deleted. This cannot be undone.`))return;const reason=prompt('Enter the reason for deleting this release (required):');if(!reason||!reason.trim())return;releaseDeleteState.set(Number(id),'data');setDeleteButtonState(button,'data');try{await api('/admin/api/releases/'+id+'/rollback',{method:'POST',headers:csrfHeaders({'Content-Type':'application/json'}),body:JSON.stringify({reason:reason.trim()})});releaseDeleteState.set(Number(id),'source');setDeleteButtonState(button,'source');try{await api('/admin/api/releases/'+id,{method:'DELETE',headers:csrfHeaders()});releaseDeleteState.delete(Number(id));toast('Production data and source import permanently deleted','ok');await load()}catch(e){releaseDeleteState.delete(Number(id));await load();toast('Production data was removed, but release/source cleanup failed. Use Delete Permanently on this rolled-back release. '+e.message,'err')}}catch(e){releaseDeleteState.delete(Number(id));await load();toast('Delete failed: '+e.message,'err')}}
async function purge(id,button){if(!confirm('Permanently delete this rolled-back release, source import, and stored PDF? This cannot be undone.'))return;releaseDeleteState.set(Number(id),'source');setDeleteButtonState(button,'source');try{await api('/admin/api/releases/'+id,{method:'DELETE',headers:csrfHeaders()});releaseDeleteState.delete(Number(id));toast('Release and source import permanently deleted','ok');await load()}catch(e){releaseDeleteState.delete(Number(id));await load();toast('Delete failed: '+e.message,'err')}}window.__cetAdminRunPoll(load);setInterval(()=>window.__cetAdminRunPoll(load),15000);
</script>'''
    body = body.replace('<h1>Releases</h1>', '<h1>'+escape(title)+'</h1>')
    return _shell(title, active, body, js)


def derived_data() -> str:
    """Build the CET Data Calculator administration page.

    Its browser script checks derived-data status and sends build, retry and clear requests to the backend.
    """
    body ='''<div class="title"><div><h1>CET Data Calculator</h1></div><div class="live"><span class="dot"></span>Admin controlled</div></div>
<div class="pagegrid derived-grid"><div class="card panel derived-build-card"><div class="toolbar"><h2>Build derived data</h2></div>
<div class="filters" style="margin-top:14px"><div class="course-picker" id="coursePicker"><select id="course" class="select" style="display:none" aria-hidden="true"><option value="">All courses in production DB</option></select><button type="button" id="coursePickerTrigger" class="course-picker-trigger" aria-haspopup="listbox" aria-expanded="false" onclick="toggleCoursePicker()"><span id="coursePickerLabel">All courses in production DB</span></button><div id="coursePickerMenu" class="course-picker-menu" role="listbox" aria-label="Choose course"></div></div><button id="buildBtn" class="btn primary" onclick="startBuild()">▶ Calculate & Store</button><button id="clearBuildBtn" class="btn" onclick="clearCalculatedData()">Clear calculated data</button></div>
<div id="buildProgress" class="notice build-loading" style="margin-top:12px;display:none"><span class="activityspin" aria-hidden="true"></span><div><b id="progressTitle">Calculating…</b><div id="progressMessage" class="small muted" style="margin-top:5px">Waiting for server…</div></div></div>
</div>
<div class="card panel" style="margin-top:14px"><div class="toolbar"><h2>Build history</h2></div><div class="tablewrap"><table class="table"><thead><tr><th>ID</th><th>Course</th><th>Status</th><th>Progress</th><th>Message</th><th>Started</th><th>Finished</th><th>Actions</th></tr></thead><tbody id="history"></tbody></table></div></div>'''
    js =_common_js()+r'''<script>
let jobs=[];
function renderCoursePicker(sel){
  const menu=document.querySelector('#coursePickerMenu'),label=document.querySelector('#coursePickerLabel');
  if(!menu||!label)return;
  const selected=sel.options[sel.selectedIndex];label.textContent=selected?selected.textContent:'All courses in production DB';
  menu.innerHTML=[...sel.options].map(o=>'<button type="button" class="course-picker-option" role="option" aria-selected="'+(o.value===sel.value?'true':'false')+'" data-value="'+esc(o.value)+'" onclick="chooseCourse(this.dataset.value)">'+esc(o.textContent)+'</button>').join('');
}
function toggleCoursePicker(){
  const picker=document.querySelector('#coursePicker'),trigger=document.querySelector('#coursePickerTrigger');
  const opening=!picker.classList.contains('open');picker.classList.toggle('open',opening);trigger.setAttribute('aria-expanded',String(opening));
}
function chooseCourse(value){
  const sel=document.querySelector('#course');sel.value=value;renderCoursePicker(sel);
  document.querySelector('#coursePicker').classList.remove('open');document.querySelector('#coursePickerTrigger').setAttribute('aria-expanded','false');
}
document.addEventListener('click',e=>{const picker=document.querySelector('#coursePicker');if(picker&&!picker.contains(e.target)){picker.classList.remove('open');document.querySelector('#coursePickerTrigger').setAttribute('aria-expanded','false')}});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){const picker=document.querySelector('#coursePicker');if(picker){picker.classList.remove('open');document.querySelector('#coursePickerTrigger').setAttribute('aria-expanded','false')}}});
const activeStates=['QUEUED','RUNNING'];
const terminalStates=['COMPLETED','FAILED','CANCELLED'];
function actionButtons(j){
  const s=String(j.status||'').toUpperCase();
  if(activeStates.includes(s)) return '<span class="small muted">Running…</span>';
  let out='';
  if(s==='FAILED'||s==='CANCELLED') out+='<button class="btn success" style="padding:6px 9px" onclick="retryBuild('+j.id+',this)">↻ Retry</button>';
  if(terminalStates.includes(s)) out+='<button class="trashbtn" title="Delete build history" aria-label="Delete build history" onclick="deleteBuild('+j.id+',this)">🗑</button>';
  return out||'<span class="small muted">—</span>';
}
async function load(){
  try{
    const d=await api('/admin/api/derived-data/status');jobs=d.jobs||[];
    const sel=document.querySelector('#course'),current=sel.value;
    sel.innerHTML='<option value="">All courses in production DB</option>'+d.courses.map(c=>'<option value="'+esc(c)+'">'+esc(displayCourseFamily(c))+'</option>').join('');
    if([...sel.options].some(o=>o.value===current))sel.value=current;
    renderCoursePicker(sel);
    const j=jobs[0],box=document.querySelector('#buildProgress');

    if(j){
      const running=activeStates.includes(String(j.status).toUpperCase());
      box.style.display=running?'flex':'none';document.querySelector('#progressTitle').textContent='Calculating CET data…';
      document.querySelector('#progressMessage').textContent=j.message||'Working in the background. This may take a while.';

    }else{box.style.display='none'}
    const active=jobs.some(x=>activeStates.includes(String(x.status).toUpperCase()));document.querySelector('#buildBtn').disabled=active;
    document.querySelector('#history').innerHTML=jobs.map(x=>'<tr><td>#'+x.id+'</td><td>'+esc(displayCourseFamily(x.course_family||'ALL'))+'</td><td>'+badge(x.status)+'</td><td>'+esc(x.progress)+'%</td><td>'+esc(x.message||'—')+'</td><td>'+fmtTime(x.started_at)+'</td><td>'+fmtTime(x.finished_at)+'</td><td><span class="rowactions">'+actionButtons(x)+'</span></td></tr>').join('')||'<tr><td colspan="8" class="empty">No builds yet.</td></tr>';
  }catch(e){toast(e.message,'err')}
}
// Request a derived-data rebuild; source cutoff and seat records remain unchanged.
async function startBuild(){
  const course=document.querySelector('#course').value;

  try{document.querySelector('#buildBtn').disabled=true;const form=new FormData();if(course)form.append('course',course);await api('/admin/api/derived-data/build',{method:'POST',headers:csrfHeaders(),body:form});toast('Derived-data build started','ok');await load()}catch(e){toast(e.message,'err');await load()}
}
async function retryBuild(id,btn){
  if(btn.disabled)return;
  btn.disabled=true;const old=btn.textContent;btn.textContent='Retrying…';
  try{await api('/admin/api/derived-data/retry/'+id,{method:'POST',headers:csrfHeaders()});toast('Retry started','ok');await load()}catch(e){btn.disabled=false;btn.textContent=old;toast(e.message,'err')}
}
async function deleteBuild(id,btn){
  if(btn.disabled)return;
  const job=jobs.find(x=>Number(x.id)===Number(id));
  const scope=job&&job.course_family?displayCourseFamily(job.course_family):'ALL courses';
  if(!confirm('Delete build history and clear stored calculated data for '+scope+'? This removes graph, filter-option and seat-matrix cache rows, but keeps source cutoff/seat records.'))return;
  btn.disabled=true;
  try{await api('/admin/api/derived-data/'+id,{method:'DELETE',headers:csrfHeaders()});toast('Build history and its calculated data deleted','ok');await load()}catch(e){btn.disabled=false;toast(e.message,'err')}
}
// Clear calculated rows for the selected scope, never the source cutoff or seat records.
async function clearCalculatedData(){
  const course=document.querySelector('#course').value;
  const scope=course||'ALL courses';
  if(!confirm('Permanently clear stored calculated data for '+scope+'? Public graphs/filter options/seat matrices for this scope will be unavailable until recalculated. Source cutoff and seat records will remain.'))return;
  const btn=document.querySelector('#clearBuildBtn');if(btn.disabled)return;btn.disabled=true;
  try{const form=new FormData();if(course)form.append('course',course);await api('/admin/api/derived-data/clear',{method:'POST',headers:csrfHeaders(),body:form});toast('Calculated data cleared for '+scope,'ok');await load()}catch(e){toast(e.message,'err')}finally{btn.disabled=false}
}
window.refreshAdminData=load;window.__cetAdminRunPoll(load);setInterval(()=>window.__cetAdminRunPoll(load),15000);
</script>'''
    return _shell('CET Data Calculator', 'derived', body, js)


def health_page() -> str:
    """Build the production data health page using the backend health endpoint.

    The browser script turns the returned health checks and dataset counts into the page display.
    """
    body ='''<div class="title"><div><h1>Data Health</h1></div><div class="live"><span class="dot"></span>Continuous checks</div></div><div class="card panel" id="overall" style="margin-bottom:14px">Checking health…</div><div class="grid4 health-metrics" id="metrics"></div><div class="card panel" style="margin-top:14px"><div class="toolbar"><h2>Production Data</h2><span class="muted small" id="refreshAt">—</span></div><div class="tablewrap"><table class="table"><thead><tr><th>Dataset</th><th>Rows</th><th>State</th></tr></thead><tbody id="counts"></tbody></table></div></div>'''
    js =_common_js()+r'''<script>
async function load(){try{const d=await api('/admin/api/health');const c=d.counts||{},r=d.runtime||{},ok=!!d.ok&&!!r.site_exists;document.querySelector('#overall').innerHTML=`<div style="display:flex;align-items:center;justify-content:space-between;gap:12px"><div><b style="font-size:18px">${ok?'System healthy':'Attention required'}</b><div class="small muted">${ok?'Core runtime checks are passing.':'One or more checks need attention.'}</div></div><span class="status ${ok?'green':'red'}">${ok?'HEALTHY':'CHECK'}</span></div>`;const names=[['Institutes','institutes'],['Programs','programs'],['Cutoffs','cutoffs']];const issues=[];if(!r.site_exists)issues.push('Published site directory is missing.');if((c.programs||0)===0)issues.push('Programs table is empty.');document.querySelector('#metrics').innerHTML=names.map(([n,k])=>`<div class="card metric"><div class="label">${n}</div><div class="value">${Number(c[k]||0).toLocaleString()}</div></div>`).join('')+`<div class="card metric detected-issues"><div class="label">Detected Issues</div><div class="value">${issues.length}</div><div id="issues" class="small muted issue-summary">${issues.length?issues.map(esc).join(' · '):'No obvious issues detected.'}</div></div>`;document.querySelector('#counts').innerHTML=Object.entries(c).map(([k,v])=>`<tr><td>${esc(k.replaceAll('_',' '))}</td><td><b>${Number(v).toLocaleString()}</b></td><td>${Number(v)>0||['audit_log','import_jobs'].includes(k)?badge('HEALTHY'):badge('EMPTY')}</td></tr>`).join('');document.querySelector('#refreshAt').textContent='Updated '+new Date().toLocaleTimeString()}catch(e){toast(e.message,'err')}}window.refreshAdminData=load;window.__cetAdminRunPoll(load);setInterval(()=>window.__cetAdminRunPoll(load),15000);
</script>'''
    return _shell('Data Health', 'health', body, js)


def audit_page(rows) -> str:
    """Render the audit records supplied by the backend route.

    Serializes the rows into the page so browser-side search can filter them without another API request.
    """
    data = json.dumps(rows,ensure_ascii=False,default=str).replace('</','<\\/')
    body ='''<div class="title"><div><h1>Audit Log</h1></div><div class="live">''' + '<span class="dot"></span>Last 200 events</div></div>' + '''<div class="card panel"><div class="toolbar"><div class="filters"><input id="q" class="input" placeholder="Search user, action, entity, reason…"></div><span class="muted small" id="count"></span></div><div class="tablewrap"><table class="table"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Entity</th><th>Reason</th></tr></thead><tbody id="list"></tbody></table></div></div>'''
    js =_common_js()+f'''<script>const rows={data};const q=document.querySelector('#q');q.addEventListener('input',render);function render(){{const t=q.value.toLowerCase();const d=rows.filter(x=>!t||Object.values(x).some(v=>String(v??'').toLowerCase().includes(t)));document.querySelector('#count').textContent=d.length+' event(s)';document.querySelector('#list').innerHTML=d.map(x=>`<tr><td>${{fmtTime(x.created_at)}}</td><td>${{esc(x.username||'system')}}</td><td>${{badge(x.action)}}</td><td>${{esc(x.entity_type)}} #${{esc(x.entity_id)}}</td><td>${{esc(x.reason||'—')}}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">No audit events match.</td></tr>'}}render();</script>'''
    return _shell('Audit Log', 'audit', body, js)


def feedback_page(rows) -> str:
    """Render the feedback records supplied by the backend route.

    The browser filters the supplied records and periodically reloads the inbox through the shared API helper.
    """
    data =json.dumps(rows,ensure_ascii=False,default=str).replace('</','<\\/')
    body = '<div class="title"><div><h1>Public Feedback</h1></div><div class="live"><span class="dot"></span>Live inbox</div></div><div class="grid4"><div class="card metric"><div class="label">Total</div><div class="value" id="total">0</div></div><div class="card metric"><div class="label">New</div><div class="value" id="newCount">0</div></div><div class="card metric"><div class="label">Reviewed</div><div class="value" id="reviewed">0</div></div><div class="card metric"><div class="label">Resolved</div><div class="value" id="resolved">0</div></div></div><div class="card panel" style="margin-top:14px"><div class="toolbar"><div class="filters"><input id="q" class="input" placeholder="Search feedback…"></div></div><div class="tablewrap"><table class="table feedback-table"><thead><tr><th>Time</th><th>Rating</th><th>Feedback</th><th>Status</th></tr></thead><tbody id="list"></tbody></table></div></div>'
    js =_common_js()+f'''<script>
let rows={data};
const q=document.querySelector('#q');
function render(){{const term=q.value.toLowerCase();const d=rows.filter(x=>(!term||String(x.message).toLowerCase().includes(term)));document.querySelector('#total').textContent=rows.length;document.querySelector('#newCount').textContent=rows.filter(x=>x.status==='NEW').length;document.querySelector('#reviewed').textContent=rows.filter(x=>x.status==='REVIEWED').length;document.querySelector('#resolved').textContent=rows.filter(x=>x.status==='RESOLVED').length;document.querySelector('#list').innerHTML=d.map(x=>`<tr><td>${{fmtTime(x.created_at)}}</td><td>${{x.rating?('★'.repeat(x.rating)+'☆'.repeat(5-x.rating)):'—'}}</td><td><div class="feedback-message-box">${{esc(x.message)}}</div></td><td>${{badge(x.status)}}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">No feedback matches.</td></tr>'}}
q.addEventListener('input',render);
async function load(){{try{{rows=await api('/admin/api/feedback');render()}}catch(e){{toast(e.message,'err')}}}}

render();window.refreshAdminData=load;setInterval(()=>window.__cetAdminRunPoll(load),15000);
</script>'''
    return _shell('Public Feedback', 'feedback', body, js)


def live_processing(job_id: int) -> str:
    """Build the live progress page for one import job.

    Uses job_id to poll import status and events, then exposes the available approve or delete actions.
    """
    body = f'''<div class="title"><div><h1>Live Processing</h1></div><a class="btn secondary" href="/admin/review">← Review Center</a></div>
<div class="pagegrid"><div class="card panel"><div class="toolbar"><h2 id="jobTitle">Loading…</h2><span id="jobStatus">—</span></div>
<div id="meta" class="notice">Loading import metadata…</div>
<div id="currentStep" class="notice" style="margin-top:10px;background:#FFFBF4;border-color:#D8CFBC">Current step: checking…</div>
<div style="margin-top:18px"><div class="toolbar"><b>Overall progress</b><span class="muted small" id="progressText">0%</span></div><div style="height:10px;background:#D8CFBC;border-radius:999px;overflow:hidden"><div id="progress" style="height:100%;width:0;background:linear-gradient(90deg,#11120D,#11120D);transition:width .35s"></div></div></div>
<div id="steps" style="display:grid;gap:8px;margin-top:20px"></div>
<div class="timeline" id="events" style="margin-top:22px"></div></div>
<div class="card panel"><h2>Controls</h2><p class="small muted">Processing runs in the background. This page refreshes the actual job status from the server every second.</p><div id="actions"></div><div id="controlNote" class="notice" style="margin-top:10px">Checking status…</div></div></div>'''
    js =_common_js()+f'''<script>const terminal=['COMPLETED','FAILED','CANCELLED','QUARANTINED','ROLLED_BACK'];async function load(){{try{{const d=await api('/admin/api/imports/{job_id}'),j=d.job;document.querySelector('#jobTitle').textContent=j.job_key+' · '+j.original_filename;document.querySelector('#jobStatus').innerHTML=badge(j.status);document.querySelector('#currentStep').textContent='Current step: '+String(j.status||'').replaceAll('_',' ');document.querySelector('#meta').innerHTML=`${{esc(j.data_type||'')}} · ${{esc(displayCourseFamily(j.course_family||''))}} · ${{esc(j.year||'')}} · ${{esc(j.round||'')}}`;const ev=d.events||[];const last=ev[ev.length-1],pct=last?.progress??(j.status==='REVIEW_REQUIRED'?100:0);document.querySelector('#progress').style.width=Math.max(0,Math.min(100,pct))+'%';document.querySelector('#progressText').textContent=Math.round(pct)+'%';document.querySelector('#events').innerHTML=ev.slice().reverse().map((x,i)=>`<div class="event ${{i===0&&!terminal.includes(j.status)?'active':''}}"><div class="eventdot"></div><div><h4>${{esc(x.event_type||'Event')}} · ${{esc(x.progress??'')}}%</h4><p>${{esc(x.message)}} · ${{fmtTime(x.created_at)}}</p></div></div>`).join('')||'<div class="empty">No events yet.</div>';const actions=document.querySelector('#actions');actions.innerHTML=['RECEIVED','IDENTIFIED','REVIEW_REQUIRED','STAGED','FAILED','CANCELLED','QUARANTINED'].includes(j.status)?'<button class="btn dangerbtn" onclick="removeImport()">Delete import</button>':'';if(j.status==='STAGED')actions.innerHTML+='<button class="btn success" style="margin-left:8px" onclick="approve()">Approve & Commit</button>';if(j.status==='REVIEW_REQUIRED')actions.innerHTML+='<a class="btn primary" style="margin-left:8px" href="/admin/review">Open Review Center</a>';document.querySelector('#controlNote').textContent=terminal.includes(j.status)?'Processing has finished.':'Live status will refresh automatically.';if(!terminal.includes(j.status))setTimeout(()=>window.__cetAdminRunPoll(load),3000)}}catch(e){{toast(e.message,'err')}}}}async function removeImport(){{if(!confirm('Delete this import? The uploaded PDF and all uncommitted import data will be removed.'))return;try{{await api('/admin/api/imports/{job_id}',{{method:'DELETE',headers:csrfHeaders()}});toast('Import deleted','ok');location.href='/admin'}}catch(e){{toast(e.message,'err')}}}}async function approve(){{const notes=prompt('Approval note (optional):','');if(notes===null)return;try{{await api('/admin/api/imports/{job_id}/approve',{{method:'POST',headers:csrfHeaders({{'Content-Type':'application/json'}}),body:JSON.stringify({{notes}})}});toast('Import approved and committed','ok');load()}}catch(e){{toast(e.message,'err')}}}}load();</script>'''
    return _shell('Live Processing', 'processing', body, js)


def resolver_page(rows) -> str:
    """Build the college website resolver page and its browser-side controls.

    The current FastAPI route passes an empty row list; the browser loads the
    current resolver records from the API. Callers may also supply initial rows,
    which are escaped and rendered into the page before the browser refreshes.
    """
    data =json.dumps(rows,ensure_ascii=False,default=str).replace('</','<\\/')
    server_rows = []
    for x in rows:
        code = escape(str(x.get('institution_code') or ''))
        name = escape(str(x.get('institution_name') or ''))
        city = escape(str(x.get('city') or '—'))
        website = str(x.get('website') or '').strip()
        website_html = (f'<a href="{escape(website, quote=True)}" target="_blank" rel="noopener">{escape(website)}</a>' if website else '—')
        status = escape(str(x.get('status') or 'PENDING'))
        source = escape(str(x.get('source') or '—'))
        checked = escape(str(x.get('last_checked_at') or x.get('updated_at') or '—'))
        action = (f'<span class="small muted">Verified</span>' if status=='VERIFIED' else
                (f'<button class="btn success" style="padding:6px 9px" data-code="{code}" data-name="{name}" data-website="{escape(website, quote=True)}" onclick="manualVerify(this)">✓ Verify</button>' if website else '<span class="small muted">No URL</span>'))
        server_rows.append(f'<tr><td><b>{code}</b></td><td>{name}</td><td>{city}</td><td>{website_html}</td><td><span class="status gray">{status}</span></td><td>{source}</td><td>{checked}</td><td>{action}</td></tr>')
    server_table = ''.join(server_rows)
    body ='''<div class="title"><div><h1>College Website Resolver</h1></div><div class="live"><span class="dot"></span>Resolver</div></div><div class="grid4"><div class="card metric"><div class="label">Total Colleges</div><div class="value" id="total">{len(rows)}</div></div><div class="card metric"><div class="label">Verified</div><div class="value" id="verified">0</div></div><div class="card metric"><div class="label">Needs Review</div><div class="value" id="review">0</div></div><div class="card metric"><div class="label">Pending</div><div class="value" id="pending">0</div></div></div><div class="card panel" style="margin-top:14px"><div class="toolbar"><div class="filters"><input id="q" class="input" placeholder="Search college name or ID…"><select id="status" class="select"><option value="">All statuses</option><option>PENDING</option><option value="CANDIDATE">UNVERIFIED</option><option>VERIFIED</option><option>NEEDS_REVIEW</option><option>FAILED</option></select></div><div class="filters"><button class="btn primary" id="resolverScanBtn" onclick="startResolver()">▶ Scan selected status</button><button class="btn secondary" id="resolverStopBtn" onclick="stopResolver()" style="display:none">■ Stop scan</button></div></div><div id="resolverProgress" class="notice" style="margin-bottom:12px;display:none"><div style="display:flex;justify-content:space-between;gap:12px"><b id="resolverProgressTitle">AI resolver idle</b><span id="resolverProgressCount" class="small muted">0 / 0</span></div><div style="height:9px;background:#e8edf3;border-radius:99px;overflow:hidden;margin-top:9px"><div id="resolverProgressBar" style="height:100%;width:0%;background:#11120D;transition:width .25s"></div></div><div id="resolverProgressCollege" class="small muted" style="margin-top:7px">Waiting to start.</div></div><div class="tablewrap"><table class="table resolver-table"><thead><tr><th>ID</th><th>College</th><th>City</th><th>Website</th><th>Status</th><th>Source</th><th>Checked</th><th>Action</th></tr></thead><tbody id="list"></tbody></table></div></div><div class="modalback" id="resolverModal"><div class="modal"><div class="modalhead"><b id="modalTitle">Resolver result</b><button class="close" onclick="closeModal()">×</button></div><div class="modalbody" id="modalBody"></div><div class="modalfoot"><button class="btn secondary" onclick="closeModal()">Close</button><button class="btn primary" id="resolverSaveEdit" style="display:none" onclick="saveResolverEdit()">Save changes</button></div></div></div>'''
    js =_common_js()+f'''<script>let rows={data};const q=document.querySelector('#q'),st=document.querySelector('#status');function render(){{const t=q.value.toLowerCase(),f=st.value,d=rows.filter(x=>(!f||x.status===f)&&(!t||String(x.institution_code+' '+x.institution_name+' '+(x.city||'')).toLowerCase().includes(t)));for(const [id,v] of [['total',rows.length],['verified',rows.filter(x=>x.status==='VERIFIED').length],['review',rows.filter(x=>x.status==='NEEDS_REVIEW').length],['pending',rows.filter(x=>x.status==='PENDING').length]])document.querySelector('#'+id).textContent=v;function resolverAction(x){{const verify=x.website?(x.status==='VERIFIED'?'<span class="small muted">Verified</span>':'<button class="btn success" style="padding:6px 9px" data-code="'+esc(x.institution_code)+'" data-name="'+esc(x.institution_name)+'" data-website="'+esc(x.website||'')+'" onclick="manualVerify(this)">✓ Verify</button>'):'<span class="small muted">No URL</span>';const research='<button class="btn ghost" style="padding:6px 9px" data-code="'+esc(x.institution_code)+'" data-name="'+esc(x.institution_name)+'" data-website="'+esc(x.website||'')+'" onclick="researchAgain(this)">↻ Research</button>';const edit='<button class="btn secondary" style="padding:6px 9px" data-code="'+esc(x.institution_code)+'" onclick="editResolverCollege(this.dataset.code)">✎ Edit</button>';return '<span class="rowactions resolver-actions">'+edit+verify+research+'</span>'}}document.querySelector('#list').innerHTML=d.map(x=>'<tr><td><b>'+esc(x.institution_code)+'</b></td><td>'+esc(x.institution_name)+'</td><td>'+esc(x.city||'—')+'</td><td>'+(x.website?'<a href="'+esc(x.website)+'" target="_blank" rel="noopener">'+esc(x.website)+'</a>':'—')+'</td><td>'+badge(x.status)+'</td><td>'+esc(x.source||'—')+'</td><td>'+fmtTime(x.last_checked_at||x.updated_at)+'</td><td>'+resolverAction(x)+'</td></tr>').join('')||'<tr><td colspan="9" class="empty">No colleges match.</td></tr>'}}
q.addEventListener('input',render);st.addEventListener('change',render);async function load(){{try{{rows=await api('/admin/api/resolver');render()}}catch(e){{toast(e.message,'err')}}}}async function findSelected(){{const ids=[...document.querySelectorAll('.pick:checked')].map(x=>x.value);if(!ids.length)return toast('Select at least one college','err');document.querySelector('#modalTitle').textContent='Resolving '+ids.length+' college(s)…';document.querySelector('#modalBody').innerHTML='<div class="notice">Existing candidates are verified first. Gemini is only used for unresolved colleges.</div>';document.querySelector('#resolverModal').classList.add('show');try{{const r=await api('/admin/api/resolver/find',{{method:'POST',headers:csrfHeaders({{'Content-Type':'application/json'}}),body:JSON.stringify({{ids}})}});document.querySelector('#modalTitle').textContent='Resolver results';document.querySelector('#modalBody').innerHTML=r.results.map(x=>`<div class="notice" style="margin-bottom:8px"><b>${{esc(x.institution_name)}}</b><br>${{x.website?`<a href="${{esc(x.website)}}" target="_blank" rel="noopener">${{esc(x.website)}}</a>`:'No URL found'}}<br><span class="small muted">${{esc(x.status)}} · ${{esc(x.note||'')}}</span></div>`).join('');await load()}}catch(e){{document.querySelector('#modalBody').innerHTML='<div class="issue">'+esc(e.message)+'</div>'}}}}// Process matching colleges one at a time while the backend owns each resolver job.
async function startResolver(){{if(window.resolverRunning)return;const statusFilter=st.value,scanBtn=document.querySelector('#resolverScanBtn'),stopBtn=document.querySelector('#resolverStopBtn'),box=document.querySelector('#resolverProgress'),title=document.querySelector('#resolverProgressTitle'),count=document.querySelector('#resolverProgressCount'),bar=document.querySelector('#resolverProgressBar'),college=document.querySelector('#resolverProgressCollege'),scannedCodes=[];window.resolverRunning=true;if(scanBtn){{scanBtn.disabled=true;scanBtn.textContent='Scanning selected status…'}}if(stopBtn){{stopBtn.style.display='inline-flex';stopBtn.disabled=false}}box.style.display='block';let total=rows.filter(x=>!statusFilter||x.status===statusFilter).length,done=0;title.textContent='AI resolver starting';college.textContent='Selected status: '+(statusFilter||'All statuses');count.textContent='0 / '+total;bar.style.width='0%';try{{while(window.resolverRunning){{const r=await api('/admin/api/resolver/next',{{method:'POST',headers:csrfHeaders({{'Content-Type':'application/json'}}),body:JSON.stringify({{status:statusFilter,exclude_codes:scannedCodes}})}});if(r.configured===false){{title.textContent='AI resolver not configured';college.textContent=r.reason||'Configure the resolver before scanning.';break}}if(r.busy){{title.textContent='AI resolver paused — server busy';college.textContent=r.reason+'; waiting safely…';await new Promise(x=>setTimeout(x,3000));continue}}if(!r.current||!r.current.institution_code){{title.textContent='AI resolver complete';college.textContent='No more colleges match the selected status.';bar.style.width='100%';count.textContent=done+' / '+done;break}}const code=String(r.current.institution_code);if(!scannedCodes.includes(code))scannedCodes.push(code);college.textContent='AI working on: '+r.current.institution_name+' ('+code+')';done++;const remaining=Number(r.remaining||0);total=Math.max(total,done+remaining);bar.style.width=(total?Math.min(100,done/total*100):100)+'%';count.textContent=done+' / '+total;title.textContent='AI resolver running';if(done%10===0)await load();if(remaining===0){{title.textContent='AI resolver complete';college.textContent='All colleges matching the selected status have been processed.';bar.style.width='100%';break}}await new Promise(x=>setTimeout(x,350))}}}}catch(e){{title.textContent='AI resolver stopped';college.textContent=e.message;toast(e.message,'err')}}finally{{const stopped=!window.resolverRunning;window.resolverRunning=false;if(stopped&&title.textContent!=='AI resolver not configured'&&title.textContent!=='AI resolver complete'){{title.textContent='AI resolver stopped';college.textContent='Scan stopped. Any college already in progress was allowed to finish.'}}if(scanBtn){{scanBtn.disabled=false;scanBtn.textContent='▶ Scan selected status'}}if(stopBtn){{stopBtn.style.display='none';stopBtn.disabled=false}}await load()}}}}// Stop after the current college finishes so an in-flight lookup is not abandoned.
function stopResolver(){{if(!window.resolverRunning)return;window.resolverRunning=false;const title=document.querySelector('#resolverProgressTitle'),college=document.querySelector('#resolverProgressCollege'),stopBtn=document.querySelector('#resolverStopBtn');title.textContent='AI resolver stopping';college.textContent='Finishing the current college before stopping.';if(stopBtn)stopBtn.disabled=true}}// Research a fresh website candidate while excluding the currently saved URL.
async function researchAgain(btn){{if(btn.disabled)return;btn.disabled=true;const oldText=btn.textContent;btn.textContent='Researching…';try{{const r=await api('/admin/api/resolver/find',{{method:'POST',headers:csrfHeaders({{'Content-Type':'application/json'}}),body:JSON.stringify({{ids:[btn.dataset.code],force_research:true,exclude_website:btn.dataset.website}})}});const x=r.results?.[0];if(!x)throw new Error('No resolver result returned');toast(x.status==='VERIFIED'?'New website verified':'New website researched — review the result','ok');await load()}}catch(e){{btn.disabled=false;btn.textContent=oldText;toast(e.message,'err')}}}}
let editingResolverCode=null;
function editResolverCollege(code){{const x=rows.find(r=>String(r.institution_code)===String(code));if(!x)return toast('College row not found','err');editingResolverCode=String(code);document.querySelector('#modalTitle').textContent='Edit college metadata';document.querySelector('#modalBody').innerHTML='<p class="small muted">Saved changes persist and are marked as manual corrections.</p><label>College ID</label><input class="input" value="'+esc(x.institution_code)+'" disabled style="width:100%;margin:5px 0 12px"><label>College name (read-only)</label><input class="input" value="'+esc(x.institution_name||'')+'" disabled style="width:100%;margin:5px 0 12px"><label>City</label><input id="editCity" class="input" value="'+esc(x.city||'')+'" placeholder="City" style="width:100%;margin:5px 0 12px"><label>Website URL</label><input id="editWebsite" class="input" value="'+esc(x.website||'')+'" placeholder="https://college.edu" style="width:100%;margin:5px 0 12px"><label>Source description</label><input id="editSource" class="input" value="'+esc(x.source||'')+'" placeholder="Official college website / CAP PDF" style="width:100%;margin:5px 0 12px"><label>Source URL (optional)</label><input id="editSourceUrl" class="input" value="'+esc(x.source_url||'')+'" placeholder="https://official-source..." style="width:100%;margin:5px 0 12px">';document.querySelector('#resolverSaveEdit').style.display='inline-flex';document.querySelector('#resolverModal').classList.add('show')}}
// Persist manual city, website and source corrections through the resolver API.
async function saveResolverEdit(){{const btn=document.querySelector('#resolverSaveEdit');if(!editingResolverCode||btn.disabled)return;btn.disabled=true;btn.textContent='Saving…';try{{await api('/admin/api/resolver/edit',{{method:'POST',headers:csrfHeaders({{'Content-Type':'application/json'}}),body:JSON.stringify({{institution_code:editingResolverCode,city:document.querySelector('#editCity').value,website:document.querySelector('#editWebsite').value,source:document.querySelector('#editSource').value,source_url:document.querySelector('#editSourceUrl').value}})}});document.querySelector('#resolverModal').classList.remove('show');document.querySelector('#resolverSaveEdit').style.display='none';editingResolverCode=null;toast('College metadata saved','ok');await load()}}catch(e){{toast('Save failed: '+e.message,'err')}}finally{{btn.disabled=false;btn.textContent='Save changes'}}}}
// Submit the administrator's verification decision; the backend performs final checks.
async function manualVerify(btn){{if(btn.disabled)return;btn.disabled=true;const oldText=btn.textContent;btn.textContent='Verifying…';try{{await api('/admin/api/resolver/verify',{{method:'POST',headers:csrfHeaders({{'Content-Type':'application/json'}}),body:JSON.stringify({{institution_code:btn.dataset.code,institution_name:btn.dataset.name,website:btn.dataset.website}})}});toast('Website marked verified','ok');await load()}}catch(e){{btn.disabled=false;btn.textContent=oldText;toast(e.message,'err')}}}}
function closeModal(){{document.querySelector('#resolverModal').classList.remove('show');document.querySelector('#resolverSaveEdit').style.display='none';editingResolverCode=null}}render();load();</script>'''
    body =body.replace('id="total">{len(rows)}','id="total">'+str(len(rows)))
    body =body.replace('<tbody id="list"></tbody>', '<tbody id="list">'+server_table+'</tbody>')
    return _shell('College Website Resolver', 'resolver', body, js)
