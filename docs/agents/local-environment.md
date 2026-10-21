# 本机环境纪律

在 Windows 宿主 + WSL 实验室 + Android 模拟器上跑检查、恢复环境、或写跨 shell 命令前读这一页。它只记录**环境本身不会告诉你的东西**：哪些命令形态在这台机器上会静默失败、权威检查走哪个入口、以及出问题时的恢复路径。

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

约定：**把命令写进 `.sh` / `.ps1` 文件，再执行那个文件**。PowerShell 只负责调用，不承载引号。WSL 侧用 `/mnt/<drive>/...` 路径引用脚本。输出统一 `| tail -N` 过滤，别把整份日志灌进上下文。

## 2. 权威检查的入口

- 首选：**Git for Windows Bash** 里 `bash scripts/check.sh`（`"C:\Program Files\Git\bin\bash.exe"`）。
- `scripts/check.ps1` 只是把同一入口委托给 Git Bash，本身兼容 Windows PowerShell 5.1；只有命令名 `pwsh` 需要 PowerShell 7。本机没有 `pwsh` 时用 `powershell -NoProfile -File scripts/check.ps1`，或直接走 Git Bash。
- 检查跑在慢盘（如 D: 上的 worktree）可能让整套测试明显变慢；e2e 的等待预算已改成 `PRIVACYTRACE_E2E_JOB_BUDGET_SECONDS`（默认 60s），慢机直接调大，不要改测试。

## 3. 实验室与执行器

- 移动端本机验收执行器：`deploy/acceptance/mobile/`（README 里有用例契约、环境变量、已知假失败）。该目录随 PR #137 落地；合入前 main 上没有，别按路径去找。
- 部署专项入口：`deploy/check_acceptance.sh`（R1–R6）。
- 实验室业务态重置（保留 PKI/证书，用于清草稿配额）：`deploy/acceptance/mobile/lab-reset.sh`，参数见脚本头部（同样随 #137 落地）。
- 实验栈恢复后先跑健康探针：`https://localhost:<port>/api/v1/health` 必须 200，再看容器状态；只看 `docker ps` 会被“容器在跑但转发断了”骗到。

## 4. 常见假失败

- `uiautomator dump` 在部分镜像上写完文件就段错误退出；崩溃时会留下上一次的 XML，看起来像“对话框没出现”。dump 前删文件、只接受含 `<hierarchy>` 的新文件。
- 模拟器输入法会在字段刚出现时吞掉开头几次 `input text`；输入后回读确认。
- 设备序列号缺失时不要猜；执行器与矩阵脚本都会直接报错，避免连到错误设备。
