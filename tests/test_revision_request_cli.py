"""Public CLI preserves review text/origin and explicit request routing."""
from pathlib import Path

import pytest

from haean import cli, exam_resume


@pytest.mark.parametrize('from_file', [False, True])
def test_request_text_and_identity(tmp_path, monkeypatch, capsys, from_file):
    from haean import revision_request
    calls = []
    monkeypatch.setattr(revision_request, 'create_request',
                        lambda *a, **kw: calls.append((a, kw)) or {})
    opinion = '두 오답의 판단 역할을 나눠 주세요.\n이미 검토한 조건은 유지합니다.\n'
    source = tmp_path / 'opinion.txt'
    source.write_text(opinion, encoding='utf-8')
    parent, out = tmp_path / 'parent', tmp_path / 'request.json'
    argv = ['haean-tool', 'exam-revision-request', str(parent), '--out', str(out),
            '--slots', '2', '22', '--origin', 'model', '--reviewer', '편집 검토', '--severity', 'C']
    argv += ['--file', str(source)] if from_file else ['--text', opinion]
    monkeypatch.setattr('sys.argv', argv)
    cli.main()
    capsys.readouterr()
    assert calls == [((parent, out), dict(slots=[2, 22], text=opinion,
                                        origin='model', reviewer='편집 검토', severity='C'))]


def test_resume_multiple_requests(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(exam_resume, 'resume', lambda *a, **kw: calls.append(kw) or {})
    monkeypatch.setattr('sys.argv', ['haean-tool', 'exam-resume', str(tmp_path / 'parent'),
        '--out', str(tmp_path / 'new'), '--slots', '2', '22', '4', '24',
        '--revision-request', 'first.json', '--revision-request', 'second.json'])
    cli.main()
    capsys.readouterr()
    assert calls == [dict(slots=[2, 22, 4, 24], revision_requests=[Path('first.json'), Path('second.json')])]


@pytest.mark.parametrize('extra', [[], ['--text', 'a', '--file', 'b'],
                                  ['--text', 'a', '--origin', 'expert']])
def test_invalid_opinion_arguments_before_backend(tmp_path, monkeypatch, extra):
    from haean import revision_request
    monkeypatch.setattr(revision_request, 'create_request', lambda *a, **k: pytest.fail('unexpected write'))
    monkeypatch.setattr('sys.argv', ['haean-tool', 'exam-revision-request', str(tmp_path / 'parent'),
        '--out', str(tmp_path / 'request.json'), '--slots', '2', '22',
        '--reviewer', 'editor', '--origin', 'model', *extra])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert not (tmp_path / 'request.json').exists()
