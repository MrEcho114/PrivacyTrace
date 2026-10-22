# 前端交付（移动端 App）

前端页面、样式或组件任务按此流程执行。任务授权与完成标准仍由根部 AGENTS.md 和 `core/workflow.md` 管理。

**范围已收窄**：只做移动端 App —— `apps/mobile/`（Android/Tauri 壳）、`apps/web/src/mobile/`（移动界面），以及移动报告复用的共享呈现（`App.vue` 的 `mobile` 分支、`components/`、`theme.css` 的 `--ui-*` 语义别名）。桌面专用布局与视觉（`WorkflowApp.vue` 的桌面分支、`workbench.css` 的桌面断点）冻结，不再作为设计目标；改共享文件时只做移动映射（`body.is-mobile-app` / `--ui-*`）作用域内的改动，并保持桌面既有断言通过。`apps/api` 后端由隔壁会话负责。设计来源是 [移动端规范](../design/frontend-design-spec-mobile.md)（Claude 基线，2026-10-23）；round2 的 Android 壳合同（[frontend-round2-android-pioneer.md](../design/frontend-round2-android-pioneer.md)）继续有效，替换其视觉层并补少量移动交互规则。Apple 草案已归档，不再实施。

## 先读规范与代表页面

1. 先读 [移动端规范](../design/frontend-design-spec-mobile.md)：颜色、字体、字号、间距、圆角、组件几何、状态与无障碍下限。规范里的"来源值 / 计算值 / 建议值"不要混用。
2. 先实现导入与候选两张代表页面，在 390×844 与 320×568 下出视口图与完整图。独立视觉审阅代理读取规范与实际截图，检查阅读顺序、密度、重复信息、遮挡、触控辨识度与状态文字。修正这些问题后再扩展进度、报告、设置。普通文案小改动无需强制跑整套视觉流程。
3. 实施结束分别进行需求、代码标准与视觉审阅。截图和交互测试证明不同事项；代理视觉检查不等于用户认可审美。

## 预览与验证

`npm run dev:start`、`dev:status`、`dev:stop` 管理此工作树的前端预览，默认端口 5184；可通过 `PRIVACYTRACE_WEB_PORT` 选择端口。若端口落在 Windows WinNAT/Hyper-V 排除段，脚本会以 `EACCES` 和可用端口建议失败，不再误报为 occupied。日志位于忽略的 `tmp/frontend-preview/preview.log`，进程身份记录同目录。普通浏览器打开的是 Web 工作台；移动界面由 Tauri 入口加载，浏览器调试请使用下面的验收 harness，而不是伪造一个移动入口。

需要保留预览时运行 `npm run check`：暂停受管预览，委托同一个权威 `scripts/check.ps1` 或 `scripts/check.sh`，成功或失败后恢复原端口与接口地址。Windows 下自动探测 `pwsh`，缺失时回退系统自带的 `powershell`，不要求 PowerShell 7。直接权威入口仍可使用；手动启动的预览不受工具管理，需由启动者先停止，以免 Windows 的 esbuild 文件锁影响 `npm ci`。

移动端验收（生产 Vue + 受控 native bridge 替身，Playwright）：
- `npm run acceptance:mobile`：四步流程、320/390/768 长文本、200% 根字号、触控与软键盘、返回/焦点/滚动恢复、单次启动断言。
- `npm run acceptance:reading`：报告阅读态与长政策正文。
- `npm run acceptance:motion`：动效 token 与 `prefers-reduced-motion`。
- `npm run acceptance:frontend` 仍覆盖 Web 工作台与 Pioneer 契约，桌面冻结期间保留，不拿它替代移动验收。
- 验收脚本尊重 `PRIVACYTRACE_WEB_PORT`（各脚本默认端口不同）；已有受管预览时用 `PRIVACYTRACE_FRONTEND_URL` 复用，避免 Windows 排除端口段直接 `EACCES`。

移动契约是 `scripts/fixtures/mobile-design.json`（已落地，由 `assertMobileDesign` 消费）；共享组件/共享 CSS 消费 `--ui-*`，移动专属样式消费 `--mt-*`。`scripts/fixtures/pioneer-design.json` 与 `scripts/lib/frontend-guards.cjs` 的桌面断言继续冻结服务桌面，不得为了过测删掉；退役触发条件与 2026-11-06 复审点见 [ADR-0004](../adr/0004-frontend-contract-retirement.md)。`npm run acceptance:preview` 验证进程生命周期与检查恢复，运行前停止已有受管预览。

## 文案与外部 skill

需要模型文案时，先准备 [事实简报模板](frontend-copy-brief.md)，从代码和接口核实能力、失败、取消、恢复、持久化与示例行为。简报使用功能事实和文案键名，记录用户已授权的目的地、发送内容及同范围纠错边界；需要扩大范围时按实际授权处理。采用最新生成结果，事实错误反馈模型修订，保留生成与修订记录。

参考外部 skill 时先固定来源版本，再确认本地拥有的是文档还是完整安装。仅下载文档时采用其文档备用流程；执行启动器前检查目标文件存在。安装、二进制、hook 与全局配置变更按当前用户授权判断，不为读取指南自动安装运行环境。

## 最后更新 PR

完成相关验证、完整 diff 与独立审阅，填写已有 PR 模板，准备最终正文。已有 PR 先更新正文，再推送交付提交，避免同一交付 SHA 因再次编辑正文取消并重启 CI。新 PR 先推分支，再用已准备的正文创建。远端结果绑定最终 SHA；等待 CI 后汇报，避免为更新"待通过"为"通过"再次编辑正文。保留治理 CI 对正文编辑的校验。
