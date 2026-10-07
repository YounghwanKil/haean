import kr.dogfoot.hwplib.object.HWPFile;
import kr.dogfoot.hwplib.object.bodytext.paragraph.Paragraph;
import kr.dogfoot.hwplib.object.bodytext.control.gso.*;
import kr.dogfoot.hwplib.object.bodytext.control.ctrlheader.gso.*;
import kr.dogfoot.hwplib.object.bodytext.control.gso.shapecomponent.ShapeComponentNormal;
import kr.dogfoot.hwplib.object.bodytext.control.gso.shapecomponent.lineinfo.LineType;
import kr.dogfoot.hwplib.object.bodytext.control.gso.shapecomponent.lineinfo.OutlineStyle;
import kr.dogfoot.hwplib.object.bodytext.control.gso.shapecomponent.shadowinfo.ShadowType;
import kr.dogfoot.hwplib.object.docinfo.BinData;
import kr.dogfoot.hwplib.object.docinfo.bindata.*;
import kr.dogfoot.hwplib.object.docinfo.borderfill.fillinfo.ImageFillType;
import java.nio.file.*;
import javax.imageio.ImageIO;

/** Inline PNG rectangle using hwplib's documented image-fill API. */
public class HaeanImage {
    static Paragraph paragraph(HWPFile file,Path path,int style) throws Exception {
        return paragraph(file,path,style,28000);
    }
    static Paragraph paragraph(HWPFile file,Path path,int style,int width) throws Exception {
        if(width<1000)throw new IllegalArgumentException("Image body cell is too narrow");
        var image=ImageIO.read(path.toFile());if(image==null)throw new IllegalArgumentException("Invalid PNG");
        int stream=1;for(var data:file.getDocInfo().getBinDataList())stream=Math.max(stream,data.getBinDataID()+1);
        file.getBinData().addNewEmbeddedBinaryData(String.format("Bin%04X.png",stream),Files.readAllBytes(path),BinDataCompress.ByStorageDefault);
        BinData data=new BinData();data.setBinDataID(stream);data.setExtensionForEmbedding("png");
        data.getProperty().setType(BinDataType.Embedding);data.getProperty().setCompress(BinDataCompress.ByStorageDefault);
        data.getProperty().setState(BinDataState.NotAccess);file.getDocInfo().getBinDataList().add(data);
        int binId=file.getDocInfo().getBinDataList().size();
        Paragraph p=new Paragraph();HaeanText.text(file,p,style,0,"",false);
        p.getText().getCharList().clear();p.getText().addExtendCharForGSO();p.getText().addString("");
        p.getHeader().setCharacterCount(p.getText().getCharSize());p.getHeader().getControlMask().setHasGsoTable(true);
        ControlRectangle rectangle=(ControlRectangle)p.addNewGsoControl(GsoControlType.Rectangle);
        int height=(int)Math.round(width*(double)image.getHeight()/image.getWidth());
        var header=rectangle.getHeader();var prop=header.getProperty();
        prop.setLikeWord(true);prop.setApplyLineSpace(true);prop.setVertRelTo(VertRelTo.Para);
        prop.setHorzRelTo(HorzRelTo.Para);prop.setVertRelativeArrange(RelativeArrange.TopOrLeft);
        prop.setHorzRelativeArrange(RelativeArrange.TopOrLeft);prop.setWidthCriterion(WidthCriterion.Absolute);
        prop.setHeightCriterion(HeightCriterion.Absolute);prop.setTextFlowMethod(TextFlowMethod.FitWithText);
        prop.setTextHorzArrange(TextHorzArrange.BothSides);prop.setObjectNumberSort(ObjectNumberSort.Figure);
        header.setWidth(width);header.setHeight(height);header.setInstanceId(0x61000000L+binId);
        header.setPreventPageDivide(true);
        ShapeComponentNormal shape=(ShapeComponentNormal)rectangle.getShapeComponent();
        shape.setLocalFileVersion(1);shape.setWidthAtCreate(width);shape.setHeightAtCreate(height);
        shape.setWidthAtCurrent(width);shape.setHeightAtCurrent(height);
        shape.setRotateXCenter(width/2);shape.setRotateYCenter(height/2);
        shape.createLineInfo();shape.getLineInfo().getProperty().setLineType(LineType.None);
        shape.getLineInfo().setOutlineStyle(OutlineStyle.Normal);
        shape.createShadowInfo();shape.getShadowInfo().setType(ShadowType.None);
        shape.createFillInfo();var fill=shape.getFillInfo();fill.getType().setImageFill(true);fill.createImageFill();
        fill.getImageFill().setImageFillType(ImageFillType.FitSize);fill.getImageFill().getPictureInfo().setBinItemID(binId);
        shape.setMatrixsNormal();var box=rectangle.getShapeComponentRectangle();
        box.setX1(0);box.setY1(0);box.setX2(width);box.setY2(0);box.setX3(width);box.setY3(height);box.setX4(0);box.setY4(height);
        return p;
    }
}
