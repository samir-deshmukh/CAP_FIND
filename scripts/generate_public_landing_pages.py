"""Generate crawlable, data-backed public SEO pages from a verified API snapshot.

The generator never invents college/course facts. It only renders records present
in the supplied public API snapshot. Run manually after a data publication.
"""
from __future__ import annotations
import argparse, html, json, re
from pathlib import Path
from collections import defaultdict
from urllib.parse import quote

BASE = "https://cetfind.onrender.com"

def esc(v): return html.escape(str(v or ""), quote=True)

def slug(v):
    s = re.sub(r"[^a-z0-9]+", "-", str(v).lower()).strip("-")
    return s or "item"

def years(rows):
    ys = {int(h["year"]) for r in rows for h in r.get("history", [])}
    return sorted(ys)

def shell(title, description, canonical, body, schema=None):
    ld = ""
    if schema:
        ld = '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False) + '</script>'
    return f'''<!doctype html><html lang="en-IN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><meta name="description" content="{esc(description)}"><meta name="robots" content="index, follow, max-image-preview:large"><link rel="canonical" href="{esc(canonical)}"><meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{esc(canonical)}"><meta property="og:site_name" content="CETFind"><style>body{{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;background:#f7f6f1;color:#111;line-height:1.65}}main{{max-width:980px;margin:auto;padding:42px 22px 80px}}a{{color:#111}}.ey{{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#777}}h1{{font-size:clamp(36px,6vw,62px);line-height:1.08;letter-spacing:-.035em;margin:10px 0 15px}}h2{{margin-top:34px;line-height:1.2}}.lead{{font-size:18px;color:#444;max-width:780px}}.card{{background:#fff;border:1px solid #ddd8ce;border-radius:16px;padding:22px;margin:16px 0}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.stat{{background:#fff;border:1px solid #ddd8ce;border-radius:14px;padding:18px}}.num{{font-size:28px;font-weight:700}}.muted{{color:#666;font-size:13px}}ul{{padding-left:22px}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}}} </style>{ld}</head><body><main><a href="{BASE}/">← Back to CETFind</a>{body}</main></body></html>'''

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--site',default='site'); args=ap.parse_args()
    records=json.loads(Path(args.input).read_text())
    if not records: raise SystemExit('No records supplied')
    site=Path(args.site); root=site/'seo'; root.mkdir(parents=True,exist_ok=True)
    course=records[0]['course']; course_dir=root/'courses'; city_dir=root/'cities'; college_dir=root/'colleges';
    for d in (course_dir,city_dir,college_dir): d.mkdir(parents=True,exist_ok=True)
    cities=defaultdict(list)
    for r in records:
        if r.get('city'): cities[r['city']].append(r)
    all_years=years(records)
    latest=max(all_years) if all_years else None
    links=[]
    course_url=f'{BASE}/seo/courses/{course.lower()}.html'
    course_body=f'''<div class="ey">Course data · {esc(course)}</div><h1>{esc(course)} colleges in Maharashtra</h1><p class="lead">Explore CETFind's published historical Maharashtra CAP data for {esc(course)}. This page is generated from the same public college-search dataset used by CETFind.</p><div class="grid"><div class="stat"><div class="num">{len(records)}</div><div>college records</div></div><div class="stat"><div class="num">{len(cities)}</div><div>cities represented</div></div><div class="stat"><div class="num">{latest or '—'}</div><div>latest data year</div></div></div><h2>What the data means</h2><div class="card"><p>CETFind presents historical cutoff information for comparison and research. A past cutoff is not a guaranteed future cutoff. Current eligibility, CAP rules, seat availability and admission notices should be verified with the Maharashtra State CET Cell.</p></div><h2>Cities with published {esc(course)} records</h2><div class="card"><ul>'''
    for city, rs in sorted(cities.items(), key=lambda kv:(-len(kv[1]),kv[0])):
        if len(rs)<3: continue
        u=f'{BASE}/seo/cities/{slug(city)}-{course.lower()}.html'; links.append(u)
        course_body += f'<li><a href="{u}">{esc(city)} {esc(course)} colleges</a> — {len(rs)} college records</li>'
    course_body += '</ul></div><p class="muted">Data snapshot generated from CETFind public search results. Coverage can change when the underlying published dataset is updated.</p>'
    schema={"@context":"https://schema.org","@type":"CollectionPage","name":f"{course} colleges in Maharashtra — CETFind","url":course_url,"isPartOf":{"@type":"WebSite","name":"CETFind","url":BASE}}
    (course_dir/f'{course.lower()}.html').write_text(shell(f'{course} Colleges in Maharashtra | CETFind',f'Explore historical Maharashtra CET CAP college data for {course}, including cities and past cutoff records.',course_url,course_body,schema),encoding='utf-8')
    links.append(course_url)

    for city, rs in sorted(cities.items()):
        if len(rs)<3: continue
        u=f'{BASE}/seo/cities/{slug(city)}-{course.lower()}.html'; ys=years(rs); latest_city=max(ys) if ys else None
        body=f'''<div class="ey">City · {esc(city)} · Course · {esc(course)}</div><h1>{esc(course)} colleges in {esc(city)}</h1><p class="lead">CETFind has {len(rs)} published {esc(course)} college records for {esc(city)} in its current historical CAP dataset.</p><div class="grid"><div class="stat"><div class="num">{len(rs)}</div><div>college records</div></div><div class="stat"><div class="num">{len(ys)}</div><div>data years</div></div><div class="stat"><div class="num">{latest_city or '—'}</div><div>latest year</div></div></div><h2>Colleges</h2><div class="card"><ul>'''
        for r in sorted(rs,key=lambda x:x['name'].lower()):
            cu=f'{BASE}/seo/colleges/{slug(r["name"])}-{r["institution_code"]}-{course.lower()}.html'
            body+=f'<li><a href="{cu}">{esc(r["name"])}</a></li>'; links.append(cu)
        body+='''</ul></div><h2>Using historical cutoffs</h2><div class="card"><p>The cutoff information shown by CETFind describes past CAP outcomes. It should be used as historical context, not as a prediction or admission guarantee. Check the current official CET Cell information for the active admission cycle.</p></div><p><a href="/seo/courses/''' + course.lower() + '''.html">See all '''+course+''' college records →</a></p>'''
        schema={"@context":"https://schema.org","@type":"CollectionPage","name":f"{course} colleges in {city} — CETFind","url":u}
        (city_dir/f'{slug(city)}-{course.lower()}.html').write_text(shell(f'{course} Colleges in {city} | CETFind',f'Explore {course} colleges in {city} using historical Maharashtra CET CAP data published by CETFind.',u,body,schema),encoding='utf-8')

    for r in records:
        name=r['name']; u=f'{BASE}/seo/colleges/{slug(name)}-{r["institution_code"]}-{course.lower()}.html'; hs=r.get('history',[]); ys=years([r]);
        hist=''.join(f'<li>{int(h["year"])}: historical percentile range {float(h["low"]):.2f}–{float(h["high"]):.2f}</li>' for h in hs)
        body=f'''<div class="ey">College · {esc(course)}</div><h1>{esc(name)}</h1><p class="lead">Historical {esc(course)} CAP information for this college in the CETFind public dataset.</p><div class="card"><p><strong>City:</strong> {esc(r.get('city') or 'Not listed')}</p><p><strong>Data years:</strong> {', '.join(map(str,ys)) if ys else 'Not listed'}</p><p><strong>Latest historical high percentile in this summary:</strong> {float(r.get('highest_cutoff',0)):.2f}</p></div><h2>Historical cutoff summary</h2><div class="card"><ul>{hist}</ul></div><h2>Important</h2><div class="card"><p>These are historical records, not current admission guarantees. Cutoffs can change with applicant demand, merit, seats, category, CAP round and current rules. Verify the current admission cycle with the Maharashtra State CET Cell.</p></div><p><a href="{BASE}/">Search CETFind for your percentile and city →</a></p>'''
        schema={"@context":"https://schema.org","@type":"WebPage","name":f"{name} — {course} Historical CAP Data","url":u,"about":{"@type":"EducationalOrganization","name":name}}
        (college_dir/f'{slug(name)}-{r["institution_code"]}-{course.lower()}.html').write_text(shell(f'{name} | {course} Historical CAP Data | CETFind',f'Historical {course} CAP cutoff information for {name} from the CETFind public dataset.',u,body,schema),encoding='utf-8'); links.append(u)
    manifest={'course':course,'records':len(records),'city_pages':sum(len(v)>=3 for v in cities.values()),'college_pages':len(records),'urls':sorted(set(links))}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in manifest.items() if k!='urls'},indent=2))

if __name__=='__main__': main()
