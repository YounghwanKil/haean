# -*- coding: utf-8 -*-
"""LaTeX 수식(`$...$` 안쪽) → 한글 수식(HancomEQN) 스크립트.

  conv(r"\\frac{1}{2}")            -> "{1} over {2}"
  conv(r"\\lim_{x\\to 1}f(x)")       -> "lim _{x -> 1} f(x)"

문항 원고(items/*.json)가 쓰는 LaTeX 만 다룬다. 2022~2027 기출 데이터셋(dataset.jsonl)의 공통·선택
문항 618개와 생성 문항을 모두 변환해 모르는 명령이 없는지 확인했다(`python latex2eqn.py --survey`).
모르는 명령은 이름을 그대로 두고 unknown 에 모은다(빌드가 경고로 알린다).

한글 수식 문법은 수학스나이퍼 build_sniper.py·시그마 모의고사 원본 hwpx 의 수식과 한글 수식 도움말을 따랐다.
  분수 {a} over {b}, 근호 sqrt {x} / root {n} of {x}, 첨자 x _{1} ^{2}, 괄호 LEFT ( … RIGHT ),
  극한 lim _{x -> a}, 합 sum _{k=1} ^{n}, 적분 int _{a} ^{b}, 경우 {cases{… & … # … & …}},
  정체 {rm AB}, 선분 overline {rm AB}, 벡터 vec {a}, 부등호 LEQ GEQ, 같지 않음 !=.
"""
import re

GREEK = {"alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta", "theta", "vartheta",
         "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau", "upsilon", "phi", "varphi",
         "chi", "psi", "omega", "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Phi", "Psi", "Omega"}
FUNCS = {"sin", "cos", "tan", "sec", "csc", "cot", "ln", "log", "exp", "max", "min", "lim", "det"}
SYMBOLS = {
    "le": "LEQ", "leq": "LEQ", "leqslant": "LEQ", "ge": "GEQ", "geq": "GEQ", "geqslant": "GEQ",
    "neq": "!=", "ne": "!=", "times": "times", "cdot": "cdot", "cdots": "cdots", "ldots": "cdots",
    "dots": "cdots", "infty": "inf", "to": "->", "rightarrow": "->", "longrightarrow": "->",
    "leftarrow": "<-", "Rightarrow": "=>", "Leftrightarrow": "<=>", "iff": "<=>",
    "angle": "angle", "circ": "circ", "perp": "bot", "parallel": "parallel", "in": "in", "notin": "notin",
    "cap": "smallinter", "cup": "smallunion", "subset": "subset", "subseteq": "subseteq",
    "emptyset": "emptyset", "varnothing": "emptyset", "pm": "+-", "mp": "-+", "div": "div",
    "approx": "approx", "sim": "sim", "equiv": "==", "therefore": "therefore", "because": "because",
    "mid": "|", "vert": "|", "lbrace": "lbrace", "rbrace": "rbrace", "triangle": "triangle",
    "prime": "'", "%": "%", "{": "lbrace", "}": "rbrace", "|": "||", "#": "#", "&": "&", "_": "_",
    "lvert": "|", "rvert": "|", "langle": "<", "rangle": ">", "star": "*", "ast": "*",
}
SPACES = {",": "`", ";": "~", ":": "`", " ": "~", "quad": "~~", "qquad": "~~~~", "!": "", ">": "`",
          "enspace": "~", "thinspace": "`"}
DROP = {"displaystyle", "textstyle", "scriptstyle", "limits", "nolimits", "left.", "right.", "big", "Big",
        "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr", "hline", "nonumber", "relax", "middle"}
ACCENT = {"overline": "overline", "bar": "bar", "vec": "vec", "overrightarrow": "vec", "hat": "hat",
          "widehat": "hat", "tilde": "tilde", "dot": "dot", "ddot": "ddot", "underline": "underline",
          "overleftrightarrow": "dyad", "check": "check", "acute": "acute", "grave": "grave"}
FONT = {"mathrm": "rm", "rm": "rm", "textrm": "rm", "operatorname": "rm", "mathbf": "rm bold",
        "mathit": "it", "boldsymbol": "bold", "mathsf": "rm"}
