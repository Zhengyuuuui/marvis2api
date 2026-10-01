# Findings — Marvis uskey 离线脱壳（总报告）

> 项目：让 Marvis Bridge 不启动 Marvis GUI 即可完成鉴权
> 日期：2026-10-01
> 总负责：opencode session（software-research + 2api 方法论）
> 阶段报告：PHASE1 / PHASE2 / PHASE3 / PHASE3.5 / PHASE3.6-FINDINGS.md（本文件为其合并与定稿）
> 前置研究：`~/Documents/search example/sessions/2026-09-30-marvis/RECON.md`

---

## 0. 结论（TL;DR）

**T-A（离线生成）成立并已交付。**
在**不启动 Marvis GUI**、**断网**、**全新空 HOME** 的条件下，本地可独立生成服务端可接受的 `uskey`；
bridge 关闭 Marvis GUI 后实测 **25/25** 与 **30/30** 连续 HTTP 200。

核心事实（三条，均为 Confirmed）：
1. `uskey` 由 app 内 `libbeacon_wrapper.dylib` 的 `startrail::uskey` 引擎**纯本地**生成，**无需网络、无需落盘状态**。
2. 服务端校验 `uskey` 的**新鲜度**（每请求唯一），**当前不校验其内容/签名**。
3. `4100404/4100403` = **账号级自适应风控**（密集突发触发，会冷却），**不**绑定 uskey 或 requestid 的具体取值。

---

## 1. 生成链（逆向结论，Confirmed）

```
libbeacon_wrapper.dylib   (~1.8MB, arm64)
  UKInstanceGetDefault(void) -> inst                       # 全局单例
  UKInstanceInit(inst, appkey, appver) -> void             # appkey=0MAC06Y3ZMNM1MH4 appver=1.0.0.10634
  UKInstanceGetUSkey(inst, bus_id, q36, businfo) -> char*  # 返回 malloc 字符串, 每次不同
  UKInstanceFreeUskey(char*)
        └─ QimeiClient::GenerateUskey(str,str,int)
              └─ startrail::uskey::get_uskey_inner_info_provider()
                    └─ 本地引擎 @0x72808（无符号函数）
依赖：@rpath/BeaconAPI_Base.framework（app 内 Contents/Frameworks/）
```

**修正的签名**（初版 probe.c 假设错误，Phase 1 反汇编修正）：
- `UKInstanceInit` 返回 **void**（非 int）
- `UKInstanceGetUSkey` **返回 char\***（非 out-param）
- 参数顺序由 ObjC 选择器 `gukWithQimeiAppkey:appVer:bus_id:q36:businfo:` 交叉确认

**踩坑**：
- `businfo` 必须是 JSON 字符串（`"{}"` 可用；`""` 触发 `NSException`）
- **首次** `GetUSkey` 会抛 IOKit NSException（惰性初始化竞态）→ **重试一次即稳定**（实测 30/30）

---

## 2. 关键实验与判定

### 2.1 H1：是否纯离线？ → **成立**（Phase 1）
`sandbox-exec`(deny network, 已自证) + 空 HOME 下：
- 仍生成 uskey，`len=992`，前缀 `CiDVDCER`（与抓包一致）
- 头部 ~100B **跨运行确定性**，尾部每次随机
- → 无网络依赖、无缓存依赖 → **T-A 可行**

### 2.2 服务端验收 → **成功**（Phase 2）
照抄抓包头，仅替换 uskey：
- 离线 uskey ×8 → **8/8 HTTP 200**（`Marvis-Actual-Model=ark_deepseek-v4-flash-ga-260731`）
- 坏 token → 401 `4100403`（**token 是硬凭据**）
- 长度差异：真实抓包 332 vs 离线 992。base64 解码后**均以 `0a 20 d5 0c 21 11` 开头**（TLV，32B 设备成分一致）→ 差异来自可变 TLV 块，**服务端不要求固定长度**。

### 2.3 uskey 被校验什么？ → **内容不校验**（Phase 3）
| uskey 输入 | 结果 |
|--|--|
| 纯随机 base64 (32B) | 200 |
| `"CiDVDCER"+随机尾` | 200 |
| 空 / 截断 / 垃圾 | 200 |
| 离线真实 (992B) | 200 |

→ 仅需**每请求唯一**；内容当前无关。

### 2.4 风控机制（Phase 3.5 + 3.6）→ **账号级自适应**
干净态矩阵（每格前有 200 baseline）：

