#!/bin/bash
# acceptance.sh — Marvis Bridge 验收脚本
#
# 判据（SPEC §6）：
#   1. Marvis GUI 未运行
#   2. provider(:4607) 能产出非空 uskey
#   3. bridge(:4605) 连续 N 次 /v1/chat/completions 返回 200（非 4100404）
#
# 用法:
#   ./acceptance.sh [N]        # N 默认 10
#
# 注意：会向真实上游发 N 次请求（消耗额度、可能触发账号风控）。
#       建议 N<=10 且间隔>1s。大样本压测会触发 4100404，请勿滥用。
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
N="${1:-10}"
BASE="http://127.0.0.1:4605"
MODEL="main-auto"

pass=0; fail=0; codes=()

echo "== Marvis Bridge 验收 (N=$N) =="

# 1) GUI 检查（用 ps 精确匹配可执行路径，避免 pgrep -f 匹配到本脚本命令行自身）
if ps ax -o command= | grep -q '^/Applications/Marvis\.app/Contents/MacOS/Marvis'; then
  echo "[!] 警告: Marvis GUI 正在运行（判据1 要求关闭）。可先: osascript -e 'quit app \"Marvis\"'"
else
  echo "[ok] Marvis GUI 未运行"
fi

# 2) provider 检查
u="$(curl -s -m 20 http://127.0.0.1:4607/uskey)"
ulen="$(printf '%s' "$u" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("len",0))' 2>/dev/null || echo 0)"
if [ "${ulen:-0}" -gt 0 ]; then
  echo "[ok] provider uskey len=$ulen  ($u)"
else
  echo "[!] provider 异常: $u"
fi

# 3) bridge 连续请求
echo "[..] 连续请求 $N 次 (间隔 1.2s)"
for i in $(seq 1 "$N"); do
  code="$(curl -s -o /tmp/acc_body.json -w '%{http_code}' -m 60 "$BASE/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"reply OK\"}],\"stream\":false}")"
  codes+=("$code")
  if [ "$code" = "200" ]; then pass=$((pass+1)); else fail=$((fail+1)); fi
  printf "  [%2d] %s\n" "$i" "$code"
  sleep 1.2
done

model="$(python3 -c 'import json;print(json.load(open("/tmp/acc_body.json")).get("model","?"))' 2>/dev/null || echo '?')"
echo ""
echo "== 结果 =="
echo "  200: $pass / $N   (序列: ${codes[*]})"
echo "  last response model: $model"
if [ "$fail" = "0" ] && [ "$pass" = "$N" ]; then
  echo "  VERDICT: PASS ✅"
  exit 0
else
  echo "  VERDICT: FAIL ❌  (若有 4100404/4100403 → 账号级风控，请冷却后再试)"
  exit 1
fi
