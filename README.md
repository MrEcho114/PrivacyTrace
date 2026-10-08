# PrivacyTrace

PrivacyTrace 是一个面向普通 Android 用户的应用隐私对照工具。它读取 APK 里的隐私相关静态线索，并与隐私政策文本进行对照，让用户可以查看这些线索在代码与政策原文中的具体位置。工具目前只对照敏感数据类型是否提及，不证明应用实际上收集或传输了数据。

## 现在能用到什么

- **查看演示报告**：不用准备 APK，也不用启动 Docker，启动服务后即可在浏览器中查看样例应用的代码线索和政策原文位置。演示报告仅用于体验界面与流程，不代表真实应用分析结果，也不支持保存复核备注。
- **分析真实 APK**：通过宿主命令行触发 Docker 容器，扫描未知 APK 中的敏感权限与调用，结合人工整理的政策文本生成对照作业。生成的真实作业可以在前端查看，并支持填写与保存人工复核备注。

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

## 真实 APK 隔离扫描与政策摄取

对真实未知 APK 的分析必须在 Docker 隔离环境中运行，禁止在宿主机直接解析未知 APK；以下宿主 CLI 负责调用隔离容器。

### 1. 构建隔离 Worker 镜像

- **Linux**：`docker build -f apps/api/worker.Dockerfile -t privacytrace-worker:s1 .`
- **Windows WSL2 (PowerShell)**：
  ```powershell
  $root = (wsl.exe -d Ubuntu-24.04 --exec wslpath -u $PWD.Path).Trim()
  wsl.exe -d Ubuntu-24.04 --exec docker build --file "$root/apps/api/worker.Dockerfile" --tag privacytrace-worker:s1 $root
  ```

### 2. 政策摄取与扫描作业

政策摄取需提供已准备好的纯文本 raw 与 candidates 候选文件。摄取将在指定的新目录生成不可变快照，不覆盖旧快照；若原文中出现重复原句，需分别给出各自精确的 start/end offsets。

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
- **分析边界**：
  - 清单中的权限声明仅代表应用申请了对应能力，不代表实际发生调用；代码中存在调用线索，也不作合法性、安全性或实际数据收集判定。
  - 对加壳应用、Native 库（so）、反射、动态加载、Flutter 及混合开发（hybrid）应用覆盖不保证。
  - 生产分析容器内不含 JADX 反编译引擎，使用字节码兜底（`UNAVAILABLE_BYTECODE_FALLBACK`）。
  - 无大模型自动生成政策，无动态沙箱抓包与用户行为实验。
- **存储与安全边界**：
  - 本地作业存储于 `data/jobs` JSON 文件，SQLite 模式暂未接入运行时。
  - 在已提交的 S1 版本中，分析产生的 `tmp/` 目录运行副本长期保留供复核，没有自动清理机制，也没有累计磁盘配额。
  - 后端接口仅绑定本机回环地址（127.0.0.1），无身份认证与数字签名，禁止公网部署。

## 验证与测试

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

## 项目状态与相关文档

- 阶段状态：技术链路已跑通，当前处于 `PENDING_HUMAN_AB` 状态，仍未完成团队 A+B 双人验收。复核改用 [Issue #15 的双人 comment](https://github.com/MrEcho114/PrivacyTrace/issues/15)，格式见 [复核 comment 模板](evidence/review.comment.template.md)，不再要求签字。代码或自动化测试通过不替代人工验收。
- 技术报告：详细交付与边界说明见 [`docs/stages/s1-report.md`](docs/stages/s1-report.md)。
- 竞赛材料：赛务对照见 [`docs/competition-checklist.md`](docs/competition-checklist.md)。
- 依赖许可：依赖库 Androguard 遵循 [Apache-2.0 许可证](https://raw.githubusercontent.com/androguard/androguard/v4.1.3/LICENCE-2.0)。本项目源代码许可待团队最终确定。