| 设计 | 结果 |
|--|--|
| same-uskey + fresh-reqid ×10 | 全 200 |
| fresh-uskey + same-reqid ×10 | 全 200 |
| same-uskey + same-reqid (60s) | 全 200 |
| 复现早期失败 (0.15s ×6, 3轮) | 全 200（**无法复现**） |
| fresh-uskey 无间隔 ×30 | 全 200 |

早期失败（`200,200,403...`）**在干净态不复现** → 证明是**账号级风控/锁定态**，
与**累计突发量**强相关，且**会冷却**。

**修正 SPEC 前提**：`4100404` **不是**"固定 uskey 必错"，而是**风控触发**；token 才是硬凭据。

### 2.5 provider 稳健性（Phase 3.5）
- beacon 连续生成 **200/200**
- 全新进程首调（异常重试路径）**30/30**
- 10 并发取 uskey：**10/10 唯一，无竞态**
- kill 后 `deploy.sh` 可恢复

---

## 3. 风控模型（定稿）

```
校验层级（由强到弱）：
  1. access_token   —— 硬凭据；失效/临时锁定 → 401 {4100403}
  2. uskey 新鲜度    —— 每请求唯一即可（内容不校验，当前）
  3. 请求节奏        —— 账号级自适应；密集突发 → 403 {4100404}，会冷却
```

**安全不变量**：每请求唯一 uskey（+ bridge 已保证每请求唯一 requestid）+ 正常节奏。

**错误码语义**：
- `401 / 4100403`：登录态过期 **或** 临时账号锁定态（两者同码不同因，需结合冷却观察区分）
- `403 / 4100404`：风控拦截（请求被拒）

---

## 4. 假设判定汇总

| 编号 | 假设 | 判定 |
|--|--|--|
| H1 | uskey 生成完全离线 | ✅ 成立 |
| H2 | 可脱离 Marvis 进程独立调用 | ✅ 成立（需首次重试） |
| H3 | uskey 与请求内容无关 | ✅ 成立（仅需唯一） |
| H4 | appkey = MARVIS_QIMEI_APPKEY | ✅ 成立 |
| H5 | 服务端校验 uskey 内容 | ❌ 当前**不**校验（脆弱假设，可能收紧） |

---

## 5. 交付物

| 文件 | 说明 |
|--|--|
| `uskey_provider.py` | 独立 uskey 生成服务 `:4607`（beacon 默认 / random 降级） |
| `uskey-probe/uskey-gen(.m)` | 一次性 ObjC 生成器（子进程隔离 + 异常重试） |
| `bridge.py` | OpenAI 网关；`uskey_source=provider\|mitm\|config` |
| `config.toml` | 凭证/端点/来源配置 |
| `deploy.sh` / `undeploy.sh` | 一键启停 |
| `acceptance.sh` | 验收脚本（关 GUI → 连发 N 次 → PASS/FAIL） |
| `uskey-probe/PHASE*-FINDINGS.md` | 各阶段原始报告 |

---

## 6. 残留风险

| 风险 | 等级 | 说明 / 缓解 |
|--|--|--|
| **服务端加严 uskey 内容校验** | 高 | 当前 random 可过；若收紧，beacon（真实 uskey）仍安全。**故默认 beacon**。 |
| **账号级风控触发** | 中 | 密集请求会 403；正常节奏 + 冷却即可。避免压测。 |
| **Marvis 版本更新改变指纹算法** | 中 | provider 参数化（appkey/appver/dylib 路径可配）；更新后需重新验证 |
| **token 过期/锁定** | 中 | token 需人工重新登录获取（抓包或提取器） |
| **依赖 app 内 dylib** | 低 | 已复制到 `marvis-copy/`，不依赖 Marvis 运行 |

---

## 7. 复现步骤（摘要）

```bash
cd ~/marvis-bridge
./deploy.sh                       # 起 provider(:4607) + bridge(:4605)
curl -s :4607/uskey               # 应返回 len=992 source=beacon
curl -s :4605/v1/chat/completions -H 'Content-Type: application/json' \
     -d '{"model":"main-auto","messages":[{"role":"user","content":"hi"}],"stream":false}'
# → 200, model=ark_deepseek-v4-flash-ga-260731
./acceptance.sh                   # 自动化验收
```

> 详细过程与原始输出见 `uskey-probe/PHASE*-FINDINGS.md`。
