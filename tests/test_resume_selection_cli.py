"""CLI routing keeps slot selection explicit and opt-in; no model calls."""
import pytest

from haean import cli, exam_resume


@pytest.mark.parametrize('selection', [None, [2, 22]])
@pytest.mark.parametrize('compact', [False, True])
def test_cli_resume_selection_reaches_backend(tmp_path, monkeypatch, capsys, selection, compact):
    calls = []
    monkeypatch.setattr(exam_resume, 'resume', lambda *args, **kwargs: calls.append(kwargs) or {})
    args = ['haean-tool', 'exam-resume', str(tmp_path / 'parent'), '--out', str(tmp_path / 'new')]
    if selection is not None:
        args += ['--slots', *map(str, selection)]
    if compact:
        args += ['--compact-reference-audit']
    monkeypatch.setattr('sys.argv', args)
    cli.main()
    capsys.readouterr()
    expected = {} if selection is None else {'slots': selection}
    if compact:
        expected['compact_reference_audit'] = True
    assert calls == [expected]


@pytest.mark.parametrize('selection', [[], ['two'], ['2.0']])
def test_cli_bad_selection_stops_before_backend(tmp_path, monkeypatch, selection):
    monkeypatch.setattr(exam_resume, 'resume', lambda *a, **k: pytest.fail('backend must not run'))
    monkeypatch.setattr('sys.argv', ['haean-tool', 'exam-resume', str(tmp_path / 'parent'),
                                   '--out', str(tmp_path / 'new'), '--slots', *selection])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert not (tmp_path / 'new').exists()
