# -*- coding: utf-8 -*-
"""조판 프로필. 프로필 = 양식 하나 + 그 양식의 규칙. 이름으로 부른다(api.load_profile("psat5_data")).

| 이름 | 시험지 | 해설 프로필 |
|---|---|---|
| leet_reasoning | LEET 추리논증 (40문항·20쪽, 한 단에 한 문항) | leet_reasoning_solutions |
| leet_verbal | LEET 언어이해 (30문항·15쪽, 세트) | leet_verbal_solutions |
| psat5_language | PSAT 언어논리 5급(심화) | psat_solutions(언어논리) |
| psat5_situation | PSAT 상황판단 5급(심화) | psat_solutions(상황판단) |
| psat5_data | PSAT 자료해석 5급(심화) | psat_solutions(자료해석) |

psat_common 은 PSAT·언어이해 공통 흐름 조판 엔진(프로필 아님). 7급(기본)은 양식 hwpx 를 받으면 psat7_* 로 추가한다.
"""
DEFAULT = "leet_reasoning"
PROBLEM_PROFILES = ("leet_reasoning", "leet_verbal", "psat5_language", "psat5_situation", "psat5_data")
