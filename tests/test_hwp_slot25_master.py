"""25-slot derived masters, ordered box content (E), merged table cells (G spans) and summary neutralization (U).

Synthetic Java checks always run when the JDK and hwplib are installed. The master round trip runs only when the
supplied blank LEET masters are available locally (HAEAN_LEET_QUESTION_MASTER / HAEAN_LEET_SOLUTION_MASTER);
they are private materials and are never committed.
"""
import base64
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JAR = ROOT / 'data/bin/hwplib-1.1.11.jar'
JDK = Path('/opt/homebrew/opt/openjdk/bin')
JAVAC = str(JDK / 'javac') if (JDK / 'javac').exists() else shutil.which('javac')
JAVA = str(JDK / 'java') if (JDK / 'java').exists() else shutil.which('java')
DOWNLOADS = Path.home() / 'Downloads'
QUESTIONS = Path(os.environ.get('HAEAN_LEET_QUESTION_MASTER', DOWNLOADS / '시대LEET_추리논증_40문항(20p)양식_260804_0000_v3.hwp'))
SOLUTIONS = Path(os.environ.get('HAEAN_LEET_SOLUTION_MASTER', DOWNLOADS / '시대LEET_추리논증_40문항해설지양식_250928_2226_v3 (3).hwp'))


def compiled(tmp_path):
    if not JAR.exists() or not JAVAC or not JAVA:
        pytest.skip('Run ./haean setup-layout to test native Java formatting')
    subprocess.run([JAVAC, '-encoding', 'UTF-8', '-cp', str(JAR), '-d', str(tmp_path),
                    *map(str, sorted((ROOT / 'tools/layout-java').glob('*.java')))], check=True, capture_output=True, text=True)
    return os.pathsep.join([str(JAR), str(tmp_path)])


def test_placeholder_replaced_by_appended_content_and_null_summary(tmp_path):
    cp = compiled(tmp_path)
    (tmp_path / 'AppendTest.java').write_text('''
import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.control.table.Cell;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
public class AppendTest {
 public static void main(String[] a) throws Exception {
  HWPFile f=new HWPFile();f.getDocInfo().addNewCharShape();f.getDocInfo().addNewParaShape();
  var s=f.getDocInfo().addNewStyle();s.setHangulName("x");s.setCharShapeId(0);s.setParaShapeId(0);
  Cell cell=new Cell();
  Paragraph blank=cell.getParagraphList().addNewParagraph();HaeanText.text(f,blank,0,0,"",false);HaeanFill.placeholders.add(blank);
  Paragraph p=new Paragraph();HaeanText.text(f,p,0,0,"table or figure",false);HaeanFill.append(cell,p);
  if(cell.getParagraphList().getParagraphCount()!=1)throw new AssertionError("placeholder kept");
  Paragraph q=new Paragraph();HaeanText.text(f,q,0,0,"after",false);HaeanFill.append(cell,q);
  if(cell.getParagraphList().getParagraphCount()!=2||cell.getListHeader().getParaCount()!=2)throw new AssertionError("order");
  if(cell.getParagraphList().getParagraph(0).getHeader().isLastInList()||!q.getHeader().isLastInList())throw new AssertionError("last flag");
  HaeanMeta.neutral(f,"t");  // no summary stream: no-op
 }
}
''')
    subprocess.run([JAVAC, '-encoding', 'UTF-8', '-cp', cp, '-d', str(tmp_path), str(tmp_path / 'AppendTest.java')], check=True, capture_output=True, text=True)
    subprocess.run([JAVA, '-cp', cp, 'AppendTest'], check=True, capture_output=True, text=True)


def enc(t):
    return base64.b64encode(t.encode()).decode()


@pytest.mark.skipif(not (QUESTIONS.exists() and SOLUTIONS.exists()), reason='private blank LEET masters not available')
def test_derived_25_slot_masters_round_trip(tmp_path):
    cp = compiled(tmp_path / 'classes')
    run = lambda cls, *args: subprocess.run([JAVA, '-cp', cp, cls, *map(str, args)], check=True, capture_output=True, text=True)
    q_spec, s_spec = tmp_path / 'q.tsv', tmp_path / 's.tsv'
    q_spec.write_text('\n'.join(['R\t' + enc('40문항') + '\t' + enc('25문항'), 'C\t25', 'U\t' + enc('derived')]) + '\n')
    s_spec.write_text('\n'.join(['C\t25', 'U\t' + enc('derived')] + [f'A\t{n}\t1\t{enc("")}' for n in range(1, 26)]) + '\n')
    for name, cls, src, spec in (('q', 'HaeanFill', QUESTIONS, q_spec), ('s', 'HaeanSolutions', SOLUTIONS, s_spec)):
        run(cls, src, spec, tmp_path / f'{name}25.hwp')
        run(cls, src, spec, tmp_path / f'{name}25b.hwp')
        assert (tmp_path / f'{name}25.hwp').read_bytes() == (tmp_path / f'{name}25b.hwp').read_bytes()  # fixed summary dates
    # A derived master is accepted as a 25-slot master; trimming it again is refused.
    fill = tmp_path / 'fill.tsv'
    fill.write_text('\n'.join([
        'S\t1\t0\t' + enc('발문'), 'P\t1\t0\t' + enc(''),
        'G\t1\t0\t' + enc('\x1f'.join(['구분', '소득', '1분위', '5분위', '갑', '4', '48'])) + '\t3\t2,1;1,2;1,1;1,1;1,1;1,1;1,1',
        'E\t1\t0\t' + enc('표 뒤 글') + '\tpassage', 'B\t1\t0\t' + enc('')]) + '\n')
    run('HaeanFill', tmp_path / 'q25.hwp', fill, tmp_path / 'filled.hwp')
    retrim = tmp_path / 'retrim.tsv'
    retrim.write_text('C\t25\n')
    with pytest.raises(subprocess.CalledProcessError):
        run('HaeanFill', tmp_path / 'q25.hwp', retrim, tmp_path / 'bad.hwp')
    answers = tmp_path / 'answers.tsv'
    answers.write_text('\n'.join(f'A\t{n}\t1\t{enc("①②③④⑤"[n % 5])}' for n in range(1, 26)) + '\n')
    run('HaeanSolutions', tmp_path / 's25.hwp', answers, tmp_path / 'answers.hwp')  # Java re-reads both grids and 25 boxes
