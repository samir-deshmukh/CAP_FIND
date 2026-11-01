import csv,json,os,re,logging,urllib.parse,urllib.request,urllib.error,ipaddress,socket,http.client,ssl
from pathlib import Path

log = logging.getLogger(__name__)
BASE=Path(__file__).resolve().parents[2]
CONTACTS=BASE/'data'/'reference'/'institute_contacts.csv'
GEMINI_MODEL=os.getenv('GEMINI_RESOLVER_MODEL','gemini-2.5-flash')

def valid_url(url):
    if not url:
        return None
    url = str(url).strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.scheme:
        url = "https://" + url
    try:
        u = urllib.parse.urlparse(url)
        host = (u.hostname or "").rstrip(".").lower()
        if u.scheme.lower() not in ("http", "https") or not host or not u.netloc:
            return None
        if u.username is not None or u.password is not None:
            return None
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in url):
            return None
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            return None
        # Accessing .port also validates malformed/out-of-range port values.
        _ = u.port
        return urllib.parse.urlunparse((u.scheme.lower(), u.netloc, u.path or "/", u.params, u.query, ""))
    except (ValueError, UnicodeError):
        return None


def _public_dns_target(url):
    """Resolve once and return only public socket addresses for a pinned request."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    if not host:
        return []
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        targets = []
        for family, socktype, proto, canonname, sockaddr in records:
            address = ipaddress.ip_address(sockaddr[0])
            if not address.is_global:
                return []
            targets.append((family, socktype, proto, sockaddr))
        return targets
    except (OSError, ValueError):
        return []

def verify_url(url, college_name, timeout=7, _redirects=0):
    url = valid_url(url)
    if not url:
        return {'ok': False, 'url': None, 'note': 'Invalid URL'}
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    targets = _public_dns_target(url)
    if not targets:
        return {'ok': False, 'url': None, 'note': 'URL resolves to a non-public or unreachable address'}
    try:
        response = None
        for family, socktype, proto, sockaddr in targets:
            try:
                raw = socket.socket(family, socktype, proto)
                raw.settimeout(timeout)
                raw.connect(sockaddr)
                if parsed.scheme == "https":
                    context = ssl.create_default_context()
                    raw = context.wrap_socket(raw, server_hostname=host)
                conn = http.client.HTTPConnection(host, port, timeout=timeout)
                conn.sock = raw
                path = urllib.parse.urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
                conn.request("GET", path, headers={"Host": parsed.netloc, "User-Agent": "CET-CAP-Website-Resolver/1.0", "Connection": "close"})
                response = conn.getresponse()
                break
            except OSError:
                try:
                    raw.close()
                except (UnboundLocalError, OSError):
                    pass
        if response is None:
            return {'ok': False, 'url': url, 'note': 'Unreachable: ConnectionError'}
        status = response.status
        if status in (301, 302, 303, 307, 308):
            location = response.getheader('location')
            if not location:
                return {'ok': False, 'url': url, 'status': status, 'note': f'HTTP {status}; redirect has no Location header'}
            if _redirects >= 5:
                return {'ok': False, 'url': url, 'status': status, 'note': 'Too many website redirects'}
            target = valid_url(urllib.parse.urljoin(url, location))
            if not target:
                return {'ok': False, 'url': url, 'status': status, 'note': 'Redirect target rejected by URL safety checks'}
            # Re-resolve and re-check every redirect target to prevent redirects
            # from turning the verifier into an SSRF path.
            return verify_url(target, college_name, timeout=timeout, _redirects=_redirects + 1)
        ctype = response.getheader('content-type', '')
        body = response.read(120000).decode('utf-8', 'ignore') if 'text' in ctype.lower() or 'html' in ctype.lower() else ''
        tokens = [x.lower() for x in re.findall(r'[a-z0-9]+', college_name) if len(x) > 2]
        hay = (url + ' ' + body[:100000]).lower()
        hits = sum(t in hay for t in tokens)
        denom = max(1, min(len(tokens), 8))
        return {'ok': 200 <= status < 400, 'url': url, 'status': status,
                'match_score': hits / denom, 'note': f'HTTP {status}; college-name match {hits}/{denom}'}
    except Exception as e:
        return {'ok': False, 'url': url, 'note': f'Unreachable: {type(e).__name__}'}

def _same_site(a, b):
    """Compare hostnames while allowing www/subdomains of the same site."""
    try:
        ha = (urllib.parse.urlparse(valid_url(a)).hostname or "").lower().removeprefix("www.")
        hb = (urllib.parse.urlparse(valid_url(b)).hostname or "").lower().removeprefix("www.")
        return bool(ha and hb and (ha == hb or ha.endswith("." + hb) or hb.endswith("." + ha)))
    except Exception:
        return False


def _json_object_from_text(text):
    """Decode the first complete JSON object without greedy brace matching."""
    text = str(text or "")
    for start, char in enumerate(text):
        if char != "{":
            continue
        depth = 0
        in_string = escaped = False
        for end in range(start, len(text)):
            current = text[end]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start:end + 1])
                    except (json.JSONDecodeError, TypeError):
                        break
                    if isinstance(value, dict):
                        return value
                    break
    raise RuntimeError("Gemini returned no valid JSON object")


def _grounding_evidence(data):
    """Extract actual Google Search citations, not URLs asserted by the model."""
    evidence = []
    queries = []
    for candidate in (data or {}).get("candidates", []):
        metadata = candidate.get("groundingMetadata") or candidate.get("grounding_metadata") or {}
        for query in metadata.get("webSearchQueries", metadata.get("web_search_queries", [])) or []:
            query = str(query or "").strip()
            if query and query not in queries:
                queries.append(query)
        candidate_evidence = []
        for chunk in metadata.get("groundingChunks", metadata.get("grounding_chunks", [])) or []:
            web = chunk.get("web") or {}
            uri = valid_url(web.get("uri") or web.get("url"))
            title = str(web.get("title") or "").strip()
            if uri:
                candidate_evidence.append({"url": uri, "title": title, "supporting_text": []})
        for support in metadata.get("groundingSupports", metadata.get("grounding_supports", [])) or []:
            segment = support.get("segment") or {}
            segment_text = str(segment.get("text") or "").strip()
            for index in support.get("groundingChunkIndices", support.get("grounding_chunk_indices", [])) or []:
                if isinstance(index, int) and 0 <= index < len(candidate_evidence) and segment_text:
                    candidate_evidence[index]["supporting_text"].append(segment_text)
        for item in candidate_evidence:
            if not any(existing["url"] == item["url"] for existing in evidence):
                evidence.append(item)
        for part in candidate.get("content", {}).get("parts", []):
            for annotation in part.get("annotations", []) or []:
                citation = annotation.get("url_citation") or annotation.get("urlCitation") or {}
                uri = valid_url(citation.get("url") or citation.get("uri") or annotation.get("url"))
                title = str(citation.get("title") or annotation.get("title") or "").strip()
                if uri and not any(item["url"] == uri for item in evidence):
                    evidence.append({"url": uri, "title": title, "supporting_text": []})
    return evidence, queries


def _grounding_supports_site(url, evidence):
    """Require a citation to the candidate site (or its own subdomain)."""
    candidate = valid_url(url)
    if not candidate:
        return False
    candidate_host = (urllib.parse.urlparse(candidate).hostname or "").lower().removeprefix("www.")
    for item in evidence or []:
        source_url = valid_url(item.get("url"))
        source_host = (urllib.parse.urlparse(source_url).hostname or "").lower().removeprefix("www.") if source_url else ""
        if source_host and source_host != "vertexaisearch.cloud.google.com" and (
            source_host == candidate_host or source_host.endswith("." + candidate_host)
        ):
            return True
        host_pattern = re.compile(r"(?<![a-z0-9.-])" + re.escape(candidate_host) + r"(?![a-z0-9.-])", re.I)
        if candidate_host and any(host_pattern.search(str(text)) for text in item.get("supporting_text", [])):
            return True
        # Some legacy search citations use a Google redirect URI and put the
        # original result domain only in its title. Never trust a title from a
        # normal third-party result as proof of the candidate domain.
        if source_host == "vertexaisearch.cloud.google.com" or (
            source_host in {"google.com", "www.google.com"}
            and urllib.parse.urlparse(source_url).path == "/url"
        ):
            title = str(item.get("title") or "").lower()
            domains = re.findall(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}", title)
            if any(domain.removeprefix("www.") == candidate_host
                   or domain.removeprefix("www.").endswith("." + candidate_host)
                   for domain in domains):
                return True
    return False


def _grounding_supports_value(value, evidence):
    """Return true only when Google linked a response segment containing value."""
    value = str(value or "").strip()
    if not value:
        return False
    pattern = re.compile(r"(?<![a-z0-9])" + re.escape(value) + r"(?![a-z0-9])", re.I)
    for item in evidence or []:
        for segment in item.get("supporting_text", []):
            text = str(segment)
            for match in pattern.finditer(text):
                # Do not treat the last word of a compound city (e.g. Mumbai
                # in Navi Mumbai) as evidence for a different city value.
                preceding = re.search(r"([A-Z][a-z]+)\s+$", text[:match.start()])
                if len(value.split()) == 1 and preceding:
                    continue
                return True
    return False


def gemini_verify_candidate(college_name, candidate_url, city=None, institution_code=None):
    """Use Gemini + Google Search to verify that a working URL belongs to the college."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    location = f", {city}" if city else ""
    code_hint = f"\nMaharashtra CAP institute code: {institution_code}" if institution_code else ""
    prompt = f'''Verify whether this URL is the official website of the exact Indian college/institution.
College: {college_name}{location}
{code_hint}
Candidate URL: {candidate_url}
Search the web for the exact CAP code and candidate domain, then inspect the candidate identity.
At least one Google Search citation must be from the candidate domain or an official government/
university source that explicitly identifies or links to that domain. Do not accept directories, social profiles,
ranking sites, admission aggregators, unrelated universities, or another institution with a
similar name. Use the CAP institute code to distinguish similarly named colleges. Return ONLY JSON
with keys verified, confidence, official_url, city, address, evidence_urls, note. Evidence URLs must
be actual official or government source pages that support the decision. Set verified=true only when
the candidate clearly belongs to the named institution.'''
    payload = {"contents":[{"parts":[{"text":prompt}]}],"tools":[{"google_search":{}}]}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(GEMINI_MODEL,safe='')}:generateContent",
        data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json","x-goog-api-key":key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini verification failed ({e.code})")
    text = "".join(part.get("text","") for c in data.get("candidates",[])
                   for part in c.get("content",{}).get("parts",[]))
    result = _json_object_from_text(text)
    evidence, queries = _grounding_evidence(data)
    result["grounding_evidence"] = evidence
    result["grounding_queries"] = queries
    result["official_url"] = valid_url(result.get("official_url"))
    if not evidence or not _grounding_supports_site(candidate_url, evidence):
        result["verified"] = False
        result["note"] = str(result.get("note") or "").strip()
        result["note"] = (result["note"] + " " if result["note"] else "") + "Google Search citations did not support the candidate website domain."
    return result


