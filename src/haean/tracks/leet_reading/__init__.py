"""LEET 언어이해 트랙: 지문 1개에 3문항 세트, 30문항.

인지 과제·내용 영역은 법학전문대학원협의회 공식 가이드의 분류를 쓴다.
조판 프로필은 leet_verbal(+ 해설 leet_verbal_solutions).
"""
from ..core.track import Track


class LeetReading(Track):
    name = "leet_reading"
    label = "LEET 언어이해"
    comment_required = False     # 지문 총평·출처는 세트 해설에
    typeset_profiles = {None: "leet_verbal"}
    polish_note = '언어이해 통합데이터가 들어오면 `haean tools style leet_reading`으로 만든다.'
    vocab = {
        "area": ["법철학", "인문", "사회", "과학기술", "예술", "법", "경제", "철학", "언어", "역사"],   # 해설지 양식 목록
        "item_type": ["주제·구조·관점 파악", "정보 확인·재구성", "추론·해석", "평가·적용"],
        "item_format": None,
        "discourse": None,
    }
    set_size = 3
    set_required = True
    set_mixed_types = True     # 한 세트의 세 문항은 서로 다른 인지 과제(명세 item_type='혼합')

    def max_items(self, grade=None):
        return 30

    def check_item(self, item, brief):
        return [], []


TRACK = LeetReading()
