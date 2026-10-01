#!/bin/bash
launchctl unsetenv HTTPS_PROXY; launchctl unsetenv HTTP_PROXY
launchctl unsetenv ALL_PROXY; launchctl unsetenv NO_PROXY
echo "全局代理已还原"