def seed_from_contacts(conn):
    if not CONTACTS.exists():return 0
    n=0
    with CONTACTS.open(newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            code=str(r.get('college_code','')).strip(); name=str(r.get('college_name','')).strip()
            if not code or not name:continue
            city=str(r.get('city','')).strip() or None; w=str(r.get('website','')).strip(); w=None if w.lower() in {'','unknown','nan','none'} else w
            conn.execute('''INSERT INTO college_website_resolver(institution_code,institution_name,city,website,status,source,source_url) VALUES (?,?,?,?,?,?,?) ON CONFLICT(institution_code) DO UPDATE SET institution_name=excluded.institution_name,city=COALESCE(excluded.city,college_website_resolver.city),website=CASE WHEN college_website_resolver.website IS NULL OR college_website_resolver.website='' THEN excluded.website ELSE college_website_resolver.website END''',(code,name,city,w,'CANDIDATE' if w else 'PENDING','reference_csv','data/reference/institute_contacts.csv'))
            conn.execute("UPDATE institutes SET city=COALESCE(?,city), website=COALESCE(?,website), city_source=CASE WHEN ? IS NOT NULL THEN 'reference_csv' ELSE city_source END, website_source=CASE WHEN ? IS NOT NULL THEN 'reference_csv' ELSE website_source END, verified_at=CURRENT_TIMESTAMP WHERE institution_code=?",(city,w,city,w,code)); n+=1
    return n

def _reference_contacts():
    """Load the maintained contact file, supporting both headered and legacy headerless CSVs."""
    contacts = {}
    if not CONTACTS.exists():
        return contacts
    with CONTACTS.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))
    if not rows:
        return contacts
    header = [str(x).strip().lower() for x in rows[0]]
    if {'college_code', 'college_name', 'city', 'website'}.issubset(header):
        data_rows = [dict(zip(header, r)) for r in rows[1:]]
    else:
        data_rows = [
            {'college_code': r[0] if len(r) > 0 else '',
             'college_name': r[1] if len(r) > 1 else '',
             'city': r[2] if len(r) > 2 else '',
             'website': r[3] if len(r) > 3 else ''}
            for r in rows
        ]
    for r in data_rows:
        code = str(r.get('college_code', '')).strip()
        if not code:
            continue
        website = str(r.get('website', '')).strip()
        if website.lower() in {'', 'unknown', 'nan', 'none'}:
            website = None
        contacts[code] = {
            'institution_name': str(r.get('college_name', '')).strip() or None,
            'city': str(r.get('city', '')).strip() or None,
            'website': valid_url(website) if website else None,
        }
    return contacts