DELIM = {"(": "(", ")": ")", "[": "[", "]": "]", "|": "|", "\\{": "lbrace", "\\}": "rbrace", "\\lbrace": "lbrace",
         "\\rbrace": "rbrace", "\\lvert": "|", "\\rvert": "|", "\\|": "||", "\\langle": "<", "\\rangle": ">",
         ".": None, "\\lfloor": "[", "\\rfloor": "]", "\\lceil": "[", "\\rceil": "]"}

TOKEN = re.compile(r"\\[A-Za-z]+\*?|\\.|\d+(?:\.\d+)?|[{}^_&]|\s+|.", re.S)

# 평가원 실측 간격(2026-10-10, `원칙/하위/참조/평가원_글조판양식.md` `수식 안 간격`). 한글 수식 빈칸: `~` 5.52pt, `` ` `` 1.44pt.
COMMA = "`,``"                 # 쉼표: 앞 +1.08, 뒤 +3.43 (평가원 2022~2027 수백 곳). 그냥 `,` 는 앞 -0.3, 뒤 +0.7
RELS = {"=", "<", ">", "LEQ", "GEQ", "!=", "->", "=>", "<=>", "approx", "sim", "=="}
# 관계 기호 간격(2026-10-14 실측, 정본 '관계 기호 간격', 조판.md 조1-15). 문제지만 켠다(KICE_REL_GAPS).
# EBS 해설(같은 한글 2022)은 둘 다 기본값이라 해설지는 끈다(build_solution_hwp).
# 1) 닫는 큰 괄호(`RIGHT |`, `RIGHT )` …) 바로 뒤 관계 기호: 한글 수식은 관계 기호 왼쪽 간격을 지운다
#    (`|a|=6` 막대→= -0.25pt, `)`→= -0.56). 평가원은 막대→= 1.15(21곳)·2.53(14곳), 괄호→= 2.19(320곳).
#    사이에 빈 위첨자 `^{}` 를 끼우면 간격이 되살아나 막대→= 3.11, 괄호→= 2.68 (`` ` `` 는 3.47 / 3.16, 그 사이 수단 없음).
# 2) `=` 오른쪽: 평가원은 2025학년도부터 `=` 뒤를 손으로 띄운다(`= 6`: 3.37). `=`→숫자 2023·24 3%, 2025·26 52%,
#    2027 81%(빼기·로마 대문자 100%). 우리 기본 1.99 → `` ` `` 3.31. 분수 앞(기본 4.87 이미 넓다)·첨자 안(`k=1`,
#    평가원 1.8)·경우 나눔 중괄호 앞(이미 `` ` ``)은 뺀다.
# 3) 분수 바로 뒤 관계 기호(사용자 지적 2026-10-14, 1회 11번 `lim f(x)/x = lim …`): 한글 수식은 분수 → `=` 1.68pt.
#    평가원 표시 수식 600dpi 잉크 실측 4.32·4.44(2022.09 공통 8), 4.56(2027.09 공통 8). 한글에서 고를 수 있는 값은
#    없음 1.68 / `^{}` 5.04 / `` ` `` 5.40 / `` `` `` 6.72 / `^{`}` 6.0 → 가장 가까운 `^{}`(+0.5, 그 사이 수단 없음).
REL_AFTER_FRAC = {"=", "<", ">", "LEQ", "GEQ", "!="}
REL_AFTER_RIGHT = {"=", "<", ">", "LEQ", "GEQ", "!="}
RIGHT_CLOSE = re.compile(r"RIGHT\s+(\||\)|\]|rbrace|\|\|)\s*$")
KICE_REL_GAPS = True
VEC_NEXT = {"=", "+", "-", "<", ">"}
VEC_NEXT_CMD = {"le", "leq", "ge", "geq", "neq", "ne", "pm", "mp"}
LATIN = re.compile(r"[A-Za-z]")


