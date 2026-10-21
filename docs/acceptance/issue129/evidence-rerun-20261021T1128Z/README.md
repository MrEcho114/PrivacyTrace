# A 组 H 案例最终执行器补跑（2026-10-21）

本目录保留 #129 的 H01/H04/H07/H10 在**最终合并执行器**上的补跑证据，用于补齐首轮记录中缺失的“报告下钻”物证。首轮证据仍保留在 `../evidence/`，不覆盖、不改写。

## 1. 为什么补跑

首轮 H 案例的报告页只记录了对照摘要行（“查看 N 条证据”），没有展开面板里的原句、码点区间和代码/权限位置。PR #147（合并为 `3996fa6`）修复了移动执行器的报告页等待与证据面板采集，因此用合并后的执行器补跑四个 H 案例，并把展开面板一并归档。

## 2. 被测身份

| 项 | 值 |
| --- | --- |
| 源码 | `ffadeb06af70072b5ee2d931ee565e5b7e546acd`（产品代码；`origin/main` 之后只有 docs/theme 等变更） |
| 执行器 | PR #147 head `42b17fbb` 的 `deploy/acceptance/mobile/client-case.cjs`（合并为 `3996fa6`），加本票本地补丁：`自动准备政策并继续` 按钮的 busy 重试、证据面板容错（面板没有 `原文位置` 时继续采集，最终以 `evidence_quote` 判定） |
| 实例 I | `pt81-c36811dfa963` / `18dee246-d274-49d3-9bfa-73832a51a6d2`，宿主转发 `28443` |
| 实例 J | `pt81-43f6be29e5c0` / `fa470b68-ecc3-471d-93a1-102b3c5daa45`，宿主转发 `29444` |
| 设备 | MuMu 实例，Android 15 / x86_64，`127.0.0.1:16512`，1080×1920 竖屏 |
| 受控政策 | `http://1.1.1.1/policy.html`，472 B UTF-8，SHA-256 `2d9a31a5f1b1a64c5d9d800c5e64963f7207b095d4c8fdc64a1e7e3a1b6e7106` |
| 夹具 | base `4f949286…55c1`；split `fixture_feature` `1467df68…8db7` |

## 3. 逐案例结果

| 案例 | 输入 / 实例 | 结果 | 扫描范围 | 展开证据 | 关键下钻 |
| --- | --- | --- | --- | --- | --- |
| H01 | 单 APK / I | `SUCCEEDED`、`PRESENT`、`DELETED`、`evidence_quote=true` | base:classes.dex、base:classes2.dex | 3 条 | 权限 `ACCESS_FINE_LOCATION`；`LocationProbe.readLastKnownGps`，`base:classes2.dex`，`offset_bytes=30`；原句 `[38,50)`、候选原句 `[66,72)` |
| H04 | base+split / I | `SUCCEEDED`、`PRESENT`、`DELETED`、`evidence_quote=true` | base 与 split 各 2 个 DEX | 4 条 | split `fixture_feature:classes2.dex`，`ContactsProbe.readContacts`，`offset_bytes=24`，`android.contacts.query`；原句 `[66,72)`、`[38,50)` |
| H07 | 单 APK / J | `SUCCEEDED`、`PRESENT`、`DELETED`、`evidence_quote=true` | base:classes.dex、base:classes2.dex | 3 条 | 与 H01 相同结构，实例 J |
| H10 | base+split / J | `SUCCEEDED`、`PRESENT`、`DELETED`、`evidence_quote=true` | base 与 split 各 2 个 DEX | 4 条 | 与 H04 相同结构，实例 J |

所有原句区间按 Unicode 码点计数；报告结论仍为 `证据不足 · 待复核`，没有升级 UNKNOWN/PARTIAL/UNREVIEWED。

## 4. 文件约定

每个案例前缀 `Hxx-129-<instance>-<input>-auto`：

- `-result.json`：执行器结果（job_state、policy_comparison、evidence_captured、evidence_quote、deletion、captured_at）；
- `-webview.txt` / `-webview.png`：报告页正文与截图；
- `-device.png`：设备截图；
- `-candidates.txt`：开始分析前的候选页正文；
- `-evidence-N.txt`：逐行展开的证据面板正文（原句、码点、代码/权限位置、来源）。

原始运行目录中的 `-evidence-N.png` 与重复 `-evidence.txt` 未入库；文本面板是复核依据。
