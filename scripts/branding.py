"""Portable block-character companion to the HAEAN wave/book mascot."""
import unicodedata

# Original terminal artwork; . = transparent, N = ink, B = ocean, W = paper/foam.
PIXELS = (
    '          NNNNN         ',
    '       NNNWWWWWNN       ',
    '      NWWBBBBBWWWN      ',
    '     NWBBBBBBBWWNN      ',
    '    NWBBBBBBNNNN        ',
    '   NWBBBBBBNWNN         ',
    '  NWBBBBBBBBWNN    BN   ',
    '  NBBBBBBBBBBWWN        ',
    ' NBBNNBBBBBNNBBBN       ',
    ' NBBNWBBBBBNWBBBN       ',
    ' NBBNNBBBBBNNBBBN       ',
    ' NBBBBBBNBBBBBBBN       ',
    '  NBBBBBBNNBBBBN        ',
    ' NWWNNBBBBBBNNWWN       ',
    ' NWWWWNNBBNNWWWWN       ',
    'NBWWWWWWNNWWWWWWBN  WN  ',
    'NBWWWWWWNNWWWWWWBN WBN  ',
    'NNWWWWWWNNWWWWWWNNWBBN  ',
    '  NWWWWWNNWWWWWN BBBBN  ',
    '  NWWWWWNNWWWWWNBBBBN   ',
    '   NWWWWNNWWWWNBBBN     ',
    '   BBNWWNNWWN BBBN      ',
    '  BBBBNWNNWN BBBBB      ',
    '   NNNNNNNNN NNNN       ',
)
PALETTE = {'N': (15, 23, 42), 'B': (56, 189, 248), 'W': (248, 250, 252)}
PLAIN = ('        ~~~', '      / ~  \\', '     / o  o \\', '     \\  u   /', '    __\\____/___', '   /   /|\\    /', '  /___/ | \\__/', '      ~~~~~')


def display_width(text):
    return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in text)


def pixel_lines():
    rows = [r.ljust(24, '.') for r in PIXELS]
    result = []
    for top, bottom in zip(rows[::2], rows[1::2]):
        line = ''
        for a, b in zip(top, bottom):
            a, b = PALETTE.get(a), PALETTE.get(b)
            if a is None and b is None:
                line += '\033[0m '
            elif a == b:
                line += '\033[0;38;2;%d;%d;%dm█' % a
            elif a is None:
                line += '\033[0;38;2;%d;%d;%dm▄' % b
            elif b is None:
                line += '\033[0;38;2;%d;%d;%dm▀' % a
            else:
                line += ('\033[0;38;2;%d;%d;%d;48;2;%d;%d;%dm▀' % (*a, *b))
        result.append(line + '\033[0m')
    return result


def welcome_lines(width, color=False, madmax=False, skill='haean'):
    """A 74-column card, or a compact card for smaller terminals."""
    accent = '\033[36;1m' if color else ''
    reset = '\033[0m' if color else ''
    mode = 'MADMAX · 승인/샌드박스 생략' if madmax else 'STANDARD · 기존 권한 설정'
    if width < 76:
        return [f'{accent}  ≋ haean / 해안{reset}', *('  '+s for s in PLAIN),
                '  '+mode, '  LEET / PSAT · $'+skill, '  자연어로 요청하세요.']
    inner = 70
    result = [accent + '  ╭─ HAEAN / 해안 ' + '─' * 55 + '╮' + reset]
    messages = [
        '해안에 오신 것을 환영합니다.', '',
        mode, '$' + skill, '',
        'LEET 추리논증 · 언어이해', 'PSAT 5급 · 7급', '',
        '출제 → 독립 풀이 → 검토 → 출력',
        '자연어로 작업을 요청하세요.',
        '스킬 목록  haean skills', 'HUD 확인   haean hud',
    ]
    art = pixel_lines() if color else [s.ljust(24) for s in PLAIN] + [' '*24]*4
    for left, right in zip(art, messages):
        line = '  │  ' + left + '  ' + right
        padding = inner - 2 - 24 - 2 - display_width(right)
        result.append(line + ' '*max(0, padding) + '│')
    result.append(accent + '  ╰' + '─'*inner + '╯' + reset)
    return result
