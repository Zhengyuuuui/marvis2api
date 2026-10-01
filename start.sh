#!/bin/bash
# 启动 Marvis Bridge：OpenAI 网关(:4605) + uskey 提取器(:4606)
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
pkill -f "bridge.py" 2>/dev/null
pkill -f "uskey_addon.py" 2>/dev/null
sleep 1
nohup python3 bridge.py > bridge.log 2>&1 &
echo $! > bridge.pid
sleep 4
echo "Marvis Bridge 已启动 (pid $(cat bridge.pid))"
echo "  OpenAI base URL : http://127.0.0.1:4605/v1"
echo "  uskey 状态      : $(curl -s http://127.0.0.1:4605/uskey)"
echo "  日志            : $DIR/bridge.log"
echo ""
echo "下一步（首次需让 Marvis 走代理以捕获 uskey）: ./use_live.sh"
echo "完成后还原代理: ./unset_proxy.sh"