class Conv:
    def __init__(self, src):
        self.toks = [t for t in TOKEN.findall(src)]
        self.i = 0
        self.unknown = []
        self.need_it = False     # 앞에 {rm …} 이 나와 다음 라틴 글자 앞에 `it` 를 넣어야 한다
        self.script = 0          # 첨자(^ _) 안 깊이: `=` 뒤 빈칸은 첨자 밖에서만

    # ------------------------------------------------------------ 토큰
    def peek(self, skip_ws=True):
        j = self.i
        while skip_ws and j < len(self.toks) and self.toks[j].isspace():
            j += 1
        return self.toks[j] if j < len(self.toks) else None

    def next(self, skip_ws=True):
        while skip_ws and self.i < len(self.toks) and self.toks[self.i].isspace():
            self.i += 1
        if self.i >= len(self.toks):
            return None
        t = self.toks[self.i]
        self.i += 1
        return t

    def arg(self):
        """인자 하나: {…} 묶음이면 안쪽, 아니면 토큰 하나(명령이면 그 명령 하나)."""
        t = self.peek()
        if t is None:
            return ""
        if t == "{":
            self.next()
            return self.seq(stop="}")
        self.next()
        if re.fullmatch(r"\d{2,}", t):          # \frac12 → 1, 2
            self.toks.insert(self.i, t[1:])
            return t[0]
        if t.startswith("\\"):
            return self.command(t)
        return self.atom(t)

    def raw_group(self):
        """{…} 안의 글을 그대로(\\text 용)."""
        if self.peek() != "{":
            t = self.next()
            return t or ""
        self.next()
        depth, out = 1, ""
        while self.i < len(self.toks):
            t = self.toks[self.i]
            self.i += 1
            if t == "{":
                depth += 1
            elif t == "}":
                depth -= 1
                if depth == 0:
                    break
            out += t
        return out

    def vec_followed_by_op(self):
        t = self.peek()
        if t is None:
            return False
        return t in VEC_NEXT or (t.startswith("\\") and t[1:] in VEC_NEXT_CMD)

    def find_close(self, opener, closer):
        """지금 자리부터 같은 깊이에서 closer 토큰이 있나. (찾았나, 그 사이 같은 깊이에 쉼표가 있나)"""
        depth, comma = 0, False
        for t in self.toks[self.i:]:
            if t == "{":
                depth += 1
            elif t == "}":
                if depth == 0:
                    return False, comma
                depth -= 1
            elif depth == 0 and t == closer:
                return True, comma
            elif depth == 0 and t in ("\\right", "\\end", "\\\\", "&"):
                return False, comma
            elif depth == 0 and t == ",":
                comma = True
        return False, comma

    def opt(self):
        """[…] 선택 인자."""
        if self.peek() == "[":
            self.next()
            out = []
            while self.peek() not in (None, "]"):
                t = self.next()
                out.append(self.command(t) if t.startswith("\\") else self.atom(t))
            self.next()
            return " ".join(x for x in out if x)
        return None

    # ------------------------------------------------------------ 변환
    def atom(self, t):
        if t in ("^", "_"):
            self.script += 1
            a = self.arg()
            self.script -= 1
            return "%s{%s}" % (t, a)
        if t == "&":
            return "&"
        if t == "~":
            return "~"
        if t == "{":
            return "{%s}" % self.seq(stop="}")
        if t == "}":
            return ""
        if t == "#":
            return '"#"'
        if t == '"':
            return '""'
        if t == "`":
            return "'"
        if t == "'":
            return "'"
        if t == "%":
            return "%"
        if t == ",":
            # 쉼표 뒤 빼기는 두 항 사이 빼기로 넓게 잡혀 `` `` `` 이면 4.99pt(평가원 3.67) — `` ` `` 하나
            return "`,`" if self.peek() == "-" else COMMA
        if LATIN.fullmatch(t) and self.need_it:
            # `{rm A} it` 처럼 정체 묶음 바로 뒤에 it 를 두면 한글 수식이 뒤 기호(=, +, ( )의 왼쪽 간격을 지운다
            # (`{rm B} it = 2` 의 B→= 가 -0.5pt, 평가원 +2.7). 그래서 it 는 다음 라틴 글자 바로 앞에 둔다.
            self.need_it = False
            return "it " + t
        return t

    def command(self, t):
        name = t[1:]
        if name in SPACES:
            return SPACES[name]
        if name in DROP:
            return ""
        if name in ("frac", "dfrac", "tfrac", "cfrac"):
            a = self.arg(); b = self.arg()
            return "{{%s} over {%s}}" % (a, b)
        if name == "binom":
            a = self.arg(); b = self.arg()
            return "LEFT ( pile{%s # %s} RIGHT )" % (a, b)
        if name == "sqrt":
            n = self.opt()
            a = self.arg()
            return ("root {%s} of {%s}" % (n, a)) if n else ("sqrt {%s}" % a)
        if name in ACCENT:
            s = "%s {%s}" % (ACCENT[name], self.arg())
            if self.vec_followed_by_op():
                # 벡터·선분(vec, overline …) 뒤 =, +, - : 한글 수식은 꾸밈 묶음 뒤 간격을 지운다(a→= -0.1pt,
                # AB→= 0.0). 평가원 2.7(=), 2.9(+), 3.4(-). `` ` `` 하나면 3.7 / 3.2 / 2.8. 내적 cdot 은 평가원도 붙여 쓴다(0.2)
                s += " `"
            return s
        if name in FONT:
            # 한글 수식의 rm/it 는 묶음 밖으로 이어진다(`{rm P}(A)` 의 A 까지 정체가 된다). 다음 라틴 글자 앞에서
            # it 로 되돌린다(atom). 묶음 바로 뒤 it 는 뒤 기호의 간격을 지운다.
            f = FONT[name]
            if f == "it":
                return "{%s}" % self.arg()
            self.need_it = False
            s = "{%s %s}" % (f, self.arg())
            self.need_it = True
            return s
        if name in ("text", "textup", "mbox", "textnormal", "hbox"):
            s = self.raw_group()
            s = s.replace('"', "'")
            if not s.strip():
                return "~"
            # 한글 수식은 따옴표 안 빈칸을 찍지 않는다(`"이 홀수인 경우"` → `이홀수인경우`). 낱말마다 따옴표로 묶고
            # 빈칸은 `~`(5.52pt, 평가원 낱말 사이 5.28)로 잇는다.
            words = s.split(" ")
            out = "~".join('"%s"' % w if w else "" for w in words)
            return re.sub(r"~{2,}", "~", out)
        if name == "boxed":
            # 문장 속 상자(`$\boxed{\text{(가)}}$`)는 build_exam 이 수식을 끊고 표 상자로 찍는다. 여기 오는 것은
            # 분수 안처럼 끊을 수 없는 자리. 한글 수식 box 에 `~` 를 붙이면 31.7 x 13.4pt(평가원 31.1 x 15.6)
            return "box{~%s~}" % self.arg()
        if name == "left":
            return self.leftright()
        if name == "right":            # 짝 없는 \right
            d = self.next()
            return DELIM.get(d, d) or ""
        if name == "begin":
            return self.env(self.raw_group())
        if name == "end":
            self.raw_group()
            return ""
        if name in GREEK:
            return name
        if name in FUNCS:
            return name
        if name in ("sum", "prod", "int", "oint", "iint", "bigcup", "bigcap"):
            m = {"prod": "prod", "bigcup": "UNION", "bigcap": "INTER"}.get(name, name)
            return m
        if name in SYMBOLS:
            return SYMBOLS[name]
        if name == "\\":
            return "#"
        if name in ("not",):
            nxt = self.next()
            if nxt in ("=",):
                return "!="
            return "not " + (self.command(nxt) if nxt and nxt.startswith("\\") else (nxt or ""))
        if name in ("phantom", "hphantom", "vphantom", "label", "tag"):
            self.arg()
            return ""
        if name in ("stackrel", "overset"):
            a = self.arg(); b = self.arg()
            return "{%s} ^{%s}" % (b, a)
        if name == "pmod":
            return "(mod~%s)" % self.arg()
        self.unknown.append(t)
        return name

    def leftright(self):
        d = self.next()
        if d == "\\":           # 안 쓰이지만 막아 둔다
            d = "\\\\"
        ld = DELIM.get(d, d)
        inner = self.seq(stop="\\right")
        rd_tok = self.next()
        rd = DELIM.get(rd_tok, rd_tok) if rd_tok else None
        if ld is None and rd is None:
            return "{%s}" % inner
        if ld is None:           # \left. … \right|  → 오른쪽만 큰 괄호
            return "LEFT ~ %s RIGHT %s" % (inner, rd) if rd != "|" else "{%s} |" % inner
        if rd is None:           # \left\{ … \right.  (경우 나눔)
            if ld == "lbrace" and inner.strip().startswith("{cases"):
                return inner
            return "LEFT %s %s RIGHT ~" % (ld, inner) if ld != "lbrace" else "LEFT lbrace %s RIGHT ~" % inner
        return "LEFT %s %s RIGHT %s" % (ld, inner, rd)

    def env(self, name):
        if name == "array" and self.peek() == "{":
            self.raw_group()                      # 열 지정 {c|c}
        body = self.seq(stop="\\end")
        self.raw_group()
        rows = [r.strip() for r in body.split("#")]
        while rows and not rows[-1]:
            rows.pop()
        rows = [re.sub(r"^\s*\[[^\]]*\]", "", r) for r in rows]
        if name.startswith("cases") or name == "dcases":
            return CASES_MARK + cases(rows)
        if name in ("array", "matrix", "smallmatrix", "aligned", "align", "align*", "gathered", "split",
                    "eqnarray"):
            if name == "array":
                pass
            if name in ("aligned", "align", "align*", "gathered", "split", "eqnarray"):
                return "{eqalign{%s}}" % " # ".join(rows)
            return "{matrix{%s}}" % " # ".join(rows)
        if name in ("pmatrix",):
            return "{pmatrix{%s}}" % " # ".join(rows)
        if name in ("bmatrix",):
            return "{bmatrix{%s}}" % " # ".join(rows)
        if name in ("vmatrix",):
            return "{dmatrix{%s}}" % " # ".join(rows)
        self.unknown.append("\\begin{%s}" % name)
        return "{matrix{%s}}" % " # ".join(rows)

    def seq(self, stop=None):
        out = []
        while True:
            t = self.peek(skip_ws=False)
            if t is None:
                break
            if stop == "}" and t == "}":
                self.next(skip_ws=False)
                break
            if stop in ("\\right", "\\end", "|", "\\}") and t == stop:
                self.next(skip_ws=False)
                break
            if stop == "\\right" and t == "\\middle":
                self.next(skip_ws=False)
                d = self.next()
                out.append(DELIM.get(d, d) or "")
                continue
            t = self.next(skip_ws=False)
            if t.isspace():
                continue
            if t == "|" and stop != "|" and self.find_close("|", "|")[0]:
                # 절댓값: 평가원은 늘 LEFT | … RIGHT | (막대 12.2pt, 안쪽 -0.17). 그냥 `|` 는 11.0pt 에 간격 +0.07
                inner = self.seq(stop="|")
                out.append("LEFT | %s RIGHT |" % inner)
                continue
            if t == "\\{":
                found, comma = self.find_close("\\{", "\\}")
                if found and not comma:
                    # 수열 {a_n}: 평가원은 LEFT lbrace (12.2pt, a_n 에 붙음). 집합 {1, 2, 3} 은 그냥 중괄호(11.2pt)
                    inner = self.seq(stop="\\}")
                    out.append("LEFT lbrace %s RIGHT rbrace" % inner)
                    continue
            if t.startswith("\\") and len(t) > 1:
                if t == "\\\\":
                    out.append("#")
                else:
                    if t[1:] in FUNCS and out and out[-1].split()[-1:] in (["times"], ["cdot"]):
                        # `times tan theta`: 한글 수식이 tan 을 함수로 알아보지 못해 기울여 찍는다(t a n 낱자).
                        # `` ` `` 를 끼우면 바로 선 tan, × → tan 2.21pt(평가원 × → 숫자·a 2.2)
                        out.append("`")
                    piece = self.command(t)
                    self.rel_gap(out, piece)
                    out.append(piece)
            else:
                piece = self.atom(t)
                if piece == "-" and out and out[-1].split()[-1:] and out[-1].split()[-1] in RELS:
                    # `= -2`: 한글 수식은 관계 기호 뒤 간격을 지운다(-0.3pt). `it` 를 끼우면 평가원과 같은 +1.99
                    piece = "it -"
                if KICE_REL_GAPS and out and re.fullmatch(r"[A-Za-z]", piece) and re.fullmatch(r"_\{.*\}", out[-1]):
                    # 첨자 문자의 곱 `a_2a_4`·`a_ka_{k+1}`: 한글 수식은 첨자 끝 → 다음 문자 0.96pt, 평가원 1.80
                    # (2022.09 공통 3 `a_2a_4=36`, 600dpi 잉크). 첨자 안 끝에 `` ` `` 를 넣으면 1.92(밖에 넣으면 2.40).
                    # 사용자 지적 2026-10-14(1회 3번). 조판.md 조1-15 (4)
                    out[-1] = out[-1][:-1] + "`}"
                self.rel_gap(out, piece)
                out.append(piece)
        return join(out)

    def rel_gap(self, out, piece):
        """관계 기호 간격(머리 KICE_REL_GAPS 설명): 닫는 큰 괄호 → 관계 기호 사이 `^{}`, `=` 뒤 `` ` ``."""
        if not KICE_REL_GAPS or not out or not piece:
            return
        head = piece.split()[:1]
        if head and head[0] in REL_AFTER_FRAC and out[-1].startswith("{{") and " over " in out[-1] \
                and self.script == 0:
            out.append("^{}")
        elif head and head[0] in REL_AFTER_RIGHT and RIGHT_CLOSE.search(out[-1]):
            out.append("^{}")
        elif out[-1] == "=" and self.script == 0 and piece[0] not in "`~#&" + CASES_MARK \
                and not (piece.startswith("{{") and " over " in piece):
            out.append("`")