def _city_key(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def infer_city_from_name(institution_name, known_cities):
    """Infer a city only when a known city name appears as a whole phrase.

    Longest-first matching avoids choosing a short city contained in a longer
    place name. This is a deterministic fallback, not a substitute for source
    verification when the name does not contain a known city.
    """
    name = " " + _city_key(institution_name) + " "
    candidates = sorted(
        {str(city).strip() for city in known_cities if str(city or '').strip()},
        key=lambda city: len(_city_key(city)), reverse=True,
    )
    matches = []
    for city in candidates:
        key = _city_key(city)
        if len(key) < 3 or key in {"india", "maharashtra", "vidarbha", "konkan"}:
            continue
        if " " + key + " " in name:
            matches.append(city)
    if not matches:
        return None
    longest = len(_city_key(matches[0]))
    best = [city for city in matches if len(_city_key(city)) == longest]
    return best[0] if len({_city_key(city) for city in best}) == 1 else None


def _known_city_names(conn):
    """Build a local city vocabulary from already populated CAP/reference rows."""
    cities = set()
    try:
        cities.update(str(r[0]).strip() for r in conn.execute(
            "SELECT DISTINCT city FROM institutes WHERE city IS NOT NULL AND TRIM(city)<>''"
        ) if r[0])
    except Exception:
        pass
    cities.update(str(row.get('city') or '').strip() for row in _reference_contacts().values() if row.get('city'))
    return {city for city in cities if city}


def seed_from_import(conn, job_id, codes_out=None):
    """Create resolver rows from the colleges actually present in an import.

    The PDF/import is the scope of work. Existing institute/reference data is
    preferred for city and website; no broad external dataset is used to
    invent unrelated resolver institutions.
    """
    refs = _reference_contacts()
    known_cities = _known_city_names(conn)
    colleges = {}
    last_id = 0
    while True:
        source_rows = conn.execute(
            "SELECT id,COALESCE(normalized_json,raw_json) AS normalized_json FROM import_staging_records "
            "WHERE job_id=? AND result_type IN ('CUTOFFS','SEATS') AND id>? "
            "ORDER BY id LIMIT 500",
            (job_id, last_id),
        ).fetchall()
        if not source_rows:
            break
        last_id = int(source_rows[-1]['id'])
        for row in source_rows:
            try:
                data = json.loads(row.get('normalized_json') or '{}')
            except Exception:
                continue
            code = str(data.get('institution_code', '')).strip()
            if not code:
                continue
            colleges.setdefault(code, {
                'institution_name': str(data.get('institution_name', '')).strip() or code
            })
    if codes_out is not None:
        codes_out.update(colleges)

    seeded = 0
    for code, incoming in colleges.items():
        inst = conn.execute(
            "SELECT institution_code,institution_name,city,website,address "
            "FROM institutes WHERE institution_code=?",
            (code,),
        ).fetchone()
        ref = refs.get(code, {})
        name = (
            (inst['institution_name'] if inst else None)
            or incoming['institution_name']
            or code
        )
        city = (inst['city'] if inst else None) or ref.get('city')
        city_source = 'institutes' if inst and inst['city'] else ('reference_csv' if ref.get('city') else None)
        if not city:
            city = infer_city_from_name(name, known_cities)
            city_source = 'college_name_match' if city else None
        website = valid_url(inst['website']) if inst and inst['website'] else None
        website_source = 'institutes' if website else None
        if not website and ref.get('website'):
            website = ref['website']
            website_source = 'reference_csv'

        existing = conn.execute(
            "SELECT status,website,city FROM college_website_resolver "
            "WHERE institution_code=?",
            (code,),
        ).fetchone()
        if existing and existing['status'] == 'VERIFIED':
            # Never downgrade an already verified resolver result.
            conn.execute(
                "UPDATE college_website_resolver SET institution_name=?,"
                "city=COALESCE(city,?),city_source=CASE WHEN city IS NULL THEN COALESCE(?,city_source) ELSE city_source END,updated_at=CURRENT_TIMESTAMP "
                "WHERE institution_code=?",
                (name, city, city_source, code),
            )
        else:
            status = 'CANDIDATE' if website else 'PENDING'
            conn.execute(
                """INSERT INTO college_website_resolver
                   (institution_code,institution_name,city,website,status,
                    source,source_url,city_source,website_source,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(institution_code) DO UPDATE SET
                     institution_name=excluded.institution_name,
                     city=COALESCE(college_website_resolver.city,excluded.city),
                     city_source=CASE WHEN college_website_resolver.city IS NULL THEN COALESCE(excluded.city_source,college_website_resolver.city_source) ELSE college_website_resolver.city_source END,
                     website=CASE
                         WHEN college_website_resolver.website IS NULL
                              OR college_website_resolver.website=''
                         THEN excluded.website
                         ELSE college_website_resolver.website
                     END,
                     status=CASE
                         WHEN college_website_resolver.website IS NOT NULL
                              AND college_website_resolver.website<>'' THEN college_website_resolver.status
                         ELSE excluded.status
                     END,
                     source=CASE
                         WHEN college_website_resolver.website IS NOT NULL
                              AND college_website_resolver.website<>'' THEN college_website_resolver.source
                         ELSE excluded.source
                     END,
                     source_url=CASE
                         WHEN college_website_resolver.website IS NOT NULL
                              AND college_website_resolver.website<>'' THEN college_website_resolver.source_url
                         ELSE excluded.source_url
                     END,
                     updated_at=CURRENT_TIMESTAMP""",
                (code, name, city, website, status, website_source, website, city_source, website_source,
                 ),
            )
        seeded += 1
    return seeded


def _update_institute_resolution(conn, code, city=None, address=None, website=None, source=None):
    """Mirror trusted resolver fields into the institute reference when present."""
    if not (city or address or website):
        return
    conn.execute(
        """UPDATE institutes
           SET city=CASE WHEN ? IS NOT NULL THEN ? ELSE NULLIF(TRIM(city),'') END,
               address=CASE WHEN ? IS NOT NULL THEN ? ELSE NULLIF(TRIM(address),'') END,
               website=CASE WHEN ? IS NOT NULL THEN ? ELSE NULLIF(TRIM(website),'') END,
               city_source=CASE WHEN ? IS NOT NULL THEN ? ELSE city_source END,
               address_source=CASE WHEN ? IS NOT NULL THEN ? ELSE address_source END,
               website_source=CASE WHEN ? IS NOT NULL THEN ? ELSE website_source END,
               verified_at=CURRENT_TIMESTAMP
           WHERE institution_code=?""",
        (
            city, city, address, address, website, website,
            city, source, address, source, website, source, code,
        ),
    )


def resolve_import_job(job_id=None, limit=None, status_filter=None, exclude_codes=None,
                       institution_code=None):
    """Resolve a bounded number of colleges without running a long background loop.

    When job_id is supplied, only colleges from that import are considered.
    When job_id is None, the resolver queue is taken from the CAP resolver table.
    A small limit lets the admin UI process one college at a time and keeps the
    web service responsive on small Render instances.

    Order is deliberate:
      1. existing resolver/institute/reference website
      2. verify that URL and capture its redirect target
      3. only then use Gemini + Google Search for unresolved colleges

    City follows the same local-data-first rule. Network discovery is never
    used to create extra institutions outside the uploaded PDF.
    """
    from .db import connect

    seeded = 0
    import_codes = set()
    with connect() as c:
        if job_id is not None:
            seeded = seed_from_import(c, job_id, import_codes)
            c.commit()

        if job_id is None:
            excluded = sorted({str(code).strip() for code in (exclude_codes or []) if str(code or '').strip()})
            query = (
                "SELECT institution_code,institution_name,city,website,status,source "
                "FROM college_website_resolver"
            )
            clauses = []
            params = []
            if status_filter:
                clauses.append("status = ?")
                params.append(str(status_filter))
            else:
                # The empty/All filter deliberately includes every resolver status.
                pass
            if institution_code:
                clauses.append("institution_code = ?")
                params.append(str(institution_code))
            if excluded:
                clauses.append("institution_code NOT IN (" + ",".join("?" for _ in excluded) + ")")
                params.extend(excluded)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY CASE status WHEN 'CANDIDATE' THEN 0 WHEN 'PENDING' THEN 1 ELSE 2 END, LOWER(institution_name)"
            if limit is not None:
                query += " LIMIT ?"
                params.append(max(1, int(limit)))
            rows = [dict(r) for r in c.execute(query, params)]
        else:
            if import_codes:
                codes = sorted(import_codes)
                placeholders = ','.join('?' for _ in codes)
                query = (
                    "SELECT institution_code,institution_name,city,website,status,source "
                    "FROM college_website_resolver WHERE institution_code IN ("
                    + placeholders + ") "
                    "AND (status NOT IN ('VERIFIED','NEEDS_REVIEW') "
                    "OR (status='VERIFIED' AND COALESCE(TRIM(city),'')='')) "
                    "ORDER BY institution_name LIMIT ?"
                )
                rows = [dict(r) for r in c.execute(
                    query,
                    (*codes, max(1, int(limit)) if limit is not None else 2147483647),
                )]
    if not rows:
        return {'ok': True, 'seeded': seeded, 'resolved': 0, 'searched': 0, 'failed': 0, 'remaining': 0}

    resolved = searched = failed = 0
    refs = _reference_contacts()

    for row in rows:
        code = row['institution_code']
        name = row['institution_name']
        city = row.get('city')
        if row.get('status') == 'VERIFIED' and not str(city or '').strip():
            # A verified website does not imply that its location is known.
            # Enrich the missing location without re-verifying or overwriting
            # the trusted website/status/source fields.
            searched += 1
            try:
                location_ai, _ = gemini_find(name, None, institution_code=code)
                found_city = str(location_ai.get('city') or '').strip() or None
                found_address = str(location_ai.get('address') or '').strip() or None
                evidence = location_ai.get('evidence_urls')
                note_parts = [str(location_ai.get('note') or '').strip()]
                if isinstance(evidence, list) and evidence:
                    note_parts.append('Location evidence: ' + ', '.join(str(url) for url in evidence[:4]))
                with connect() as c:
                    c.execute(
                        """UPDATE college_website_resolver
                           SET city=CASE WHEN city IS NULL OR TRIM(city)='' THEN ? ELSE city END,
                               address=CASE WHEN address IS NULL OR TRIM(address)='' THEN ? ELSE address END,
                               verification_note=CASE WHEN ?<>'' THEN ? ELSE verification_note END,
                               last_checked_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                           WHERE institution_code=? AND status='VERIFIED'""",
                        (found_city, found_address, ' '.join(x for x in note_parts if x),
                         ' '.join(x for x in note_parts if x), code),
                    )
                    _update_institute_resolution(
                        c, code, city=found_city, address=found_address,
                        source='gemini_google_search',
                    )
                    c.commit()
                if found_city or found_address:
                    resolved += 1
            except Exception as exc:
                log.warning("AI location lookup failed for verified college %s: %s", code, exc)
            continue
        if row.get('status') == 'VERIFIED':
            # Scanning All statuses must never downgrade or replace an already
            # verified URL. Use the explicit Research action for replacement.
            continue
        candidate_urls = []
        if row.get('website'):
            candidate_urls.append((row['website'], row.get('source') or 'existing_data'))
        ref_url = refs.get(code, {}).get('website')
        if ref_url and all(ref_url != u for u, _ in candidate_urls):
            candidate_urls.append((ref_url, 'reference_csv'))

        verified = None
        ai_unavailable = False
        reachable_candidate = None
        for url, source in candidate_urls:
            result = verify_url(url, name)
            if result.get('ok'):
                reachable_candidate = (result, source)
            else:
                continue
            # A reachable URL is only a candidate. Gemini + Google Search must
            # confirm the site's identity before we mark it VERIFIED.
            try:
                ai_check = gemini_verify_candidate(name, result['url'], city, code)
                ai_conf = float(ai_check.get('confidence') or 0)
                ai_url = ai_check.get('official_url')
                if bool(ai_check.get('verified')) and ai_conf >= 0.70 and (
                    not ai_url or _same_site(result['url'], ai_url)
                ):
                    verified = (result, source, ai_check)
                    break
            except Exception as exc:
                if 'GEMINI_API_KEY is not configured' in str(exc):
                    ai_unavailable = True
                    break
                log.warning("AI website verification failed for %s: %s", code, exc)

        if ai_unavailable:
            # Do not misclassify a reachable college website as FAILED just
            # because the optional AI verifier is not configured.
            result, source = reachable_candidate if reachable_candidate else (None, None)
            with connect() as c:
                c.execute(
                    """UPDATE college_website_resolver
                       SET website=COALESCE(?,website),status='NEEDS_REVIEW',
                           source=COALESCE(?,source),
                           source_url=COALESCE(?,source_url),
                           verification_note=?,
                           last_checked_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE institution_code=?""",
                    (
                        result.get('url') if result else None,
                        source,
                        result.get('url') if result else None,
                        'Reachable candidate found; Gemini AI verification is not configured on the server.',
                        code,
                    ),
                )
                c.commit()
            continue

        if verified:
            result, source, ai_check = verified
            found_city = city or (str(ai_check.get('city')).strip() if ai_check.get('city') else None)
            found_address = None
            if not city:
                # The website is already verified, but city is still missing.
                # Use search only for the missing location field; never replace
                # the already verified website with the search result.
                try:
                    location_ai, _ = gemini_find(name, None, institution_code=code)
                    found_city = str(location_ai.get('city')).strip() if location_ai.get('city') else None
                    found_address = str(location_ai.get('address')).strip() if location_ai.get('address') else None
                except Exception:
                    pass
            with connect() as c:
                c.execute(
                    """UPDATE college_website_resolver
                           SET city=CASE WHEN city IS NULL OR TRIM(city)='' THEN ? ELSE city END,
                               address=CASE WHEN address IS NULL OR TRIM(address)='' THEN ? ELSE address END,
                           website=?,status='VERIFIED',source=?,
                           source_url=?,verification_note=?,
                           last_checked_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE institution_code=?""",
                    (
                        found_city, found_address, result['url'], source,
                        result['url'], result['note'], code,
                    ),
                )
                _update_institute_resolution(
                    c, code, city=found_city, address=found_address,
                    website=result['url'], source=source
                )
                c.commit()
            resolved += 1
            continue

        try:
            searched += 1
            ai, _ = gemini_find(name, city, institution_code=code)
            url = ai.get('official_url')
            found_city = str(ai.get('city')).strip() if ai.get('city') else city
            address = str(ai.get('address')).strip() if ai.get('address') else None
            result = (
                verify_url(url, name)
                if url
                else {'ok': False, 'url': None, 'note': 'Search returned no official URL'}
            )
            ai_check = {}
            if result.get('ok'):
                try:
                    ai_check = gemini_verify_candidate(name, result['url'], found_city, code)
                except Exception as exc:
                    ai_check = {'verified': False, 'confidence': 0, 'note': f'AI verification failed: {exc}'}
            ai_conf = float(ai_check.get('confidence') or 0)
            ai_url = ai_check.get('official_url')
            if (
                result.get('ok')
                and bool(ai_check.get('verified'))
                and ai_conf >= 0.70
                and (not ai_url or _same_site(result['url'], ai_url))
            ):
                status = 'VERIFIED'
            elif result.get('ok') or result.get('status') is not None or 'Unreachable' in str(result.get('note', '')):
                status = 'NEEDS_REVIEW'
            else:
                status = 'FAILED'
                failed += 1
            final_url = result.get('url') or url
            note = ' '.join(x for x in (
                (ai.get('note') or '').strip(),
                ('Evidence: ' + ', '.join(str(u) for u in ai.get('evidence_urls', [])[:4]) if isinstance(ai.get('evidence_urls'), list) and ai.get('evidence_urls') else ''),
                (ai_check.get('note') or '').strip(),
                ('Verification evidence: ' + ', '.join(str(u) for u in ai_check.get('evidence_urls', [])[:4]) if isinstance(ai_check.get('evidence_urls'), list) and ai_check.get('evidence_urls') else ''),
                result.get('note', ''),
            ) if x)
            with connect() as c:
                c.execute(
                    """UPDATE college_website_resolver
                       SET city=CASE WHEN city IS NULL OR TRIM(city)='' THEN ? ELSE city END,
                           website=?,address=CASE WHEN address IS NULL OR TRIM(address)='' THEN ? ELSE address END,status=?,source=?,
                           source_url=?,verification_note=?,
                           last_checked_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE institution_code=?""",
                    (
                        found_city, final_url, address, status,
                        'gemini_google_search', final_url, note, code,
                    ),
                )
                _update_institute_resolution(
                    c, code, city=found_city, address=address,
                    website=final_url if status == 'VERIFIED' else None,
                    source='gemini_google_search',
                )
                c.commit()
            if status == 'VERIFIED':
                resolved += 1
        except Exception as exc:
            message = str(exc)
            if 'GEMINI_API_KEY is not configured' in message:
                # Search cannot run without Gemini, so leave the college queued
                # for a real AI attempt instead of marking it as a dead website.
                failed_note = 'Gemini AI verification/search is not configured on the server.'
                with connect() as c:
                    c.execute(
                        """UPDATE college_website_resolver
                           SET status='NEEDS_REVIEW',verification_note=?,
                               last_checked_at=CURRENT_TIMESTAMP,
                               updated_at=CURRENT_TIMESTAMP
                           WHERE institution_code=?""",
                        (failed_note, code),
                    )
                    c.commit()
                continue
            failed += 1
            with connect() as c:
                c.execute(
                    """UPDATE college_website_resolver
                       SET status='FAILED',verification_note=?,
                           last_checked_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE institution_code=?""",
                    (message[:500], code),
                )
                c.commit()

    with connect() as c:
        excluded = sorted({str(code).strip() for code in (exclude_codes or []) if str(code or '').strip()})
        remaining_sql = "SELECT COUNT(*) AS n FROM college_website_resolver"
        remaining_clauses = []
        remaining_params = []
        if status_filter:
            remaining_clauses.append("status = ?")
            remaining_params.append(str(status_filter))
        if excluded:
            remaining_clauses.append("institution_code NOT IN (" + ",".join("?" for _ in excluded) + ")")
            remaining_params.extend(excluded)
        if remaining_clauses:
            remaining_sql += " WHERE " + " AND ".join(remaining_clauses)
        remaining = c.execute(remaining_sql, remaining_params).fetchone()['n']
    return {
        'ok': True,
        'seeded': seeded,
        'resolved': resolved,
        'searched': searched,
        'failed': failed,
        'remaining': int(remaining),
    }


def _import_names_for_codes(conn, codes):
    """Recover real institution names from retained import staging records.

    Only query codes whose institute name is missing or is just the code. The
    staging payload is the original CAP-import evidence; never treat the code
    itself as a valid display name when a better source exists.
    """
    codes = sorted({str(code).strip() for code in codes if str(code or '').strip()})
    if not codes:
        return {}
    placeholders = ','.join('?' for _ in codes)
    try:
        rows = conn.execute(
            "SELECT COALESCE(normalized_json,raw_json) AS normalized_json FROM import_staging_records "
            "WHERE result_type IN ('CUTOFFS','SEATS') "
            f"AND (COALESCE(normalized_json,raw_json)::jsonb ->> 'institution_code') IN ({placeholders}) "
            "ORDER BY id DESC",
            tuple(codes),
        ).fetchall()
    except Exception:
        log.exception('Could not recover institution names from import staging')
        return {}
    found = {}
    for row in rows:
        try:
            data = json.loads(row.get('normalized_json') or '{}')
        except Exception:
            continue
        code = str(data.get('institution_code') or '').strip()
        name = str(data.get('institution_name') or '').strip()
        if code in codes and name and name != code and code not in found:
            found[code] = name
    return found


def sync_institutes_to_resolver(conn):
    """Synchronize resolver only from institutes still backed by production data.

    Older rollback flows could leave orphan institute rows behind. Those rows
    must never reappear in the resolver queue after the underlying production
    data has been deleted.
    """
    refs = _reference_contacts()
    # Resolver is a derived view of production-backed institutes. Never delete
    # rows from the authoritative institutes table while merely opening this page.
    # Use EXISTS instead of NOT IN so NULLs in imported data cannot empty the scope.
    conn.execute(
        "DELETE FROM college_website_resolver r "
        "WHERE r.institution_code LIKE 'GH:%' "
        "OR NOT EXISTS ("
        "SELECT 1 FROM cutoffs c WHERE c.institution_code=r.institution_code "
        "UNION ALL "
        "SELECT 1 FROM seats s WHERE s.institution_code=r.institution_code)"
    )
    # Production records are the ultimate source of scope. Do not require
    # the derived institutes table to already exist; older rollback/import flows
    # can leave cutoffs/seats intact while institutes needs reconstruction.
    rows = conn.execute(
        "SELECT institution_code,institution_name,city,website,address "
        "FROM institutes ORDER BY institution_code"
    ).fetchall()
    # Fallback to the exact production-backed institute scope used by the
    # public /api/options endpoint. This prevents the resolver from appearing
    # empty if the compound UNION scope behaves differently on a migrated DB.
    if not rows:
        rows = conn.execute(
            "SELECT i.institution_code, COALESCE(i.institution_name,'') AS institution_name, "
            "i.city, i.website, i.address FROM institutes i WHERE "
            "EXISTS (SELECT 1 FROM cutoffs c WHERE c.institution_code=i.institution_code) "
            "OR EXISTS (SELECT 1 FROM seats s WHERE s.institution_code=i.institution_code) "
            "ORDER BY i.institution_code"
        ).fetchall()
        log.warning('Resolver UNION scope returned 0; public-scope fallback returned %s rows', len(rows))
    else:
        log.info('Resolver scope returned %s production-backed rows', len(rows))
    count = 0
    known_cities = _known_city_names(conn)
    placeholder_codes = [
        str(r['institution_code']).strip() for r in rows
        if str(r['institution_code'] or '').strip()
        and (not str(r['institution_name'] or '').strip()
             or str(r['institution_name'] or '').strip() == str(r['institution_code']).strip())
        and not str(refs.get(str(r['institution_code']).strip(), {}).get('institution_name') or '').strip()
    ]
    staged_names = _import_names_for_codes(conn, placeholder_codes)
    for r in rows:
        code = str(r['institution_code']).strip()
        if not code:
            continue
        ref = refs.get(code, {})
        ref_name = str(ref.get('institution_name') or '').strip()
        db_name = str(r['institution_name'] or '').strip()
        # Imports can temporarily store only the CAP choice code as the name.
        # Prefer the maintained reference name when it is available.
        staged_name = staged_names.get(code, '')
        name = (ref_name if ref_name and (not db_name or db_name == code)
                else staged_name if (not db_name or db_name == code) and staged_name
                else db_name or ref_name or staged_name or code)
        # Repair a missing derived institute row from production-backed scope.
        conn.execute(
            "INSERT INTO institutes(institution_code,institution_name) VALUES(?,?) "
            "ON CONFLICT(institution_code) DO UPDATE SET "
            "institution_name=CASE WHEN institutes.institution_name IS NULL OR institutes.institution_name='' "
            "THEN excluded.institution_name ELSE institutes.institution_name END",
            (code, name),
        )
        city = r['city'] or ref.get('city')
        city_source = 'institutes' if r['city'] else ('reference_csv' if ref.get('city') else None)
        if not city:
            city = infer_city_from_name(name, known_cities)
            city_source = 'college_name_match' if city else None
        website = valid_url(r['website']) if r['website'] else ref.get('website')
        source = 'institutes' if r['website'] else ('reference_csv' if website else None)
        # Keep the public institute metadata aligned with the same maintained
        # reference source used by the resolver, without overwriting admin data.
        if (ref_name or (name and name != code) or city or website):
            conn.execute(
                "UPDATE institutes SET "
                "institution_name=CASE WHEN (institution_name IS NULL OR institution_name=?) AND ? IS NOT NULL THEN ? ELSE institution_name END,"
                "city=COALESCE(city,?),website=COALESCE(website,?),"
                "city_source=CASE WHEN city IS NULL AND ? IS NOT NULL THEN ? ELSE city_source END,"
                "website_source=CASE WHEN website IS NULL AND ? IS NOT NULL THEN 'reference_csv' ELSE website_source END,"
                "verified_at=CASE WHEN (? IS NOT NULL OR ? IS NOT NULL) THEN COALESCE(verified_at,CURRENT_TIMESTAMP) ELSE verified_at END "
                "WHERE institution_code=?",
                (code, (name if name != code else None), (name if name != code else None), city, website,
                 city, city_source, website, city, website, code),
            )
        existing = conn.execute(
            "SELECT status,website FROM college_website_resolver WHERE institution_code=?",
            (code,),
        ).fetchone()
        if existing and existing['status'] == 'VERIFIED':
            conn.execute(
                "UPDATE college_website_resolver SET institution_name=?,"
                "city=COALESCE(city,?),updated_at=CURRENT_TIMESTAMP "
                "WHERE institution_code=?",
                (name, city, code),
            )
        else:
            conn.execute(
                """INSERT INTO college_website_resolver
                   (institution_code,institution_name,city,website,status,source,source_url,city_source,website_source)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(institution_code) DO UPDATE SET
                     institution_name=excluded.institution_name,
                     city=COALESCE(college_website_resolver.city,excluded.city),
                     city_source=CASE WHEN college_website_resolver.city IS NULL THEN COALESCE(excluded.city_source,college_website_resolver.city_source) ELSE college_website_resolver.city_source END,
                     website=CASE
                       WHEN college_website_resolver.website IS NULL
                            OR college_website_resolver.website=''
                       THEN excluded.website
                       ELSE college_website_resolver.website
                     END,
                     status=CASE
                       WHEN college_website_resolver.website IS NOT NULL
                            AND college_website_resolver.website<>'' THEN college_website_resolver.status
                       ELSE excluded.status
                     END,
                     source=CASE
                       WHEN college_website_resolver.website IS NOT NULL
                            AND college_website_resolver.website<>'' THEN college_website_resolver.source
                       ELSE excluded.source
                     END,
                     source_url=CASE
                       WHEN college_website_resolver.website IS NOT NULL
                            AND college_website_resolver.website<>'' THEN college_website_resolver.source_url
                       ELSE excluded.source_url
                     END,
                     updated_at=CURRENT_TIMESTAMP""",
                (
                    code, name, city, website,
                    'CANDIDATE' if website else 'PENDING',
                    source, website, city_source, source,
                ),
            )
        count += 1
    return count


GITHUB_MAPPING_URL='https://raw.githubusercontent.com/github/india/main/Students/GCP-India.md'

def sync_github_india(conn):
    req=urllib.request.Request(GITHUB_MAPPING_URL,headers={'User-Agent':'CET-CAP-Website-Resolver/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r: text=r.read().decode('utf-8','ignore')
    n=0
    import hashlib
    for line in text.splitlines():
        if not line.startswith('|') or 'University Name' in line or '---' in line: continue
        cells=[x.strip() for x in line.strip().strip('|').split('|')]
        if len(cells)<3: continue
        name,url=cells[0],valid_url(cells[1])
        if not name or not url: continue
        code='GH:'+hashlib.sha1(name.strip().lower().encode()).hexdigest()[:16]
        conn.execute("INSERT INTO college_website_resolver(institution_code,institution_name,website,status,source,source_url) VALUES (?,?,?,?,?,?) ON CONFLICT(institution_code) DO UPDATE SET website=excluded.website,source=excluded.source,source_url=excluded.source_url",(code,name,url,'CANDIDATE','github_india_2021',GITHUB_MAPPING_URL)); n+=1
    return n

def gemini_find(college_name,city=None,excluded_url=None,institution_code=None):
    key=os.getenv('GEMINI_API_KEY','').strip()
    if not key:raise RuntimeError('GEMINI_API_KEY is not configured')
    location=f', {city}' if city else ''
    exclusion=f' Do NOT return this previously rejected website: {excluded_url}.' if excluded_url else ''
    code_hint=f' CAP/college code: {institution_code}.' if institution_code else ''
    prompt=f'''Find the official website and physical campus location of this Maharashtra CAP college/institution.
College name: {college_name}{location}
{code_hint}
Use Google Search. Search using the exact college name and CAP code. First search official Maharashtra State CET Cell and DTE institute records for that code; open the institute summary/profile where possible. Then compare the college's own contact/about page and another independent official source. Prefer the college's own domain and official CET Cell, AICTE, UGC, or affiliating-university pages. The official URL must be the college's own website, not a directory, social profile, ranking site, admissions portal, or aggregator. Find the city from the campus/contact address or official institute profile; return the actual city/town/locality and never a district, division, region, or state. Do not infer a city from the college name alone. Return ONLY one valid JSON object with keys official_url, city, address, confidence, evidence_urls, note. evidence_urls must contain actual source page URLs that support each non-null field. If the evidence does not establish a field, set that field to null and confidence low.{exclusion}'''
    payload={'contents':[{'parts':[{'text':prompt}]}],'tools':[{'google_search':{}}]}
    req=urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(GEMINI_MODEL,safe="")}:generateContent',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=45) as r:data=json.load(r)
    except urllib.error.HTTPError as e:raise RuntimeError(f'Gemini request failed ({e.code})')
    text=''.join(part.get('text','') for c in data.get('candidates',[]) for part in c.get('content',{}).get('parts',[]))
    result = _json_object_from_text(text)
    evidence, queries = _grounding_evidence(data)
    result['grounding_evidence'] = evidence
    result['grounding_queries'] = queries
    # Never present URLs typed by the model as citations. Keep those separately
    # for diagnostics and expose only citations returned by Google as evidence.
    result['model_evidence_urls'] = result.get('evidence_urls')
    result['evidence_urls'] = [item['url'] for item in evidence]
    # The model may return a plausible city without citing it. Only persist a
    # city when Google's grounding metadata links a response segment containing
    # that city to a search result.
    if result.get('city') and not _grounding_supports_value(result['city'], evidence):
        result['city'] = None
    return result,data
