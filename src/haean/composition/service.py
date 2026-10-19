"""Generate and seal optional 40-slot composition proposals, without a model."""
from __future__ import annotations

from pathlib import Path

from .. import execution_provenance as provenance
from .profiles import identity, load_profile, read_json, sha


LIMITS = [
    "형식·내용설계는 출제 제안이며 문항 작성·정답 검증·전문가 검토를 수행하지 않았습니다.",
    "외부 규칙의 분류·통계·기출 참고 ID의 의미와 정확성을 개별 원문에 대조하지 않았습니다.",
    "프로필의 출처 익명화·우회 점검 등 정책은 검증 전 제안입니다. 기존 배정·출처·논리 조건이 우선합니다.",
    "소재 대장은 누적 생성물의 논리 구조·오답 함정 중복 검토를 대체하지 않습니다.",
    "7급·언어이해·20문항을 40문항 설계의 절단 또는 이름 변경으로 만들지 않습니다.",
]


def _write(path, value):
    with Path(path).open("xb") as stream:
        stream.write(provenance.encoded(value))


def _slots(value, key):
    rows = value.get(key) if isinstance(value, dict) else None
    if not isinstance(rows, list) or len(rows) != 40 or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{key}: 회차 형식·내용설계에 40개 슬롯이 필요합니다")
    numbers = [row.get("slot") for row in rows]
    if any(type(n) is not int for n in numbers) or sorted(numbers) != list(range(1, 41)):
        raise ValueError(f"{key}: 1–40 슬롯 번호 누락·중복")
    return {row["slot"]: row for row in rows}


def _validate_design(engine, value):
    formatted = _slots(value["format_design"], "slots")
    content = _slots(value["content_spec"], "슬롯")
    for number, row in formatted.items():
        if row.get("type_code") is not None and row["type_code"] != content[number].get("type_code"):
            raise ValueError(f"{number}: 형식·내용설계 유형 코드 불일치")
    # sample-only knobs (e.g. search tries) are not validation options.
    kwargs = {k: v for k, v in value["options"].items() if k in {"presets", "custom"}}
    report = engine.validate_report(value["format_design"], **kwargs)
    if report["errors"]:
        raise ValueError("형식설계 검증 실패: " + "; ".join(report["errors"]))
    return report


def design(profile_path, out, *, seed=0, options=None, ledger_path=None):
    """Create a new proposal and preserve failures. Never overwrite a run."""
    if type(seed) is not int:
        raise ValueError("seed는 정수여야 합니다")
    options = {} if options is None else options
    if not isinstance(options, dict) or ("size" in options and options["size"] != 40):
        raise ValueError("회차 연결은 40문항만 지원하며 options는 JSON 객체여야 합니다")
    provenance.encoded(options)
    profile = load_profile(profile_path)
    engine = profile.engine()
    inputs = dict(profile.inputs)
    ledger = None
    ledger_sha = None
    if ledger_path is not None:
        inputs["ledger.json"] = Path(ledger_path).resolve()
        ledger_sha = sha(ledger_path)
        ledger = read_json(ledger_path)
        if not isinstance(ledger, dict):
            raise ValueError("소재 대장은 JSON 객체여야 합니다")
        if sha(ledger_path) != ledger_sha:
            raise ValueError("읽는 중 소재 대장이 변경되었습니다")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    parameters = {"track": profile.manifest["track"], "profile_sha256": profile.manifest["manifest_sha256"],
                  "seed": seed, "options": options, "model_calls": 0}
    try:
        snapshot = provenance.capture(out / "execution", inputs=inputs,
            instructions={"scope": "외부 프로필을 통한 40슬롯 형식·내용설계 제안. " + " ".join(LIMITS)},
            schemas={"artifact": {"schema_version": 1, "slot_numbers": "unique integers 1..40"}},
            parameters=parameters)
        # Bind the loaded dictionaries to the bytes captured above.
        if load_profile(profile_path).manifest != profile.manifest:
            raise ValueError("프로필이 설계 시작 전에 변경되었습니다")
        if ledger_sha is not None and read_json(snapshot)["inputs"]["ledger.json"]["sha256"] != ledger_sha:
            raise ValueError("소재 대장이 설계 시작 전에 변경되었습니다")
        value = {"schema_version": 1, **{k: profile.manifest[k] for k in ("exam", "subject", "track", "exam_grade")},
                 "seed": seed, "options": options, "profile": profile.manifest,
                 "format_design": engine.sample(seed=seed, **options),
                 "human_approved": False, "quality_verified": False, "model_generation_executed": False}
        # Validate format before asking the content stage to run.
        _slots(value["format_design"], "slots")
        report = engine.validate_report(value["format_design"],
            **{k: v for k, v in options.items() if k in {"presets", "custom"}})
        if report["errors"]:
            raise ValueError("형식설계 검증 실패: " + "; ".join(report["errors"]))
        value["content_spec"] = engine.content(value["format_design"], ledger=ledger, seed=seed)
        report = _validate_design(engine, value)
        check = provenance.verify(snapshot)
        if not check["valid"]:
            raise ValueError("설계 중 코드·입력 변경: " + "; ".join(check["issues"]))
        value["execution_snapshot"] = {"path": str(snapshot), "sha256": sha(snapshot)}
        value["validation"] = {**report, "unavailable_checks": LIMITS}
        # Preserve complete algorithm outputs, not just slot-count diagnostics.
        _write(out / "format.json", value["format_design"])
        _write(out / "content.json", value["content_spec"])
        outputs = provenance.capture(out / "output-evidence",
            inputs={"format.json": out / "format.json", "content.json": out / "content.json",
                    "input-manifest.json": snapshot},
            instructions={"scope": "알고리즘이 생성한 형식·내용 원문 전체를 실행 입력과 연결"},
            schemas={}, parameters={"input_snapshot_sha256": sha(snapshot), "seed": seed})
        value["output_snapshot"] = {"path": str(outputs), "sha256": sha(outputs)}
        _write(out / "design.json", value)
        (out / "design.sha256").write_text(sha(out / "design.json") + "\n")
        return {"design": str(out / "design.json"), "sha256": sha(out / "design.json"),
                "track": value["track"], "slots": 40, "validation": value["validation"],
                "model_generation_executed": False, "human_approved": False}
    except Exception as exc:
        _write(out / "failure.json", {"state": "failed", "error": f"{type(exc).__name__}: {exc}",
                                      "parameters": parameters, "human_approved": False})
        raise


