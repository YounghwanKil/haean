import kr.dogfoot.hwplib.object.HWPFile;
import java.util.Date;

/** Replace inherited author/saver identities in the document summary with neutral values. */
public class HaeanMeta {
    // Fixed instant keeps derived masters byte-reproducible (2026-01-01T00:00:00Z).
    static final Date NEUTRAL_DATE = new Date(1767225600000L);
    static void neutral(HWPFile file, String title) {
        var info = file.getSummaryInformation();
        if (info == null) return;
        info.setAuthor("haean"); info.setLastAuthor("haean");
        info.setTitle(title); info.setSubject(""); info.setKeywords(""); info.setComments("");
        info.setCreateDateTime(NEUTRAL_DATE); info.setLastSaveDateTime(NEUTRAL_DATE);
    }
}
