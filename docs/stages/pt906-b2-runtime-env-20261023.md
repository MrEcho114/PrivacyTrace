# PT-906-B2 运行环境定稿与环境声明核对

- 日期：2026-10-23
- 任务：Issue [#221](https://github.com/MrEcho114/PrivacyTrace/issues/221)（父票 #107，来源 #197）
- 范围：报名系统「运行环境」字段定稿；包内 `04_运行或使用说明/运行与使用说明.md` 环境段与离线回放段的修订建议
- 事实来源：包内静态材料、仓库配置、既有验收收据。定稿只写实测过的组合。

## 一、结论

1. 定稿可直接粘贴，见第二节。
2. 04 要修两段（环境段、离线回放段），第三节给出可替换文本：`Ubuntu 22.04` 没有「在 22.04 上跑通」的实测记录（仓库里出现的 3 处 `22.04` 都是发行版名、宿主要求或配置示例，见第四节第 1 行）；`Python 3.12` 是构建与验收的实测版本，仓库约束写的是 `>=3.11,<3.14`；离线回放段的路径和描述与包内两种页面都不符。
3. 04 没有 tracked 源，只活在 `.scratch/package-final/` 的打包副本里，成品包正被其他会话重建。本页交补丁文本与依据，由打包会话并入。

## 二、定稿（可直接粘贴到报名系统）

### 长版（字段允许多行时）

```text
运行环境

一、离线回放（推荐，零安装）
用桌面浏览器直接打开包内 01_作品及成果文件/demo-web/web/comparison.html（实测 Chromium 内核的 Chrome/Edge；Safari、Firefox 未实测，不作兼容性承诺），
即为六场景对照表（静态页，不加载脚本、不发起网络请求），不重新分析应用、不依赖后端与数据库。
如需交互式回放：在包内 demo-web 目录执行 python viewer.py --port 8765（仅需 Python 3.11+ 标准库），
再用浏览器访问 http://127.0.0.1:8765；同样不依赖产品后端、数据库或 Docker。

二、完整服务（复现全部功能）
Ubuntu 24.04（原生或 WSL2）；
Docker Engine + Docker Compose v2（实测 Engine 28.0.4 / 29.7.2，Compose 2.38.2）；
Python 3.12、uv 0.11.x、Node.js 24.x；
构建与首次运行需联网安装依赖。
```

### 短版（字段限 150 字左右时）

```text
离线回放：浏览器直接打开包内 demo-web/web/comparison.html 查看六场景对照，无需安装、无需后端。
完整服务：Ubuntu 24.04（原生或 WSL2）、Docker Engine + Compose v2、Python 3.12、uv 0.11.x、Node.js 24.x，首次构建需联网。
```

### 定稿取舍

- `Ubuntu 22.04` 没有「跑通」的实测记录（仓库里只有发行版名、宿主要求和配置示例，见第四节第 1 行），字段里删掉，只写 24.04（原生或 WSL2）。
- 字段写主次版本。Engine、Compose、uv、Node 的 patch 号留在 04 和第三节依据里，字段不被单个 patch 号绑死。
- 两条回放路径分开写：`comparison.html` 打开即看，`index.html` 要配 `viewer.py` 才成立。两句话里「无需后端」的含义不同，混写会让评委白屏。

## 三、04 修订补丁

### 3.1 环境段（第 3–8 行）

替换前：

```markdown
## 环境

- Linux（Ubuntu 22.04/24.04）或 WSL2；
- Docker Engine + Docker Compose v2；
- Python 3.12、uv 0.11.x、Node 24.x；
- 首次运行需联网准备依赖；离线回放不需要后端。
```

替换后：

```markdown
## 环境

- Ubuntu 24.04（原生或 WSL2）；
- Docker Engine + Docker Compose v2（部署验收实测 Engine 28.0.4 / 29.7.2、Compose 2.38.2）；
- Python 3.12（`apps/api/pyproject.toml` 允许 3.11–3.13；构建镜像与验收实测均为 3.12）、uv 0.11.23、Node 24.17.0；
- 首次运行需联网准备依赖；离线回放不需要后端。
```

### 3.2 离线回放段（第 10–14 行）

替换前：

```markdown
## 一、离线回放（最快）

1. 解压本包；
2. 用浏览器打开 `01_作品及成果文件/demo-web/comparison.html`（或 `index.html`）；
3. 页面只读取包内 `reports.json`、`taxonomy.json` 与静态资源，不请求后端。
```

替换后：

```markdown
## 一、离线回放（最快）

1. 解压本包；
2. 用浏览器直接打开 `01_作品及成果文件/demo-web/web/comparison.html`：静态单页，六场景对照表，不加载脚本、不发起网络请求；
3. 如需交互式回放：在 `01_作品及成果文件/demo-web` 执行 `python viewer.py --port 8765`（仅需 Python 3.11+ 标准库），浏览器访问 `http://127.0.0.1:8765`。`web/index.html` 是构建产物，引用绝对路径 `/assets/`，不能用 `file://` 直接打开。
```

### 3.3 修订依据

- 包内文件名是 `demo-web/web/comparison.html` 和 `demo-web/web/index.html`；`demo-web/comparison.html`、`demo-web/index.html` 都不存在。6 份打包副本里 4 份写错，只有匿名化血脉（`deccced-anon`、`deccced-anon-b4`）写对。
- `web/comparison.html` 是自包含单页，没有 `<script>`。检索 `fetch(`、`XMLHttpRequest`、`/api/`、`http://`、`https://`，命中 0。它也不读 `reports.json` 或 `taxonomy.json`。
- `web/index.html` 第 9–10 行引用根绝对路径 `/assets/index-DXpy2zGV.js` 与 `/assets/index-BSn3A6pu.css`，`file://` 下解析不到。前端代码调 `/api/v1/*`，由 `demo-web/viewer.py` 在 `127.0.0.1` 上用标准库应答。
- `demo-web/README.txt` 原文：`Requires Python 3.11+ only; no model key.` / `Run: python viewer.py --port 8765` / `Open http://127.0.0.1:8765`。

## 四、核对结果

| # | 04 原声明 | 实际依据 | 判定 |
| --- | --- | --- | --- |
| 1 | Linux（Ubuntu 22.04/24.04）或 WSL2 | 部署验收收据环境为 `Linux-6.18.33.2-microsoft-standard-WSL2`、`glibc2.39`（即 Ubuntu 24.04）；`docs/acceptance/issue132/environment-recipe.md`、`execution-20261021.md` 记录 Ubuntu 24.04.5 WSL2；CI `runs-on: ubuntu-latest`；全仓 `22.04` 共 3 处，均为发行版名、宿主要求或配置示例（`docs/acceptance/issue136/R02-R04-handoff.md:22`、`apps/api/tests/test_wsl_distro.py`、`docs/agents/local-environment.md`），**没有「在 22.04 上跑通」的实测记录** | 24.04 有证据，22.04 无证据 |
| 2 | Docker Engine + Docker Compose v2 | 部署验收收据 `docker_server` 28.0.4 / 29.7.2；`docker compose version --short` 得 2.38.2；`deploy/compose.yaml`、`compose.smoke.yaml`、`compose.tls-smoke.yaml`、`runner.compose.yaml` 均在库 | 成立 |
| 3 | Python 3.12 | `apps/api/pyproject.toml` `requires-python = ">=3.11,<3.14"`、`target-version = "py311"`；`apps/api/uv.lock` 头部 `>=3.11, <3.14`；构建镜像 `python:3.12.13`；验收实测 Python 3.12.3 | 3.12 是实测版本，仓库约束是区间，04 需注明 |
| 4 | uv 0.11.x | `scripts/check.sh` 装 `uv==0.11.23`；`deploy/Dockerfile`、`apps/api/worker.Dockerfile` 用 `uv:0.11.23` | 成立，可精确到 0.11.23 |
| 5 | Node 24.x | CI `node-version: "24.17.0"`；构建镜像 `node:24.17.0-bookworm-slim`；验收收据 `node v24.17.0`；仓库内所有 `package.json` 都没有 `engines` 或 `packageManager` 字段 | 版本成立，缺机器可读约束 |
| 6 | 离线回放不需要后端 | `docs/acceptance/issue136/evidence/final-package-e17d2e3/demo-receipt.json`：`file://` 打开该页、`offline: true`、`blocked_requests: []`、结果 PASS | 成立，只对 `comparison.html` |
| 7 | 离线回放路径 | 见 3.3 | 4/6 副本写错 |

## 五、未验证项与限制

- Ubuntu 22.04 原生环境没有实测记录，定稿和 04 修订都不写它。
- Compose 版本有两套采集口径：`deploy/check_linux.py` 调 `docker compose version --short`，得 2.38.2；`deploy/acceptance/topology.py` 调裸 `compose`，同一批收据里记 5.5.0。本页取 2.38.2 作 Compose v2 的依据，差异照记。
- 报名系统字段的字数上限没有实测，短版按 150 字量级准备。
- 04 的修订没有进任何成品包，包内文件保持原样。

## 六、范围外（未做）

- `package.json` 的 `engines` 字段：属代码改动，另票。
- `docs/adr/0003-public-api-docker-boundary.md` 的状态：改动需要验收证据，另票。
- 包内 04 文件：留给打包会话，避免和正在进行的重打包争抢写入。
- 视频、06、07 与部署验收：本票不动。

## 七、交接

- 分支：`codex/issue221-runtime-env`（PR #228）
- 剩余工作：打包会话把第三节两段并入 04；负责人把第二节长版或短版粘贴进报名系统；系统上传见子票 C–G。
