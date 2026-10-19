# -*- coding: utf-8 -*-
"""명령 줄.

  python -m haean_typeset 원고.json -o 문제지.hwpx                 조판 + 점검.md + 점검.json (+ 해설)
  python -m haean_typeset 원고.json --lines-only -o 원고_줄.json   줄 나눈 원고(기본: 옛 줄 지우고 다시)
  옵션: --profile <프로필 이름>  --title "…"  --strict  --keep-lines  --line-mode fit|force|none  --no-solution
"""
import argparse
import copy
import glob
import json
import os
import sys

from . import api
from .diagnostics import line


def load(src):
    """시험 JSON(파일) 또는 문항 JSON 폴더 → (시험 dict, 그림 기준 폴더)."""
    if os.path.isdir(src):
        items = []
        for p in sorted(glob.glob(os.path.join(src, "*.json"))):
            with open(p, encoding="utf-8") as f:
                items.append(json.load(f))
        return {"문항": items}, src
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        data = {"문항": data}
    return data, os.path.dirname(os.path.abspath(src))


def write_reports(base, result, title):
    with open(base + "_점검.json", "x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    D = result["diagnostics"] or []
    L = ["# 조판 점검", "",
         "- 출력: `%s`%s" % (os.path.basename(result["path"] or "(만들지 않음)"),
                            " · 해설 `%s`" % os.path.basename(result["solution_path"]) if result.get("solution_path") else ""),
         "- 시험명: %s" % (title or "(양식 그대로)"),
         "- 문항: %d개 · 쪽 수: %s" % (len(result["items"]), result["pages"] if result["pages"] else "양식 그대로"),
         "- 프로필: %s" % (result.get("profile") or ""),
         "- 오류 %d건 · 경고 %d건" % (sum(d["level"] == "error" for d in D), sum(d["level"] == "warning" for d in D)),
         "", "## 진단", ""]
    L += ["- " + line(d) for d in D] or ["- 없음"]
    L += ["", "## 문항별", "",
          "높이 = 줄 수 × 줄 간격 + 문단·상자·그림 간격. 여유 줄 2 미만 'tight', 0 미만 'over'.", "",
          "| 번호 | id | 배치 | 쪽·단 | 줄 수 | 높이 | 단 높이 | 여유 줄 | 판정 |", "|---|---|---|---|---|---|---|---|---|"]
    for m in result["items"]:
        if m.get("verdict") == "invalid":
            L.append("| %d | | | | | | | | invalid |" % m["number"])
            continue
        where = "%d쪽 %s" % (m["page"], "왼쪽" if m["column"] % 2 else "오른쪽") if m.get("column") else ""
        L.append("| %d | %s | %s | %s | %d | %.0f | %.0f | %.1f | %s |" % (
            m["number"], m.get("id") or "", m.get("layout", ""), where, m["lines"], m["height_pt"], m["capacity_pt"],
            m["spare_lines"], m["verdict"]))
    with open(base + "_점검.md", "x", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="haean_typeset", description="원고 JSON → 양식 hwpx")
    ap.add_argument("src", nargs="?", help="시험 JSON 파일 또는 문항 JSON 폴더")
    ap.add_argument("-o", "--out")
    ap.add_argument("--profiles", action="store_true", help="쓸 수 있는 프로필 목록")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--title")
    ap.add_argument("--template", help="로컬 문제지 양식(출력 시 필수)")
    ap.add_argument("--solution-template", help="로컬 해설 양식(해설 출력 시 필수)")
    ap.add_argument("--strict", action="store_true", help="오류가 있으면 만들지 않고 종료 코드 1")
    ap.add_argument("--lines-only", action="store_true", help="hwpx 대신 줄 나눈 원고 JSON")
    ap.add_argument("--keep-lines", action="store_true", help="--lines-only 에서 원고의 \\n 을 그대로 둠(rewrap=False)")
    ap.add_argument("--line-mode", choices=("fit", "force", "none"), default="fit",
                    help="fit(기본): 줄을 정하고 자간으로 맞춤(한글이 같은 자리에서 접음·양쪽 맞춤) · force: 강제 줄 나눔(옛 방식) · none: 한글에 맡김")
    ap.add_argument("--no-auto-break", action="store_true", help=argparse.SUPPRESS)   # = --line-mode none
    ap.add_argument("--no-solution", action="store_true")
    a = ap.parse_args(argv)
    if a.profiles:
        from ..profiles import PROBLEM_PROFILES, DEFAULT
        labels = {"leet_reasoning": "LEET 추리논증", "leet_verbal": "LEET 언어이해",
                  "psat5_language": "PSAT 5급 언어논리", "psat5_situation": "PSAT 5급 상황판단",
                  "psat5_data": "PSAT 5급 자료해석"}
        for name in PROBLEM_PROFILES:
            api.load_profile(name)  # 프로필이 열리는지 확인
            print("%-16s %s · 외부 양식 필요%s" %
                  (name, labels[name], "  (기본)" if name == DEFAULT else ""))
        return
    if not a.src or not a.out:
        ap.error("원고와 -o 출력 경로가 필요합니다")
    if os.path.lexists(a.out):
        ap.error("기존 출력은 덮어쓰지 않습니다: " + a.out)
    exam, base_dir = load(a.src)
    profile = a.profile or exam.get("profile")

    if a.lines_only:
        out, D, n = copy.deepcopy(exam), [], 1
        for k, item in enumerate(exam.get("문항") or []):
            new, d = api.wrap(item, profile, rewrap=not a.keep_lines, number=n, base_dir=base_dir,
                              template_path=a.template)
            out["문항"][k] = new
            D += d
            n += len(item.get("문항") or []) if isinstance(item, dict) and "세트" in item else 1
        if a.strict and any(d["level"] == "error" for d in D):
            for d in D:
                print(line(d), file=sys.stderr)
            sys.exit(1)
        with open(a.out, "x", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print("만들었습니다: %s (진단 %d건)" % (a.out, len(D)))
        for d in D:
            print("  - " + line(d))
        sys.exit(1 if a.strict and any(d["level"] == "error" for d in D) else 0)

    title = a.title or exam.get("시험명")
    base = a.out[:-5] if a.out.endswith(".hwpx") else a.out
    if not a.template:
        ap.error("출력에는 --template 로컬 양식 경로가 필요합니다")
    for suffix in ("_점검.json", "_점검.md"):
        if os.path.lexists(base + suffix):
            ap.error("기존 점검 기록은 덮어쓰지 않습니다: " + base + suffix)
    try:
        result = api.typeset(exam, a.out, profile, title=title, strict=a.strict, base_dir=base_dir,
                             auto_break="none" if a.no_auto_break else a.line_mode, solution=not a.no_solution,
                             template_path=a.template, solution_template_path=a.solution_template)
    except api.StrictError as e:
        write_reports(base, e.result, title)
        print("만들지 않았습니다: %s — 점검: %s_점검.md" % (e, base))
        for d in e.result["diagnostics"]:
            print("  - " + line(d))
        sys.exit(1)
    except (api.TemplateError, OSError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    write_reports(base, result, title)
    D = result["diagnostics"]
    print("만들었습니다: %s%s" % (a.out, " · 해설 %s" % result["solution_path"] if result["solution_path"] else ""))
    print("점검: %s_점검.md / .json (오류 %d건 · 경고 %d건)" % (
        base, sum(d["level"] == "error" for d in D), sum(d["level"] == "warning" for d in D)))
    for d in D:
        print("  - " + line(d))