CASES_MARK = "\x01"


def cases(rows):
    """경우 나눔. 평가원 2021학년도 이후 실측(2022~2027 40곳, `평가원_글조판양식.md`):
      - 두 줄 기준선 간격 25.5pt 안팎(23.9~27.8). 한글 수식 cases 그대로는 15.2pt 라 좁다.
        마지막 줄을 뺀 줄을 `eqalign{… # }` 로 감싸 빈 줄 하나를 더하면 24.0(첨자 없는 줄)~26.3(a_n 줄).
        (팀 시그마 1회 원고 hwpx 의 경우 나눔이 쓰던 방법)
      - 큰 중괄호 → 식 첫 글자 5.29pt: 줄 앞 `~` (없으면 2.5)
      - 식 끝 → 조건 `(` 15.2pt(평가원 10~17, 가운데 15.9): `&&` 뒤 `~`. 조건 괄호는 LEFT ( … RIGHT )(평가원 11.15pt 괄호)
      - `=` → 큰 중괄호 3.37pt(40곳 중 29곳, 나머지 2.0): 앞에 `` ` `` (없으면 1.99)"""
    out = []
    for k, r in enumerate(rows):
        e, _, c = r.partition("&")
        e, c = e.strip(), c.strip()
        if c.startswith("(") and c.endswith(")"):
            c = "LEFT ( %s RIGHT )" % c[1:-1].strip()
        last = k == len(rows) - 1
        if last:
            out.append("~%s && ~%s" % (e, c) if c else "~%s" % e)
        else:
            out.append("eqalign{~%s # }&&eqalign{~%s # }" % (e, c) if c else "eqalign{~%s # }" % e)
    return "{cases{%s}}" % " # ".join(out)


