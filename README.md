# Marvis2API

将腾讯 **Marvis** 桌面助手的私有接口逆向为**标准 OpenAI 兼容网关**（`/v1/chat/completions`、`/v1/models`），
并可**脱离 Marvis 客户端离线运行**——包括离线复现其设备指纹 `uskey`。

> 本项目是**互操作性研究**成果：还原协议 → 复现鉴权 → 落地为 OpenAI 兼容服务。
> 逆向过程与证据见 [`FINDINGS.md`](./FINDINGS.md)，原始任务书见 [`OFFLINE-USKEY-SPEC.md`](./OFFLINE-USKEY-SPEC.md)。

---

## 亮点

- **OpenAI 协议零转换**：上游 `POST /v1/chat/completions` 本身就是标准 OpenAI 协议（含 SSE、`tool_calls`、`file`/`image`），网关原样透传。
- **离线 uskey**：`uskey` 由客户端内 Beacon 指纹 SDK 生成；本项目已将其**脱壳为独立 provider**，**无需启动 Marvis GUI**，断网亦可生成。
- **纯本地、无签名**：上游无 Cloudflare / 无 Turnstile / 无请求级签名，鉴权仅靠一组 `Ual-Access-*` 头。
- **抗封设计**：默认使用**真实指纹（beacon）**而非伪造值，贴合真实客户端行为。

---

## 架构

```
                       ┌─────────────────────────────────────────┐
  OpenAI Client ──────►│  bridge :4605  (FastAPI, OpenAI 兼容)    │
                       └───────────────┬─────────────────────────┘
                                       │ 每请求取新 uskey
                                       ▼
                       ┌─────────────────────────────────────────┐
                       │  uskey_provider :4607                     │
                       │   dlopen libbeacon_wrapper.dylib         │
                       │   → UKInstanceGetUSkey()  离线生成指纹    │
                       └───────────────┬─────────────────────────┘
                                       │
                                       ▼
              https://yybadaccess.3g.qq.com/v1/chat/completions
```

---

## uskey 解密原理

`uskey` 是请求头 `Ual-Access-MarvisExt`(JSON) 中的字段，由 **Beacon/Qimei 设备指纹体系**生成。
逆向结论（均在 `FINDINGS.md` 附证据）：

### 生成链

```
libbeacon_wrapper.dylib   (app 内, arm64)
  ├─ UKInstanceGetDefault()                            → 全局单例 inst
  ├─ UKInstanceInit(inst, appkey, appver)              → void
  ├─ UKInstanceGetUSkey(inst, bus_id, q36, businfo)    → char*（每次不同）
  └─ UKInstanceFreeUskey(ptr)
        └─ QimeiClient::GenerateUskey(...)
             └─ startrail::uskey::get_uskey_inner_info_provider()
                  └─ 本地引擎（无符号函数 @0x72808）
```

- `appkey = 0MAC06Y3ZMNM1MH4`，`appver = 1.0.0.10634`
- `bus_id = "marvis_client"`，`businfo = "{}"`（**必须是 JSON 字符串**，空串会触发 `NSException`）
- **首次**调用会抛 IOKit `NSException`（惰性初始化竞态）→ **重试一次即稳定**

### 关键性质（实测）

| 性质 | 结论 |
|--|--|
| 是否依赖网络 | **否**（断网 + 空 HOME 仍可生成） |
| 是否依赖落盘状态 | **否**（全新 HOME 正常） |
| 长度 | 992B（前缀 `CiDVDCER`，与真实抓包同结构；服务端不要求固定长度） |
| 每次是否相同 | **不同**（头部设备成分确定性，尾部随机） |
| 服务端是否校验内容 | **当前不校验**（随机值亦可通过，见下「风险」） |

### 服务端实际校验的层级

```
1. access_token   —— 硬凭据（mv_ token）；失效/锁定 → 401 {4100403}
2. uskey 新鲜度    —— 每请求唯一即可；内容当前不校验
3. 请求节奏        —— 账号级自适应风控；密集突发 → 403 {4100404}，会冷却
```

> **一句话**：`uskey` 必须**每请求唯一**，但它具体是什么目前不重要；真正决定成败的是 **token** 与**请求节奏**。

---

## 快速开始

### 前置：准备 app 内的 dylib

```bash
# 从本机已安装的 Marvis 复制指纹库（版权归腾讯，请勿再分发）
mkdir -p marvis-copy/bin marvis-copy/BeaconAPI_Base.framework
cp /Applications/Marvis.app/Contents/Resources/bin/libbeacon_wrapper.dylib marvis-copy/bin/
cp -R /Applications/Marvis.app/Contents/Frameworks/BeaconAPI_Base.framework marvis-copy/
# 编译一次性生成器
clang -O2 -framework Foundation uskey-probe/uskey-gen.m -o uskey-probe/uskey-gen
```

