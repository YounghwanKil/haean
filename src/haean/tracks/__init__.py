"""과목별 생성 트랙. 트랙 하나 = 과목 하나(어휘·세트·지침·검사·조판 프로필).

새 과목을 붙이려면 tracks/<이름>/ 에 __init__.py(TRACK)와 rules/ 를 만들고 아래 목록에 이름을 더한다.
"""
from importlib import import_module

NAMES = ("leet_reasoning", "leet_reading", "psat_verbal", "psat_data", "psat_situation")


def get(name):
    if name not in NAMES:
        raise ValueError(f"알 수 없는 트랙 {name}. 가능: {', '.join(NAMES)}")
    return import_module(f"haean.tracks.{name}").TRACK


def all_tracks():
    return [get(n) for n in NAMES]
