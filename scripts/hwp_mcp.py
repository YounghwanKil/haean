#!/usr/bin/env python3
"""Project-local HWP MCP entrypoint. No remote upload or credentials."""
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
binary = root / 'data/bin/hwp'
if not binary.is_file():
    print('Run ./haean setup-layout first', file=sys.stderr)
    raise SystemExit(2)
os.execv(str(binary), [str(binary), 'mcp', '--root', str(root), '--font-dir', str(root / 'data/fonts')])
