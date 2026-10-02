# 建仓验证记录

日期：2026-10-02（香港时间）。验证对象：本次初始化代码与合成 fixture。当前真实 APK 第一里程碑尚未完成。

## 已执行

| 检查 | 结果 |
|---|---|
| 安装脚本 `scripts/setup.ps1` | npm ci、uv locked sync 成功 |
| 后端 pytest | 35 passed |
| Ruff 静态检查 | All checks passed |
| 前端 TypeScript / vue-tsc | 通过，包含在 build 中 |
| Vite production build | 成功，12 modules transformed |
| 服务健康检查 | `/api/v1/health` 返回 ok / scaffold |
| 演示报告 API | demo=true；7 条结果，10 条证据 |
| 真实浏览器联调 | 3 类数据、2 个来源、7 条结果正常显示 |
| 证据下钻 | 点击精确位置结果，能看到 API 代码、权限配置、政策原句与完整快照 |
| 浏览器错误日志 | 检查时未发现前端 error |
| Git 忽略项 | .env、APK、私人材料、依赖和虚拟环境均被忽略 |

页面截图：`screenshots/demo-report.png`，仅展示人工构造的演示数据。

测试覆盖：六种状态、精确/上位/下位匹配方向、不同宿主渠道冲突、同渠道与不完整快照不误触发冲突、SDK 政策不替宿主补声明、权限/SDK 单独存在时证据不足、证据引用、快照 hash 与原句校验、规则版本、事实/声明边界、SQL 外键、生成契约一致性和 API 状态码。

## 限制与环境问题

- FastAPI/Starlette TestClient 在已安装版本中给出 HTTPX 迁移弃用提示；35 项测试仍全部通过。后续依赖升级时处理该提示，不隐藏警告。
- Windows 下运行开发服务时，esbuild.exe 会被占用，重跑 npm ci 可能无法删除文件。已停止前端服务，重新运行 setup 成功。安装依赖应先于启动服务。
- 中断后残留的 npm install 曾与后续安装重叠，已停止该任务并用单次 npm ci 恢复；随后成功构建。
- 未执行真实 APK 扫描、真实政策抽取、LLM 调用、真实 App 精度评测、用户实验或线上部署。
- CI 配置已建立，本次本机结果不等于 GitHub Actions 已运行。

## GitHub 状态

用户已创建并授权私有仓库 [MrEcho114/-](https://github.com/MrEcho114/-)。GitHub 连接已验证 visibility=private 与 push=true，本地 origin 指向该仓库。代码通过已授权连接同步，保留远程初始提交；后续终端 push 仍需本机 Git 登录和网络连通。GitHub Actions 的运行结果应以远程实际记录为准。
