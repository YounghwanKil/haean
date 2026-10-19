"""Load named JSON inputs without discovering or executing external code."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import import_module
import json
from pathlib import Path
import re


TRACKS = {
    "leet_reasoning": ("leet", "추리논증", None),
    "psat_verbal": ("psat5", "언어논리", 5),
    "psat_data": ("psat5", "자료해석", 5),
    "psat_situation": ("psat5", "상황판단", 5),
}
REQUIRED = {"format_rules", "content_rules", "content_config", "rules_config"}
ROLES = REQUIRED | {"labels"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"중복 JSON 키: {key}")
        result[key] = value
    return result


def read_json(path):
    def nonfinite(value):
        raise ValueError(f"비유한 JSON 수치: {value}")
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                          object_pairs_hook=_pairs, parse_constant=nonfinite)
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"JSON 입력을 읽을 수 없습니다: {path}") from exc


def identity(value):
    if not isinstance(value, dict) or value.get("track") not in TRACKS:
        raise ValueError("회차 설계는 LEET 추리논증·PSAT 5급 세 과목만 지원합니다")
    expected = TRACKS[value["track"]]
    actual = (value.get("exam"), value.get("subject"), value.get("exam_grade"))
    if actual != expected or (expected[2] is not None and type(actual[2]) is not int):
        raise ValueError("회차 프로필의 시험·과목·급수 불일치")


@dataclass(frozen=True)
class Profile:
    manifest: dict
    inputs: dict[str, Path]
    values: dict[str, dict]

    def engine(self):
        # Import names come only from the fixed allowlist, never from source data.
        module = import_module("haean.composition.engines." + self.manifest["track"])
        try:
            return module.Engine(**self.values)
        except (KeyError, TypeError, IndexError, ZeroDivisionError) as exc:
            raise ValueError(f"회차 프로필 구조 오류: {exc}") from exc


def load_profile(path: Path) -> Profile:
    path = Path(path).resolve()
    original_sha = sha(path)
    value = read_json(path)
    identity(value)
    if value.get("schema_version") != 1 or value.get("usage") != "development":
        raise ValueError("개발용 schema_version=1 회차 프로필이 필요합니다; holdout은 사용할 수 없습니다")
    origin = value.get("origin")
    if not isinstance(origin, dict) or any(not isinstance(origin.get(k), str) or not origin[k].strip()
                                           for k in ("source", "revision")):
        raise ValueError("프로필의 원천과 버전을 origin.source/revision에 기록하세요")
    records = value.get("files")
    if not isinstance(records, list):
        raise ValueError("프로필 files 목록이 필요합니다")
    inputs, values, files = {"profile.json": path}, {}, []
    for record in records:
        if not isinstance(record, dict) or record.get("role") not in ROLES:
            raise ValueError("지원하지 않는 프로필 파일 역할")
        role = record["role"]
        if role in values:
            raise ValueError("프로필 파일 역할 중복: " + role)
        if record.get("usage") != "development" or record.get("exam_grade") != value["exam_grade"]:
            raise ValueError("프로필 입력의 분할·급수가 다릅니다: " + role)
        if not isinstance(record.get("locator"), str) or not record["locator"].strip():
            raise ValueError("입력 출처 locator 누락: " + role)
        if not isinstance(record.get("path"), str) or not record["path"]:
            raise ValueError("입력 경로 누락: " + role)
        source = (path.parent / record["path"]).resolve()
        if source.suffix.lower() != ".json":
            raise ValueError("회차 프로필은 JSON 자료만 읽습니다: " + role)
        expected = record.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or sha(source) != expected:
            raise ValueError("프로필 파일 해시 불일치: " + role)
        loaded = read_json(source)
        if not isinstance(loaded, dict):
            raise ValueError("프로필 파일은 JSON 객체여야 합니다: " + role)
        if sha(source) != expected:
            raise ValueError("읽는 중 프로필 입력이 바뀌었습니다: " + role)
        values[role] = loaded
        inputs[role + ".json"] = source
        files.append({**record, "path": str(source)})
    if not REQUIRED <= values.keys() or (value["track"] == "psat_verbal" and "labels" not in values):
        raise ValueError("필수 회차 프로필 파일 누락 (언어논리는 labels도 필요)")
    if sha(path) != original_sha:
        raise ValueError("읽는 중 프로필 manifest가 바뀌었습니다")
    manifest = {**value, "files": files, "manifest_path": str(path), "manifest_sha256": original_sha,
                "source_semantics_verified": False}
    return Profile(manifest, inputs, values)
