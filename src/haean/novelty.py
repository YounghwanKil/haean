"""Local generation memory and repeat-candidate triage, not an originality score."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from .models import Draft
from .source_resolution import resolve_source


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def records(paths):
    """Explicit production/run inputs only: never crawl held-out evals or experiments."""
    seen = {}
    for raw in paths:
        path = Path(raw).resolve()
        assembled = path / 'assembled.json'
        if assembled.exists():
            children = json.loads(assembled.read_text())['item_runs']
            for row in records(children):
                key = (row['exam'], row['subject'], row['item']['id'])
                if key in seen and seen[key]['sha256'] != row['sha256']:
                    raise ValueError(f'Conflicting versions in one import: {key}')
                seen[key] = row
        else:
            candidate = path / 'candidate.json'
            draft = Draft.model_validate_json(candidate.read_text())
            brief = json.loads((path / 'brief.json').read_text())
            for item in draft.items:
                data = item.model_dump()
                row = {'exam': brief['exam'], 'subject': brief['subject'], 'item': data,
                       'sha256': digest(data), 'source': str(candidate)}
                key = (row['exam'], row['subject'], item.id)
                if key in seen and seen[key]['sha256'] != row['sha256']:
                    raise ValueError(f'Conflicting versions in one import: {key}')
                seen[key] = row
    return list(seen.values())


def connect(path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS versions (exam TEXT, subject TEXT, item_id TEXT, sha TEXT, payload TEXT, source TEXT, recorded TEXT, PRIMARY KEY(exam,subject,item_id,sha))')
    db.execute('CREATE TABLE IF NOT EXISTS current (exam TEXT, subject TEXT, item_id TEXT, sha TEXT, PRIMARY KEY(exam,subject,item_id))')
    return db


def remember(path, rows):
    with connect(path) as db:
        for row in rows:
            identity = (row['exam'], row['subject'], row['item']['id'])
            db.execute('INSERT OR IGNORE INTO versions VALUES (?,?,?,?,?,?,?)', (*identity, row['sha256'], json.dumps(row['item'], ensure_ascii=False), row['source'], datetime.now(timezone.utc).isoformat()))
            db.execute('INSERT OR REPLACE INTO current VALUES (?,?,?,?)', (*identity, row['sha256']))
        count = db.execute('SELECT COUNT(*) FROM current').fetchone()[0]
        versions = db.execute('SELECT COUNT(*) FROM versions').fetchone()[0]
    return {'current_items': count, 'versions': versions, 'indexed_inputs': len(rows), 'originality_verified': False}


def history(path):
    if not Path(path).exists():
        return []
    with connect(path) as db:
        return [{'exam': e, 'subject': s, 'item': json.loads(p), 'sha256': h, 'source': f}
                for e, s, p, h, f in db.execute('SELECT exam,subject,payload,sha,source FROM versions ORDER BY recorded,sha')]


def memory_index(path, exam, subject, offset=0, limit=40):
    """Verbatim planning index; it is neither a full read nor semantic retrieval."""
    if offset < 0 or not 1 <= limit <= 200:
        raise ValueError('offset must be nonnegative and limit must be 1..200')
    path = Path(path)
    rows = []
    if path.exists():
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
            rows = db.execute('''SELECT v.payload,v.sha,v.source FROM current c
                JOIN versions v ON c.exam=v.exam AND c.subject=v.subject
                  AND c.item_id=v.item_id AND c.sha=v.sha
                WHERE c.exam=? AND c.subject=? ORDER BY c.item_id''', (exam, subject)).fetchall()
    entries = []
    for payload, sha, source in rows[offset:offset+limit]:
        item = json.loads(payload)
        entries.append({'id': item['id'], 'sha256': sha, 'source': source,
                        'source_resolution': {'origin_path': source, 'status': 'not_checked'},
                        **{key: item.get(key) for key in
                           ('item_type', 'topic', 'cognitive_task', 'essential_conditions')}})
    return {'exam': exam, 'subject': subject, 'total_items': len(rows),
            'offset': offset, 'limit': limit, 'items': entries,
            'next_offset': offset+limit if offset+limit < len(rows) else None,
            'catalog_missing_or_empty': not rows,
            'full_items_read': False,
            'limitations': ['Index fields may contain author errors. Retrieve the original item before using it as evidence.',
                            'Follow next_offset to inspect later items; this page is not the whole catalog.']}


def memory_get(path, exam, subject, item_ids, all_versions=False):
    """Retrieve explicit identities, preserving their recorded payload and hash."""
    wanted = set(item_ids)
    if not wanted:
        raise ValueError('At least one item ID is required')
    path = Path(path)
    matches = []
    if path.exists():
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
            placeholders = ','.join('?' for _ in wanted)
            records = db.execute(f'''SELECT payload,sha,source FROM versions
                WHERE exam=? AND subject=? AND item_id IN ({placeholders})
                ORDER BY item_id,recorded,sha''', (exam, subject, *sorted(wanted)))
            matches = [{'exam': exam, 'subject': subject, 'item': json.loads(payload),
                        'sha256': sha, 'source': source} for payload, sha, source in records]
    if not all_versions:
        current = set()
        path = Path(path)
        if path.exists():
            with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
                current = set(db.execute('SELECT item_id,sha FROM current WHERE exam=? AND subject=?', (exam, subject)))
        matches = [row for row in matches if (row['item']['id'], row['sha256']) in current]
    missing = wanted - {row['item']['id'] for row in matches}
    if missing:
        raise ValueError('Items not found in requested exam/subject: ' + ', '.join(sorted(missing)))
    for row in matches:
        row['source_resolution'] = resolve_source(row['source'], row['item'])
    return {'exam': exam, 'subject': subject, 'all_versions': all_versions,
            'items': matches, 'originality_verified': False}


def normalized(text):
    text = unicodedata.normalize('NFC', text).lower()
    text = re.sub(r'</?u>', '', text)
    text = re.sub(r'\d+(?:[.,]\d+)*', '#', text)
    text = re.sub(r'\b[a-z]\b', '@', text)
    return re.sub(r'\s+', '', text)


def shingles(text):
    text = normalized(text)
    return {text[i:i+5] for i in range(len(text)-4)} if len(text) >= 20 else set()


def features(item):
    return {
        'passage': shingles(item['passage']),
        'reasoning': shingles(' '.join([item['cognitive_task'], *item['essential_conditions'], item['explanation']])),
        'options': shingles(' '.join(o['text'] for o in item['options'])),
        'data': shingles(json.dumps({'tables': item['tables'], 'figures': item.get('figures', [])}, ensure_ascii=False)),
    }


def audit(candidates, previous, limit=5):
    # Compare within subject across PSAT levels too. History versions of the same
    # stable ID are one lineage, not newly authored questions.
    cache = [(row, features(row['item'])) for row in previous]
    outputs = []
    for row in candidates:
        item = row['item']; current = features(item); hits = []
        for other, old in cache:
            if row['subject'] != other['subject']:
                continue
            if (row['exam'], item['id']) == (other['exam'], other['item']['id']):
                continue
            paired = bool(item.get('shared_passage_id')) and row['exam'] == other['exam'] and item['shared_passage_id'] == other['item'].get('shared_passage_id') and item['passage'] == other['item']['passage']
            scores = {key: round(2*len(value & old[key])/(len(value)+len(old[key])), 4) if value and old[key] else 0.0 for key, value in current.items()}
            if paired:
                scores['passage'] = 0.0; scores['data'] = 0.0
            # Common option labels or table schemas alone are insufficient.
            flagged = scores['passage'] >= .55 or scores['reasoning'] >= .55 or (scores['options'] >= .65 and scores['reasoning'] >= .30)
            rank = max(scores['passage'], scores['reasoning'], .6*scores['options']+.4*scores['reasoning'])
            hits.append({'previous_id': other['item']['id'], 'previous_exam': other['exam'], 'previous_sha256': other['sha256'], 'previous_source': other['source'], 'previous_item': other['item'], 'scores': scores, 'rank': round(rank,4), 'review_candidate': flagged, 'shared_passage_pair': paired})
        hits.sort(key=lambda x: (-x['rank'], x['previous_id']))
        # Keep one version per lineage, preferring a flagged version if present.
        # A higher weighted rank can otherwise hide an older threshold match.
        unique = {}
        for hit in hits:
            identity = (hit['previous_exam'], hit['previous_id'])
            current_hit = unique.get(identity)
            if current_hit is None or (hit['review_candidate'] and not current_hit['review_candidate']):
                unique[identity] = hit
        hits = sorted(unique.values(), key=lambda x: (-x['rank'], x['previous_id']))
        # The display limit must not hide a threshold-triggered review candidate.
        neighbors = [hit for index, hit in enumerate(hits)
                     if index < limit or hit['review_candidate']]
        outputs.append({'item_id': item['id'], 'exam': row['exam'], 'subject': row['subject'], 'candidate_sha256': row['sha256'], 'source': row['source'], 'neighbors': neighbors, 'flagged_neighbor_count': sum(x['review_candidate'] for x in hits)})
    return {'version': 1, 'candidate_count': len(candidates), 'history_versions': len(previous), 'history_items': len({(x['exam'], x['subject'], x['item']['id']) for x in previous}), 'items': outputs, 'originality_verified': False, 'method': 'numeric/letter-normalized character shingles over passage, reasoning and options; candidate retrieval only', 'limitations': ['Semantic paraphrases and renamed logic structures can evade this check.', 'Same question type is not itself duplication. A reviewer must compare premises, decisive inference and distractor roles.', 'Stable item IDs identify revisions; genuinely new questions require new IDs.', 'This is a snapshot audit, not evidence from 100 sequential generations.']}
