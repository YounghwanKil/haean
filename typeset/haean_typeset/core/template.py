# -*- coding: utf-8 -*-
"""양식 hwpx 열기·모양 번호 검증·조립·그림 등록. 과목 값은 프로필이 넘긴다."""
import re
import zipfile

from .hwpx import zinfo


class TemplateError(Exception):
    """양식을 쓸 수 없음(code 는 TEMPLATE_*)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class TemplateDoc:
    def __init__(self, path):
        if path is None:
            raise TemplateError("TEMPLATE_REQUIRED", "로컬 양식 경로(template_path)가 필요합니다")
        try:
            self.z = zipfile.ZipFile(path)
        except (OSError, zipfile.BadZipFile) as e:
            raise TemplateError("TEMPLATE_OPEN", "양식을 열 수 없습니다: %s (%s)" % (path, e))
        self.path = path
        self.names = self.z.namelist()
        if "Contents/header.xml" not in self.names:
            raise TemplateError("TEMPLATE_OPEN", "hwpx 양식이 아닙니다: %s" % path)
        self.header = self.read("Contents/header.xml")
        self.hpf = self.read("Contents/content.hpf")

    def read(self, name):
        return self.z.read(name).decode("utf-8")

    def sections(self):
        return sorted(n for n in self.names if re.match(r"Contents/section\d+\.xml$", n))

    def masters(self):
        return sorted(n for n in self.names if re.match(r"Contents/masterpage\d+\.xml$", n))

    # ── 모양 번호 검증
    def verify_ids(self, expect):
        """expect: {("paraPr"|"charPr", ID): (속성, 값)} — 다르면 TemplateError(TEMPLATE_IDS)."""
        bad = []
        for (kind, idx), (attr, want) in expect.items():
            if kind == "paraPr":
                m = re.search(r'<hh:paraPr id="%d".*?</hh:paraPr>' % idx, self.header, re.S)
                got = m and re.search(r'<hc:%s value="(-?\d+)"' % attr, m.group(0))
            else:
                m = re.search(r'<hh:%s id="%d"[^>]*>' % (kind, idx), self.header)
                got = m and re.search(r'%s="(\d+)"' % attr, m.group(0))
            if not got or int(got.group(1)) != want:
                bad.append("%s %d 의 %s 가 %s (기대 %d)" % (kind, idx, attr, got.group(1) if got else "없음", want))
        if bad:
            raise TemplateError("TEMPLATE_IDS", "양식의 모양 번호가 프로필과 다릅니다: " + "; ".join(bad))

    # ── 조립
    def write(self, out_path, replace, add_bins=(), drop_bins=()):
        """replace: {zip 안 이름: 새 글}, add_bins: [(BinData/이름, 바이트, media-type, id)],
        drop_bins: 지울 BinData 이름들(manifest 항목도 지운다)."""
        hpf = self.hpf
        for name in drop_bins:
            hpf = re.sub(r'<opf:item [^>]*href="%s"[^>]*/>' % re.escape(name), "", hpf)
        if add_bins:
            items = "".join('<opf:item id="%s" href="%s" media-type="%s" isEmbeded="1"/>' % (i, n, m)
                            for n, _, m, i in add_bins)
            hpf = hpf.replace("</opf:manifest>", items + "</opf:manifest>", 1)
        replace = dict(replace)
        if hpf != self.hpf:
            replace["Contents/content.hpf"] = hpf
        with zipfile.ZipFile(out_path, "x") as o:
            for info in self.z.infolist():
                n = info.filename
                if n in drop_bins:
                    continue
                data = replace[n].encode("utf-8") if n in replace else self.z.read(n)
                o.writestr(zinfo(info), data)
            for n, data, _, _ in add_bins:
                ni = zipfile.ZipInfo(n, date_time=(1980, 1, 1, 0, 0, 0))
                ni.compress_type = zipfile.ZIP_STORED            # 양식이 그림을 압축하지 않고 넣는 방식
                o.writestr(ni, data)

    def bin_names(self):
        return [n for n in self.names if n.startswith("BinData/")]
