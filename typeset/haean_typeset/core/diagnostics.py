# -*- coding: utf-8 -*-
"""구조화된 진단(경고·오류).

Diagnostic = {"level": "error"|"warning", "code": "...", "item": 번호|id|None,
              "where": ["지문", 3]|None, "message": "...", "data": {...}}
code 목록과 뜻은 profile 의 spec.md 와 README 의 진단 표.
"""

ERROR = "error"
WARNING = "warning"


class Diag:
    """진단 모음. 조판 1회(또는 API 호출 1회)마다 새로 만든다."""

    def __init__(self, item=None):
        self.items = []
        self.item = item            # 기본 문항 번호(또는 id)

    def add(self, level, code, message, item=None, where=None, **data):
        self.items.append({
            "level": level,
            "code": code,
            "item": self.item if item is None else item,
            "where": list(where) if where else None,
            "message": message,
            "data": data,
        })

    def error(self, code, message, **kw):
        self.add(ERROR, code, message, **kw)

    def warning(self, code, message, **kw):
        self.add(WARNING, code, message, **kw)

    def extend(self, other):
        self.items.extend(other.items if isinstance(other, Diag) else other)

    def errors(self):
        return [d for d in self.items if d["level"] == ERROR]

    def has(self, code):
        return any(d["code"] == code for d in self.items)

    def as_list(self):
        return list(self.items)


def line(d):
    """사람이 읽는 한 줄."""
    where = ""
    if d.get("item") is not None:
        where = "%s번" % d["item"] if isinstance(d["item"], int) else str(d["item"])
    if d.get("where"):
        where += " " + "·".join(str(x) for x in d["where"])
    return "[%s %s] %s%s" % ("오류" if d["level"] == ERROR else "경고", d["code"],
                             (where.strip() + ": ") if where.strip() else "", d["message"])
