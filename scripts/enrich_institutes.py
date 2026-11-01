"""Enrich the authoritative PostgreSQL institute registry with city/website/address.

The CET cutoff PDFs identify institutes by stable institute code, but do not
provide a reliable dedicated city field. This script joins external enrichment
by institution_code and never invents a city from the college name.
"""
from __future__ import annotations
import argparse, difflib, re, sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import pandas as pd
from sqlalchemy import text

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
from src.cet_cap.db import get_engine

NAME_SIMILARITY_THRESHOLD=0.30

def validate_website(value):
    if not value:return None
    value=str(value).strip()
    if not value or value.lower() in {'unknown','nan','none'}:return None
    if any(ord(ch)<32 or ord(ch)==127 for ch in value):return None
    try:p=urlsplit(value)
    except ValueError:return None
    if p.scheme.lower() not in {'https','http'} or not p.netloc or p.username or p.password:return None
    if (p.hostname or '').lower() in {'localhost','127.0.0.1','0.0.0.0','::1'}:return None
    return urlunsplit((p.scheme.lower(),p.netloc,p.path or '/',p.query,p.fragment))

def norm(s):return re.sub(r'\s+',' ',re.sub(r'[^A-Z0-9 ]',' ',str(s).upper())).strip()

def load_and_reconcile(csv_path, conn):
    raw=pd.read_csv(csv_path,dtype=str,keep_default_na=False); raw.columns=[c.strip().lower() for c in raw.columns]
    required={'college_code','college_name','city','website'}
    missing=required-set(raw.columns)
    if missing: raise ValueError(f'Missing columns: {sorted(missing)}')
    rows=[]
    for _,r in raw.iterrows():
        for code in str(r['college_code']).split(','):
            rows.append({'college_code':code.strip(),'college_name':str(r['college_name']).strip(),'city':str(r['city']).strip() or None,'website':validate_website(r['website'])})
    split=pd.DataFrame(rows); quarantined=[]; clean=[]
    for code,g in split.groupby('college_code'):
        cities=sorted({x for x in g['city'].dropna() if x})
        if len(cities)>1:
            quarantined.append({'college_code':code,'reason':'CITY_CONFLICT','detail':dict(zip(g['city'],g['college_name']))}); continue
        site=g[g.website.notna()]; chosen=site.iloc[0] if len(site) else g.iloc[0]
        clean.append({'institution_code':code,'city':chosen['city'],'website':chosen['website'],'source_name':chosen['college_name']})
    clean=pd.DataFrame(clean)
    inst=pd.read_sql(text('SELECT institution_code,institution_name FROM institutes'),conn)
    merged=clean.merge(inst,on='institution_code',how='left',indicator=True)
    for _,r in merged[merged['_merge']=='left_only'].iterrows(): quarantined.append({'college_code':r.institution_code,'reason':'CODE_NOT_IN_DB','detail':r.source_name})
    in_db=merged[merged['_merge']=='both'].copy()
    if len(in_db):
        in_db['similarity']=in_db.apply(lambda r:difflib.SequenceMatcher(None,norm(r.institution_name),norm(r.source_name)).ratio(),axis=1)
        for _,r in in_db[in_db.similarity<NAME_SIMILARITY_THRESHOLD].iterrows():
            quarantined.append({'college_code':r.institution_code,'reason':'NAME_MISMATCH','detail':f'DB={r.institution_name!r} vs source={r.source_name!r} (similarity={r.similarity:.2f})'})
        in_db=in_db[in_db.similarity>=NAME_SIMILARITY_THRESHOLD]
    return in_db[['institution_code','city','website']],pd.DataFrame(quarantined)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('csv_path',nargs='?',default='data/reference/institute_contacts.csv'); ap.add_argument('--db-url',default=None); args=ap.parse_args()
    csv_path=Path(args.csv_path)
    if not csv_path.exists():sys.exit(f'{csv_path} not found')
    eng=get_engine(args.db_url)
    with eng.begin() as conn:
        conn.execute(text('ALTER TABLE institutes ADD COLUMN IF NOT EXISTS district TEXT'))
        conn.execute(text('ALTER TABLE institutes ADD COLUMN IF NOT EXISTS address TEXT'))
        conn.execute(text('ALTER TABLE institutes ADD COLUMN IF NOT EXISTS city_source TEXT'))
        conn.execute(text('ALTER TABLE institutes ADD COLUMN IF NOT EXISTS website_source TEXT'))
        conn.execute(text('ALTER TABLE institutes ADD COLUMN IF NOT EXISTS address_source TEXT'))
        conn.execute(text('ALTER TABLE institutes ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP'))
        clean,q=load_and_reconcile(csv_path,conn)
        for _,r in clean.iterrows():
            conn.execute(text('''UPDATE institutes SET city=:city, website=:website, city_source=:city_source, website_source=:website_source, verified_at=CURRENT_TIMESTAMP WHERE institution_code=:code'''),{'city':r.city or None,'website':r.website or None,'city_source':'reference_csv' if r.city else None,'website_source':'reference_csv' if r.website else None,'code':r.institution_code})
        total=conn.execute(text('SELECT COUNT(*) FROM institutes')).scalar_one(); cities=conn.execute(text('SELECT COUNT(*) FROM institutes WHERE city IS NOT NULL')).scalar_one(); sites=conn.execute(text('SELECT COUNT(*) FROM institutes WHERE website IS NOT NULL')).scalar_one()
    print(f'Updated {len(clean)} institutes.'); print(f'Coverage: {cities}/{total} have a city, {sites}/{total} have a website.')
    if len(q):
        print(f'\n{len(q)} rows quarantined (not applied):')
        for _,r in q.iterrows():print(f"  [{r['reason']}] {r['college_code']}: {r['detail']}")
if __name__=='__main__':main()