def load_design(path):
    """Fail closed on changed input, code, profile or output before binding."""
    path = Path(path).resolve()
    if sha(path) != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("회차 설계 출력 해시 불일치")
    value = read_json(path)
    identity(value)
    if value.get("schema_version") != 1 or any(value.get(k) is not False for k in
        ("human_approved", "quality_verified", "model_generation_executed")):
        raise ValueError("회차 설계 상태·버전 불일치")
    try:
        profile = load_profile(value["profile"]["manifest_path"])
        if value["profile"] != profile.manifest or any(value[k] != profile.manifest[k]
                                                      for k in ("exam", "subject", "track", "exam_grade")):
            raise ValueError("설계 프로필·시험 정보 불일치")
        reference = value["execution_snapshot"]
        check = provenance.verify(Path(reference["path"]), expected_sha256=reference["sha256"])
        if not check["valid"]:
            raise ValueError("회차 설계 실행 근거 불일치: " + "; ".join(check["issues"]))
        outputs = value["output_snapshot"]
        check = provenance.verify(Path(outputs["path"]), expected_sha256=outputs["sha256"])
        if not check["valid"]:
            raise ValueError("회차 설계 산출 근거 불일치: " + "; ".join(check["issues"]))
        output_manifest = read_json(outputs["path"])
        if output_manifest["parameters"] != {"input_snapshot_sha256": reference["sha256"], "seed": value["seed"]}:
            raise ValueError("설계 산출 매개변수 불일치")
        if output_manifest["inputs"]["input-manifest.json"]["sha256"] != reference["sha256"]:
            raise ValueError("설계 산출 실행 연결 불일치")
        for field, name in (("format_design", "format.json"), ("content_spec", "content.json")):
            # Original JSON bytes are already verified above. Compare parsed
            # values: integer mapping keys become strings on a JSON round trip,
            # which can change sort order without changing the saved data.
            if value[field] != read_json(output_manifest["inputs"][name]["path"]):
                raise ValueError("형식·내용설계 원문이 생성 당시와 다릅니다: " + field)
        manifest = read_json(reference["path"])
        expected_parameters = {"track": value["track"], "profile_sha256": profile.manifest["manifest_sha256"],
                               "seed": value["seed"], "options": value["options"], "model_calls": 0}
        if manifest["parameters"] != expected_parameters:
            raise ValueError("설계 실행 매개변수 불일치")
        for name, source in profile.inputs.items():
            if manifest["inputs"][name]["path"] != str(source) or manifest["inputs"][name]["sha256"] != sha(source):
                raise ValueError("설계 실행 입력 불일치: " + name)
        report = _validate_design(profile.engine(), value)
        if value["validation"] != {**report, "unavailable_checks": LIMITS}:
            raise ValueError("설계 검증 결과 불일치")
    except (KeyError, TypeError) as exc:
        raise ValueError("불완전한 회차 설계 패킷") from exc
    return value
