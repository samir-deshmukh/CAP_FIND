"""Load validated seat-matrix CSVs into PostgreSQL."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import pandas as pd
from sqlalchemy import text
sys.path.insert(0,str(Path(__file__).resolve().parent))
from db_bootstrap import bootstrap_schema, engine_for
from validate_seats import TOTAL_MARKER, load_whitelists, normalize_category, parse_filename, KNOWN_BAD_CATEGORY_VALUES
from category_codes import is_category_code

REQUIRED_COLUMNS=['source_pdf','page','institution_code','choice_code','allocation_type','category','gender','seats']

def canonical_institution_code(institution_code_raw: str, choice_code: str) -> str:
    from_choice=choice_code[:5]
    if institution_code_raw.strip() and institution_code_raw.strip().zfill(5)!=from_choice:
        raise ValueError(f'institution_code mismatch: column={institution_code_raw.strip().zfill(5)} vs choice_code prefix={from_choice}')
    return from_choice

def ingest_file(conn,path,year,valid_cats,lane_map,alias_map):
    meta=parse_filename(path)
    if not meta: raise ValueError(f'{path.name}: invalid seat filename')
    family=meta['family']; df=pd.read_csv(path,dtype=str,keep_default_na=False,encoding='utf-8-sig')
    missing=[c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing: raise ValueError(f'{path.name}: missing columns {missing}')
    read=len(df); ins=skip=dup=fail=0
    for _,row in df.iterrows():
        page=int(row['page']) if row['page'].strip().isdigit() else None
        conn.execute(text('INSERT INTO staging_seats(source_file,raw_row) VALUES(:f,:r)'),{'f':path.name,'r':row.to_json()})
        cat=row['category'].strip(); lane_raw=row['allocation_type'].strip()
        def err(reason): conn.execute(text('''INSERT INTO seats_ingest_errors(source_file,source_page,institution_code,choice_code,raw_allocation_type,raw_category,reason) VALUES(:f,:p,:i,:c,:l,:cat,:r)'''),{'f':path.name,'p':page,'i':row['institution_code'],'c':row['choice_code'],'l':lane_raw,'cat':cat,'r':reason})
        if cat in KNOWN_BAD_CATEGORY_VALUES:
            skip+=1; err('QUARANTINED_EXTRACTION_ANOMALY'); continue
        try:
            inst=canonical_institution_code(row['institution_code'],row['choice_code']); lane=lane_map.get(lane_raw)
            if lane is None: raise ValueError(f'unknown allocation_type {lane_raw!r}')
            total=cat.strip().casefold()==TOTAL_MARKER.casefold(); base=None if total else normalize_category(cat,alias_map)
            if not total and not is_category_code(cat): raise ValueError(f'malformed category code {cat!r}')
            gender=row['gender'].strip(); ladies={'G':False,'L':True}.get(gender) if gender else None; seats=int(row['seats'])
            if base is not None:
                conn.execute(text('INSERT INTO base_categories(base_code) VALUES(:cat) ON CONFLICT(base_code) DO NOTHING'), {'cat':base})
            result=conn.execute(text('''INSERT INTO seats(capture_year,program_family,institution_code,choice_code,allocation_lane,base_category,is_total,is_ladies,seats,raw_category,raw_allocation_type,raw_gender,source_pdf,source_page)
                VALUES(:y,:family,:inst,:choice,:lane,:cat,:total,:ladies,:seats,:rawcat,:rawlane,:gender,:pdf,:page)
                ON CONFLICT(capture_year,program_family,institution_code,choice_code,allocation_lane,raw_category,raw_gender) DO NOTHING'''),
                {'y':year,'family':family,'inst':inst,'choice':row['choice_code'],'lane':lane,'cat':base,'total':total,'ladies':ladies,'seats':seats,'rawcat':cat,'rawlane':lane_raw,'gender':gender,'pdf':row['source_pdf'],'page':page})
            if result.rowcount==0: dup+=1; err('DUPLICATE_UNIQUE_KEY')
            else: ins+=1
        except Exception as exc:
            fail+=1; err(str(exc))
    conn.execute(text('''INSERT INTO seats_ingest_log(source_file,rows_read,rows_inserted,rows_skipped,rows_duplicate,rows_failed) VALUES(:f,:r,:i,:s,:d,:e)'''),{'f':path.name,'r':read,'i':ins,'s':skip,'d':dup,'e':fail})
    return read,ins,skip,dup,fail

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('raw_dir',nargs='?',default='data/raw/seats'); ap.add_argument('--year',type=int,required=True); ap.add_argument('--db-url',default=None); args=ap.parse_args()
    engine=engine_for(args.db_url); bootstrap_schema(engine); ref=Path('data/reference'); valid,lane,alias=load_whitelists(ref); paths=sorted(Path(args.raw_dir).glob('*.csv'))
    if not paths: raise SystemExit(f'No CSVs in {args.raw_dir}')
    totals=[0,0,0,0,0]
    with engine.begin() as conn:
        for _,r in pd.read_csv(ref/'allocation_lane_whitelist.csv',dtype=str).drop_duplicates('lane_code').iterrows():
            conn.execute(text('INSERT INTO allocation_lanes(lane_code,lane_full) VALUES(:c,:f) ON CONFLICT(lane_code) DO UPDATE SET lane_full=EXCLUDED.lane_full'),{'c':r['lane_code'],'f':r['lane_full']})
        for p in paths:
            vals=ingest_file(conn,p,args.year,valid,lane,alias); print(f'{p.name}: read={vals[0]} inserted={vals[1]} skipped={vals[2]} duplicate={vals[3]} failed={vals[4]}'); totals=[a+b for a,b in zip(totals,vals)]
    print('TOTAL:',dict(zip(['read','inserted','skipped','duplicate','failed'],totals)))
    if totals[0]!=sum(totals[1:]): raise SystemExit('ROW COUNT MISMATCH')
if __name__=='__main__': main()
