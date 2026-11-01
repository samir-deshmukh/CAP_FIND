"""Seed PostgreSQL reference tables from the project's validated reference files."""
from __future__ import annotations
import argparse, sys
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_data import parse_filename  # noqa: E402
from db_bootstrap import bootstrap_schema, engine_for  # noqa: E402


def seed_base_categories(conn, ref_dir: Path) -> int:
    df = pd.read_csv(ref_dir / 'category_whitelist.csv', dtype=str, keep_default_na=False)
    for _, row in df.iterrows():
        conn.execute(text('''INSERT INTO base_categories (base_code, category_full, category_group)
            VALUES (:code,:full,:group)
            ON CONFLICT(base_code) DO UPDATE SET category_full=EXCLUDED.category_full,
              category_group=EXCLUDED.category_group'''),
            {'code':row['base_code'],'full':row['category_full'],'group':row['category_group']})
    return len(df)


def seed_sections(conn, ref_dir: Path) -> int:
    df = pd.read_csv(ref_dir / 'section_whitelist.csv', dtype=str, keep_default_na=False)
    for _, row in df.iterrows():
        conn.execute(text('''INSERT INTO sections (section_code, section_full)
            VALUES (:code,:full) ON CONFLICT(section_code) DO UPDATE SET section_full=EXCLUDED.section_full'''),
            {'code':row['section_code'],'full':row['section_full']})
    return len(df)


def seed_stages(conn, ref_dir: Path) -> int:
    vals = sorted(set(pd.read_csv(ref_dir / 'stage_whitelist.csv', dtype=str, keep_default_na=False)['canonical']))
    for value in vals:
        conn.execute(text('INSERT INTO stages(stage_code) VALUES(:v) ON CONFLICT(stage_code) DO NOTHING'), {'v':value})
    return len(vals)


def _pick_canonical_name(code: str, by_year: dict[int, Counter]) -> str:
    latest_year = max(by_year)
    counts = by_year[latest_year].most_common()
    top = counts[0][1]
    return sorted(name for name, count in counts if count == top)[0]


def seed_institutes(conn, raw_dir: Path) -> tuple[int,int]:
    names_by_code: dict[str,dict[int,Counter]] = defaultdict(lambda: defaultdict(Counter))
    for path in sorted(raw_dir.glob('*.csv')):
        meta = parse_filename(path)
        if not meta: continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=['institution_code','institution_name'])
        for code,name in zip(df['institution_code'],df['institution_name']):
            code,name=code.strip(),name.strip()
            if code and name: names_by_code[code][meta['year']][name]+=1
    variants=0
    for code,by_year in sorted(names_by_code.items()):
        all_names=Counter()
        for counts in by_year.values(): all_names.update(counts)
        if len(all_names)>1: variants+=1
        conn.execute(text('''INSERT INTO institutes(institution_code,institution_name)
            VALUES(:code,:name) ON CONFLICT(institution_code) DO UPDATE SET institution_name=EXCLUDED.institution_name'''),
            {'code':code,'name':_pick_canonical_name(code,by_year)})
    return len(names_by_code),variants


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db-url',default=None)
    ap.add_argument('--raw-dir',default='data/raw')
    ap.add_argument('--ref-dir',default='data/reference')
    args=ap.parse_args()
    engine=engine_for(args.db_url); bootstrap_schema(engine)
    with engine.begin() as conn:
        print(f'base_categories: {seed_base_categories(conn,Path(args.ref_dir))}')
        print(f'sections: {seed_sections(conn,Path(args.ref_dir))}')
        print(f'stages: {seed_stages(conn,Path(args.ref_dir))}')
        n,v=seed_institutes(conn,Path(args.raw_dir)); print(f'institutes: {n} (variants: {v})')

if __name__=='__main__': main()