def join(pieces):
    """조각을 빈칸 하나로 잇는다. 한글 수식에서 빈칸은 보이지 않고 낱말만 가른다
    (보이는 띄어쓰기는 `~`, 좁은 띄어쓰기는 `` ` ``). 글자를 하나씩 띄워 두므로 라틴 글자가 이어져도
    `in`, `it`, `over` 같은 예약어가 우연히 생기지 않는다."""
    return re.sub(r" {2,}", " ", " ".join(p for p in pieces if p)).strip()


def conv(src, unknown=None):
    c = Conv(src)
    s = c.seq()
    s = re.sub(r"^\s*%s" % CASES_MARK, "", s).replace(CASES_MARK, "` ")
    if unknown is not None:
        unknown.extend(c.unknown)
    return s


def digits(s):
    """숫자열 모음(순서 무시 비교용). 한글 수식의 `rm`·`over` 같은 낱말은 숫자가 없어 그대로 비교된다."""
    return sorted(re.findall(r"\d+", s))


def roundtrip(src):
    """LaTeX 와 변환 결과의 숫자 다중집합 비교. 다르면 (원본 숫자, 결과 숫자)."""
    out = conv(src)
    a, b = digits(src.replace("\\,", " ")), digits(out)
    return None if a == b else (a, b)
