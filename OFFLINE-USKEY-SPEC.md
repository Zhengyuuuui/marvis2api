# SPEC：Marvis uskey 离线脱壳（Offline USKey Reimplementation）

> 版本：v1
> 日期：2026-10-01
> 目标读者：执行逆向的 Agent / 工程师
> 前置研究：`~/Documents/search example/sessions/2026-09-30-marvis/RECON.md`

---

## 1. 目标（Objective）

**让 Marvis Bridge 在不启动 Marvis 客户端的前提下完成鉴权**，方法有二选一（按优先级）：

- **T-A（首选）：离线生成 uskey**
  还原 `libbeacon_wrapper.dylib` 中 `startrail::uskey` 引擎，用纯本地代码（或复用 dylib 的独立调用）
  生成服务端可接受的 `uskey`。
- **T-B（兜底）：无头 uskey 服务**
  用 app 自带二进制最小化拉起一个**常驻轻量进程**（非完整 Electron GUI），仅负责产出 uskey，
  由一个本地 HTTP 接口暴露给 bridge。

**成功判据（必须同时满足）**：
1. 不运行 `Marvis.app` 主 GUI（不出现 Electron 内存占用）
2. bridge 能对上游 `POST /v1/chat/completions` 返回 200（非 `4100404 风控拦截`）
3. 连续 ≥ 3 次调用成功（证明不是"恰好命中某有效窗口"）

---

## 2. 背景：现有链路（Confirmed，抓包证据）

```
MarvisAgent(Python)
  │ headers:
  │   Ual-Access-Access-Token: mv_...        # 登录态，长期稳定（登录后不变）
  │   Ual-Access-Openid:      oAN1...        # 账号，稳定
  │   Ual-Access-Guid / X-Device-GUID        # 设备ID，稳定
  │   Ual-Access-MarvisExt:  {               # ← 动态字段集中在此 JSON
  │        qimei36, osVersion, guid, uskey, nonce, reqScene, taskType,
  │        clientVersion, clientPlatform, clientPlatformVersion, isIoa }
  ▼
POST https://yybadaccess.3g.qq.com/v1/chat/completions
  │  (标准 OpenAI 协议; 无 CF / 无 Turnstile / 无 ual 签名)
  ▼
服务端：校验 Ual-Access-* → 其中 uskey 由其指纹体系验证
```

### 2.1 uskey 语义（实测）
- 位于 `Ual-Access-MarvisExt.uskey`
- 每次请求都不同（4 连续请求 → 4 个不同值；前缀 `CiDVDCER` 固定，后缀随机）
- **每请求唯一**（疑似与 `nonce`/时间绑定）
- 固定旧值 → `{"code":4100404,"msg":"客户端通用错误:请求被风控拦截"}`（HTTP 403）

### 2.2 uskey 生成点（静态证据）
```
libbeacon_wrapper.dylib   (~1.8MB, arm64)
├── UKInstanceGetDefault()                       → 单例
├── UKInstanceInit(inst, char* appkey, char* x)  → 初始化（内部 __call_once）
├── UKInstanceGetUSkey(inst, out, char* a, char* b)
│      └── QimeiClient::GenerateUskey(str, str, int)
│             ├── WaitAuditDone() / DriveAuditInBackground()   ← 可疑：可能需联网/审计
│             ├── GetCurrentQimei()
│             ├── startrail::uskey::get_uskey_inner_info_provider()
│             └── 本地引擎 @0x72808 (无符号, startrail 编译单元)
├── beacon_wrapper::MacBackend::GetUskey(...)
└── beacon_get_uskey()  (C 导出, MarvisAgent 通过 ctypes 调用)
```

依赖：`@rpath/BeaconAPI_Base.framework`（app 内 `Contents/Frameworks/BeaconAPI_Base.framework`）

### 2.3 现有 bridge 行为
`~/marvis-bridge/`：`bridge.py`(OpenAI 网关 :4605) + `uskey_addon.py`(mitm 提取器 :4606)。
提取器旁听 Marvis 流量 → 回调 `/_ingest` 写入 `LIVE["uskey"]` → 发请求时注入。
**问题：依赖 Marvis 常驻运行（重）。**

---

## 3. 待验证的关键假设（Hypothesis）

| 编号 | 假设 | 若成立 | 若证伪 |
|--|--|--|--|
| H1 | uskey 生成**完全离线**，不依赖网络审计 | T-A 可行 | 只能走 T-B |
| H2 | `UKInstanceGetUSkey` 可脱离 Marvis 进程独立调用（无 GUI 依赖） | 可写 launcher | 需模拟进程环境 |
| H3 | uskey 与**请求内容无关**（只与设备/时间/nonce 有关） | 可预生成/复用窗口 | 需每请求实时 |
| H4 | `UKInstanceInit` 的 appkey 参数 = `MARVIS_QIMEI_APPKEY`(0MAC06Y3ZMNM1MH4) | 参数已知 | 需提取真实 appkey |

---

## 4. 逆向路径（分阶段，每阶段有明确验证）

### Phase 0：环境复现（0.5h）
- [ ] 复制整个 `Marvis.app/Contents/{Resources/bin, Frameworks}` 到工作区（避免改原 app）
- [ ] 用 `DYLD_FRAMEWORK_PATH=<app>/Contents/Frameworks` 使 `dlopen(libbeacon_wrapper.dylib)` 成功
- [ ] 修正 `uskey-probe/probe.c`：确认 `UKInstanceInit` 返回 void、`GetUSkey` 输出参数位置

