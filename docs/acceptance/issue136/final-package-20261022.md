# #136 最终候选包重建与冷启动（2026-10-22）

- 依据：用户 2026-10-22 明确授权“按最终 head 重建交付包”。
- 源码：`00f9263690e8b58b82cb615618fee96ec5b8df66`（R01–R04 证据绑定版本）。
- 包名：`PrivacyTrace_322234-final-00f9263.zip`
- 根目录：`PrivacyTrace_322234/`

## 1. 包身份

| 项 | 实测 |
| --- | --- |
| SHA-256 | `4253eaeec0b66f87f1e8d458ff8cd76cc857b0acaa3b4e451631bd5d212aeb26` |
| 字节数 | 40,897,122 |
| ZIP 条目 | 547（文件 547；不含独立目录条目） |
| 解压后 | 44,803,161 字节；91 个目录 |
| CRC | `zipfile.testzip()` → None |
| 包内清单 | `00_材料清单.md`（逐文件 SHA-256） |
| 顶层结构 | `00_材料清单.md` + `01_作品及成果文件` / `02_作品展示视频` / `03_作品介绍文档` / `04_运行或使用说明` / `05_补充成果材料` / `06_第三方资源说明` / `07_AI工具使用补充说明` / `08_学籍等专项材料` |

本包是**重建候选包**，不等同旧 64,261,830 B 包（SHA-256 `6ba1fbde…`）；旧包在本机不可定位，未重算其哈希，未冒充。

### 构建与修复

首次重建为 40,897,122 B（`216f2d86…`）的包，包内冷启动 R04 失败于两项：

- R3：缺少 `docs/deployment/acceptance-scope.json`（源码子集裁掉了 `docs/deployment/`）；
- R6：缺少 `.gitignore`，`npm ci`/`uv sync` 后 `node_modules` 被 `git ls-files --others` 计入 shipping 材料，扫出两条 URL 凭据（来自依赖包文本），触发 `secret_audit`。

修复：在包内源码加入 `.gitignore` 与 `docs/deployment/acceptance-scope.json`，重新生成清单/哈希后复跑。失败收据保留在 `evidence/final-package-00f9263/rejected-r04/`（如有归档）与本记录中，不删除历史。

## 2. 解压冷启动

- 解压到全新目录 `<package-extract>/`：547 条目全部落盘，`testzip()` 返回 None，`00_材料清单.md` 可读。
- 源码路径：`01_作品及成果文件/source/`；包内不含 `.git`、`node_modules`、`.venv`、APK、数据库、模型 Key 或私人样本。
- 依赖准备：`npm ci` 与 `uv sync --project apps/api --locked --extra worker` 从包内锁文件成功（首次失败记录见上）。

## 3. 离线回放

- 页面：`01_作品及成果文件/demo-web/web/comparison.html`。
- Playwright 1.64 + Chromium 1248，`context.setOffline(true)`，并中止所有 `http(s)` 请求。
- 结果：HTTP 200、标题 `PrivacyTrace 六场景公平比较`、H1 `OFFLINE REPLAY · 六场景三方案比较`、18 行表格、0 个外部请求、0 个页面错误；收据 `demo-receipt.json`，截图 1440/390。
- 观察：390px 视口下表格横向溢出 1848px；该页面是桌面比较表，包内 README 未声明移动适配，因此不记为失败，但作为边界保留。

## 4. 从包内源码运行完整部署（R04）

- 包内源码不含 `.git`，而 `deploy/check_acceptance.sh` 硬编码基线 `201d34da…` 并要求干净已提交工作区；冷启动时从本机干净克隆导入该基线对象，再提交包内源码，因此 R04 收据中的 `source_sha` 是包内提交 `6c04b331…`，不是原仓库 `00f9263`。
- 结果：`acceptance-summary-20261022T005623Z.json`，退出码 0，**40 pass / 0 fail / 0 skip**（R1 1 / R2 13 / R3 1 / R4 12 / R5 4 / R6 9），唯一既有豁免 `dedicated-scan-host-verification`，`pass_rate_of_verified=1.0`。
- R3 实际隔离用例包含单 APK 与 base+splits 的真实受限扫描；报告非空、可追溯。R4 含重启/故障注入/恢复，R5 含备份恢复与删除重放，R6 含容量与秘密审计。
- 收据在 `evidence/final-package-00f9263/r04/`；包内源码改动只来自包子集（不含 docs/evidence/showcase），产品代码与 `00f9263` 同源。

## 5. Android 竖屏证据（PARTIAL）

- 包内不含 APK；使用 `.scratch/issue131-evidence/client.apk`（158,593,090 B，SHA-256 `8BB257DF…FDDC8`，`org.privacytrace.mobile` 1000/0.1.0，targetSdk 36，仅 x86_64，调试签名 v2）。这是 early candidate，不是在本包重建出的 APK。
- MuMu VM0（`127.0.0.1:16384`，Android 15/SDK35，1080×1920）安装并实际运行；11 张原生竖屏截图存 `evidence/final-package-00f9263/android/`。
- 可达：启动、应用选择、上传目标/确认、材料与政策候选、设置/帮助等界面。
- 阻断：上传该 158 MB APK 本身触发 `LIMIT_EXCEEDED`（上限 157,286,400 B）；改用 29 MB 系统设置包上传成功，但“保存候选并开始分析”返回 `UPLOAD_CONFLICT_REFRESH`，任务/报告界面未取得；删除远端材料一次挂起 20s+。未伪造任务/报告截图。
- 因此最终 APK 的完整竖屏链路（任务进度、报告、静态代码/政策原句下钻）仍为 **PARTIAL/NOT_RUN**；包内不含该 APK，不能把候选 APK 截图称为“最终包构建产物”。

## 6. 与 H 票清单的对应

| 清单项 | 结论 |
| --- | --- |
| R01/R02/R03/R04 最终组合本机证据 | **PASSED**（`65b49f7`，见 `execution-20261022.md`；远端 CI 绑定同一 head） |
| 最终压缩包新目录可安装/运行/停启；单包/splits 报告非空 | **PASSED**（本包，R04 40/0/0；R3 含单包+splits） |
| 产物/材料清单、哈希、脱敏、未验证边界 | 清单/哈希/CRC/脱敏通过；最终冻结后仍需按最终 head 重算（当前 main 已到 `7b1e070`，且 #157/#148/#160 仍开放） |
| 每个变体预期/实际/证据 | R01–R04 已记录；包冷启动记录在本文件 |
| 原始状态保留 | 首次包 R04 失败、Android 阻断与旧 64 MB 包缺失均保留，不冒充 |
| 代码/配置修复复测 | 包内修复 `.gitignore`/`docs/deployment` 后复跑全绿；产品代码未改 |

## 7. 边界与剩余

- 本包不是官方提交成功，也不等同旧 64,261,830 B 包；旧包身份仍缺失。
- 最终 APK 竖屏完整链路仍缺；包内无 APK，调试签名候选包只作界面证据。
- 包绑定 `00f9263`；若 #157/#148/#160 等合并或冻结 head 变化，必须重建包、重算哈希并重跑受影响项。
- 本记录不关闭 #136/#128，不把包冷启动通过相加为父票通过。
