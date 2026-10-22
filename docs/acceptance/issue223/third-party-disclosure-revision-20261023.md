# #223：修订 06 第三方资源说明（PT-906-B4，2026-10-23）

Refs #223、#197、#107。本票范围：只改 `06_第三方资源说明/第三方资源说明.md`；不引入新依赖、不改依赖版本、不改代码、不删改任何上游版权与许可文本。

关闭对象为 #197 终报第五节报出的 G7–G10。

## 一、交付物与位置

| 项 | 值 |
| --- | --- |
| 审阅基线（#197 对象，未改动） | `.scratch/package-final/deccced-anon/PrivacyTrace_322234/` |
| 修订副本 | `.scratch/package-final/deccced-anon-b4/PrivacyTrace_322234/`（建立于 2026-10-23T02:00:17 +08:00） |
| 06 修订前 | 18 行 / 1106 B / SHA-256 `86D666201F864A1A881C6C7CAC6F8C0CC9C41F258C537AE8CC27821A4E118A02` |
| 06 修订后 | 116 行 / 11245 B / SHA-256 `6268F9A241874B5402BFCB076C937301D553DB06339B17F0800A34B399B965CC` |
| 副本内文件数 | 630（不含 ZIP；见第五节对旧 ZIP 的处置） |
| 复现脚本 | `docs/acceptance/issue223/extract-deps.cjs`（只读解析三份锁定文件） |

副本内的 `00_材料清单.md` **未重算**，仍记录修订前 06 的哈希。这是已声明的中间态，不是遗漏：整包重冻结与清单重算归 #224。

## 二、决策记录

| # | 决策 | 结论 |
| --- | --- | --- |
| 1 | 修订稿落点 | 复制 `deccced-anon-b4`，只改副本；原基线不动 |
| 2 | 「直接依赖」边界 | 三套清单的直接声明逐项列出；传递依赖在第七节统一说明，不逐条展开 |
| 3 | 部署基础设施 | 列入但另立「不随包分发」小节，许可按事实写 |
| 4 | 运行时 LLM 服务 | 列入「可选运行时第三方服务」，写明默认关闭 |
| 5 | 素材与数据 | 只列字体与自制项；演示数据、截图、影片归入自制内容 |
| 6 | 文件名与格式 | 保持 `第三方资源说明.md`，不加 PDF、不改名 |
| 7 | 仓库留痕 | 本文件 + `extract-deps.cjs`，提交到 `codex/pt-906-b4-third-party-20261023`，不自动合并 |
| 8 | 表格列 | 六列：名称 / 版本 / 来源 URL / 用途 / 许可 / 许可凭证 |
| 9 | 对外是否写票号 | 不写。06 内无票号、无内部编号、无修订说明 |
| 10 | 副本内清单 | 不重算，交 #224 |
| 11 | 许可抽检 | 抽 reka-ui、Pydantic、Redis 7.4.x 三条，联网核对上游 raw LICENSE |
| 12 | 与 07 的口径 | 06 只写运行期事实，不写研发期用途，不互引票号 |
| 13 | 范围外发现 | 记录进本文件与 Issue，不在本票修 |
| 14 | Assignee / 关票 | 不认领、不关票；关票留待 #224 重冻结后由负责人决定 |

## 三、G7–G10 关闭映射

| 缺口 | 处理 |
| --- | --- |
| G7 漏列直接依赖 | 新增 `reka-ui 2.11.0`、`pydantic 2.13.5`、`psycopg 3.3.6`；另补 `@tauri-apps/api`、`@tauri-apps/cli`、`@vitejs/plugin-vue`、`httpx`、`ruff`、`pytest`、`celery`、`redis`（Python 客户端）、`androguard`、`tauri`、`tauri-build` |
| G8 无来源 URL 列 | 全表增设「来源 URL」列，逐行填写上游仓库地址 |
| G9 三处许可错误 | TypeScript 改 `Apache-2.0`；Python 改 `PSF-2.0`；Redis 7.4.8 改 `RSALv2 或 SSPLv1（接收方二选一）`，并补注 7.2.x 与 8.0.0 的版本线差异 |
| G10 字体行「若存在」 | 改为「Noto Sans SC / Noto Serif SC」实名两行，许可凭证指向包内两份 OFL 文本，删去「思源」与「若存在」 |

顺带修正的既有不准确项：