### Phase 1：判定 H1（是否离线）——**决定性实验**（1-2h）
- [ ] 断网（或 firewall 屏蔽 outbound）下调用 `UKInstanceGetUSkey`
- [ ] 若返回非空 uskey → **H1 成立**，直接进 Phase 3
- [ ] 若返回空/报错，检查 `WaitAuditDone` 的依赖：
  - [ ] 抓 `StarTrailService`/`QimeiService` 的初始化网络请求（mitm 或 tcpdump）
  - [ ] 判断审计是否只做一次、结果是否落盘（`STStorageKeyStarTrailJson`）

### Phase 2：还原生成参数（若 H1 成立但签名不对，2-4h）
- [ ] 用 lldb 在运行中的 MarvisAgent 里 hook `UKInstanceGetUSkey`，dump 4 个参数实参
  （`po` / `x1..x4`），与抓包中同请求的 uskey 对照
- [ ] Hook `startrail::uskey::get_uskey_inner_info_provider` 返回值 → 得到 inner info 结构
- [ ] 反汇编 `0x72808` 引擎：确认输入=(inner_info, 时间, nonce) 与输出编码（`CiDVDCER...` 是 base64）

### Phase 3：独立 uskey provider（2-4h）
- [ ] 写 `uskey_provider`（C 或 Python ctypes）：
  - dlopen dylib → `UKInstanceGetDefault` → `UKInstanceInit(appkey,...)` → `UKInstanceGetUSkey(...)`
  - 暴露本地 HTTP：`GET http://127.0.0.1:<port>/uskey` → 返回 uskey
- [ ] bridge 改为：每次请求向 provider 取新 uskey（替换 mitm 提取器）
- [ ] 验证：关闭 Marvis GUI，provider 单独运行，bridge 连续 3+ 次 200

### Phase 4（T-B 兜底，仅当 H1 证伪时）
- [ ] 用 `MarvisHost`（Rust 网关）或直接 `MarvisAgent --work_mode=cloud` 无头启动
- [ ] 保留 App 生命周期所需最小组件，只开启 uskey 生成路径
- [ ] 目标是"无 Electron GUI，仅后台 agent/host 进程"

---

## 5. 交付物

| 交付物 | 说明 |
|--|--|
| `uskey_provider` | 可独立运行的 uskey 生成器（含源码 + 构建脚本） |
| `bridge.py`（改） | 用 provider 取代 mitm 提取器；开关 `uskey_source = provider|mitm|config` |
| `findings.md` | 逆向结论：H1-H4 判定、参数语义、引擎调用链、证据 |
| `deploy.sh` | 一键：起 provider + bridge，无需启动 Marvis |

---

## 6. 验收（Acceptance）

```bash
# 关闭 Marvis GUI 后：
./deploy.sh
# 期望：
#   provider  : 127.0.0.1:4607 返回非空 uskey
#   bridge    : 127.0.0.1:4605 可用
curl -s http://127.0.0.1:4605/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"main-auto","messages":[{"role":"user","content":"hi"}],"stream":false}'
# → 连续 3 次均 200，返回 Marvis-Actual-Model（无 4100404）
```

---

## 7. 风险与止损

| 风险 | 应对 / 止损 |
|--|--|
| uskey 依赖服务端审计（H1 证伪） | 转 T-B；或接受"轻量常驻 agent 进程" |
| 算法含服务端下发密钥 | 判死 T-A，转 T-B |
| Marvis 版本更新使签名失效 | provider 参数化；记录版本绑定 |
| 频繁调试触发账号风控 | 降低调用频率；调试期用 mock 上游 |

**止损条件**：Phase 1 若确认必须联网审计且无法缓存 → 放弃 T-A，直接做 T-B。

---

## 8. 法律/边界

- 目标为本机已安装软件的互操作性研究；uskey 为**设备指纹**，非账号凭据破解。
- 不规避计费、不访问他人数据；仅复用本机已登录会话的合法调用能力。

---

# 附：执行结果回填（2026-10-01 定稿）

> 本 SPEC 假设已全部验证，结论见 `FINDINGS.md`。以下为回填与修正。

## 假设判定
| 编号 | 假设 | 判定 |
|--|--|--|
| H1 | uskey 生成完全离线 | ✅ 成立（断网+空HOME 仍出 uskey） |
| H2 | 可脱离 Marvis 进程独立调用 | ✅ 成立（首次调用需重试一次） |
| H3 | uskey 与请求内容无关 | ✅ 成立（仅需每请求唯一） |
| H4 | appkey = MARVIS_QIMEI_APPKEY | ✅ 成立 |
| （新增）H5 | 服务端校验 uskey 内容 | ❌ 当前不校验（脆弱） |

## SPEC 前提修正（重要）
- 原写「固定 uskey 会被 4100404」→ **不准确**。
  更准确：`4100404` 是**账号级自适应风控**（密集突发触发，会冷却），**不绑定 uskey/requestid 取值**。
- 硬凭据是 **access_token**；uskey 只需**每请求唯一**。

## 阶段结果
- Phase 1：H1 成立 → 进 Phase 2
- Phase 2：离线 uskey 服务端 8/8 200 → T-A 确认
- Phase 3：内容不校验（随机可过）；交付 provider(:4607) + bridge 集成；关 GUI 25/25 200
- Phase 3.5：provider 稳健（200/200、并发安全、自愈）
- Phase 3.6：风控归因 = 账号级自适应（非 uskey/requestid 取值）
- Phase 4（按 SPEC 仅在 Phase 1 证伪时需要）：**跳过**

## 交付状态
✅ T-A 达成，已交付离线 provider + bridge + deploy/acceptance。
残留风险见 `FINDINGS.md` §6。
