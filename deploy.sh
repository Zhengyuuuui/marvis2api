#!/bin/bash
# deploy.sh — 一键启动 uskey_provider(:4607) + bridge(:4605)，无需启动 Marvis GUI。
#
#   provider : dlopen libbeacon_wrapper.dylib 离线生成真实 uskey（每请求唯一）
#   bridge   : OpenAI 兼容网关，uskey_source=provider，每请求向 provider 取新 uskey
#
# 用法:
#   ./deploy.sh                 # 默认 beacon 模式
#   USKEY_MODE=random ./deploy.sh   # 降级：纯随机 uskey（无 dylib 依赖）
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

MODE="${USKEY_MODE:-beacon}"

echo "[deploy] 停止旧进程 ..."
pkill -f "bridge.py" 2>/dev/null || true
pkill -f "uskey_provider.py" 2>/dev/null || true
pkill -f "mitmdump" 2>/dev/null || true
sleep 1

# 1) uskey provider
nohup python3 uskey_provider.py --mode "$MODE" > provider.log 2>&1 &
echo $! > provider.pid
echo "[deploy] uskey_provider 已启动 (pid $(cat provider.pid), mode=$MODE)"

# 等 provider 就绪
for i in $(seq 1 15); do
  if curl -s -m2 http://127.0.0.1:4607/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo "[deploy] provider 自检: $(curl -s -m20 http://127.0.0.1:4607/uskey | head -c 120)"

# 2) bridge (provider 模式，不启动 mitm 提取器)
nohup python3 bridge.py --no-extractor > bridge.log 2>&1 &
echo $! > bridge.pid
sleep 3
echo "[deploy] bridge 已启动 (pid $(cat bridge.pid))"

echo ""
echo "  OpenAI base URL : http://127.0.0.1:4605/v1"
echo "  uskey provider  : http://127.0.0.1:4607/uskey"
echo "  bridge health   : $(curl -s -m5 http://127.0.0.1:4605/health)"
echo ""
echo "验证:"
echo "  curl -s http://127.0.0.1:4605/v1/chat/completions -H 'Content-Type: application/json' \\"
echo "    -d '{\"model\":\"main-auto\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":false}'"
echo ""
echo "退出: ./undeploy.sh"
