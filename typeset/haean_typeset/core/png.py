# -*- coding: utf-8 -*-
"""PNG 크기·해상도 읽기(표준 라이브러리만). IHDR 의 픽셀 크기, pHYs 의 DPI(없으면 96)."""
import struct

SIG = b"\x89PNG\r\n\x1a\n"


def png_info(path):
    """→ (가로 px, 세로 px, 가로 dpi, 세로 dpi). PNG 가 아니거나 깨졌으면 ValueError."""
    with open(path, "rb") as f:
        data = f.read(1 << 20)
    if not data.startswith(SIG):
        raise ValueError("PNG 파일이 아닙니다")
    i, w, h, dpi = 8, None, None, (96.0, 96.0)
    while i + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[i:i + 8])
        body = data[i + 8:i + 8 + n]
        if kind == b"IHDR":
            w, h = struct.unpack(">II", body[:8])
        elif kind == b"pHYs" and len(body) >= 9:
            px, py, unit = struct.unpack(">IIB", body[:9])
            if unit == 1 and px and py:                 # 1 = 미터당 픽셀
                dpi = (px * 0.0254, py * 0.0254)
        elif kind in (b"IDAT", b"IEND"):
            break
        i += 12 + n
    if not w or not h:
        raise ValueError("PNG 크기(IHDR)를 읽지 못했습니다")
    return w, h, dpi[0], dpi[1]
