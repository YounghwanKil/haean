import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.Section;
import kr.dogfoot.hwplib.object.bodytext.control.ControlTable;
import kr.dogfoot.hwplib.object.bodytext.control.table.*;
import kr.dogfoot.hwplib.object.bodytext.paragraph.*;
import kr.dogfoot.hwplib.reader.HWPReader;
import kr.dogfoot.hwplib.writer.HWPWriter;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Fill the supplied solution master, retaining its answer grids and per-item metadata boxes. */
public class HaeanSolutions {
    static String cellText(Cell c) throws Exception {
        StringBuilder b=new StringBuilder();for(Paragraph p:c.getParagraphList())b.append(HaeanFill.normal(p));return b.toString();
    }
    static void cell(HWPFile f,Cell c,String text,int style) throws Exception {
        c.getParagraphList().deleteAllParagraphs();
        Paragraph p=c.getParagraphList().addNewParagraph();HaeanText.text(f,p,style,0,text,false);
        p.getHeader().setLastInList(true);c.getListHeader().setParaCount(1);
    }
    static List<Cell> cells(ControlTable table) {
        List<Cell> result=new ArrayList<>();for(Row row:table.getRowList())result.addAll(row.getCellList());return result;
    }
    static void answers(HWPFile f,ControlTable table,Map<Integer,String> answers,int style) throws Exception {
        List<Cell> cells=cells(table);
        long count=0;for(Cell c:cells)if(cellText(c).matches("[1-9][0-9]?"))count++;
        if(count!=40)throw new IllegalArgumentException("Expected 40-slot answer grid");
        for(int i=0;i<cells.size()-1;i++) {
            String n=cellText(cells.get(i));
            if(n.matches("[1-9][0-9]?"))cell(f,cells.get(++i),answers.getOrDefault(Integer.parseInt(n),""),style);
        }
    }
    static void compactGrid(HWPFile f,ControlTable table,Map<Integer,String> answers,int style,int size) throws Exception {
        // Retain the master's heading rows and widths. Three number/answer pairs,
        // Nine rows for 25 questions, ten rows for 30; unused cells stay blank.
        var rows=table.getRowList();int first=-1;
        for(int i=0;i<rows.size();i++)if(cellText(rows.get(i).getCellList().get(0)).equals("1")){first=i;break;}
        if(first<1)throw new IllegalArgumentException("Unrecognized answer grid");
        Cell label=rows.get(first).getCellList().get(0).clone(),answer=rows.get(first).getCellList().get(1).clone();
        long width=0;for(Cell c:rows.get(first).getCellList())width+=c.getListHeader().getWidth();
        long height=label.getListHeader().getHeight();
        for(int i=0;i<first;i++) {
            var cells=rows.get(i).getCellList();
            if(cells.size()==1){cells.get(0).getListHeader().setColSpan(6);continue;}
            while(cells.size()>6)cells.remove(cells.size()-1);
            for(int j=0;j<cells.size();j++){cells.get(j).getListHeader().setWidth(width/6);cells.get(j).getListHeader().setTextWidth(width/6);}
        }
        while(rows.size()>first)rows.remove(rows.size()-1);
        int rowCount=(size+2)/3;
        for(int r=0;r<rowCount;r++) {
            Row row=new Row();rows.add(row);
            for(int c=0;c<6;c++) {
                Cell cell=(c%2==0?label:answer).clone();int number=(c/2)*rowCount+r+1;
                cell.getListHeader().setRowIndex(first+r);cell.getListHeader().setColIndex(c);
                cell.getListHeader().setWidth(width/6);cell.getListHeader().setTextWidth(width/6);
                int labelStyle=cell.getParagraphList().getParagraph(0).getHeader().getStyleId();
                cell(f,cell,number>size?"":(c%2==0?Integer.toString(number):answers.get(number)),c%2==0?labelStyle:style);
                row.getCellList().add(cell);
            }
        }
        table.getTable().setRowCount(first+rowCount);table.getTable().setColumnCount(6);
        table.getTable().getCellCountOfRowList().clear();table.getTable().getZoneInfoList().clear();
        for(Row row:rows)table.getTable().getCellCountOfRowList().add(row.getCellList().size());
        table.getHeader().setHeight(table.getHeader().getHeight()-(10-rowCount)*height);
    }
    static void verifyGrid(ControlTable table,Map<Integer,String> answers,int size) throws Exception {
        List<Cell> values=cells(table);Set<Integer> seen=new HashSet<>();
        for(int i=0;i<values.size()-1;i++) {
            String label=cellText(values.get(i));
            if(!label.matches("[1-9][0-9]?"))continue;
            int number=Integer.parseInt(label);
            if(!seen.add(number)||number>size)throw new IllegalStateException("Duplicate/invalid answer slot: "+number);
            if(!cellText(values.get(++i)).equals(answers.getOrDefault(number,"")))
                throw new IllegalStateException("Answer grid mismatch: "+number);
        }
        if(seen.size()!=size)throw new IllegalStateException("Missing answer grid slots");
    }
    static void verifyAnswers(HWPFile file,Map<Integer,String> answers,int size) throws Exception {
        Section section=file.getBodyText().getSectionList().get(1);
        verifyGrid((ControlTable)file.getBodyText().getSectionList().get(0).getParagraph(1).getControlList().get(0),answers,size);
        verifyGrid((ControlTable)section.getParagraph(1).getControlList().get(0),answers,size);
        int number=0;
        for(Paragraph paragraph:section) {
            if(paragraph.getControlList()==null)continue;
            for(var control:paragraph.getControlList())if(control instanceof ControlTable) {
                List<Cell> values=cells((ControlTable)control);
                boolean metadata=false;
                for(Cell value:values)if(cellText(value).equals("난이도"))metadata=true;
                if(!metadata)continue;
                for(int i=0;i<values.size()-1;i++)if(cellText(values.get(i)).equals("정답")) {
                    number++;
                    if(!cellText(values.get(i+1)).equals(answers.getOrDefault(number,"")))
                        throw new IllegalStateException("Solution answer mismatch: "+number);
                }
            }
        }
        if(number!=size)throw new IllegalStateException("Missing solution answer boxes: "+number);
    }
    public static void main(String[] args) throws Exception {
        HWPFile file=HWPReader.fromFile(args[0]);
        HaeanComments.clean(file);
        if(file.getBodyText().getSectionList().size()!=2)throw new IllegalArgumentException("Requires supplied blank solution master");
        Section s=file.getBodyText().getSectionList().get(1);
        List<Integer> starts=new ArrayList<>();
        for(int i=0;i<s.getParagraphCount();i++)if(HaeanFill.normal(s.getParagraph(i)).equals("제재 / 주제"))starts.add(i);
        if(starts.size()!=40)throw new IllegalArgumentException("Requires 40 blank solution slots");
        Map<Integer,List<String[]>> ops=new TreeMap<>(Comparator.reverseOrder());
        Map<Integer,String> answerMap=new HashMap<>();
        int answerStyle=1;
        int size=40;
        // Keep the named style, but give answer circles a restrained 10 pt size.
        var answerStyleDef=file.getDocInfo().getStyleList().get(answerStyle);
        var answerShape=file.getDocInfo().getCharShapeList().get(answerStyleDef.getCharShapeId()).clone();
        answerShape.setBaseSize(1000);answerShape.getRatios().setForAll((short)100);
        answerStyleDef.setCharShapeId(file.getDocInfo().getCharShapeList().size());
        file.getDocInfo().getCharShapeList().add(answerShape);
        for(String line:Files.readAllLines(Path.of(args[1]),StandardCharsets.UTF_8)) {
            String[] f=line.split("\t",-1);
            if(f[0].equals("R")) {for(Section sec:file.getBodyText().getSectionList())HaeanFill.replaceInList(file,sec,HaeanFill.decode(f[1]),HaeanFill.decode(f[2]));continue;}
            if(f[0].equals("C")){size=Integer.parseInt(f[1]);if(size!=25 && size!=30)throw new IllegalArgumentException("Only 25/30 supported");continue;}
            int slot=Integer.parseInt(f[1]);if(slot<1||slot>40)throw new IllegalArgumentException("Slot out of range");
            ops.computeIfAbsent(slot,k->new ArrayList<>()).add(f);
            if(f[0].equals("A"))answerMap.put(slot,HaeanFill.decode(f[3]));
        }
        ControlTable cover=(ControlTable)file.getBodyText().getSectionList().get(0).getParagraph(1).getControlList().get(0);
        ControlTable grid=(ControlTable)s.getParagraph(1).getControlList().get(0);
        answers(file,cover,answerMap,answerStyle);answers(file,grid,answerMap,answerStyle);
        for(int n=0;n<starts.size();n++) {
            ControlTable meta=(ControlTable)s.getParagraph(starts.get(n)+1).getControlList().get(0);
            List<Cell> values=cells(meta);
            for(int i=0;i<values.size()-1;i++)if(cellText(values.get(i)).equals("정답"))
                cell(file,values.get(i+1),answerMap.getOrDefault(n+1,""),answerStyle);
        }
        // The master's sample overall commentary is not an assessment of the new exam.
        ControlTable comment=(ControlTable)s.getParagraph(2).getControlList().stream().filter(c->c instanceof ControlTable).findFirst().orElseThrow();
        for(Cell c:cells(comment))cell(file,c,"모델 검토본 · 전문가 최종 검토 전",4);
        if(size<40) {
            if(answerMap.size()!=size || !answerMap.keySet().containsAll(java.util.stream.IntStream.rangeClosed(1,size).boxed().toList()))throw new IllegalArgumentException("Requires complete answers for selected size");
            compactGrid(file,cover,answerMap,answerStyle,size);compactGrid(file,grid,answerMap,answerStyle,size);
            for(int i=s.getParagraphCount()-1;i>=starts.get(size);i--)s.deleteParagraph(i);
        }
        for(var entry:ops.entrySet()) {
            int slot=entry.getKey(),start=starts.get(slot-1),end=slot<size?starts.get(slot):s.getParagraphCount();
            Paragraph heading=s.getParagraph(start);
            Paragraph metadata=s.getParagraph(start+1);
            ControlTable meta=(ControlTable)metadata.getControlList().get(0);
            List<Cell> mc=cells(meta);
            for(int i=end-1;i>start+1;i--)s.deleteParagraph(i);
            int insert=start+2;
            for(String[] f:entry.getValue()) {
                int style=Integer.parseInt(f[2]);String value=HaeanFill.decode(f[3]);
                // The master's paragraph numbering supplies the question number.
                if(f[0].equals("H")) {
                    HaeanFill.setText(file,heading,value,style);
                    heading.getHeader().getDivideSort().setDividePage(false);
                    heading.getHeader().getDivideSort().setDivideColumn(true);
                }
                else if(f[0].equals("A")) {
                    for(int i=0;i<mc.size()-1;i++)if(cellText(mc.get(i)).equals("정답"))cell(file,mc.get(i+1),value,style);
                } else if(f[0].equals("M")) {
                    String[] values=value.split("\u001f",-1);String[] labels={"난이도","내용 영역","문항 유형"};
                    for(int i=0;i<mc.size()-1;i++)for(int j=0;j<labels.length;j++)if(cellText(mc.get(i)).equals(labels[j]))cell(file,mc.get(i+1),values[j],style);
                } else if(f[0].equals("T")) {
                    Paragraph p=new Paragraph();HaeanText.text(file,p,style,0,value,false);s.insertParagraph(insert++,p);
                } else throw new IllegalArgumentException("Unknown operation "+f[0]);
            }
        }
        s.getLastParagraph().getHeader().setLastInList(true);
        var caret=file.getDocInfo().getDocumentProperties().getCaretPosition();
        caret.setListID(0);caret.setParagraphID(0);caret.setPositionInParagraph(0);
        HWPWriter.toFile(file,args[2]);verifyAnswers(HWPReader.fromFile(args[2]),answerMap,size);
    }
}
