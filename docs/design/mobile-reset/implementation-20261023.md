# 移动端迁移实施记录（2026-10-23）

- 目标：把 [移动端 Claude 规范](frontend-design-spec-mobile.md) 从规范层落到 `apps/web` 移动入口，桌面工作台保持冻结。
- 结果：移动界面已切到 Claude 视觉基线；桌面无 `body.is-mobile-app` 时仍使用 Pioneer 旧值，桌面验收通过。
- 本轮没有 git add/commit/push。

## 1. 实现策略

- `apps/web/src/theme.css`：`:root` 追加 102 个 `--mt-*` 原始 token（附录 A 全量）；旧 Pioneer 变量与第一块 `:root` 原样保留。
- `body.is-mobile-app`：把共享组件与 round2 消费的 46 个旧变量重映射到 `--mt-*`（18 个颜色、5 个形状/字体、23 个 `--m-*` 几何/字号/动效）。这样共享组件零改动即生效，`DialogPortal` 挂到 body 的 sheet 也能继承。
- `apps/web/src/main.ts` 在 `isTauri()` 时、`MobileApp.vue` 在 onMounted/onBeforeUnmount 同步挂/摘 `body.is-mobile-app`；`html.mobile-shell` 同步画布/文字/字体，避免 edge-to-edge 露旧色。
- `apps/web/index.html` 的 `theme-color` 改为 `#f5f4ed`。

### 与规范 §11 的偏差（已由第二轮关闭）

第一轮为减少共享组件改动，采用 **`body.is-mobile-app` 直接重映射旧变量** 的过渡态；2026-10-23 第二轮已建立 `--ui-*` 语义别名、共享组件/共享 CSS 改为消费别名，并删除旧变量重映射，见 §6。

## 2. 改动的文件

| 文件 | 改动 |
| --- | --- |
| `apps/web/src/theme.css` | `--mt-*` token、`--ui-*` 别名层（第二轮）、reduced-motion、`html.mobile-shell`、`body.is-mobile-app` 别名映射 |
| `apps/web/src/main.ts` | Tauri 挂载前加 `is-mobile-app` |
| `apps/web/src/mobile/MobileApp.vue` | onMounted/onBeforeUnmount 增删 body class |
| `apps/web/index.html` | `theme-color` → `#f5f4ed` |
| `apps/web/src/mobile/mobile.css` | 移动壳与五屏视觉迁移（顶栏/步骤条/内容列/卡片/行/按钮/字段/状态标签/通知/阅读/sheet/设置/焦点/高对比） |
| `apps/web/src/components/UiSheet.vue` | detail 变体关闭键左置 |
| `scripts/fixtures/mobile-design.json` | 新增机器可读移动契约（roles/typography/geometry/states/components/coverage） |
| `scripts/lib/frontend-guards.cjs` | 新增并导出 `assertMobileDesign(page)`；原 `assertDesign/assertSurface/verifyGuardFailures` 不变 |
| `scripts/verify-mobile-flow.cjs` | 调用移动契约守卫；触控目标改量布局盒（忽略按压缩放） |
| `scripts/verify-frontend-round2.cjs` | 视觉期望迁到 Claude；保留全部行为断言 |
| `scripts/verify-mobile-reading.cjs` | 新增 17/1.75 + 阅读衬线断言 |
| `scripts/verify-issue146-motion.cjs` | 颜色反馈按作用域解析（移动 120ms / 桌面 150ms） |
| `scripts/verify-issue145-a11y.cjs` | 未改（computed token 现算，桌面作用域不需要变） |

## 3. 验收结果（2026-10-23）

| 入口 | 结果 | 证据 |
| --- | --- | --- |
| `npm run acceptance:mobile` | PASS，13 组检查；`mobile design` 15/15 契约组覆盖 | `tmp/issue72-native/` |
| `node scripts/verify-frontend-round2.cjs` | PASS；23 张截图 + walkthrough | `docs/acceptance/issue144/round2/` |
| `node scripts/verify-mobile-reading.cjs` | PASS，8 checks / 8 captures | `tmp/mobile-reading/` |
| `node scripts/verify-issue146-motion.cjs` | PASS，20 checks | `tmp/issue146-motion/` |
| `node scripts/verify-issue145-a11y.cjs` | PASS，14 checks | `tmp/issue145-a11y/` |
| `npm run acceptance:frontend`（桌面冻结套件） | PASS（import/quote/report 流程、17 mocked report 请求、15 mobile assertions、policy assist 10） | 需用 `PRIVACYTRACE_FRONTEND_URL` 指向可用预览 |
| `node scripts/verify-round2-primitives.cjs` | PASS，15/15 | 终端输出 |
| `powershell -NoProfile -File scripts/check.ps1` | PASS（API 1591 passed / 200 skipped；e2e 61 passed / 4 skipped；前端 126 tests；build） | 终端输出 |

完整 `check.ps1` 首次在最后 `npm ci` 阶段报 `EPERM: unlink node_modules/@esbuild/win32-x64/esbuild.exe`，原因是上一轮验收留下了两个 vite dev server 锁住 esbuild；停掉残留进程后重跑，全绿。这是本机进程残留，不是代码失败。旧 round2 截图已复制到 `docs/acceptance/issue144/round2-pioneer-20261022/`（25 个文件），新截图保留在 `docs/acceptance/issue144/round2/`，未覆盖历史证据的可用副本。

