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
    static void text(HWPFile file, Paragraph p, int styleId, int breaks, String text, boolean first) throws Exception {
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
        p.deleteLineSeg(); p.deleteRangeTag();
        p.getHeader().setStyleId((short)styleId);
        p.getHeader().setParaShapeId(s.getParaShapeId());
        p.getHeader().setCharacterCount(p.getText().getCharSize());
        p.getHeader().setCharShapeCount(1);
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
        shape.getProperty1().setLineDivideForHangul(LineDivideForHangul.ByWord);
        shape.getProperty1().setLineDivideForEnglish(LineDivideForEnglish.ByWord);
    }
}
