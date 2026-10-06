import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.ParagraphListInterface;
import kr.dogfoot.hwplib.object.bodytext.control.*;
import kr.dogfoot.hwplib.object.bodytext.control.gso.*;
import kr.dogfoot.hwplib.object.bodytext.control.gso.textbox.TextBox;
import java.util.*;

/** Remove the blank master's editorial memo fields from the output copy only. */
public class HaeanComments {
    static void clean(HWPFile file) throws Exception {
        for(var section:file.getBodyText().getSectionList())walk(section);
        file.getBodyText().getMemoList().clear();
    }
    static void walk(ParagraphListInterface list) throws Exception {
        for(var p:list) {
            if(p.getControlList()==null)continue;
            boolean memo=false,otherField=false;
            for(var c:p.getControlList())if(c instanceof ControlField f) {
                if(f.getHeader().getCommand().toUTF16LEString().startsWith("MEMO/"))memo=true;
                else otherField=true;
            }
            if(memo) {
                if(otherField)throw new IllegalArgumentException("Mixed memo and other fields require a separate template adapter");
                var chars=p.getText().getCharList();
                for(int i=chars.size()-1;i>=0;i--)if(chars.get(i).getCode()==3 || chars.get(i).getCode()==4) {
                    long pos=0;for(int j=0;j<i;j++)pos+=chars.get(j).getCharSize();
                    int size=chars.get(i).getCharSize();chars.remove(i);
                    if(p.getCharShape()!=null)for(var pair:p.getCharShape().getPositonShapeIdPairList())
                        if(pair.getPosition()>pos)pair.setPosition(Math.max(pos,pair.getPosition()-size));
                }
                p.getControlList().removeIf(c->c instanceof ControlField);
                p.deleteLineSeg();p.getHeader().setLineAlignCount(0);
                p.getHeader().setCharacterCount(p.getText().getCharSize());
            }
            for(var c:p.getControlList()) {
                if(c instanceof ControlTable t)for(var row:t.getRowList())for(var cell:row.getCellList())walk(cell.getParagraphList());
                else if(c instanceof ControlHeader h)walk(h.getParagraphList());
                else if(c instanceof ControlFooter f)walk(f.getParagraphList());
                else if(c instanceof ControlSectionDefine s)for(var b:s.getBatangPageInfoList())walk(b.getParagraphList());
                else if(c instanceof ControlContainer group) {
                    for(var child:group.getChildControlList())textBox(child);
                } else if(c instanceof GsoControl)textBox(c);
            }
        }
    }
    static void textBox(Control c) throws Exception {
        try {
            TextBox box=(TextBox)c.getClass().getMethod("getTextBox").invoke(c);
            if(box!=null)walk(box.getParagraphList());
        } catch(NoSuchMethodException ignored) { }
    }
}
