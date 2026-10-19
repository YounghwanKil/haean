# -*- coding: utf-8 -*-
"""원고 자리(경로) 다루기. 경로는 dict 키·list 번호의 튜플: ("발문",) ("지문", 2) ("지문", 2, "내용", 0) ("선지", 4).

줄 나눔 결과를 원고에 되쓰거나(set_body), 옛 줄바꿈을 지울 때(unwrap) 쓴다.
"""
import re

NON_TEXT_KEYS = {"표", "그림", "폭", "id", "정답", "해설", "profile", "그림선지배치", "새단", "이어붙이기",
                 "가로", "세로", "머리행", "열폭", "정렬"}


def get_at(root, path):
    x = root
    for k in path:
        x = x[k]
    return x


def text_key(d):
    """dict 블록에서 글이 든 키."""
    if "글" in d:
        return "글"
    for k, v in d.items():
        if k not in NON_TEXT_KEYS and isinstance(v, str):
            return k
    return None


def set_body(root, path, prefix, body):
    """path 자리 글을 prefix + body 로(dict 블록이면 그 글 키에)."""
    parent = get_at(root, path[:-1]) if len(path) > 1 else root
    k = path[-1]
    v = parent[k]
    if isinstance(v, dict):
        tk = text_key(v)
        if tk:
            v[tk] = prefix + body          # dict 블록의 prefix 는 글 키 안에서 body 앞부분(예: 조문 글의 "① ")
    else:
        parent[k] = prefix + body


def join_lines(s):
    return re.sub(r"\s*\n\s*", " ", s)


def unwrap(obj, skip=("표", "그림", "해설")):
    """글 안의 줄바꿈(\\n)을 빈칸으로(다시 나누기 전). 표·그림·해설은 건드리지 않는다."""
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i] = join_lines(v)
            else:
                unwrap(v, skip)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in skip:
                continue
            if isinstance(v, str):
                if k not in NON_TEXT_KEYS:
                    obj[k] = join_lines(v)
            else:
                unwrap(v, skip)
    return obj
