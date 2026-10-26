# 技术依赖与来源

| 依赖 | 用途 | 官方来源 | 许可证 |
|---|---|---|---|
| Vue 3 | 报告交互 | https://github.com/vuejs/core | MIT |
| Vite | 前端开发和构建 | https://github.com/vitejs/vite | MIT |
| TypeScript / vue-tsc | 类型检查 | https://github.com/microsoft/TypeScript / https://github.com/vuejs/language-tools | Apache-2.0 / MIT |
| FastAPI | API | https://github.com/fastapi/fastapi | MIT |
| Pydantic | 类型与引用校验 | https://github.com/pydantic/pydantic | MIT |
| Uvicorn | 服务进程 | https://github.com/encode/uvicorn | BSD-3-Clause |
| pytest / HTTPX / Ruff | 验证 | https://github.com/pytest-dev/pytest / https://github.com/encode/httpx / https://github.com/astral-sh/ruff | MIT / BSD-3-Clause / MIT |
| Androguard 4.1.3 | 隔离 worker 的 Manifest / DEX 静态解析 | https://github.com/androguard/androguard/tree/v4.1.3 | Apache-2.0，见官方 LICENCE-2.0 |

精确版本和间接依赖以锁文件为准。发布前检查安装包实际许可证。本项目自行创作的源码与文档采 MIT（根 [LICENSE](../LICENSE)，决策见 [ADR 0006](adr/0006-source-license-mit.md)）；psycopg 为 LGPL-3.0 且只作未修改的 Python 依赖使用，Redis 7.4.8 服务端按 RSALv2/SSPLv1 双许可另按部署条件评估，两者都不改变本仓库自身的源码许可。

演示政策、代码片段和图标均为初始化编写，属于合成样本。SDK signatures 已有 v1.0.0 有限有据种子（`rules/sdk-signatures.v1.0.json`）；政策候选抽取是默认关闭的可选插件；LLM 服务商尚未锁定。Androguard 只解析静态证据，不证明运行时访问；JADX 未打包进生产 worker，缺失时保留字节码。原始 PRD 为用户提供材料，随仓库归档；用户于 2026-10-03 授权仓库公开，不宣称该 PRD 由本次开发生成。
