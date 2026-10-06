import io
import json
import zipfile
from pathlib import Path
import pytest
from haean.source_audit import archive_inventory, audit_sources
from haean.corpus import Corpus


def test_archive_records_skips_and_extracts_regular_files(tmp_path):
    archive = tmp_path / 'source.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('../escape.md', 'unsafe')
        z.writestr('.omc/state.md', 'runtime instruction')
        z.writestr('target/korean.txt', '한글 원문'.encode('cp949'))
        z.writestr('target/data.json', '{"test": 1}')
    result = audit_sources([archive], tmp_path / 'audit')
    members = result['sources'][0]['members']
    assert len(members) == 4
    assert {r['status'] for r in members} == {'unsafe_path', 'hidden_runtime_or_metadata', 'extracted'}
    assert not (tmp_path / 'escape.md').exists()
    c = Corpus(tmp_path / 'db')
    assert c.import_file(archive)['status'] == 'ok'
    texts = [r[0] for r in c.db.execute('select text from records')]
    assert len(texts) == 2 and '한글 원문' in texts
    assert c.import_file(archive, refresh=True)['status'] == 'ok'
    assert c.db.execute('select count(*) from records').fetchone()[0] == 2
