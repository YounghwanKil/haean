#!/bin/sh
set -eu
HAEAN_INSTALL_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HAEAN_PYTHON=${HAEAN_PYTHON:-python3}
if ! "$HAEAN_PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  printf '%s\n' 'Python 3.11 이상이 필요합니다. 설치 후 HAEAN_PYTHON=python3.13 ./install.sh 로 지정할 수 있습니다.' >&2
  exit 2
fi
exec "$HAEAN_PYTHON" "$HAEAN_INSTALL_ROOT/scripts/install.py" "$@"
