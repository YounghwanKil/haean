"""Expose portable role instructions for runtimes without custom-role selection."""
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def role_packet(name: str):
    roles = [tomllib.loads(p.read_text()) for p in sorted((ROOT / '.codex/agents').glob('*.toml'))]
    role = next((r for r in roles if r['name'] == name), None)
    if role is None:
        raise ValueError('알 수 없는 역할: ' + name)
    return {**role, 'fresh_context': name == 'haean_blind_solver',
            'dispatch': 'custom-role 선택 인자가 없으면 developer_instructions를 일반 서브에이전트의 작업 지침으로 전달',
            'blind_input_rule': '풀이자에게는 공개 문항과 풀이 스키마만 전달. 정답·해설·부모 대화 금지.'}
