# Issue #146 验收记录 · 动效校准与减少动态效果

- 任务：[#146](https://github.com/MrEcho114/PrivacyTrace/issues/146)，父规格 [#141](https://github.com/MrEcho114/PrivacyTrace/issues/141)。
- 分支：`codex/issue146-motion`；实现基线 `origin/main` `0ad5f565dc6f414ac2b9c35661296dc9352e3fef`。
- 设计依据与本票决策：[`docs/design/issue146-motion.md`](../../design/issue146-motion.md)。
- 执行环境：Windows 11 + PowerShell 7，Node 24.17.0，Playwright 1.64（Chromium），本机受管预览 `npm run dev:start`（`PRIVACYTRACE_WEB_PORT=5196`）。
- 记录人：执行本次交付的代理；不要求用户补填审计表。

## 运行过的命令与结果

| 命令 | 结果 |
| --- | --- |
| `node scripts/verify-issue146-motion.cjs`（`PRIVACYTRACE_FRONTEND_URL=http://127.0.0.1:5196`） | PASS，20 项检查（含 3 条守卫反证），见 [`verification.json`](verification.json) |
| `pwsh -NoProfile -File scripts/check.ps1` | 见本次提交的 PR 正文；脚本内容未改动 |
| `npm run acceptance:frontend` | 见本次提交的 PR 正文 |

`verification.json` 记录本次运行的 `commit`、`dirty`、`apps/web/src` 全量源码 SHA-256、覆盖的模式与逐项检查文本。截图取自同一分支的同一实现状态；未修改源码后重跑即为失效证据。

## 定向检查覆盖

1. 指针能力：桌面命中 `(hover: hover) and (pointer: fine)`；触摸上下文不命中，且不再出现粘滞 hover。
2. 反馈节奏：hover 使用共用的 `--motion-color`（150ms）颜色过渡，属性仅 `background-color, border-color`；按下位移 `translateY(1px)` 与指针事件同帧、不参与过渡；按下态必须压过 hover（危险按钮按下为 `--rose` 底 + `--error` 字）。
3. 拖拽高亮：`dragenter`/`dragleave` 前后拖拽区高度与内部标签位置不变（0px 位移），高亮由 1px 实心边框 + 1px `inset box-shadow` 组成。
4. 弹窗：设置弹窗显式打开后同帧可读（`opacity: 1`，无入场动画）。
5. 预算守卫：页面内不存在 `transition: all`、不存在超过 300ms 的活动过渡、空闲时无运行中的动画；注入 `transition: all 400ms` 后守卫必须报错。
6. 普通模式：证据面板滚动 `behavior: 'smooth'`，面板内容在滚动完成前已可读。
7. 减少动效模式：滚动 `behavior: 'auto'`，全局过渡为 `0s`，无运行中动画。
8. 连续操作：每种模式 3 轮「开第一行 → 开第二行 → 收起」（共 9 次点击、3 次收起），最终落在关闭状态，无重复面板、无重复报告请求。
9. 低性能：CDP 6× CPU 节流下证据面板仍以完全不透明呈现，实测耗时见 [`verification.json`](verification.json)。
10. 后台恢复：`visibilitychange` 隐藏/可见往返后，面板仍在、内容不空、完全可读，动画未重启，报告请求数不变（DOM 级模拟，不是系统挂起）。
11. 长文本：展开报告来源里的 10 KB 政策正文，文档不产生横向溢出，`<pre>` 在自己的块内换行而不横向滚动。
12. 窄屏证据行：就地展开，无入场动画，首帧 `opacity: 1`；展开单元格与内部代码块都不横向裁切；收起后不残留空单元格。

## 证据文件

| 文件 | 说明 |
| --- | --- |
| [`evidence/before-import-drag-active-1440.png`](evidence/before-import-drag-active-1440.png) / [`evidence/after-import-drag-active-1440.png`](evidence/after-import-drag-active-1440.png) | 拖拽高亮前后：仍是一圈 2px 海军蓝描边；旧实现靠把边框从 1px 加宽到 2px 实现（因此会顶动内容），新实现用 1px 边框 + 1px 内阴影，所以**拖拽态内部内容比旧实现多出 1px**（实测差 16,221 px，全部落在拖拽区 304×502 区域内）。这是修掉回流本身的结果，不是新的视觉方向 |
| [`evidence/before-inline-evidence-390.png`](evidence/before-inline-evidence-390.png) / [`evidence/after-inline-evidence-390.png`](evidence/after-inline-evidence-390.png) | 窄屏证据行前后：**像素级一致**（差 0 px），差异只在入场阶段是否先 `opacity: 0` |
| [`evidence/before-reports-evidence-1440.png`](evidence/before-reports-evidence-1440.png) / [`evidence/after-reports-evidence-1440.png`](evidence/after-reports-evidence-1440.png) | 「已有报告」证据面板前后：**像素级一致**（差 0 px），未新增视觉方向 |
| [`evidence/feedback-hover-1440.png`](evidence/feedback-hover-1440.png) | 指针 hover 反馈（颜色过渡中/后） |
| [`evidence/feedback-pressed-1440.png`](evidence/feedback-pressed-1440.png) | 按下状态：位移已生效，未等待过渡 |
| [`evidence/reports-evidence-reduced-1440.png`](evidence/reports-evidence-reduced-1440.png) | 减少动效模式下的同一证据面板，呈现与普通模式一致 |

`before-*` 截图取自同一工作树改动前的实现（源码未修改）；`after-*`、`feedback-*`、`reduced` 取自改动后的同一实现状态，报告页截图都在滚动稳定后取帧。像素差由 Pillow 对同尺寸 PNG 逐像素比较得出。文件哈希见 [`evidence-manifest.sha256`](evidence-manifest.sha256)。

## 变更前后实测对照

| 观察项 | 改动前 | 改动后 |
| --- | --- | --- |
| 触摸上下文悬停按钮背景 | `rgba(0,0,0,0)` → `rgb(238,237,234)`（粘滞） | 保持 `rgba(0,0,0,0)` |
| `.drag-active` 拖拽区高度 / 标签 `top` | `244px → 246px` / `430px → 431px` | `244px → 244px` / `430px → 430px` |
| 窄屏证据行入场 | `animation: evidence-slide-in`，`opacity` 0→1，`translateY(-4px→0)` | 无动画，首帧 `opacity: 1` |
| 减少动效模式滚动参数 | `scrollIntoView({behavior: 'smooth'})` | `behavior: 'auto'` |
| 普通模式滚动参数 | `smooth` | `smooth`（不变） |
| 按钮颜色过渡来源 | 四个选择器各自硬编码 `150ms ease-out` | `button` 一条规则 + `--motion-color` / `--ease-color` |

## 未运行 / 不互代

以下项目本次**未运行**，不记为通过，也不被浏览器模拟替代：

- 真实触屏设备上的 hover 粘滞表现（本次用 Playwright `hasTouch` + `isMobile` 模拟指针能力）。
- 操作系统级「减少动态效果」开关在真实 Tauri Android WebView 中的表现（本次用 `emulateMedia({ reducedMotion })`）。
- 真实后台挂起/恢复（本次用 DOM `visibilitychange` 模拟，未做系统级冻结）。
- 真机低性能（本次用 CDP 6× CPU 节流）。
- 未制作视频；本票排除项明确不制作视频，`onetake` 仅作方向参考（PolyForm Noncommercial 1.0.0），未安装、未使用其运行时。
- 未合并、未部署、未发布；合并另行授权。
