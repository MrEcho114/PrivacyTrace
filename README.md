# PrivacyTrace

PrivacyTrace 是一个面向普通 Android 用户的应用隐私对照工具。它读取 APK 里的隐私相关静态线索，并与隐私政策文本对照，让用户可以查看这些线索在代码与政策原文中的具体位置。工具目前只对照敏感数据类型是否提及，不证明应用实际上收集或传输了数据。

## 现在能用到什么

- **查看演示报告**：不需要 APK、Docker 或模型 API Key，即可通过浏览器体验固定样例的代码线索、政策原句和证据定位。演示数据不代表真实 App 的扫描结果，演示模式不保存复核备注。
- **分析真实 APK**：在本机 Web 工作台上传 APK、添加多个隐私政策来源、确认政策候选，再由 Docker 隔离 Worker 执行静态分析；也可通过宿主机 CLI 运行。支持查看已持久化的作业、报告和人工复核备注。
- **对照隐私声明**：分开呈现权限能力、DEX 敏感调用线索、政策文本、候选声明与证据不足状态；政策候选可由人工整理或可选模型辅助，但不会由模型直接给出最终事实判定。
- **运行受控评测与离线回放**：主线已包含六个自建源码场景、冻结真值、三方案比较和只读离线报告包，详见 [受控评测说明](benchmarks/controlled/README.md)。离线回放不等于离线重新扫描任意 APK。

## 技术架构

| 层次 | 技术栈 | 职责 |
| --- | --- | --- |
| Web 前端 | Vue 3、TypeScript、Vite | APK 与政策材料工作台、任务状态、报告和证据下钻 |
| API 与规则 | Python、FastAPI、Pydantic | 输入与政策处理、作业管理、静态证据对照及报告模型 |
| APK 静态分析 | Androguard、隔离 Docker Worker | Manifest/DEX 解析和受规则约束的敏感调用线索提取 |
| 数据与交付 | 本地 JSON 作业存储、离线只读回放包 | 结果存档、版本/哈希核对、离线展示 |

主要路径：**APK + 政策材料 → 本机 API → 隔离扫描 → 静态证据与政策候选对照 → Web 报告／离线回放**。本地 API 当前没有远程用户认证，不能直接部署为公网服务；SQLite 尚未接入运行时。大模型辅助候选抽取是可选功能，不是默认分析或报告展示的前提。

后续公网多用户服务拟保留现有前后端，采用 API 容器、PostgreSQL、Celery/Redis 与独立扫描执行边界，继续免登录并按任务保护访问。方案详见 [可行性与实施方案](docs/planning/api-docker-20261016.md)；主线已合入 [PT-SRV-102 部署交付基线](docs/deployment/README.md)（含 stage-only 容器配置与本地 smoke 验证），生产启动门禁保持拦截，尚无公网服务部署。

## 项目进度（2026-10-19 快照）

以下为已验收交付与尚未完成工作的区分；工单状态会继续变化，以链接中的 GitHub 记录为准。

