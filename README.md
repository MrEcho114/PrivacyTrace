# PrivacyTrace

<p align="center">
  <a href="https://github.com/MrEcho114/PrivacyTrace/actions/workflows/check.yml"><img alt="Check" src="https://github.com/MrEcho114/PrivacyTrace/actions/workflows/check.yml/badge.svg?branch=main"></a>
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/License-MIT-yellow.svg"></a>
</p>

PrivacyTrace 拿 Android 安装包和它的隐私政策原文做对照。它从 APK 里静态读出隐私相关的调用线索，把每条线索指到具体的代码位置，再摆上政策里对应的那句话。它只回答两件事：代码里有没有这条线索，政策里有没有这句话。应用是否真的收集数据、有没有外传、数据往哪流、安不安全、合不合法，都不在结论范围里。

产品入口只有一个：Android App，也就是 `apps/mobile` 的 Tauri 2 壳加载移动界面。想零安装看一眼，用断网只读的离线回放包。浏览器工作台和 Web 构建产物扮演另外的角色，App 的界面来源、工程验收介质、离线回放载体，既不是第二个客户端，也不是产品入口。口径见 [ADR-0004](docs/adr/0004-client-is-android-app.md)。

项目准备参加 2026 年第十四届数媒竞赛。API、隔离扫描和部署基线在 main 上，Android 客户端主流程也合了。2026-10-22 的提交前最终验收已经收口，结论是没有全部通过：失败项和未跑项按原样留在 [#128](https://github.com/MrEcho114/PrivacyTrace/issues/128) 的记录里，项目接受现状，不补跑也不改判。正式提交和回执由 [#107](https://github.com/MrEcho114/PrivacyTrace/issues/107) 跟踪，工程节点不等于赛事结果。

## 界面预览

| 导入 | 候选 |
| :---: | :---: |
| <img src="showcase/privacytrace/assets/stills/import.png" width="420" alt="导入页：选择 APK 或 base 加 splits"><br>选文件只准备输入，点继续才上传 | <img src="showcase/privacytrace/assets/stills/candidates.png" width="420" alt="候选页：政策候选网址"><br>确认政策候选后才进入分析 |

| 报告 | 证据下钻 |
| :---: | :---: |
| <img src="showcase/privacytrace/assets/stills/report.png" width="420" alt="报告页：按来源对照"><br>按来源对照，结论指得到代码位置 | <img src="showcase/privacytrace/assets/stills/evidence.png" width="420" alt="证据页：代码位置与政策原句"><br>线索定位到文件与方法，并对照政策原句 |

这四张图是 Chromium 在 main 分支上实际截的，材料是构造的 APK 和一段人工短政策，原始 PNG 没有涂改，不代表一次真实 App 扫描。每张图的捕获时间、视口和哈希记在 [素材与制作来源](showcase/privacytrace/ASSETS.md)。想连着看流程，有 120 秒[演示视频](showcase/privacytrace/delivery/PrivacyTrace-1080p.mp4)。

## 本地启动

Node.js 24（或 22.12+），Python 3.11–3.13，依赖用 uv 管。Docker 只在扫真实 APK 时需要。

仓库根目录开两个终端：

```bash
# 终端 1：API（127.0.0.1:8000）
npm ci
uv sync --project apps/api --locked --extra worker
uv run --project apps/api --locked --extra worker uvicorn privacytrace.main:app --host 127.0.0.1 --port 8000
```

```bash
# 终端 2：Web（127.0.0.1:5173）
npm run dev
```

打开 http://127.0.0.1:5173。API 没起来时只有「体验示例」可用：固定材料，四步走完导入、候选、进度、报告，看得到代码线索、政策原句和证据定位。它是工程演示夹具，界面上的名字还是「体验示例」，不表示正在分析你刚选的那个 APK。API 起来之后，上传 APK、抓取政策正文、保存候选、启动扫描才解锁。

选文件只是准备输入，点「继续」才上传；候选确认并开始分析，扫描才启动。政策完整度、正文取得情况和附件检查状态一直显示在界面上。模型凭证只存在后端，模型抽取默认关着。

扫真实 APK 要先建 Worker 镜像，见[隔离扫描](#隔离扫描)。

## Android 客户端

第一次接触产品走这条路。流程是：选已安装应用、确认包集合、上传、准备政策（自动、辅助或自备模型）、确认候选、启动分析、看进度和报告、删掉远端材料。

源码在 [`apps/mobile`](apps/mobile)，Tauri 2 壳加载同一套移动界面，读应用列表和上传由原生 Kotlin 模块负责。构建前先在仓库根目录执行 `npm ci && npm run build`，再进客户端目录：

```bash
cd apps/mobile
npm ci
npm run android:prepare
npm run android:build
```

需要 Rust 和 Android 工具链。初始化固定在 API 36，备份和明文传输都关了。产物是 debug APK，只证明当前 ABI 和本机环境能跑，真机矩阵没验过。个人模型 Key 存在设备原生侧，只发往你自己配的 HTTPS Chat Completions 地址，不经过 WebView 和 JavaScript；不支持流式输出，也不会自动重试。模型端点不能和分析实例同源。细节见 [客户端说明](apps/mobile/README.md)。

## 浏览器工作台

浏览器工作台不是客户端。它做三件事：工程调试与内部走查、工程验收时查状态和报告、离线回放包打开后展示同一份报告。

复核真实 APK 也走这里：上传单个 APK，或者 base 加全部 splits；政策候选网址从 manifest 里提出来抓正文，抓不到可以手工补。确认候选之后，材料进 Docker 隔离 Worker 做静态扫描，产出作业、报告和能下钻的证据。

它和客户端加载同一套界面构建产物，所以状态和报告结构对得上。选应用、读包集合这类原生能力它没有，也不补。

## 隔离扫描

未知 APK 只在 Docker 里解析，宿主机 CLI 负责调容器。

先建 Worker 镜像：

- Linux：`docker build -f apps/api/worker.Dockerfile -t privacytrace-worker:s1 .`
- Windows WSL2（PowerShell）：

  ```powershell
  $root = (wsl.exe -d Ubuntu-24.04 --exec wslpath -u $PWD.Path).Trim()
  wsl.exe -d Ubuntu-24.04 --exec docker build --file "$root/apps/api/worker.Dockerfile" --tag privacytrace-worker:s1 $root
  ```

政策摄取要两份准备好的材料：纯文本 raw 和候选 candidates。快照写进指定的新目录，生成不可变快照，旧快照不动；原文里同一句重复出现，每条候选各带各的起止偏移。扫描的 Job ID 必须全局唯一。

```bash
# 政策切片摄取
uv run --project apps/api --locked --extra worker python -m privacytrace.policy_intake \
  --raw evidence/private/input-policy.txt \
  --source-url https://example.org/privacy \
  --version 1.0 \
  --output-dir evidence/private/capture-new \
  --candidates evidence/private/candidates.json
```

```bash
# 隔离扫描
uv run --project apps/api --locked --extra worker python -m privacytrace.pipeline \
  --apk samples/private/sample.apk \
  --policy evidence/private/capture-new/policy.capture.json \
  --name DemoApp \
  --job-id job-demo-001 \
  --product-scope DemoApp
```

## 架构

| 层 | 技术 | 职责 |
| --- | --- | --- |
| Web | Vue 3、TypeScript、Vite | App 的界面来源：材料工作台、任务状态、报告与证据下钻；不是客户端 |
| Android | Tauri 2、原生 Kotlin 模块 | 唯一客户端：选应用、读包集合、HTTPS 上传、政策补入、报告 |
| API | Python、FastAPI、Pydantic | 输入与政策处理、作业与持久任务、规则对照、报告模型 |
| 静态分析 | Androguard、受限 Docker Worker | 解析 Manifest 和 DEX，产出规则约束下的敏感调用线索 |
| 部署运行时 | PostgreSQL、Redis、Celery、mTLS Runner | 持久任务、投递、隔离执行、健康检查 |
| 存储与回放 | 本机 JSON、PostgreSQL、离线只读包 | 作业存档、版本与哈希核对、断网展示 |

链路是：APK 和政策材料进本机或部署的 API，交给隔离扫描，静态证据和政策候选对上，结果在 App 里看。同一份报告也能在浏览器工作台或离线回放包里只读复核。本机模式只绑回环地址、作业存 JSON、没有账号；部署模式接 PostgreSQL、Celery 和 Runner，任务访问靠随任务发放的访问材料，仍然不建账号。两种模式都没有公网实例。

## 能力边界

- 扫 AXML 和全部 `classesN.dex`，认定位、标识、联系人、相机、麦克风、文件与媒体（含截屏 `SCREEN_CAPTURE`）这类敏感调用。
- 常量推导只到方法内无分支、无 try 块的局部常量，证不出来的参数留成 `UNKNOWN`。
- `COMPLETE` 只说明支持的 DEX 范围处理完了，不代表行为全覆盖。规则没命中，不代表没有隐私行为。
- 权限声明只说明应用申请了能力，代码里的调用线索也只是静态线索。两样都证明不了实际采集，也撑不起安全或合法性的结论。
- 加壳应用、Native 库（`.so`）、反射、动态加载、Flutter 和混合开发应用不保证覆盖。生产分析容器里没有 JADX，拿不到反编译结果就走字节码兜底（`UNAVAILABLE_BYTECODE_FALLBACK`）。
- 政策不靠大模型生成，也不做动态沙箱抓包和用户行为实验。模型只辅助整理候选，最终状态由规则和人工判断。
- 本机作业存 JSON，部署模式用 PostgreSQL，本机 JSON 不会自动导入 PostgreSQL。
- 扫描器用完的 APK 副本默认在退出时删掉，只留受限收据，累计预算默认 1 GiB。网页上传的原文件留在本机供恢复和重试，不做自动清理；扫描目录里的旧残留要人工核对，见 [运行时保留策略](docs/stages/s1-runtime-retention.md)。
- 本机 API 只绑 `127.0.0.1`，没有账号认证；部署基线默认拒绝生产启动。两条路都不该直接暴露到公网。

## 评测

受控评测一共十二个源码场景：C01–C06 是第一批，扩展版补了 C07–C12。三种方案拿同一份材料对照，报告能打包成断网只读回放。

三十六行比较里，状态跟受控真值一致的是 PrivacyTrace 12/12、权限＋关键词 2/12、API＋扁平规则 4/12。这是对受控目标状态的对齐情况，不是对真实 App 的检测准确率。没有「实际采集」的二元真值，所以不给 Precision、Recall 或 F1。六个场景覆盖五类对照状态，材料是源码构建加冻结真值，同样不外推到商业应用。

6 人理解测试算探索性记录：报告在主观可读性上均值 4.00 对 2.33，「更方便找到依据」6/6；但 C05 冲突场景的 4 名参与者都读成「不涉及定位」，可能是报告的层级让结论区替代码证据区作了答。样本小、非随机、阅读顺序还不平衡，不能当产品效果结论。详见 [公开摘要](docs/stages/pt907-user-study-20261019.md)。

这些结果推不出真实采集或传输行为，推不出合法性，也推不出商业 App 上的泛化表现和未定义目标下的准确率。

## 验证

从仓库根目录跑：

```bash
# Linux / macOS / Git Bash
bash scripts/check.sh

# Windows PowerShell（pwsh 或 powershell 都行）
pwsh -NoProfile -File scripts/check.ps1
```

这个入口跑 Python 和 Web 的测试、规范检查、契约导出差异和构建；设了 `PRIVACYTRACE_DOCKER_TESTS=1` 会再建 Worker 镜像、跑 Docker 测试，CI 默认开着。单项命令：

```bash
uv run --project apps/api --locked --extra worker ruff check apps/api/src apps/api/tests scripts/export-schema.py
uv run --project apps/api --locked --extra worker pytest apps/api/tests
npm run typecheck
npm run build
```

真实流程的材料单独跑：`npm run acceptance:live`，公开政策和真实模型加 `-- --public`，两类证据分开记；前端交互用 `npm run acceptance:frontend`；报告 HTTP 用 `npm run acceptance:browser`，材料可以写进 `PRIVACYTRACE_EVIDENCE_DIR` 指定的目录；移动界面用 `npm run acceptance:mobile`。产物落在已忽略的本地目录，不进 Git。流程、限额和恢复约定见 [真实流程说明](docs/design/issue-44-live-workflow.md)。

移动端两个验收名字别混用。`npm run acceptance:mobile` 是界面契约回归，跑生产 Vue 界面加受控原生桥替身，不碰 APK、模型和真机；真实安装包在设备上的矩阵是客户端实机验收，入口见 [客户端实机验收执行器](deploy/acceptance/mobile/README.md)。浏览器里挂个模拟原生桥走一遍，不能记成真机通过。

CI 通过、真实 Docker 运行、受控评测、离线验收、正式提交，五样是五样，互相顶不了。

## 部署

`deploy/` 下有 API 和 Web 镜像、Compose 清单、Runner 与扫描镜像、R1–R6 验收脚本。验收在干净的 Linux checkout 里跑 `sudo bash deploy/check_acceptance.sh`，要 Docker、BuildKit、Compose、Git、OpenSSL 和 Python 3.12。生产启动由 `runtime-contract.json` 和 preflight 双重门禁控制，现在还是关的。没有镜像发布、DNS 和公网部署，`compose up` 不等于授权上线。配置、秘密边界和恢复手册见 [部署基线](docs/deployment/README.md) 和 [部署验收](docs/deployment/acceptance.md)。

## 进度

下表是 2026-10-23 的落点，验收结论取 2026-10-22 那次。工单状态还会变，具体以链接里的 GitHub 记录为准。

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| [S0 规则与数据契约](https://github.com/MrEcho114/PrivacyTrace/issues/2) | 完成 | 政策切片、静态证据和声明对照进了 main |
| [S1 真实 APK 分析](https://github.com/MrEcho114/PrivacyTrace/issues/3) | 完成 | 隔离扫描、作业存储、Web 报告和证据下钻 |
| [S2 六场景评测](https://github.com/MrEcho114/PrivacyTrace/issues/4) | 完成 | C01–C06 源码构建、三方案比较、浏览器和离线回放 |
| [P1 扩展评测](https://github.com/MrEcho114/PrivacyTrace/issues/6) | 主要交付完成 | C07–C12 经 [PR #76](https://github.com/MrEcho114/PrivacyTrace/pull/76) 合入，合计 12 个场景、36 行比较；[#65](https://github.com/MrEcho114/PrivacyTrace/issues/65) 的理解测试已交付并关闭 |
| [Android 客户端](https://github.com/MrEcho114/PrivacyTrace/issues/68) | 主流程已合入 | 提交前最终验收已收口，结论是未全部通过，失败项和未跑项见 [#128](https://github.com/MrEcho114/PrivacyTrace/issues/128) |
| [服务端部署](https://github.com/MrEcho114/PrivacyTrace/issues/81) | 基线已合入 | R1–R6 验收脚本在 main 的 CI 跑通；独立扫描主机和跨机防火墙按授权记为豁免，不算通过；生产门禁关着 |
| [S3 竞赛交付](https://github.com/MrEcho114/PrivacyTrace/issues/5) | 内部交付完成 | 离线包和材料已归档；正式提交和回执见 [#107](https://github.com/MrEcho114/PrivacyTrace/issues/107) |
| 理解测试 | 已完成（探索性） | 6 人测试的公开摘要见 [PT-907 理解测试](docs/stages/pt907-user-study-20261019.md)；[#65](https://github.com/MrEcho114/PrivacyTrace/issues/65) 于 2026-10-21 关闭 |
| 前端打磨 | 已完成 | [#141](https://github.com/MrEcho114/PrivacyTrace/issues/141)–[#146](https://github.com/MrEcho114/PrivacyTrace/issues/146) 的 Pioneer 视觉和交互打磨，六个工单在 2026-10-22 关闭 |

收口不等于通过。2026-10-22 的最终验收按「计划执行完了、结论是未全部通过、缺口已记录」关闭，项目接受现状，不补跑、不开新票。关闭不改变记录里的失败项和未跑项。

赛事边界：内部验包通过，不等于公开发布，也不等于在竞赛平台提交过。材料要求以 [赛事指南 #74](https://github.com/MrEcho114/PrivacyTrace/issues/74)、[正式提交 #107](https://github.com/MrEcho114/PrivacyTrace/issues/107) 和官方通知为准；官方截止是全国统一时间 2026-10-23 23:59:59，本项目没有校内提交环节。系统提交和回执以 #107 的当前记录为准，README 不预写完成态。

## 文档与协作

- 领域词汇看 [GLOSSARY.md](GLOSSARY.md)，架构决策在 [docs/adr/](docs/adr/)，建仓方案在 [docs/architecture.md](docs/architecture.md)。
- 交付流程见 [docs/workflow.md](docs/workflow.md)；[docs/backlog.md](docs/backlog.md) 只是历史快照，领任务前以 Issue 为准。
- 受控评测材料：[六场景](benchmarks/controlled/README.md)、[十二场景](benchmarks/controlled-v2/README.md)。
- 部署和客户端验收：[部署基线](docs/deployment/README.md)、[部署验收](docs/deployment/acceptance.md)、[客户端实机验收执行器](deploy/acceptance/mobile/README.md)。
- 真实流程的限额与恢复：[docs/design/issue-44-live-workflow.md](docs/design/issue-44-live-workflow.md)。
- 贡献、认领、依赖等待和交接：开始、恢复、分派或更新 PR 前，先读 [CONTRIBUTING.md](CONTRIBUTING.md)，再按[协作检查清单](docs/agents/skills-workflow.md#6-工单流转阻塞依赖与交接规范)完成任务查重、唯一执行会话和共享归属确认；任务用 [任务模板](.github/ISSUE_TEMPLATE/task.yml)，PR 用 [PR 模板](.github/PULL_REQUEST_TEMPLATE.md)。
- 短期分支用 `codex/` 前缀；交接或暂停时，在对应 Issue 留下分支名、最新提交、已有进展和剩余工作。
- 子代理只调查和检查，不独立 push、改 Issue 或合并；合并、发布和部署不在「通过验收」的范围里。
- 本机环境与已知假失败：[docs/agents/local-environment.md](docs/agents/local-environment.md)。

## 许可

本项目自己写的源码和文档按 MIT 授权（[LICENSE](LICENSE)，选择理由与范围见 [ADR 0006](docs/adr/0006-source-license-mit.md)）：可以自由使用、修改、再分发，保留版权和许可声明即可，不提供担保。

- 第三方资源保留各自的许可。`apps/web/public/fonts/` 里的 Noto Sans SC 和 Noto Serif SC 走 SIL Open Font License 1.1，许可文本和字体放一起；Androguard 4.1.3 等运行期依赖见 [docs/dependencies.md](docs/dependencies.md)。
- 随仓库归档的原始 PRD 等用户提供材料、真实样本的元数据引用和历史验收包，按各自记录的授权使用，不在这份许可的授权范围内。
- 未经授权的 APK、完整政策、反编译全文、私人日志和身份信息本来就不进仓库，这一点不因许可决定而变。

## 人工智能工具使用与开源披露声明

这一节是项目自己的披露，不是赛事官方表格，也不代表通过 GB 45438-2025 或其他法规认证。

- 项目历史里用过 Google Gemini、OpenAI Codex、Anthropic Claude 和 DeepSeek Harness，用在部分接口胶水层、数据契约生成、展示文案与视频分镜、测试模板。具体型号、文件、时间和人工修改范围以日志、PR 和仓库里的 [披露记录](docs/ai-usage-disclosure.md) 为准；参赛包内另有 `07_AI工具使用补充说明/`。有记录不等于 AI 没碰过其他环节，也不给没有复算过的比例。
- 架构、规则与界面设计、代码审查和项目管理由团队承担。Git 作者提交数不等于 AI／人工代码行比例，也不等于“100% 独立完成”。
- 类型契约生成文件、Web 报告页脚和阶段 provenance 文件都记了 AI 辅助情况；阶段性 provenance 代表不了全项目范围。
- 参赛名单、指导教师审核和正式申报还要实际确认，见 [披露记录](docs/ai-usage-disclosure.md)、参赛包内的 `07_AI工具使用补充说明/` 和 [赛事材料 #74](https://github.com/MrEcho114/PrivacyTrace/issues/74)。

## 安全声明

本工具只做静态线索和政策声明的辅助对照，不对应用是否安全、是否违法或是否真的收集数据下结论。只扫你有权处理的样本；现在没有账号体系，别把 API 直接绑到公网。
