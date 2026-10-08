"""Read-only, bounded evidence lookup for mutable historical source paths."""
import hashlib
import json
from pathlib import Path


def canonical(value):
    """Full JSON identity: no model defaults, coercion, or text normalization."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f'duplicate JSON key: {key}')
        value[key] = item
    return value


def _invalid_constant(value):
    raise ValueError(f'non-finite JSON number: {value}')


def _inspect(path, item):
    result = {'path': str(path), 'matches': []}
    try:
        raw = path.read_bytes()
        result['raw_sha256'] = hashlib.sha256(raw).hexdigest()
        data = json.loads(raw, object_pairs_hook=_object,
                          parse_constant=_invalid_constant)
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise ValueError('expected an object with an items array')
        expected = canonical(item)
        for index, actual in enumerate(data['items']):
            if (isinstance(actual, dict) and 'id' in actual
                    and type(actual['id']) is type(item['id'])
                    and actual['id'] == item['id'] and canonical(actual) == expected):
                result['matches'].append({'path': str(path),
                    'raw_sha256': result['raw_sha256'], 'locator': f'$.items[{index}]'})
        result['status'] = 'match' if result['matches'] else 'mismatch'
    except FileNotFoundError as exc:
        result.update(status='missing', error=str(exc))
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        result.update(status='error', error=f'{type(exc).__name__}: {exc}')
    return result


def resolve_source(source, item):
    """Preserve recorded origin; disclose matches and every bounded probe failure.

    Only absolute candidate.json origins enable archive lookup. Symlink entries
    are reported but never followed during archive lookup. The recorded origin
    itself remains an explicit caller-supplied source, not a discovered path.
    """
    path = Path(source)
    result = {'version': 1, 'origin_path': source,
              'payload_canonical_sha256': hashlib.sha256(canonical(item).encode()).hexdigest(),
              'identity_method': 'actual item id and full canonical JSON; type-sensitive; no schema defaults',
              'archive_scope': str(path.parent / 'revision-*' / 'candidate.json'),
              'archive_checks': [], 'matches': [], 'archive_scan_complete': False}
    if not path.is_absolute():
        result.update(status='unresolved', origin_check={'path': source,
                      'status': 'unsupported', 'error': 'relative source has no recorded base directory'})
        return result
    origin = _inspect(path, item)
    result['origin_check'] = origin
    result['matches'] = list(origin['matches'])
    if result['matches']:
        result['status'] = 'verified_origin' if len(result['matches']) == 1 else 'ambiguous'
        return result
    if path.name != 'candidate.json':
        result.update(status='unresolved', archive_scan_error='archive lookup requires candidate.json origin')
        return result
    try:
        # Exactly one directory level; never recurse or consult evals/catalogs.
        children = sorted(path.parent.iterdir(), key=lambda p: p.name)
        for child in children:
            if not child.name.startswith('revision-'):
                continue
            candidate = child / 'candidate.json'
            if child.is_symlink() or candidate.is_symlink():
                check = {'path': str(candidate), 'status': 'error', 'matches': [],
                         'error': 'symlink archive entry not followed'}
            elif not child.is_dir():
                continue
            else:
                check = _inspect(candidate, item)
            result['archive_checks'].append(check)
            result['matches'].extend(check['matches'])
        result['archive_scan_complete'] = not any(
            check['status'] in ('error', 'missing') for check in result['archive_checks'])
    except OSError as exc:
        result['archive_scan_error'] = f'{type(exc).__name__}: {exc}'
    count = len(result['matches'])
    if count > 1:
        result['status'] = 'ambiguous'
    elif not result['archive_scan_complete']:
        result['status'] = 'incomplete'
    else:
        result['status'] = 'resolved_archive' if count else 'unresolved'
    return result
