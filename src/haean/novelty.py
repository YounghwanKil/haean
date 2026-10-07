"""Local generation memory and repeat-candidate triage, not an originality score."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from .models import Draft


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
