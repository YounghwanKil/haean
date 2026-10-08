"""Exercise template styles and text preservation in actual Java paragraphs."""
from pathlib import Path
import os
import shutil
import subprocess
import pytest


def test_editorial_paragraph_styles_preserve_text(tmp_path):
    root = Path(__file__).resolve().parents[1]
    jar = root / 'data/bin/hwplib-1.1.11.jar'
    jdk = Path('/opt/homebrew/opt/openjdk/bin')
    javac = str(jdk / 'javac') if (jdk / 'javac').exists() else shutil.which('javac')
    java = str(jdk / 'java') if (jdk / 'java').exists() else shutil.which('java')
    if not jar.exists() or not javac or not java:
        pytest.skip('Run ./haean setup-layout to test native Java formatting')
    source = tmp_path / 'EditorialStyleTest.java'
    source.write_text('''
import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
public class EditorialStyleTest {
 public static void main(String[] args) throws Exception {
  HWPFile f=new HWPFile();
  String[] names={"박스내용(들여쓰기)","보기내용(내어쓰기)","<사례견해>"};
  for(int i=0;i<3;i++) {
   f.getDocInfo().addNewCharShape();var p=f.getDocInfo().addNewParaShape();
   p.setLeftMargin(i==1?1200:0);p.setIndent(i==1?-1200:0);
   var s=f.getDocInfo().addNewStyle();s.setHangulName(names[i]);s.setCharShapeId(i);s.setParaShapeId(i);
  }
  String[] lines={"〈사례〉","[규정]","<견해>","◦ 갑은 자료를 읽었다.","갑: 모든 A는 B이다.","A 가설: 온도가 오르면 속도가 는다.","[규정]에 따라 판단한다.","갑의 견해는 다르다.","설명 없는 일반 본문"};
  int[] expected={2,2,2,1,1,1,0,0,0};
  for(int i=0;i<lines.length;i++) {
   Paragraph p=new Paragraph();HaeanText.editorialText(f,p,0,lines[i]);
   if(!p.getText().getNormalString(0).strip().equals(lines[i]))throw new AssertionError("text changed "+i);
   if(p.getHeader().getStyleId()!=expected[i])throw new AssertionError("wrong style "+i);
   var shape=f.getDocInfo().getParaShapeList().get(p.getHeader().getParaShapeId());
   if(expected[i]==1 && (shape.getIndent()!=-1200 || shape.getLeftMargin()!=1200))throw new AssertionError("hanging lost");
   if(expected[i]==2) {
    int id=(int)p.getCharShape().getPositonShapeIdPairList().get(0).getShapeId();
    if(!f.getDocInfo().getCharShapeList().get(id).getProperty().isBold())throw new AssertionError("heading not bold");
    if(!shape.getProperty1().isTogetherNextPara())throw new AssertionError("heading orphan");
   }
  }
  if(f.getDocInfo().getCharShapeList().get(2).getProperty().isBold())throw new AssertionError("template mutated");
  Paragraph normal=new Paragraph();HaeanText.text(f,normal,0,0,"갑: 기본 경로",false);
  if(normal.getHeader().getStyleId()!=0)throw new AssertionError("non-LEET path changed");
  HWPFile incomplete=new HWPFile();incomplete.getDocInfo().addNewCharShape();incomplete.getDocInfo().addNewParaShape();
  var s=incomplete.getDocInfo().addNewStyle();s.setHangulName("base");s.setCharShapeId(0);s.setParaShapeId(0);
  boolean rejected=false;
  try{HaeanText.editorialText(incomplete,new Paragraph(),0,"〈사례〉");}catch(IllegalArgumentException ex){rejected=true;}
  if(!rejected)throw new AssertionError("missing style silently accepted");
 }
}
''')
    subprocess.run([javac, '-encoding', 'UTF-8', '-cp', str(jar), '-d', str(tmp_path),
                    str(root / 'tools/layout-java/HaeanText.java'), str(source)],
                   check=True, capture_output=True, text=True)
    subprocess.run([java, '-cp', os.pathsep.join([str(jar), str(tmp_path)]), 'EditorialStyleTest'],
                   check=True, capture_output=True, text=True)
