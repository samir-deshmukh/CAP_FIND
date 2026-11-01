"""Part 4: build, atomically publish, and verify public runtime artifacts."""
from __future__ import annotations
import json, logging, os, re, shutil, subprocess, sys, time
from pathlib import Path
from .db import connect, event, update_status
from .state import JobStatus

log = logging.getLogger("cet-cap-publishing")

BASE = Path(__file__).resolve().parents[2]
SITE = BASE / 'site'
PUBLISH_ROOT = BASE / 'data' / 'publish_work'
BACKUP_ROOT = BASE / 'data' / 'publish_backups'


def _run(cmd: list[str], cwd: Path = BASE, timeout: int = 1800):
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    out = (p.stdout or '') + (p.stderr or '')
    if p.returncode != 0:
        raise RuntimeError(out[-12000:] or f'Command failed: {cmd}')
    return out


def _copy_site_skeleton(dst: Path):
    if dst.exists(): shutil.rmtree(dst)
    # The candidate site is now API-backed. Do not copy or create any runtime
    # cutoff/seat data directory in the public tree.
    shutil.copytree(SITE, dst, ignore=shutil.ignore_patterns('data', '404.html', 'robots.txt', 'sitemap.xml'))


def build_runtime(release_id: int) -> tuple[Path, dict]:
    build_dir = PUBLISH_ROOT / f'release_{release_id}_{int(time.time())}'
    public_dir = build_dir / 'site'
    build_dir.mkdir(parents=True, exist_ok=True)
    _copy_site_skeleton(public_dir)
    import os
    db_url = os.getenv('DATABASE_URL', '').strip()
    if not db_url:
        raise RuntimeError('DATABASE_URL is required to build a release; PostgreSQL is the sole source of truth.')
    # No cutoff, trend, search-index, or seat-matrix payload is exported to
    # the public tree. The browser retrieves bounded data through /api/*.
    manifest = {'release_id': release_id, 'built_at': time.time(), 'files': []}
    for p in sorted(public_dir.rglob('*')):
        if p.is_file(): manifest['files'].append({'path': str(p.relative_to(public_dir)), 'bytes': p.stat().st_size})
    (build_dir / 'publish_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return public_dir, manifest


def verify_public_tree(public_dir: Path) -> dict:
    errors = []
    data = public_dir / 'data'
    # The API-backed public tree intentionally contains no runtime data directory.
    # Validate any JSON artifact if a future public asset adds one.
    # Validate every JSON artifact and reject accidental DB/secret material in public output.
    for p in data.rglob('*.json'):
        try: json.loads(p.read_text(encoding='utf-8'))
        except Exception as e: errors.append(f'invalid JSON {p.relative_to(public_dir)}: {e}')
    forbidden = [p for p in public_dir.rglob('*') if p.is_file() and p.suffix.lower() in {'.db','.sqlite','.sqlite3','.pem','.key'}]
    if forbidden: errors.append('private database/key material found in public tree')
    for p in public_dir.rglob('*'):
        if p.is_file() and p.stat().st_size > 0 and p.suffix.lower() in {'.html','.js','.json'}:
            text = p.read_text(encoding='utf-8', errors='ignore')
            if re.search(r'(?i)BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY', text):
                errors.append(f'possible secret pattern in {p.relative_to(public_dir)}')
    return {'ok': not errors, 'errors': errors, 'file_count': sum(1 for p in public_dir.rglob('*') if p.is_file())}


def atomic_publish(public_dir: Path, release_id: int):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    backup = BACKUP_ROOT / f'release_{release_id}_{int(time.time())}'
    # Keep a recoverable copy of the currently published site before replacement.
    shutil.copytree(SITE, backup)
    temp_live = BASE / f'.site_publish_{release_id}_{os.getpid()}'
    if temp_live.exists(): shutil.rmtree(temp_live)
    shutil.copytree(public_dir, temp_live)
    old = BASE / f'.site_previous_{release_id}_{os.getpid()}'
    if old.exists(): shutil.rmtree(old)
    os.replace(SITE, old)
    try:
        os.replace(temp_live, SITE)
    except Exception:
        os.replace(old, SITE)
        raise
    shutil.rmtree(old, ignore_errors=True)
    return backup


def publish_release(job_id: int, release_id: int):
    # Claim publication in a short transaction. The conditional update makes
    # duplicate clicks/retries mutually exclusive before any filesystem work.
    with connect() as conn:
        job = conn.execute('SELECT * FROM import_jobs WHERE id=?', (job_id,)).fetchone()
        rel = conn.execute('SELECT * FROM data_releases WHERE id=?', (release_id,)).fetchone()
        if not job or not rel:
            raise ValueError('Release/import not found')
        if rel['source_job_id'] != job_id:
            raise ValueError('Release does not belong to import')
        if job['status'] != JobStatus.COMMITTING.value:
            raise ValueError(f'Import is not ready to publish: {job["status"]}')
        claimed = conn.execute(
            'UPDATE import_jobs SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND status=?',
            (JobStatus.PUBLISHING.value, job_id, JobStatus.COMMITTING.value),
        ).rowcount
        if claimed != 1:
            raise ValueError('This release is already being published or is no longer ready')
        event(conn, job_id, 'EXPORT', 'Building production public runtime artifacts', 15)
        conn.commit()
        release_key = rel['release_key']
        created_by = job['created_by']

    # Never hold a PostgreSQL connection while copying, scanning or atomically
    # replacing the public site. These filesystem operations can take seconds.
    try:
        public_dir, manifest = build_runtime(release_id)
        check = verify_public_tree(public_dir)
        if not check['ok']:
            raise RuntimeError('Public artifact verification failed: ' + '; '.join(check['errors']))
        with connect() as conn:
            event(conn, job_id, 'EXPORT', f'Generated {check["file_count"]} public files', 65)
            conn.commit()

        backup = atomic_publish(public_dir, release_id)
        final_check = verify_public_tree(SITE)
        if not final_check['ok']:
            raise RuntimeError('Post-publish verification failed: ' + '; '.join(final_check['errors']))

        with connect() as conn:
            event(conn, job_id, 'PUBLISH', f'Published release {release_key}', 85)
            conn.execute(
                "UPDATE data_releases SET status='PUBLISHED', published_at=CURRENT_TIMESTAMP, manifest_json=?, backup_path=?, verified_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(manifest, ensure_ascii=False), str(backup.relative_to(BASE)), release_id),
            )
            update_status(conn, job_id, JobStatus.VERIFYING.value, 'Public files verified after atomic publish')
            event(conn, job_id, 'VERIFY', 'Published public tree passed structural verification', 100)
            update_status(conn, job_id, JobStatus.COMPLETED.value, 'Import, release, export, publish and verification completed')
            event(conn, job_id, 'COMPLETED', 'Release is live in the project public tree', 100)
            conn.execute(
                "INSERT INTO audit_log(actor_user_id,action,entity_type,entity_id,after_json,reason) VALUES (?,?,?,?,?,?)",
                (created_by, 'PUBLISH_RELEASE', 'RELEASE', str(release_id),
                 json.dumps({'release_key': release_key, 'files': final_check['file_count']}),
                 'Part 4 publish'),
            )
            conn.commit()
        return {
            'ok': True, 'release_id': release_id, 'status': 'COMPLETED',
            'files': final_check['file_count'], 'backup': str(backup.relative_to(BASE)),
        }
    except Exception as exc:
        # Record a failure only if this invocation still owns the publication
        # state. Do not overwrite a release that has already completed.
        try:
            with connect() as conn:
                changed = conn.execute(
                    "UPDATE import_jobs SET status=?,error_message=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status IN (?,?)",
                    (JobStatus.FAILED.value, str(exc), job_id,
                     JobStatus.PUBLISHING.value, JobStatus.VERIFYING.value),
                ).rowcount
                if changed:
                    event(conn, job_id, 'ERROR', str(exc), None)
                    conn.commit()
        except Exception:
            log.exception('Failed to persist release publication failure: release_id=%s', release_id)
        raise