### 配置凭证

```bash
cp config.example.toml config.toml
# 编辑 config.toml，填入你从已登录客户端抓包得到的 openid / access_token / device_guid
```

### 启动

```bash
./deploy.sh          # provider(:4607) + bridge(:4605)，无需 Marvis
curl -s http://127.0.0.1:4607/uskey          # 应返回 len=992 source=beacon

# 任意 OpenAI 客户端指向 http://127.0.0.1:4605/v1
curl -s http://127.0.0.1:4605/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"main-auto","messages":[{"role":"user","content":"你好"}],"stream":false}'
```

验收 / 停止：

```bash
./acceptance.sh 10      # 连续 10 次 200 = PASS
./undeploy.sh
```

---

## 协议要点

| 项 | 值 |
|--|--|
| 端点 | `https://yybadaccess.3g.qq.com/v1/chat/completions` |
| 协议 | 标准 OpenAI（请求体 / SSE / `tool_calls` 完全一致） |
| 模型 | `model:"main-auto"` → 服务端路由 → 响应头 `Marvis-Actual-Model`（实测 `ark_deepseek-v4-flash-ga-260731`，辅助场景 `hy3`） |
| 鉴权头 | `Ual-Access-Access-Token`(mv_) · `Ual-Access-Openid` · `Ual-Access-Guid`/`X-Device-GUID` · `Ual-Access-MarvisExt`(含 uskey) |
| SSE | 标准 `chat.completion.chunk` + `data: [DONE]` + `usage` |
| 防护 | 无 CF / 无 Turnstile / 无请求签名 |

---

## ⚠️ 五个风险点

| # | 风险 | 等级 | 说明与缓解 |
|--|--|--|--|
| **1** | **服务端加严 uskey 内容校验** | **高** | 当前随机 uskey 也能通过（服务端仅校验新鲜度，未校验签名）。一旦服务端收紧，`random` 模式立即失效。**缓解：默认使用 `beacon` 真实指纹**，与真实客户端同源。 |
| **2** | **账号级自适应风控** | 中 | 密集/重复请求会触发 `4100404`(403)，严重时临时锁定 `4100403`(401)；**会自动冷却**。缓解：保持正常节奏，**切勿压测**。 |
| **3** | **客户端版本更新漂移** | 中 | Marvis 升级可能改变指纹算法或 appkey，导致生成的 uskey 失效。缓解：provider 已参数化（`uskey_appkey`/`uskey_appver`/dylib 路径），更新后重新验证即可。 |
| **4** | **access_token 过期/锁定** | 中 | `mv_` token 是硬凭据，过期或触发风控锁定后返回 401。缓解：需人工重新登录客户端并抓取新 token 更新 `config.toml`。 |
| **5** | **依赖 app 内专有 dylib** | 低 | 离线生成依赖腾讯版权库 `libbeacon_wrapper.dylib`（本项目不入库，需用户自行从本机 app 复制）。 |

---

## uskey 来源模式（`config.toml: uskey_source`）

| 模式 | 说明 | 需 Marvis |
|--|--|--|
| **provider**（默认） | 每请求向 `:4607` 取离线生成的真实 uskey | 否 |
| mitm | mitmdump 旁听客户端流量实时提取（备用） | 是 |
| config | 使用配置文件中的固定 uskey（通常已失效） | 否 |

provider 子模式：`beacon`（默认，真实指纹）/ `random`（纯随机，**依赖风险 #1，脆弱**）。

---

## 目录结构

```
marvis2api/
├── bridge.py                 # OpenAI 兼容网关 (:4605)
├── uskey_provider.py         # 离线 uskey 生成服务 (:4607)
├── uskey_addon.py            # mitmproxy 提取 addon（备用模式）
├── config.example.toml       # 配置模板（真实凭证请写入 config.toml，已 gitignore）
├── deploy.sh / undeploy.sh   # 一键启停
├── acceptance.sh             # 验收脚本
├── FINDINGS.md               # 逆向总报告（生成链 / 假设判定 / 风控模型）
├── OFFLINE-USKEY-SPEC.md     # 任务书 + 执行回填
└── uskey-probe/              # 各阶段原始证据与逆向工具（probe 源码）
```

---

## 免责声明

本项目仅供**安全研究与互操作性学习**。使用者应自行确保符合目标服务的条款与当地法律；
请勿用于规避计费、访问他人数据或任何未授权用途。作者不对使用后果负责。