### 本机端口注意

本机 WinNAT/Hyper-V 排除了 TCP `5141–5240`，默认 5184 无法 bind（`EACCES`）。桌面验收用 `PRIVACYTRACE_WEB_PORT=6001` 起受管预览，再以 `PRIVACYTRACE_FRONTEND_URL=http://127.0.0.1:6001` 运行；`acceptance:motion`/`a11y` 同样应显式给 `PRIVACYTRACE_FRONTEND_URL`。这是环境限制，不是断言失败。

## 4. 已知偏差与未覆盖

- **sheet 退场 150ms 未实现**：组件卸载即消失，CSS 无法做退场动画；`--mt-duration-exit` 只用于 chevron。
- **报告封面深色章节未做**：移动报告模板没有封面色块，只有摘要卡深色标识；规范 §8.8 的封面章节保留为后续结构改动。
- **顶栏标题左缘 64px**：48 返回键 + gap + 16，保持四步标题不跳；不是 16 贴边。
- **行内 busy 按钮宽度仍可能变 0–6px**：把 `…` 换成 16px spinner；操作栏主按钮靠 flex 不跳。
- **按钮/列表行颜色与缩放无过渡**：为保证采样稳定，按下同帧生效；规范 §9.1 的“释放 120ms 回落”未实现，属于有意取舍。
- **骨架屏未做**：模板没有 skeleton 结构，暖砂目前只用于禁用底/分区带。
- **真机未验证**：Android WebView / IME / 刘海安全区 / TalkBack 仍为 NOT_RUN；Chromium 模拟不等于真机。
- 规范 §14 的真机、读屏、低亮度限制继续有效。

## 5. 后续建议

1. 补 sheet 退场、行内 busy 定宽、报告封面深色章节（需组件/模板改动）。
2. 在可用 Android 设备上跑一轮真机：系统栏、IME、返回手势、TalkBack、safe-area。
3. `pioneer-design.json` / `verify-round2-primitives.cjs` 按 [ADR-0004](../../adr/0004-frontend-contract-retirement.md) 保留到桌面入口正式下线；下一次前端轮次复审，最早 2026-11-06，不在本轮删除。

## 6. 第二轮（2026-10-23）：`--ui-*` 别名与契约退役决定

### 别名层

- `apps/web/src/theme.css`：`:root` 增加 48 个 `--ui-*`（46 个规范 §11.3 别名 + `--ui-canvas`、`--ui-danger-on` 两个实现补充；含 3 个触控档），`body.is-mobile-app` 全部映射到 `--mt-*`；窄屏/粗指针保留 `--ui-touch`/`--ui-button-height` 44px，字段保持 40px 以守住桌面冻结断言。
- `--ui-accent-on` 桌面取 `--surface`（#fdfcfa）而不是 `--on-action`，因为 `frontend-guards.cjs` 的桌面断言要求 `.ui-button.primary` 文字 = `roles.surface`；危险按钮文字另开 `--ui-danger-on`（桌面 #f9f9f9）。
- 共享组件与共享 CSS 改为消费别名：`UiSheet`、`UiField`、`App.vue` 报告分支、`MobileReportSummary`、`MobileMaterialContext`、`workbench.css`、`style.css`、`hierarchy.css`；`mobile.css` 的移动专属样式继续用 `--mt-*`（移动自有），两者在 body 作用域取同一组值。
- 删除 `body.is-mobile-app` 的旧 Pioneer/`--m-*` 重映射；旧变量只留在 `:root` 供桌面使用。共享组件里的旧变量 fallback 也已清掉（`UiSheet`/`UiField`/`App.vue` 只读 `--ui-*`）；`mobile.css` 的 `--mt-*, var(--m-*)` fallback 作为移动自有兜底保留，主值始终是 `--mt-*`。

### 退役决定

- 新增 [ADR-0004](../../adr/0004-frontend-contract-retirement.md)：两份桌面契约 **现在不退役**，保留到桌面 Web 入口被产品正式下线/移出受支持范围；触发条件、复审点（最早 2026-11-06）与一次性退役清单写在 ADR 里。
- 原因：`WorkflowApp` 仍是浏览器默认入口，桌面代码还在仓库；删掉 fixture/断言会让“视觉冻结”失去可执行证据。移动契约不依赖桌面 fixture。

### 验证

- `npm run build` 通过。
- `acceptance:mobile` 13 组 + 移动契约 15/15；新增 `--ui-*` 直读断言（surface/accent/fg/border-soft/canvas/radius/touch）。
- `verify-frontend-round2.cjs` 23 张截图 + walkthrough 通过；`verify-mobile-reading` 8 checks、`verify-issue146-motion` 20 checks、`verify-issue145-a11y` 14 checks 通过。
- 桌面 `acceptance:frontend` 通过（含 390/320 字段 40px 与 `.ui-button.primary` 颜色）；`verify-round2-primitives` 15/15；最终 `scripts/check.ps1` 通过（API 1591 passed / 200 skipped，e2e 61 / 4，前端 126 tests，build）。
- 首次桌面验收曾因 `--ui-field-height` 在 ≤560px 抬到 44px 失败；已改成保持 40px 后复跑通过。这是冻结契约与规范表“coarse 44”的冲突，以现有桌面断言为准并同步规范表。
