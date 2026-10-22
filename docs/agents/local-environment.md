# 本机环境纪律

在 Windows 宿主 + WSL 实验室 + Android 模拟器上跑检查、恢复环境、或写跨 shell 命令前读这一页。它只记录**环境本身不会告诉你的东西**：哪些命令形态在这台机器上会静默失败、权威检查走哪个入口、以及出问题时的恢复路径。

**环境会变，别信记忆。** 冻结 head、重建包、发布分支前先跑 `bash scripts/agent-env-probe.sh`：它报告 git/gh 连通性、docker daemon 与代理、FORWARD 策略、adb 设备、工具版本和已存在的包。一条过期的判断（“git 被墙”“容器没网”）比没有判断更贵。

## 1. 跨 shell 命令写成脚本文件

这台机器的默认 shell 是 Windows PowerShell。经过 PowerShell → `wsl` → `bash` → 容器这四层，任何内联命令都会在某一层被吃掉一段：

| 写法 | 实际结果 |
| --- | --- |
| `git commit -F - <<< "$msg"` | PowerShell 不支持 `<<<`，直接语法错误 |
| `bash -lc "for i in $(seq 1 40); do ..."` | `$(...)` 被 PowerShell 先展开成数字列表 |
| `node -e "...\`...\`..."` | 反引号是 PowerShell 的转义符，模板串被拆 |
| `bash -lc "python -c \"...\""` | 嵌套引号在 PowerShell 层就解析失败 |
| 内联 JSON 传给 node | 引号被剥掉，`JSON.parse` 报 position 1 |
| `docker exec psql -c "select ..."` | 引号不匹配，报 EOF |
| `gh api ... --jq '.a + " " + .b'` | jq 里的双引号被剥掉，gh 报 `accepts 1 arg(s), received N` |

约定：**把命令写进 `.sh` / `.ps1` / `.cjs` 文件，再执行那个文件**。PowerShell 只负责调用，不承载引号。WSL 侧用 `/mnt/<drive>/...` 路径引用脚本。输出统一 `| tail -N` 过滤，别把整份日志灌进上下文。

## 2. 检查入口

- **发布分支前的快速闸门**（约十秒）：`bash scripts/preflight.sh`。它用仓库自己的 ruff 配置扫 `deploy` 与 `tests/e2e`，并对分支改动过的文件做语法检查。它不替代权威检查，只防止 lint/语法错误进 PR、白烧一轮 CI。
- **合并前的权威检查**：Git for Windows Bash 里 `bash scripts/check.sh`（`"C:\Program Files\Git\bin\bash.exe"`）。
- `scripts/check.ps1` 只是把同一入口委托给 Git Bash，本身兼容 Windows PowerShell 5.1；只有命令名 `pwsh` 需要 PowerShell 7。本机没有 `pwsh` 时用 `powershell -NoProfile -File scripts/check.ps1`，或直接走 Git Bash。
- 检查跑在慢盘（如 D: 上的 worktree）可能让整套测试明显变慢；e2e 的等待预算已改成 `PRIVACYTRACE_E2E_JOB_BUDGET_SECONDS`（默认 60s），慢机直接调大，不要改测试。
- **开或刷新 PR 前先 rebase 到最新 `main`**：GitHub 取 **base 分支**的 workflow 文件、取 head 的代码。main 新增的 CI 步骤会在旧 head 上报 `Missing script`（#175 实际踩到），看起来像自己的改动坏了。

## 3. 实验室与执行器

- 移动端本机验收执行器：`deploy/acceptance/mobile/`（README 里有用例契约、环境变量、已知假失败）。该目录随 PR #137 落地；合入前 main 上没有，别按路径去找。
- 部署专项入口：`deploy/check_acceptance.sh`（R1–R6）。
- 实验室业务态重置（保留 PKI/证书，用于清草稿配额）：`deploy/acceptance/mobile/lab-reset.sh`，参数见脚本头部（同样随 #137 落地）。
- 实验栈恢复后先跑健康探针：`https://localhost:<port>/api/v1/health` 必须 200，再看容器状态；只看 `docker ps` 会被“容器在跑但转发断了”骗到。
- **镜像 tag 按 lane 隔离**：`privacytrace-{api,web,runner,scanner}:<lane>-<sha>`。并行 lane 共用 `:issue81-test` 会把别人的镜像变成 dangling；禁止 `docker image prune -a` / `docker system prune`——会删掉其他 lane 正在用的镜像，实验室随之 `No such image`。
- **每个 head 只冷启动一次**：R1–R6 约 12 分钟，冻结 head 后再跑，别对候选包反复跑。`scripts/agent-env-probe.sh` 会列出已存在的包与收据。

## 4. 常见假失败

- `uiautomator dump` 在部分镜像上写完文件就段错误退出；崩溃时会留下上一次的 XML，看起来像“对话框没出现”。dump 前删文件、只接受含 `<hierarchy>` 的新文件。
- 模拟器输入法会在字段刚出现时吞掉开头几次 `input text`；输入后回读确认。
- 设备序列号缺失时不要猜；执行器与矩阵脚本都会直接报错，避免连到错误设备。
- **docker build 被注入不可达代理**：daemon 的 proxy 配置会注入构建步骤，`uv sync` / `npm ci` 报 `tunnel error … tcp connect error … deadline has elapsed`。构建时显式清空：`docker build --build-arg HTTP_PROXY= --build-arg HTTPS_PROXY= --build-arg http_proxy= --build-arg https_proxy= …`。
- **容器没有 egress**：`iptables -P FORWARD DROP` 时容器能解析域名但连接超时；`iptables -P FORWARD ACCEPT` 恢复（本机曾遗留自早前的隔离实验）。
- **adb 设备消失**：adb daemon 重启或 MuMu VM 被停后 `adb devices` 为空，脚本会卡在等待而不是报错。先 `MuMuManager control -v <index> launch`，再 `adb connect`。
- **api 容器 unhealthy 但服务正常**：镜像内 `probe.py live` 打容器回环健康路径，可能返回 503；以 `https://localhost:<port>/api/v1/health` 200 为准。
- **共享 runner 偶发 provisioning 失败**：`laboratory provisioning failed: RuntimeError` 在 GitHub runner 上偶发，先重跑一次再调查。
- **WSL 里用不了 Windows 建的 worktree**：worktree 的 `.git` 文件写的是 Windows 路径（`gitdir: D:/...`），WSL 的 git 会报 `not a git repository: .../retro/D:/...`。在 Windows 建的 worktree 上跑 git 命令请用 Git Bash；WSL 只跑不需要 git 的部分。
