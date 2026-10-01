#!/bin/bash
# undeploy.sh — 停止 uskey_provider + bridge
DIR="$(cd "$(dirname "$0")" && pwd)"
for f in provider.pid bridge.pid; do
  [ -f "$DIR/$f" ] && kill "$(cat "$DIR/$f")" 2>/dev/null && rm -f "$DIR/$f"
done
pkill -f "uskey_provider.py" 2>/dev/null || true
pkill -f "bridge.py" 2>/dev/null || true
echo "[undeploy] provider + bridge 已停止"
