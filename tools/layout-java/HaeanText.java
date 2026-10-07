import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.control.ControlType;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.docinfo.Style;
import kr.dogfoot.hwplib.object.docinfo.parashape.LineDivideForHangul;
import kr.dogfoot.hwplib.object.docinfo.parashape.LineDivideForEnglish;
import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwplib.writer.HWPWriter;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Template-native paragraphs. Input is TSV style-id, break flags, base64 UTF-8 text. */
public class HaeanText {
    // Only the explicit underline markup used by exam authors is interpreted.
    // Other angle-bracket text (e.g. <표>) remains literal exam content.
    static String underlines(String source, List<int[]> ranges) {
        StringBuilder plain=new StringBuilder();int start=-1;
        for(int i=0;i<source.length();) {
            if(source.startsWith("<u>",i)) {
                if(start>=0)throw new IllegalArgumentException("Nested underline markup");
                start=plain.length();i+=3;
            } else if(source.startsWith("</u>",i)) {
                if(start<0 || start==plain.length())throw new IllegalArgumentException("Invalid underline markup");
                ranges.add(new int[]{start,plain.length()});start=-1;i+=4;
            } else plain.append(source.charAt(i++));
        }
        if(start>=0)throw new IllegalArgumentException("Unclosed underline markup");
        return plain.toString();
    }
    static int position(String text,int offset,boolean first) {
        // HWP inline tab controls occupy eight UTF-16 positions.
        int value=offset+(first?16:0);
        for(int i=0;i<offset;i++)if(text.charAt(i)=='\t')value+=7;
        return value;
    }
    static void text(HWPFile file, Paragraph p, int styleId, int breaks, String text, boolean first) throws Exception {
        List<int[]> ranges=new ArrayList<>();text=underlines(text,ranges);
        Style s = file.getDocInfo().getStyleList().get(styleId);
        p.createText();
        if (first) {
            p.getText().addExtendCharForSectionDefine();
            p.getText().addExtendCharForColumnDefine();
        }
        String[] parts=text.split("\\t",-1);
        for(int i=0;i<parts.length;i++) {
            if(i>0) {
                var chars=p.getText().getCharList();
                chars.remove(chars.size()-1);
                var tab=p.getText().addNewInlineControlChar();tab.setCode((short)9);tab.setAddition(new byte[12]);
            }
            p.getText().addString(parts[i]);
        }
        p.createCharShape();
        p.getCharShape().addParaCharShape(0, s.getCharShapeId());
        if(!ranges.isEmpty()) {
            var shape=file.getDocInfo().getCharShapeList().get(s.getCharShapeId()).clone();
            shape.getProperty().setUnderLineSort(kr.dogfoot.hwplib.object.docinfo.charshape.UnderLineSort.Bottom);
            shape.getProperty().setUnderLineShape(kr.dogfoot.hwplib.object.docinfo.charshape.BorderType2.Solid);
            int id=file.getDocInfo().getCharShapeList().size();file.getDocInfo().getCharShapeList().add(shape);
            var events=new TreeMap<Integer,Integer>();events.put(0,s.getCharShapeId());
            for(int[] range:ranges) {
                events.put(position(text,range[0],first),id);
                events.put(position(text,range[1],first),s.getCharShapeId());
            }
            p.getCharShape().getPositonShapeIdPairList().clear();
            for(var event:events.entrySet())p.getCharShape().addParaCharShape(event.getKey(),event.getValue());
        }
        p.deleteLineSeg(); p.deleteRangeTag();
        p.getHeader().setStyleId((short)styleId);
        p.getHeader().setParaShapeId(s.getParaShapeId());
        p.getHeader().setCharacterCount(p.getText().getCharSize());
        p.getHeader().setCharShapeCount(p.getCharShape().getPositonShapeIdPairList().size());
        p.getHeader().setLineAlignCount(0);
        p.getHeader().setRangeTagCount(0);
        p.getHeader().getControlMask().setValue(0);
        p.getHeader().getControlMask().setHasParaBreak(true);
        p.getHeader().getControlMask().setHasTab(text.contains("\t"));
        p.getHeader().getControlMask().setHasLineBreak(text.contains("\n"));
        if(first) p.getHeader().getControlMask().setHasSectColDef(true);
        p.getHeader().getDivideSort().setValue((short)breaks);
        p.getHeader().setLastInList(false);
        var shape = file.getDocInfo().getParaShapeList().get(s.getParaShapeId());
        // Keep short option/statement paragraphs intact; avoid single-line widows in longer prose.
        shape.getProperty1().setProtectLoner(true);
        if(s.getHangulName().equals("선택지") || s.getHangulName().equals("보기내용(내어쓰기)") || s.getHangulName().equals("코멘트내용 8pt"))shape.getProperty1().setProtectPara(true);
        if(s.getHangulName().equals("정오판단_선지"))shape.getProperty1().setTogetherNextPara(true);
        shape.getProperty1().setLineDivideForHangul(LineDivideForHangul.ByWord);
        shape.getProperty1().setLineDivideForEnglish(LineDivideForEnglish.ByWord);
    }
}
