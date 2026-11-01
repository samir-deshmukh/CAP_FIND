"""Load validated cutoff CSVs into the authoritative PostgreSQL database."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import pandas as pd
from sqlalchemy import text
sys.path.insert(0,str(Path(__file__).resolve().parent))
from db_bootstrap import bootstrap_schema, engine_for  # noqa: E402
from validate_data import (REQUIRED_COLUMNS, SECTION_MAP, STAGE_MAP,
    forward_fill_block_columns, is_extraction_anomaly, parse_category, parse_filename)  # noqa: E402
from category_codes import is_category_code  # noqa: E402


def load_program_levels(ref_dir: Path):
    df=pd.read_csv(ref_dir/'program_aliases.csv',dtype=str,keep_default_na=False)
    return dict(zip(df['raw_name'].str.strip(),df['level'].str.strip()))


def get_or_create_program(conn, cache, family, name_raw, level_map):
    key=(family,name_raw)
    if key in cache:return cache[key]
    level=level_map.get(name_raw)
    row=conn.execute(text('''INSERT INTO programs(program_family,program_name_raw,level)
        VALUES(:family,:name,:level) ON CONFLICT(program_family,program_name_raw) DO NOTHING
        RETURNING program_id'''), {'family':family,'name':name_raw,'level':level}).fetchone()
    if row is None:
        row=conn.execute(text('SELECT program_id FROM programs WHERE program_family=:family AND program_name_raw=:name'),
                         {'family':family,'name':name_raw}).fetchone()
    cache[key]=row[0]; return row[0]


def ingest_file(conn,path,program_cache,level_map):
    meta=parse_filename(path)
    if not meta: raise ValueError(f'{path.name}: invalid cutoffs filename')
    family,year,round_no=meta['family'],meta['year'],meta['round']
    df=pd.read_csv(path,dtype=str,keep_default_na=False,encoding='utf-8-sig')
    missing=[c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing: raise ValueError(f'{path.name}: missing columns {missing}')
    rows_read=len(df)
    for _,row in df.iterrows():
        conn.execute(text('INSERT INTO staging_cutoffs(source_file,raw_row) VALUES(:f,:r)'),{'f':path.name,'r':row.to_json()})
    forward_fill_block_columns(df)
    inserted=skipped=duplicate=failed=0
    for rowno,row in df.iterrows():
        page=int(row['page']) if str(row['page']).strip().isdigit() else None
        def error(reason):
            conn.execute(text('''INSERT INTO ingest_errors(source_file,source_page,source_row,raw_category,raw_program,reason)
                VALUES(:f,:p,:r,:c,:prog,:reason)'''),{'f':path.name,'p':page,'r':int(rowno),'c':row['category'],'prog':row['program_name'],'reason':reason})
        if is_extraction_anomaly(row): skipped+=1; error('EXTRACTION_ANOMALY'); continue
        cat=row['category'].strip(); base,is_ladies,_=parse_category(cat)
        if base is None or not is_category_code(cat): skipped+=1; error(f'MALFORMED_CATEGORY: {cat!r}'); continue
        stage=STAGE_MAP.get(row['stage'].strip()); section=SECTION_MAP.get(row['section'].strip())
        if stage is None: skipped+=1; error(f'UNKNOWN_STAGE: {row["stage"]!r}'); continue
        if section is None: skipped+=1; error(f'UNKNOWN_SECTION: {row["section"]!r}'); continue
        rank_raw=row['rank_number'].strip(); rank=int(rank_raw) if rank_raw.isdigit() else None
        suffix=row['rank_suffix'].strip() or None
        try: percentile=float(row['percentage'])
        except ValueError: skipped+=1; error(f'BAD_PERCENTAGE: {row["percentage"]!r}'); continue
        prog=row['program_name'].strip(); inst=row['institution_code'].strip()
        pid=get_or_create_program(conn,program_cache,family,prog,level_map)
        try:
            conn.execute(text('INSERT INTO base_categories(base_code) VALUES(:cat) ON CONFLICT(base_code) DO NOTHING'), {'cat':base})
            program_code=str(row.get('program_code','')).strip() or None
            result=conn.execute(text('''INSERT INTO cutoffs(year,round,institution_code,program_id,program_code,base_category,is_ladies,section_code,stage_code,home_university,rank_number,rank_suffix,percentile,raw_category,raw_program_name,source_pdf,source_page)
                VALUES(:year,:round,:inst,:pid,:program_code,:cat,:ladies,:section,:stage,:hu,:rank,:suffix,:pct,:rawcat,:rawprog,:pdf,:page)
                ON CONFLICT(year,round,institution_code,program_id,base_category,is_ladies,section_code,stage_code,rank_number,percentile) DO NOTHING'''),
                {'year':year,'round':round_no,'inst':inst,'pid':pid,'program_code':program_code,'cat':base,'ladies':is_ladies,'section':section,'stage':stage,'hu':None,'rank':rank,'suffix':suffix,'pct':percentile,'rawcat':cat,'rawprog':prog,'pdf':row['source_pdf'],'page':page})
            if result.rowcount==0: duplicate+=1; error('DUPLICATE_UNIQUE_KEY')
            else: inserted+=1
        except Exception as exc:
            failed+=1; error(str(exc))
    conn.execute(text('''INSERT INTO ingest_log(source_file,rows_read,rows_inserted,rows_skipped,rows_duplicate,rows_failed)
        VALUES(:f,:r,:i,:s,:d,:e)'''),{'f':path.name,'r':rows_read,'i':inserted,'s':skipped,'d':duplicate,'e':failed})
    return rows_read,inserted,skipped,duplicate,failed


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('raw_dir',nargs='?',default='data/raw'); ap.add_argument('--db-url',default=None); ap.add_argument('--ref-dir',default='data/reference'); args=ap.parse_args()
    paths=sorted(Path(args.raw_dir).glob('*.csv'))
    if not paths: raise SystemExit(f'No CSVs found in {args.raw_dir}')
    engine=engine_for(args.db_url); bootstrap_schema(engine); levels=load_program_levels(Path(args.ref_dir)); cache={}
    totals=[0,0,0,0,0]
    with engine.begin() as conn:
        for p in paths:
            vals=ingest_file(conn,p,cache,levels); print(f'{p.name}: read={vals[0]} inserted={vals[1]} skipped={vals[2]} duplicate={vals[3]} failed={vals[4]}')
            totals=[a+b for a,b in zip(totals,vals)]
    print('TOTAL:',dict(zip(['read','inserted','skipped','duplicate','failed'],totals)))
    if totals[0] != sum(totals[1:]): raise SystemExit('ROW COUNT MISMATCH')

if __name__=='__main__':main()
