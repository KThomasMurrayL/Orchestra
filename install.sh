#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

if [ -n "${BIN_DIR:-}" ]; then
  :
elif [ -d /opt/homebrew/bin ] && [ -w /opt/homebrew/bin ]; then
  BIN_DIR=/opt/homebrew/bin
elif [ -w /usr/local/bin ]; then
  BIN_DIR=/usr/local/bin
else
  BIN_DIR="$HOME/.local/bin"
fi
mkdir -p "$BIN_DIR"

echo "==> creating virtualenv at $HERE/.venv"
"$PYTHON" -m venv "$HERE/.venv"
"$HERE/.venv/bin/pip" install -q -U pip
echo "==> installing orchestra (with voice support)"
(cd "$HERE" && "$HERE/.venv/bin/pip" install -q -e '.[voice]')

ln -sf "$HERE/.venv/bin/orchestra" "$BIN_DIR/orchestra"
echo "==> installed: $BIN_DIR/orchestra"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "NOTE: add $BIN_DIR to your PATH to run 'orchestra' from anywhere." ;;
esac

"$BIN_DIR/orchestra" --version
