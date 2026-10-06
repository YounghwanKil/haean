"""Fresh Codex CLI sessions using the existing ChatGPT subscription login."""
from __future__ import annotations
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def strict_schema(value):
    if isinstance(value, list): return [strict_schema(v) for v in value]
    if not isinstance(value, dict): return value
    result = {k: strict_schema(v) for k, v in value.items() if k != "default"}
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    if "const" in result:
        result["enum"] = [result.pop("const")]
    return result


class CodexProvider:
    def __init__(self, model="gpt-6-astra", max_calls=12, timeout=600, trace_dir=None):
        self.binary = shutil.which("codex")
        if not self.binary: raise ValueError("Codex CLI가 필요합니다. codex login으로 ChatGPT 로그인하세요.")
        login = subprocess.run([self.binary, "login", "status"], capture_output=True, text=True)
        if login.returncode or "ChatGPT" not in login.stdout + login.stderr:
            raise ValueError("ChatGPT 구독 로그인 상태가 아닙니다. codex login을 실행하세요.")
        self.model, self.max_calls, self.timeout = model, max_calls, timeout
        self.calls, self.usage = 0, []
        self.trace_dir = Path(trace_dir) if trace_dir else None
        if self.trace_dir: self.trace_dir.mkdir(parents=True, exist_ok=True)

    def call(self, stage, instructions, payload, schema):
        if self.calls >= self.max_calls: raise RuntimeError("Codex 세션 실행 한도에 도달했습니다")
        self.calls += 1
        with tempfile.TemporaryDirectory(prefix="haean-codex-") as folder:
            root = Path(folder)
            schema_path, output = root / "schema.json", root / "result.json"
            schema_path.write_text(json.dumps(strict_schema(schema.model_json_schema()), ensure_ascii=False))
            task = instructions + "\n도구·파일 탐색·웹 검색·재위임을 하지 말고 아래 입력만으로 답하라. 최종 출력은 스키마 JSON이다.\n" + json.dumps(payload, ensure_ascii=False)
            prefix = f"{self.calls:02}-{stage}"
            if self.trace_dir:
                (self.trace_dir / f"{prefix}.input.json").write_text(json.dumps({
                    'instructions':instructions, 'payload':payload, 'model':self.model,
                    'schema':json.loads(schema_path.read_text()),
                    'task_sha256':hashlib.sha256(task.encode()).hexdigest()}, ensure_ascii=False))
            command = [self.binary, "exec", "--ephemeral", "--skip-git-repo-check", "--json",
                       "-C", str(root), "-s", "read-only", "-m", self.model,
                       "--output-schema", str(schema_path), "-o", str(output), "-"]
            env = os.environ.copy()
            for key in ("OPENAI_API_KEY", "CODEX_API_KEY"):
                env.pop(key, None)
            started = time.monotonic()
            try:
                result = subprocess.run(command, input=task, text=True, capture_output=True, env=env, timeout=self.timeout)
            except subprocess.TimeoutExpired as exc:
                if self.trace_dir:
                    for suffix, value in [('jsonl',exc.stdout),('stderr.txt',exc.stderr)]:
                        value = value.decode('utf-8',errors='replace') if isinstance(value,bytes) else value or ''
                        (self.trace_dir / f"{prefix}.{suffix}").write_text(value)
                self.usage.append({'stage':stage,'model':self.model,'seconds':time.monotonic()-started,
                                   'usage':None,'returncode':None,'timed_out':True})
                raise
            if self.trace_dir:
                (self.trace_dir / f"{self.calls:02}-{stage}.jsonl").write_text(result.stdout)
                (self.trace_dir / f"{self.calls:02}-{stage}.stderr.txt").write_text(result.stderr)
            events = []
            for line in result.stdout.splitlines():
                try: events.append(json.loads(line))
                except json.JSONDecodeError: continue
            tool_events = [e for e in events if e.get("item", {}).get("type") not in {None, "reasoning", "agent_message"}]
            usage = next((e.get("usage") for e in reversed(events) if e.get("type") == "turn.completed"), None)
            self.usage.append({"stage": stage, "model": self.model, "seconds": time.monotonic() - started,
                               "usage": usage, "returncode": result.returncode, "tool_events": len(tool_events)})
            if result.returncode:
                raise RuntimeError(f"Codex {stage} 실행 실패. trace stderr를 확인하세요. exit={result.returncode}")
            if tool_events:
                raise RuntimeError(f"Codex {stage}가 도구를 사용해 입력 격리 조건을 위반했습니다. 결과를 채택하지 않습니다.")
            if not output.exists(): raise RuntimeError("Codex 구조화 결과가 없습니다")
            return schema.model_validate_json(output.read_text())
