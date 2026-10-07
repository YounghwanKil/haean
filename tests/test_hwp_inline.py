"""Exercise actual Java character runs without private HWP templates."""
from pathlib import Path
import os
import shutil
import subprocess
import pytest


def test_native_underline_runs(tmp_path):
    root = Path(__file__).resolve().parents[1]
    jar = root / 'data/bin/hwplib-1.1.11.jar'
    jdk = Path('/opt/homebrew/opt/openjdk/bin')
    javac = str(jdk / 'javac') if (jdk / 'javac').exists() else shutil.which('javac')
    java = str(jdk / 'java') if (jdk / 'java').exists() else shutil.which('java')
    if not jar.exists() or not javac or not java:
        pytest.skip('Run ./haean setup-layout to test native Java formatting')
    source = tmp_path / 'InlineTest.java'
    source.write_text('''
import java.util.*;
import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.docinfo.charshape.UnderLineSort;
public class InlineTest {
 public static void main(String[] args) throws Exception {
  HWPFile f=new HWPFile();f.getDocInfo().addNewCharShape();
  f.getDocInfo().addNewParaShape();var style=f.getDocInfo().addNewStyle();
  style.setHangulName("fixture");style.setCharShapeId(0);style.setParaShapeId(0);
  Paragraph p=new Paragraph();
  HaeanText.text(f,p,0,0,"가\\t<u>나</u>다 <표> <u>라</u>",false);
  var pairs=p.getCharShape().getPositonShapeIdPairList();
  long[] positions={0,9,10,16,17};
  if(pairs.size()!=positions.length)throw new AssertionError("run count");
  for(int i=0;i<positions.length;i++)if(pairs.get(i).getPosition()!=positions[i])throw new AssertionError("position "+i+" "+pairs.get(i).getPosition());
  if(f.getDocInfo().getCharShapeList().get(1).getProperty().getUnderLineSort()!=UnderLineSort.Bottom)throw new AssertionError("underline");
  if(f.getDocInfo().getCharShapeList().get(0).getProperty().getUnderLineSort()!=UnderLineSort.None)throw new AssertionError("base style changed");
  if(p.getHeader().getCharShapeCount()!=5)throw new AssertionError("header count");
  for(String bad:List.of("<u>a","a</u>","<u></u>","<u>a<u>b</u></u>")) {
   boolean rejected=false;try{HaeanText.underlines(bad,new ArrayList<>());}catch(IllegalArgumentException ex){rejected=true;}
   if(!rejected)throw new AssertionError("invalid markup accepted");
  }
  var ranges=new ArrayList<int[]>();
  if(!HaeanText.underlines("<표> <u>내용</u>",ranges).equals("<표> 내용"))throw new AssertionError("literal label");
 }
}
''')
    subprocess.run([javac, '-encoding', 'UTF-8', '-cp', str(jar), '-d', str(tmp_path), str(root / 'tools/layout-java/HaeanText.java'), str(source)], check=True, capture_output=True, text=True)
    subprocess.run([java, '-cp', os.pathsep.join([str(jar), str(tmp_path)]), 'InlineTest'], check=True, capture_output=True, text=True)
