# PrivacyTrace 汇报 PPT · 更新说明（v0.1 / 2026-10-23）

本目录是 2026 年第十四届数媒竞赛「作品汇报 PPT」的源文件与导出件。**前端仍在迁移，本稿内容会随合入更新**；更新时按下面的口径改，不要直接改导出件。

## 1. 文件清单

| 文件 | 用途 | 说明 |
| --- | --- | --- |
| `PrivacyTrace-汇报-20261023.html` | 可编辑源（本地打开） | 键盘 ← / → / Space 翻页，`#/7` 深链；图片在同目录 `assets/` |
| `PrivacyTrace-汇报-20261023.pptx` | 提交/演示用 | 18 页 16:9，整页图像 + 演讲者备注；文字修改请改 HTML 后重新导出 |
| `PrivacyTrace-汇报-20261023.pdf` | 备选提交格式 | 18 页，与 PPTX 同版 |
| `assets/shot-workbench.png` | 截图：报告页 | 取自 2026-10-22 候选包真实运行 |
| `assets/shot-evidence.png` | 截图：证据卡 | 「相机 · 证据不足」+ 政策原句 `[10, 24)` |
| `assets/shot-mobile.png` | 截图：Android 客户端 | 同一任务/报告的移动端视图 |

PPTX/PDF 是**整页渲染版本**，不可逐字编辑；HTML 是唯一源文件。

## 2. 每页数字的来源（改数先改这里）

| 页 | 内容 | 来源（仓库内） |
| --- | --- | --- |
| 7 | GKD 真实样本：`Lr2;->p` / offset 2 / `[363, 423)` / INSUFFICIENT_EVIDENCE | `docs/stages/s1-pr29-real-sample-verification-20261009.md`、`docs/stages/s1-report.md` |
| 9 | 12 场景 / 3 方案 / 36 行 / 真值冻结 / P-R-F1 N/A | `benchmarks/controlled-v2/README.md`、`docs/stages/pt903-20261012/` |
| 10 | 隔离参数、离线包 24 成员 / 3,056,905 B | `docs/stages/s1-report.md` §4、`docs/project-introduction-draft.md` §4.3 |
| 12 | 1640 passed / 179 skipped、Web 65 passed、Ruff/契约/构建 | CI Check 运行 `e52cc71`（2026-10-22）；`scripts/check.sh` |
| 13 | 状态一致 12/12、4/12、2/12；原六场景 2/6、3/6、6/6 | `README.md`「评测与理解测试的口径」、`docs/stages/pt903-20261012/report.md` |
| 14 | 理解测试 6 人：4.00 / 2.33、6/6、12/12、C05 4/4 | `docs/stages/pt907-user-study-20261019.md` |
| 14 | H01–H11 PASSED、H12 FAILED、#171 后未复验 | `docs/acceptance/h-matrix-final-20261022.md` |
| 14 | GKD 6 证据 / 3 行为 / 2 声明 / 3 判定；120.000s / 1080p / 30fps | `docs/project-introduction-draft.md` §4、Issue #200 |
| 17 | AI 工具清单与第三方许可 | `README.md`「人工智能工具使用与开源披露声明」、`docs/project-introduction-draft.md` §5–6 |

## 3. 前端合入后要动什么

前端合入新界面后，**至少**要处理：

1. 重新截 `assets/shot-workbench.png`、`assets/shot-evidence.png`、`assets/shot-mobile.png`；
2. 第 15、16 页正文里的「前端视觉基线仍在迁移」改为当前状态（界面已定稿 / 仍在迁移）；
3. 第 14 页「#171 改界面后，客户端面未复验」按新验收结果更新；H12 修好后改为 PASSED 并补证据；
4. 第 12 页 CI 数字换成最新 Check 运行，并更新 `e52cc71` 这个 SHA；
5. 封面与页脚的 `v0.1`、`2026-10-23` 同步改为新版本日期。

## 4. 重新生成 PPTX / PDF

源文件是 `tmp/deck/deck.src.html`（构建脚本在 worktree 的 `tmp/deck/`，不随包提交）：

```bash
# 1) 生成带相对图片路径的本地 HTML（docs/presentation/20261023/）
python tmp/deck/build_html.py
# 2) 渲染 18 页 2560×1440 截图并生成 PPTX
node tmp/deck/render.mjs
# 3) 由截图生成 PDF
python tmp/deck/make_pdf.py
```

依赖：Playwright（Edge channel）+ pptxgenjs + Pillow。生成脚本会打印每页内容边界；出现 `CHECK` 行说明该页溢出，先改 HTML 的间距/字号再导出。

## 5. 匿名化与限制

- 本稿不含校名、成员姓名、账号、学校域名、个人路径；截图中的 `localhost`、`org.privacytrace.fixture`、`policy.privacytrace.test` 为受控样例标识。
- PPTX/PDF 为整页图像，元数据作者已设为 `PrivacyTrace`；不写个人或学校信息。
- 字体依赖本机 `Noto Serif SC` / Georgia / Consolas；换机器重新导出前先确认字体，否则回退效果会变。
- EAC 预览使用的图片路径是 `/vendor/privacytrace-deck/`（本机 EAC 安装目录）；本地 HTML 使用 `./assets/`。重装 EAC 后预览图会缺，重新复制 `assets/*.png` 到该目录即可。
- 本稿不是匿名化终审：正式提交前仍需按 `#74` §5.2 的 8 项门禁逐页复核。
