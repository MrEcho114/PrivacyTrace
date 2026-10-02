# PrivacyTrace

面向普通 Android 用户的 App 隐私体检工具：把多源、可追溯的隐私证据转化为能理解、能复核的报告。

项目依据：`docs/source/PrivacyTrace_PRD_MVP_项目简报_v0.1.pdf`（2026-10-01，组内审阅稿）。本文档中的技术选型是建仓阶段的工程决策，并非比赛官方要求。

## 当前能运行什么

- FastAPI 服务及 OpenAPI 文档。
- 事实、政策声明、上下文推断分开的类型模型；证据引用、政策快照与哈希校验。
- 初版确定性一致性规则：六种状态、上位类别匹配、宿主多源冲突、证据不足。
- Vue 报告骨架：概览 → 按来源对照 → 权限、API、政策原句与完整快照。
- 人工构造的演示数据、规则测试、数据库设计基线、CI 与比赛任务清单。

**当前是项目骨架。演示 App、代码片段和政策均为人工构造。** 真实 APK 导入、Manifest/DEX 解析、SDK 检测、LLM 政策结构化、数据库持久化和真实样本评测尚未实现。SDK policy 类型已建模，独立 SDK 核验待实现；它不能代替宿主声明。规则只核验数据类型声明，尚不覆盖完整 Purpose/Recipient/Transfer/TemporalScope 一致性。当前既没有实时模型调用，也没有用户实验结果。

## 本地运行

需要 Node.js 22.12+（或符合 Vite 要求的更新 LTS）、Python 3.11–3.13、Git 和 uv。建仓时验证环境为 Node.js 24 / Python 3.12；依赖分别锁在 `package-lock.json`、`apps/api/uv.lock`。官方参考：[Vite](https://vite.dev/guide/)、[Vue](https://vuejs.org/guide/quick-start.html)、[FastAPI](https://fastapi.tiangolo.com/tutorial/)、[uv](https://docs.astral.sh/uv/getting-started/installation/)。

在仓库根目录安装依赖：

```powershell
npm ci
uv sync --project apps/api --locked
```

打开两个终端，分别启动：

```powershell
# 终端一：后端
uv run --project apps/api --locked uvicorn privacytrace.main:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
# 终端二：前端
npm run dev
```

打开 [报告预览](http://127.0.0.1:5173)；接口文档在 [OpenAPI](http://127.0.0.1:8000/docs)。前端通过 Vite 转发 `/api`，无须额外配置 CORS。首次运行不需要 API 密钥或 APK。

Windows 也可使用 `scripts/setup.ps1`、`scripts/dev-api.ps1`、`scripts/dev-web.ps1`，从任意目录调用。它们优先使用 PATH 中的工具，必要时寻找 Codex 已有的运行时，不安装全局软件。

先安装再启动开发服务。Windows 下服务运行时可能占用 esbuild.exe，重新执行 npm ci 前应停止前端服务。

## 验证

```powershell
uv run --project apps/api --locked pytest
uv run --project apps/api --locked ruff check apps/api/src apps/api/tests
npm run build
```

数据库结构定义在 `apps/api/schema.sql`，当前未接入运行时。生成共享 JSON Schema：

```powershell
uv run --project apps/api --locked python scripts/export-schema.py
```

## 仓库结构

```text
apps/api/                 Python API、数据模型、规则引擎、测试、SQL 基线
apps/web/                 Vue 3 + TypeScript + Vite 报告页面
packages/contracts/       从后端模型生成的 JSON Schema
rules/                    分类体系、权限/API/政策词映射与规则版本
samples/demo/             可公开的人工构造样本
samples/real-world/       真实样本登记模板；APK 文件保持在本机
benchmarks/               评测协议与 Ground Truth 模板
docs/                     原始简报、范围、架构、任务清单、开发记录
evidence/                 可公开的复核记录模板
scripts/                  安装、启动、契约导出和私有仓库发布辅助
.github/                  CI 与工单/PR 模板
```

## 第一开发里程碑

下一步先选一个官方渠道真实 APK、冻结版本与 SHA-256，然后获得权限和敏感 API 的证据位置，收集一份真实政策并整理可追溯的 PolicyClaim。让引擎输出 3–5 条可解释结果，并在页面点击查看代码证据和政策原句。验收细项见 `docs/milestone-1.md`，任务编号沿用简报 PT-xxx，见 `docs/backlog.md`。

动态分析保持 P1，待静态主线成立后评估。比赛截止日期、队员、指导老师、评分权重和提交格式仍待核对，见 `docs/competition-checklist.md`。

## 协作与数据

每个结论绑定 Evidence IDs；静态结果表述为“潜在行为 / 静态证据”。政策声明不写入代码事实，模型推断独立保存。报告不生成总风险分数或合法性、安全性裁决。

`.gitignore` 排除了密钥、APK、DEX、数据库和私人实验记录。真实政策快照及原始样本存放在本机 `data/` 或 `samples/private/`，公开证据按授权情况整理。当前项目源码许可证待团队决定，依赖许可证单独记录在 `docs/dependencies.md`。

GitHub 私有仓库：[MrEcho114/-](https://github.com/MrEcho114/-)，本地项目名为 `privacytrace`。该仓库由用户创建并授权，origin 已配置。后续终端 push 需本机 Git 登录和网络连通。`scripts/publish-private.ps1` 仅用于通过已登录的 GitHub CLI 创建尚不存在的私有远程库。
