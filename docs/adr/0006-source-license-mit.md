# 源码许可采用 MIT

2026-10-23 · 已接受。项目负责人在 Apache-2.0、MIT、MPL-2.0、AGPL-3.0 与“继续不定”之间选择 MIT。

## 背景

仓库自 2026-10-03 起公开，但根部一直没有 `LICENSE`。公开可见不等于授权：没有许可时默认规则是保留所有权利，外部无法合法复用、修改或再分发。`README.md`、`docs/dependencies.md` 与项目介绍初稿的 N12 也一直把这件事写成“待团队决定”，赛事材料因此无法回答“源码以什么条件公开”。

运行期依赖许可已逐条核过（#223 第三方资源说明修订，记录在分支 `codex/pt-906-b4-third-party-20261023`）：Vue、Vite、Reka UI、Pydantic、FastAPI、pytest、Ruff、redis（Python 客户端）、hatchling 为 MIT；Uvicorn、HTTPX、Celery 为 BSD-3-Clause；TypeScript、Androguard 为 Apache-2.0；Tauri、tauri-build 与 uv 为 MIT 或 Apache-2.0；psycopg 为 LGPL-3.0-only；Redis 7.4.8 服务端为 RSALv2/SSPLv1 双许可；Noto Sans SC / Noto Serif SC 为 SIL OFL 1.1。

没有会强制本项目改用 GPL 的强 copyleft 依赖：psycopg 只作为未修改的 Python 依赖使用，Redis 只作为部署态服务运行、不随源码分发。

## 决定

- 本项目自行创作的源码与文档按 **MIT** 授权，全文在根 `LICENSE`，版权人写为 `PrivacyTrace contributors`。
- 随仓库的第三方资源保留各自许可，不因本决定重新授权；字体与运行期依赖的许可文本、来源继续按 `docs/dependencies.md` 维护。
- 用户提供的原始 PRD、真实样本（GKD 等）的元数据引用与历史验收材料按各自记录的授权使用，不在本许可的授权范围内。
- 产品清单声明 SPDX：根与各 app 的 `package.json`、`apps/api/pyproject.toml`、两处随产品构建的 `Cargo.toml` 写 `MIT`；`private` 与 `publish = false` 保持不变，表示不向对应注册表发布。

## 备选与取舍

| 方案 | 未采用的原因 |
| --- | --- |
| Apache-2.0 | 明示专利授权、商标条款与 NOTICE 义务对集成方更稳，但增加合规办理成本；本轮优先压低头一次集成的理解成本 |
| MPL-2.0 | 文件级 copyleft 带来逐文件回馈义务，与本项目“公开证据、便于复现”的定位叠加后收益不明显 |
| AGPL-3.0 / GPL-3.0 | 会把下游再分发或网络服务拖进 copyleft，限制未来把 API 做成托管服务的选择 |
| 维持无许可 | 公开仓库加保留所有权利是最差组合：看得见、用不了，也无法回答评委与外部引用者 |

已知取舍：MIT 没有明示专利授权与商标条款。若后续出现专利或名称使用的实际风险，可在保持 MIT 兼容的前提下补 `NOTICE` 或单独声明，不改变本 ADR 的许可选择。

## 影响与后续

- 历史材料不回改：`docs/stages/*`、`docs/acceptance/*` 等在“许可待定”时期产生的记录保留当时状态与 SHA。
- 提交包副本与仓库外文案需在下一次重打包时同步：`scripts/export-offline.py` 已改为写明 MIT，已生成的包副本（如 `demo-web/DISTRIBUTION.txt` 的“源码许可待定”）仍待 #224 重冻结时更新。
- 版权人写法为 `PrivacyTrace contributors`；若赛事申报需要具名单位或个人，应在首次对外正式发布前定稿，并把定稿写回本 ADR。
- 依赖许可变化时按 #223 的清单重新核对，不沿用旧结论。

> 编号说明：main 已有 `0004-client-is-android-app` 与 `0005-frontend-contract-retirement`，本 ADR 取 0006。