- 原「Python / FastAPI / Uvicorn / SQLAlchemy / Alembic」合并行为「MIT / BSD / Apache-2.0」，未给出逐项对应关系；已拆为独立行。
- 原「PostgreSQL / Redis / Celery」合并行把 Redis 写成 BSD；已拆分并更正。
- 原首句只提 `package-lock.json` 与 `apps/api/uv.lock`，遗漏 `Cargo.lock`；已补，并注明三份锁定文件的位置。
- 原「Tauri 2 / Rust」行未区分运行时与构建脚本；已拆为 `tauri`、`tauri-build`、Rust 工具链三行。

## 四、许可核验证据

### 4.1 抽检 3 条（验收要求的「抽 3 条与官方仓库比对」）

| 组件 | 结论 | 证据 URL | 关键原文 | 等级 |
| --- | --- | --- | --- | --- |
| reka-ui 2.11.0 | MIT | https://raw.githubusercontent.com/unovue/reka-ui/v2.11.0/LICENSE | `MIT License` / `Copyright (c) 2023 UnoVue` | 上游 raw LICENSE（tag 直达）；本机 `node_modules/reka-ui/LICENSE` 首行同为 `MIT License` |
| Pydantic 2.13.5 | MIT | https://raw.githubusercontent.com/pydantic/pydantic/main/LICENSE | `The MIT License (MIT)` / `Copyright (c) 2017 to present Pydantic Services Inc. and individual contributors.` | 上游 raw LICENSE；本机 `pydantic-2.13.5.dist-info/METADATA` 的 `License-Expression: MIT` 一致 |
| Redis 7.4.8 | RSALv2 或 SSPLv1（二选一） | https://raw.githubusercontent.com/redis/redis/7.4/LICENSE.txt | `Starting on March 20th, 2024, Redis follows a dual-licensing model ... subject to the user's choice of the Redis Source Available License v2 (RSALv2) or the Server Side Public License v1 (SSPLv1)` | 上游 raw LICENSE.txt（7.4 分支） |

Redis 版本线边界（同一 LICENSE 家族的对照，避免把 7.2 或 8.x 的许可套到 7.4.8 上）：

- 7.2.x 及更早：BSD-3-Clause（`COPYING`）。
- 7.4.0–7.4.11：RSALv2 / SSPLv1 双许可。本包固定 `redis:7.4.8-alpine`，落在这一段。
- 8.0.0 起：RSALv2 / SSPLv1 / AGPLv3 三选一。

### 4.2 追加核查（不在抽检 3 条内，但结论会写进对外文档，故一并核实）

| 组件 | 结论 | 证据 |
| --- | --- | --- |
| psycopg 3.3.6 | LGPL-3.0-only | 上游 `LICENSE.txt` 为 LGPLv3 正文；`only` 由作者发布的包元数据确认为 `License-Expression: LGPL-3.0-only`（PyPI 与本机 `psycopg-3.3.6.dist-info/METADATA` 一致） |
| redis（Python 客户端）6.4.0 | MIT | PyPI 元数据 `license_expression: MIT`。与 Redis 服务端是两个组件，已在 06 正文显式区分 |
| uv 0.11.23 | MIT OR Apache-2.0 | PyPI 元数据 `license_expression: MIT OR Apache-2.0`；本机 `uv --version` 为 0.11.23 |
| celery 5.6.3 | BSD-3-Clause | https://raw.githubusercontent.com/celery/celery/v5.6.3/LICENSE（正文含 `Celery is licensed under The BSD License (3 Clause...)`；文档部分为 CC BY-SA 4.0，不随包分发） |
| androguard 4.1.3 | Apache-2.0 | PyPI `license` 字段为 `Apache Licence, Version 2.0`；随安装包 `LICENCE-2.0` 为 Apache 2.0 正文。**注意**：同一 METADATA 的分类器写作 `License :: Other/Proprietary License`，与上述两处互斥；判为上游打包元数据笔误，采用 Apache-2.0 |
| hatchling | MIT | 仅在 `[build-system]` 声明，构建期使用，不在运行期加载；06 中以文字说明，不列表 |

### 4.3 证据分工

