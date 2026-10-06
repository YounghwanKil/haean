import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.ParagraphListInterface;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.control.*;
import kr.dogfoot.hwplib.object.bodytext.control.table.*;
import kr.dogfoot.hwplib.object.bodytext.control.gso.*;
import kr.dogfoot.hwplib.object.bodytext.control.gso.textbox.TextBox;
import kr.dogfoot.hwplib.object.bodytext.paragraph.*;
import kr.dogfoot.hwplib.object.bodytext.paragraph.text.*;
import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwplib.writer.HWPWriter;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Fill supplied HWP slots in place. Keep page furniture, boxes and named styles. */
public class HaeanFill {
    static String decode(String value) { return new String(Base64.getDecoder().decode(value),StandardCharsets.UTF_8); }
    static String normal(Paragraph p) throws Exception { return p.getText()==null ? "" : p.getText().getNormalString(0); }
    static void setText(HWPFile file, Paragraph p, String value, int style) throws Exception {
        int breaks=p.getHeader().getDivideSort().getValue();
        HaeanText.text(file,p,style,breaks,value,false);
    }
    static List<Paragraph> tables(Section section,int start,int end) {
        List<Paragraph> result=new ArrayList<>();
        for(int n=start;n<end;n++) {
            Paragraph p=section.getParagraph(n);
            if(p.getControlList()!=null && p.getControlList().size()==1 && p.getControlList().get(0) instanceof ControlTable) result.add(p);
        }
        return result;
    }
    static void fillBox(HWPFile file, Paragraph p, String value, int style) throws Exception {
        ControlTable table=(ControlTable)p.getControlList().get(0);
        Cell cell=null;
        for(Row row:table.getRowList())for(Cell candidate:row.getCellList())
            if(candidate.getListHeader().getColSpan()==table.getTable().getColumnCount()) cell=candidate;
        if(cell==null)throw new IllegalStateException("Expected full-width body cell in box");
        cell.getParagraphList().deleteAllParagraphs();
        for(String line:value.split("\n",-1)) {
            Paragraph para=cell.getParagraphList().addNewParagraph();
            HaeanText.text(file,para,style,0,line,false);
        }
        cell.getParagraphList().getParagraph(cell.getParagraphList().getParagraphCount()-1).getHeader().setLastInList(true);
        cell.getListHeader().setParaCount(cell.getParagraphList().getParagraphCount());
        cell.getListHeader().setHeight(1558);
        table.getHeader().setHeight(1558);
        p.deleteLineSeg(); p.getHeader().setLineAlignCount(0);
    }
    static void replaceInList(HWPFile file, ParagraphListInterface list,String old,String replacement) throws Exception {
        for(Paragraph p:list) {
            if(p.getText()!=null) {
                ArrayList<HWPChar> chars=p.getText().getCharList();
                String text=normal(p);
                if(text.contains(old)) {
                    // Replace contiguous normal characters, preserving control characters and shape runs.
                    for(int i=chars.size()-old.length();i>=0;i--) {
                        boolean match=true;
                        for(int j=0;j<old.length();j++)if(!(chars.get(i+j) instanceof HWPCharNormal ch) || !ch.getCh().equals(old.substring(j,j+1))) {match=false;break;}
                        if(!match)continue;
                        long offset=0;for(int j=0;j<i;j++)offset+=chars.get(j).getCharSize();
                        int delta=replacement.length()-old.length();
                        for(int j=0;j<old.length();j++)chars.remove(i);
                        for(int j=0;j<replacement.length();j++)chars.add(i+j,new HWPCharNormal(replacement.charAt(j)));
                        for(var pair:p.getCharShape().getPositonShapeIdPairList()) {
                            long pos=pair.getPosition();
                            if(pos>=offset+old.length())pair.setPosition(pos+delta);
                            else if(pos>offset)pair.setPosition(offset);
                        }
                    }
                    p.deleteLineSeg();p.getHeader().setLineAlignCount(0);
                    p.getHeader().setCharacterCount(p.getText().getCharSize());
                }
            }
            if(p.getControlList()==null) continue;
            for(Control c:p.getControlList()) replaceControl(file,c,old,replacement);

        }
    }
    static void replaceControl(HWPFile file,Control c,String old,String replacement) throws Exception {
        if(c instanceof ControlTable t) {
            for(Row row:t.getRowList()) for(Cell cell:row.getCellList())replaceInList(file,cell.getParagraphList(),old,replacement);
        } else if(c instanceof ControlHeader h)replaceInList(file,h.getParagraphList(),old,replacement);
        else if(c instanceof ControlFooter f)replaceInList(file,f.getParagraphList(),old,replacement);
        else if(c instanceof ControlSectionDefine sd) {
            for(var b:sd.getBatangPageInfoList())replaceInList(file,b.getParagraphList(),old,replacement);
        } else if(c instanceof ControlContainer group) {
            for(var child:group.getChildControlList())replaceControl(file,child,old,replacement);
        } else if(c instanceof GsoControl) {
            try {
                TextBox box=(TextBox)c.getClass().getMethod("getTextBox").invoke(c);
                if(box!=null)replaceInList(file,box.getParagraphList(),old,replacement);
            } catch(NoSuchMethodException ignored) { /* Lines and pictures have no text box. */ }
        }
    }
    public static void main(String[] args) throws Exception {
        HWPFile file=HWPReader.fromFile(args[0]);
        Section s=file.getBodyText().getSectionList().get(0);
        Map<Integer,Integer> starts=new TreeMap<>();
        for(int i=0;i<s.getParagraphCount();i++) {
            String t=normal(s.getParagraph(i));
            if(t.matches("[0-9]+\\.첫줄발문.*")) starts.put(Integer.parseInt(t.substring(0,t.indexOf('.'))),i);
        }
        if(starts.size()!=40)throw new IllegalStateException("Requires supplied 40-slot blank question template; refusal prevents old questions being carried forward");
        Set<Paragraph> remove = Collections.newSetFromMap(new IdentityHashMap<>());
        Map<Paragraph,List<Paragraph>> insertAfter = new IdentityHashMap<>();
        for(var entry:starts.entrySet()) {
            List<Paragraph> examples=tables(s,entry.getValue(),starts.getOrDefault(entry.getKey()+1,s.getParagraphCount()));
            for(int n=2;n<examples.size();n++)remove.add(examples.get(n));
        }
        for(String line:Files.readAllLines(Path.of(args[1]),StandardCharsets.UTF_8)) {
            String[] f=line.split("\\t",-1);
            if(f[0].equals("R")) { for(Section sec:file.getBodyText().getSectionList())replaceInList(file,sec,decode(f[1]),decode(f[2]));continue; }
            int slot=Integer.parseInt(f[1]);int style=Integer.parseInt(f[2]);String value=decode(f[3]);
            Integer start=starts.get(slot);if(start==null)throw new IllegalArgumentException("Missing slot "+slot);
            int end=starts.getOrDefault(slot+1,s.getParagraphCount());
            List<Paragraph> boxes=tables(s,start,end);
            // The master includes demonstration grids after Q1/Q2, outside the two content boxes.
            for(int n=2;n<boxes.size();n++)remove.add(boxes.get(n));
            if(boxes.size()<2)throw new IllegalStateException("Slot requires passage and statement boxes");
            if(f[0].equals("I")) {
                Paragraph picture=HaeanImage.paragraph(file,Path.of(value),style);
                if(f[4].equals("passage")) {
                    ControlTable outer=(ControlTable)boxes.get(0).getControlList().get(0);
                    Cell parent=outer.getRowList().get(0).getCellList().get(0);
                    parent.getParagraphList().getParagraph(parent.getParagraphList().getParagraphCount()-1).getHeader().setLastInList(false);
                    picture.getHeader().setLastInList(true);parent.getParagraphList().addParagraph(picture);
                    parent.getListHeader().setParaCount(parent.getParagraphList().getParagraphCount());
                } else {
                    Paragraph anchor=null;
                    for(int i=start+1;i<end;i++)if(normal(s.getParagraph(i)).contains("⑤"))anchor=s.getParagraph(i);
                    if(anchor==null)throw new IllegalStateException("Missing option anchor for diagram");
                    insertAfter.computeIfAbsent(anchor,k->new ArrayList<>()).add(picture);
                }
            } else if(f[0].equals("S"))setText(file,s.getParagraph(start),slot+". "+value,style);
            else if(f[0].equals("P"))fillBox(file,boxes.get(0),value,style);
            else if(f[0].equals("B")) {
                if(value.isBlank())remove.add(boxes.get(1));
                else fillBox(file,boxes.get(1),value,style);
            }
            else if(f[0].equals("O")) {
                List<Paragraph> opts=new ArrayList<>();
                for(int i=start+1;i<end;i++) if(normal(s.getParagraph(i)).startsWith("①")||normal(s.getParagraph(i)).startsWith("④"))opts.add(s.getParagraph(i));
                if(opts.size()!=2)throw new IllegalStateException("Expected two option rows");
                String[] lines=value.split("\u001e",-1);if(lines.length!=2)throw new IllegalArgumentException("Two option rows required");
                for(int i=0;i<2;i++)setText(file,opts.get(i),lines[i],style);
            } else if(f[0].equals("G")) {
                ControlTable outer=(ControlTable)boxes.get(0).getControlList().get(0);
                Cell parent=outer.getRowList().get(0).getCellList().get(0);
                Paragraph holder=boxes.get(0).clone();
                ControlTable grid=(ControlTable)holder.getControlList().get(0);
                Cell prototype=grid.getRowList().get(0).getCellList().get(0).clone();
                String[] values=value.split("\\u001f",-1);
                int cols=Integer.parseInt(f[4]);
                if(cols<1||values.length%cols!=0)throw new IllegalArgumentException("Invalid table dimensions");
                int rows=values.length/cols;
                long width=prototype.getListHeader().getWidth()-3400;
                grid.getRowList().clear();
                grid.getTable().setRowCount(rows);grid.getTable().setColumnCount(cols);
                grid.getTable().getCellCountOfRowList().clear();grid.getTable().getZoneInfoList().clear();
                grid.getHeader().setWidth(width);grid.getHeader().setHeight(rows*2000);
                for(int r=0;r<rows;r++) {
                    Row row=new Row();grid.getRowList().add(row);grid.getTable().getCellCountOfRowList().add(cols);
                    for(int c=0;c<cols;c++) {
                        Cell cell=prototype.clone();row.getCellList().add(cell);
                        cell.getListHeader().setRowIndex(r);cell.getListHeader().setColIndex(c);
                        cell.getListHeader().setRowSpan(1);cell.getListHeader().setColSpan(1);
                        cell.getListHeader().setWidth(width/cols);cell.getListHeader().setHeight(2000);
                        cell.getListHeader().setTextWidth(width/cols);
                        cell.getParagraphList().deleteAllParagraphs();
                        Paragraph cp=cell.getParagraphList().addNewParagraph();
                        HaeanText.text(file,cp,style,0,values[r*cols+c],false);
                        cp.getHeader().setLastInList(true);cell.getListHeader().setParaCount(1);
                    }
                }
                holder.deleteLineSeg();holder.getHeader().setLineAlignCount(0);
                parent.getParagraphList().getParagraph(parent.getParagraphList().getParagraphCount()-1).getHeader().setLastInList(false);
                holder.getHeader().setLastInList(true);
                parent.getParagraphList().addParagraph(holder);
                parent.getListHeader().setParaCount(parent.getParagraphList().getParagraphCount());
            } else throw new IllegalArgumentException("Unknown operation "+f[0]);
        }
        for(int i=s.getParagraphCount()-1;i>=0;i--) {
            Paragraph p=s.getParagraph(i);
            if(insertAfter.containsKey(p))for(Paragraph added:insertAfter.get(p))s.insertParagraph(i+1,added);
            if(remove.contains(p))s.deleteParagraph(i);
        }
        var caret=file.getDocInfo().getDocumentProperties().getCaretPosition();
        caret.setListID(0);caret.setParagraphID(0);caret.setPositionInParagraph(0);
        HWPWriter.toFile(file,args[2]);
        HWPReader.fromFile(args[2]);
    }
}
