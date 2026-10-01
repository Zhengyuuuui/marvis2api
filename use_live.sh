#!/bin/bash
# 让 Marvis 走 bridge 内置的 uskey 提取器(mitm:4606)，从而 bridge 自动获取实时 uskey
PORT=4606
echo "设置全局代理指向 127.0.0.1:$PORT ..."
launchctl setenv HTTPS_PROXY "http://127.0.0.1:$PORT"
launchctl setenv HTTP_PROXY  "http://127.0.0.1:$PORT"
launchctl setenv ALL_PROXY   "http://127.0.0.1:$PORT"
launchctl setenv NO_PROXY    "127.0.0.1,localhost"
echo "重启 Marvis 使其继承代理..."
osascript -e 'quit app "Marvis"' 2>/dev/null
sleep 3
pkill -f "Marvis.app/Contents/MacOS/Marvis" 2>/dev/null
pkill -f "components/Marvis" 2>/dev/null
sleep 2
nohup env HTTPS_PROXY="http://127.0.0.1:$PORT" HTTP_PROXY="http://127.0.0.1:$PORT" ALL_PROXY="http://127.0.0.1:$PORT" NO_PROXY="127.0.0.1,localhost" /Applications/Marvis.app/Contents/MacOS/Marvis > /tmp/marvis-live.log 2>&1 &
sleep 6
echo "完成。请在 Marvis 里发一句话，让 bridge 捕获 uskey。"
echo "查看状态: curl -s http://127.0.0.1:4605/uskey"
