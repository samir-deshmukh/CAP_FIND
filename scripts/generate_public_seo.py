"""Generate deployment-specific robots.txt and sitemap.xml without inventing a domain."""
from __future__ import annotations
import argparse
from pathlib import Path
from urllib.parse import urljoin
from xml.sax.saxutils import escape

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--site',default='site')
    ap.add_argument('--base-url',required=True,help='Absolute production HTTPS URL')
    args=ap.parse_args(); base=args.base_url.rstrip('/')+'/'
    if not base.startswith('https://'): raise SystemExit('base-url must use https://')
    site=Path(args.site); site.mkdir(parents=True,exist_ok=True)
    (site/'robots.txt').write_text('User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /preview/\nDisallow: /data/\nDisallow: /data/courses/\nDisallow: /data/search_index.js\nSitemap: '+urljoin(base,'sitemap.xml')+'\n',encoding='utf-8')
    # Include only canonical public HTML pages. Query/filter states and private
    # routes are intentionally excluded.
    public_urls = [base]
    for page in sorted(site.rglob('*.html')):
        rel = page.relative_to(site).as_posix()
        if rel in {'index.html','404.html','privacy.html','terms.html'} or rel.startswith(('admin/', 'preview/')):
            continue
        public_urls.append(urljoin(base, rel))
    seen = set(); public_urls = [u for u in public_urls if not (u in seen or seen.add(u))]
    items = ''.join(f'  <url><loc>{escape(u)}</loc></url>\n' for u in public_urls)
    (site/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+items+'</urlset>\n',encoding='utf-8')
if __name__=='__main__': main()