| 阶段 | 状态 | 已交付／剩余事项 |
| --- | --- | --- |
| [S0 · 规则与数据契约](https://github.com/MrEcho114/PrivacyTrace/issues/2) | 已完成 | 长政策切片、静态证据与声明对照基线已进入主线 |
| [S1 · 真实 APK 分析](https://github.com/MrEcho114/PrivacyTrace/issues/3) | 已完成 | 隔离扫描、作业存储、Web 报告与证据下钻 |
| [S2 · 六场景受控评测](https://github.com/MrEcho114/PrivacyTrace/issues/4) | 已完成 | C01–C06 源码构建、三方案比较、浏览器验收与误差说明 |
| [S3 · 竞赛交付](https://github.com/MrEcho114/PrivacyTrace/issues/5) | 内部交付完成 | [#18](https://github.com/MrEcho114/PrivacyTrace/issues/18) 内部断网交付验收、[#19](https://github.com/MrEcho114/PrivacyTrace/issues/19) 材料工单与 [#5](https://github.com/MrEcho114/PrivacyTrace/issues/5) 内部交付已关闭；[#107](https://github.com/MrEcho114/PrivacyTrace/issues/107) 正式平台提交与回执仍待完成 |
| [P1 · 扩展实验](https://github.com/MrEcho114/PrivacyTrace/issues/6) | 部分完成 | [#62](https://github.com/MrEcho114/PrivacyTrace/issues/62) 测试准备包、[#63](https://github.com/MrEcho114/PrivacyTrace/issues/63) 样本归档已完成；[#64](https://github.com/MrEcho114/PrivacyTrace/issues/64) 十二场景候选待合并，[#65](https://github.com/MrEcho114/PrivacyTrace/issues/65) 真实参与者测试待开展 |
| [Android 客户端](https://github.com/MrEcho114/PrivacyTrace/issues/68) | 规格阶段 | [#69–#73](https://github.com/MrEcho114/PrivacyTrace/issues/69) 已拆分远程认证、API 契约、客户端与真机验收任务，并交付 [#73 验收准备包](docs/acceptance/issue73/README.md)（PREPARATION_ONLY）；**尚无可交付 Android 客户端** |
| [服务端部署](https://github.com/MrEcho114/PrivacyTrace/issues/81) | 基线就绪 | 已合入 [PT-SRV-102 部署交付基线](docs/deployment/README.md)（含 stage-only 镜像与本地 smoke）；生产启动门禁保持拦截，[#80](https://github.com/MrEcho114/PrivacyTrace/issues/80) 运行时调度待交接 |

**赛事交付边界**：内部通过验收的离线包不代表已公开发布或已在竞赛平台正式提交。参赛材料与当前要求以 [赛事指南 Issue #74](https://github.com/MrEcho114/PrivacyTrace/issues/74)、[正式提交 Issue #107](https://github.com/MrEcho114/PrivacyTrace/issues/107) 和官方通知为准；统一以全国截止时间 2026-10-23 23:59:59 为准，本项目不存在校内提交或校内收件环节。

### 评测结果的适用范围

- **已进入 main 的基线**：六个自建受控场景 C01–C06，覆盖五类对照状态，均使用源码构建、冻结标签与同材料比较；这不是商业应用的全局真值数据集。
- **待合并的扩展**：[PR #76](https://github.com/MrEcho114/PrivacyTrace/pull/76) 在原六个场景基础上新增 C07–C12，候选分支报告 12 个场景、36 条三方案记录，状态一致数量分别为 PrivacyTrace 12/12、权限＋关键词 2/12、API＋扁平规则 4/12。这些是受控目标状态的比较结果，**不是已进入 main 的功能**，也不是对真实 App 的检测准确率。
- **尚未完成**：[#65](https://github.com/MrEcho114/PrivacyTrace/issues/65) 的 6–10 位真实参与者理解测试。已有 Synthetic 演练只用于准备包和计算工具验证，不代表真实参与者研究。
- **不能据此推导**：实际采集／传输行为、合法性、商业 App 泛化性能或未定义目标下的 Precision / Recall / F1。

## 运行环境要求

- Node.js 24（或 22.12+），npm
- Python 3.11 ~ 3.13，uv 包管理器
- Docker（仅在执行真实 APK 隔离扫描时需要；本地查看演示界面不需要 Docker，也不需要配置 API Key）

## 启动演示服务

推荐在仓库根目录打开两个终端，分别启动后端与前端服务：

```bash
# 终端 1：启动 API 服务（127.0.0.1:8000）
npm ci
uv sync --project apps/api --locked --extra worker
uv run --project apps/api --locked --extra worker uvicorn privacytrace.main:app --host 127.0.0.1 --port 8000
```

```bash
# 终端 2：启动前端界面（127.0.0.1:5173）
npm run dev
```

服务启动后，在浏览器中打开 http://127.0.0.1:5173 即可访问前端页面。

首页提供四步材料工作台。连接本机 API 后，可上传 APK、获取多个公开 HTML 政策、检查模型或手动候选，再在受限 Docker 中扫描并查看存档报告。项目设置仅在后端保存模型凭证；政策完整度、全文和附件未复核状态保持可见。选择文件只准备输入，点击继续才上传；保存候选并开始分析才启动扫描。

选择“体验示例”可仅运行前端浏览固定材料、手动阶段和固定报告；选择“已有报告”则读取后端已保存的任务。真实流程验收运行 `npm run acceptance:live`，公开政策与实际模型验收加 `-- --public`，两类证据分开记录。配置、限额和恢复约定见 [真实流程说明](docs/design/issue-44-live-workflow.md)。

前端交互验收运行 `npm run acceptance:frontend`，自行启动并关闭专用页面服务，截图及版本记录保存在本地目录 `tmp/issue44-ui/`（该目录已被 git 忽略）。真实报告 HTTP 验收使用 `npm run acceptance:browser`；设置环境变量 `PRIVACYTRACE_EVIDENCE_DIR` 可将本次材料输出到独立目录，避免覆盖历史记录。

## 真实 APK 隔离扫描与政策摄取

对真实未知 APK 的分析必须在 Docker 隔离环境中运行，禁止在宿主机直接解析未知 APK；以下宿主机 CLI 负责调用隔离容器。

### 1. 构建隔离 Worker 镜像

- **Linux**：`docker build -f apps/api/worker.Dockerfile -t privacytrace-worker:s1 .`
- **Windows WSL2 (PowerShell)**：
  ```powershell
  $root = (wsl.exe -d Ubuntu-24.04 --exec wslpath -u $PWD.Path).Trim()
  wsl.exe -d Ubuntu-24.04 --exec docker build --file "$root/apps/api/worker.Dockerfile" --tag privacytrace-worker:s1 $root
  ```

### 2. 政策摄取与扫描作业

政策摄取需提供已准备好的纯文本 raw 与 candidates 候选文件。摄取将在指定的新目录生成不可变快照，不覆盖旧快照；若原文中出现重复原句，需分别给出各自精确的起始与终止偏移量（start/end offsets）。

```bash
# 政策切片摄取
uv run --project apps/api --locked --extra worker python -m privacytrace.policy_intake \
  --raw evidence/private/input-policy.txt \
  --source-url https://example.org/privacy \
  --version 1.0 \
  --output-dir evidence/private/capture-new \
  --candidates evidence/private/candidates.json

# 执行隔离扫描作业（Job ID 必须全局唯一，不可复用）
uv run --project apps/api --locked --extra worker python -m privacytrace.pipeline \
  --apk samples/private/sample.apk \
  --policy evidence/private/capture-new/policy.capture.json \
  --name DemoApp \
  --job-id job-demo-001 \
  --product-scope DemoApp
```

## 核心能力与分析边界

- **分析范围**：读取 AXML 与全部 `classesN.dex`，识别定位、标识、联系人、相机、麦克风、文件与媒体（含截屏 `SCREEN_CAPTURE`）等敏感调用。
- **常量推导**：仅支持方法内无分支、无 try 块的局部常量推导，未证实参数保持 `UNKNOWN`。
- **覆盖语义**：COMPLETE 仅表示所支持 DEX 范围处理完成；行为识别始终是有限规则静态分析，未命中规则不代表没有隐私行为。
- **分析边界**：
  - 清单中的权限声明仅代表应用申请了对应能力，不代表实际发生调用；代码中存在调用线索，也不作合法性、安全性或实际数据收集判定。
  - 对加壳应用、Native 库（.so）、反射、动态加载、Flutter 及混合开发（hybrid）应用不保证覆盖。
  - 生产分析容器内不含 JADX 反编译引擎，使用字节码兜底（`UNAVAILABLE_BYTECODE_FALLBACK`）。
  - 不使用大模型自动生成政策，也不包含动态沙箱抓包或用户行为实验。
- **存储与安全边界**：
  - 本地作业存储于 `data/jobs` JSON 文件，SQLite 模式暂未接入运行时。
  - 扫描器 APK 运行副本默认在退出后删除，仅保留受限隔离收据；累计预算默认 1 GiB，复制前跨进程预留。网页上传的原文件和输入版本另留在本机，供恢复与重试，限额见 [真实流程说明](docs/design/issue-44-live-workflow.md)。历史文件不自动删除，失败与崩溃残留需人工核对处理。配置、访问权限与清理边界见 [运行时保留策略](docs/stages/s1-runtime-retention.md)。
  - 后端接口仅绑定本机回环地址（127.0.0.1），无身份认证与数字签名，禁止公网部署。

## 验证与测试

优先从仓库根目录执行统一检查入口：

```bash
# Linux / macOS / Git Bash
bash scripts/check.sh

# Windows PowerShell（可使用 pwsh 或 powershell）
powershell -NoProfile -File scripts/check.ps1
```

检查脚本覆盖当前配置下的 Python/Web 测试、规范与契约检查和构建；Docker 相关检查仍取决于环境与运行配置。CI 通过、实际 Docker 验证、受控评测、离线验收以及正式提交是不同的证据，不能互相替代。

### 单项检查命令

```bash
# 规范检查与模式导出
uv run --project apps/api --locked --extra worker ruff check apps/api/src apps/api/tests scripts/export-schema.py
uv run --project apps/api --locked --extra worker python scripts/export-schema.py
npm run typecheck
npm run build

# 基础自动化测试（默认跳过 Docker 测试）
uv run --project apps/api --locked --extra worker pytest apps/api/tests

# 包含 Docker 容器调用的完整测试（需已构建 Worker 镜像）
# PowerShell: $env:PRIVACYTRACE_DOCKER_TESTS="1"; uv run --project apps/api --locked --extra worker pytest apps/api/tests
# Linux: PRIVACYTRACE_DOCKER_TESTS=1 uv run --project apps/api --locked --extra worker pytest apps/api/tests
```

## 人工智能工具使用与开源披露声明

本项目遵循国家《生成式人工智能服务管理暂行办法》《人工智能生成合成内容标识办法》及配套国家标准《网络安全技术 人工智能生成合成内容标识方法》（GB 45438-2025）及高校学术规范要求，对人工智能工具的使用边界、贡献划分与合规标识作如下公开声明：

- **AI 辅助范围界定**：在学生团队主导的核心架构、接口契约与设计规范约束下，部分底层工程代码（如前端 TypeScript 契约导出 `contracts.generated.ts`、后端 API 路由胶水层及基础测试用例骨架）借助 Google Gemini（Gemini 2.5 Pro / Gemini 3.8 Flash）与 OpenAI Codex 辅助生成。AI 不参与选题策划、立项论证、核心算法与判定规则制定。
- **学生团队核心贡献与主体责任**：核心架构设计（Evidence 证据链追溯模型、Consistency Engine 六态判定状态机、Privacy Taxonomy 分类体系）、系统设计规范（红线措辞约束、Docker 隔离沙箱）、全量代码审查（逐行审查排查并发锁竞争等缺陷）及项目管理（13 个 Epic 拆解与 CI/CD 流水线）100% 由学生团队独立完成。文责与知识产权责任 100% 由学生团队独立承担。
- **显式标识与溯源闭环**：自动生成代码头部标注 `[AI-Assisted / Generated Code]` 提示；Web 前端报告页脚标注技术驱动与校对说明；完整机器生成审计凭证（Provenance Receipts）与 CI 验证凭据详见 `docs/stages/s0-gemini-provenance.json`、`docs/stages/s1-gemini-provenance.json` 与 [`docs/ai-usage-disclosure.md`](docs/ai-usage-disclosure.md)。

## Issue 认领与 Blocked 依赖说明

> **Blocked ≠ 禁止认领，也不等于整张 Issue 无法开始。** GitHub 的 `Blocked` / `blocked by` 表示存在待满足的任务依赖，通常影响某些集成步骤或最终验收，而不是对组员设置认领或开发权限限制。

- **可以认领**：对感兴趣且未明确由其他成员负责的 Issue，可先在评论区留言说明认领意向、GitHub 用户名及计划负责的范围，请维护者确认分工。无法自行设置 Assignee 通常因仓库权限限制，与是否 Blocked 无关，由维护者分配即可。已有负责人时先沟通，避免重复工作。
- **可以提前开展不受依赖影响的工作**：需求澄清、设计、独立模块实现、测试用例、测试环境与文档准备等，只要不依赖尚未交付的接口或产物，就不需要等 Blocked 消失。
- **受依赖约束的部分应等待或使用明确约定的契约**：涉及真实上游产物的联调、端到端验证、最终验收/关闭，不得在前置条件未满足时宣称完成；使用 Mock 或临时桩应明确记录，不能当作真实集成通过。
- **先查看依赖的具体范围**：阅读 Issue 正文及 GitHub Dependencies 的 `blocked by` 关系，判断阻塞的是整个实现、某个子功能，还是最终集成/验收；不明确时在该 Issue 评论询问维护者，不要仅凭一个 Blocked 标记放弃认领。
- **依赖变化及时同步**：如果正文已经取消硬依赖，但原生 Dependencies 仍保留旧关系，请通知维护者更新 GitHub 依赖边。修改文字本身不会自动清除 Blocked 标记。

**推荐认领留言**：

> 我希望认领此 Issue（GitHub：@用户名）。已阅读其依赖关系，计划先完成不受前置任务影响的部分：……；依赖就绪后再完成联调/最终验收。请维护者确认分工并按权限设置 Assignee。

**示例**：[Android 端到端验收 #73](https://github.com/MrEcho114/PrivacyTrace/issues/73) 依赖服务端和客户端可交付产物完成最终主链路验收，但测试方案、设备及用例准备可以提前开展（例如 [#73 验收准备包](docs/acceptance/issue73/README.md) 已提前交付基线与场景矩阵，等待依赖就绪后执行端到端核验）；其正文已将 [#79](https://github.com/MrEcho114/PrivacyTrace/issues/79) 定义为非阻塞扩展分支，GitHub 原生依赖边需另行同步调整。

## 项目状态与相关文档

- **使用与受控评测**：[六场景说明](benchmarks/controlled/README.md)、[真实 Web 工作流设计](docs/design/issue-44-live-workflow.md)。
- **核心技术验收**：[S1 技术报告](docs/stages/s1-report.md)、[S2 阶段记录](https://github.com/MrEcho114/PrivacyTrace/issues/4)、[S3 阶段记录](https://github.com/MrEcho114/PrivacyTrace/issues/5)（含 [S3 内部交付](docs/stages/s3-internal-delivery-20261019.md)）。
- **服务端与部署基线**：[API 容器与服务实施方案](docs/planning/api-docker-20261016.md)、[PT-SRV-102 部署交付基线](docs/deployment/README.md)（对应 [Issue #81](https://github.com/MrEcho114/PrivacyTrace/issues/81)，仅含 stage-only 容器与本地 smoke 验证，生产启动保持拦截）。
- **评测扩展与参与者研究**：[PR #76](https://github.com/MrEcho114/PrivacyTrace/pull/76)、[理解测试准备包 #62](https://github.com/MrEcho114/PrivacyTrace/issues/62)、[真实研究 #65](https://github.com/MrEcho114/PrivacyTrace/issues/65)。
- **竞赛材料与提交**：[最新指南 #74](https://github.com/MrEcho114/PrivacyTrace/issues/74)、[提交追踪 #107](https://github.com/MrEcho114/PrivacyTrace/issues/107)。仓库内旧版 [赛务核对清单](docs/competition-checklist.md) 仅作为历史文件，不作为本届最新规则来源。
- **合规披露**：人工智能工具使用与生成内容披露表见 [`docs/ai-usage-disclosure.md`](docs/ai-usage-disclosure.md)。
- **Android 规划与验收准备**：[功能规格 #68](https://github.com/MrEcho114/PrivacyTrace/issues/68)（拟用 Tauri 2 + 现有 Vue 前端，经认证的远程 FastAPI 服务与 Docker Worker；不在手机上直接运行分析引擎）、[PT-MOB-301 验收准备包](docs/acceptance/issue73/README.md)（对应 [#73](https://github.com/MrEcho114/PrivacyTrace/issues/73)，仅完成前置准备，未生成正式客户端）。
- **依赖与许可**：依赖的 Androguard 遵循 [Apache-2.0](https://raw.githubusercontent.com/androguard/androguard/v4.1.3/LICENCE-2.0)。本项目源代码许可仍待团队确定；未经授权的商业 APK、完整政策、私人日志与身份信息不进入公开交付包。

## 安全声明

本工具提供静态证据与声明之间的辅助对照，不对应用是否安全、是否违法或是否发生真实数据收集作出结论。仅在有权处理的样本上执行扫描；请勿将当前未配备远程认证的 API 直接绑定到公网。