- **npm**：本机 `node_modules/<pkg>/package.json` 的 `license` 字段 + 该包 `LICENSE*` 首行 + `package-lock.json` 对应条目，三者交叉一致（9/9）。
- **pip**：`uv.lock` 全文不含 `license` 字段，本地以 `apps/api/.venv` 的 `*.dist-info/METADATA` 的 `License-Expression` 为准（8 项），未安装的 extras 走上游或 PyPI 元数据。
- **cargo**：`Cargo.lock` 不含 `license` 字段，本机无 cargo registry，`tauri` / `tauri-build` 的 `MIT OR Apache-2.0` 依据上游仓库双许可文本，未做 raw 逐文件复核。
- 未做任何推测性填充：无法从本地与上游确认的条目未写入 06。

## 五、并发修改警示（#222 正在同一包内写入）

建立副本之后，`deccced-anon` 被另一执行会话（PT-906-B3 / #222）继续修改。`deccced-anon-b4` 与 `deccced-anon` 的内容比对（631 文件）显示 7 处非本票差异：

| 文件 | 说明 |
| --- | --- |
| `01_作品及成果文件/source/README.md` | B3 修订（对应 G5 披露链） |
| `01_作品及成果文件/source/apps/web/src/App.vue` | B3 修订（对应 G5） |
| `01_作品及成果文件/source/apps/web/src/contracts.generated.ts` | B3 修订（对应 G5） |
| `05_补充成果材料/验收摘要.md` | B3 修订（对应 G6 口径冲突） |
| `07_AI工具使用补充说明/AI工具使用说明.md` | B3 重写（对应 G1–G4，02:01:54 写入） |
| `07_AI工具使用补充说明/AI工具使用说明.docx` | B3 新增官方模板格式（02:02:10 写入，b4 内不存在） |
| `00_材料清单.md` | 已被 B3 更新 |

另外 `deccced-anon/PrivacyTrace_322234.zip`（SHA `828C5224…`，41,192,137 B）已被 B3 改名为 `PrivacyTrace_322234.zip.stale-before-PT-906-B3`，标记为修订前旧包。

因此：

- `deccced-anon-b4` 是 **02:00:17 的快照 + 本票的 06 修订**，其余文件（含 07）为修订前状态，**不可作为最终候选包**。
- 副本内同名的旧 ZIP 已在本票中删除（仅删副本，原包保留改名后的旧 ZIP）。理由：修订候选目录内带着一份 06 未修订的旧包，容易被误当成品上传。
- 最终候选必须由 #224 以 `deccced-anon`（含 B3 成果）为基座合入本票的 06，再重算清单与哈希。

## 六、范围外发现（不在本票修）

1. **包内存在「仅内部验证」限定语**：`01_作品及成果文件/demo-web/DISTRIBUTION.txt` 第 1–2 行为 `INTERNAL VERIFICATION ONLY. Project source license is pending team decision.` 与 `This task grants no public release or competition-submission authorization.`；`demo-web/README.txt` 第 5 行同类。这与本包作为竞赛提交包的用途直接冲突，需负责人裁定是改文案、还是补授权说明。
2. **Tauri 壳层的路径依赖在包内缺件**：`apps/mobile/src-tauri/Cargo.toml` 引用 `../../../experiments/android-package-probe/tauri-plugin`，而包内 `01_作品及成果文件/source/` 下没有 `experiments/` 目录，随包分发的移动端壳层无法用包内文件构建。
3. **07 未与 06 对齐**：06 已按运行期事实写明可选 LLM 服务（默认 `gpt-4o-mini`、默认关闭、需自配 Key、不随包分发）。若 07 把同一接口写成研发期辅助工具，两处会被读出矛盾。口径以事实为准，不在本票改 07。

## 七、未完成项与交接

| 项 | 归属 |
| --- | --- |
| 副本内 `00_材料清单.md` 重算（含 06 新哈希、文件数、总字节） | #224 |
| 终稿 ZIP 重打包与整体 SHA-256 | #224 |
| 06 与 07 的口径一致性复核 | #222 / #224 |
| 旧 ZIP 与 `DISTRIBUTION.txt` 限定语的处理决定 | 负责人 |
| Assignee 设置与关票 | 负责人 |

交接材料：修订后 06 见 `.scratch/package-final/deccced-anon-b4/PrivacyTrace_322234/06_第三方资源说明/第三方资源说明.md`；本节与第四节的证据可直接复核。

## 八、复现方式

```powershell
# 只读：从三份锁定文件解析直接依赖的版本与许可字段
node docs/acceptance/issue223/extract-deps.cjs .
```

脚本只读，不写任何文件；npm 侧同时读取对应包 `LICENSE*` 首行做交叉校验。
