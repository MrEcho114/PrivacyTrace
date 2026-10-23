# PT-906 上传套件与终稿 v5 记录（2026-10-23）

> **2026-10-23 18:05 更新：v6 已重建（换成新版移动端 + 后端 CLI 共 9 张截图，ZIP 重冻结），v5 不再作为上传基准。见 [v6 重建记录](v6-rebuild-20261023.md)。本文件保留为 v5 历史状态。**

> 任务来源：[#74](https://github.com/MrEcho114/PrivacyTrace/issues/74) 赛事材料整理与核对；交付槽位 [#198](https://github.com/MrEcho114/PrivacyTrace/issues/198)（ZIP）、[#199](https://github.com/MrEcho114/PrivacyTrace/issues/199)（截图）、[#200](https://github.com/MrEcho114/PrivacyTrace/issues/200)（评审视频 / PPT）、[#202](https://github.com/MrEcho114/PrivacyTrace/issues/202)（提交审核与回执）。
>
> **本记录不改变任何提交状态。** 系统上传与「提交审核」均未发生，截止仍为 2026-10-23 23:59:59。

## 1. 结论

- 上传材料已整理为单一套件，13 个文件逐件复算 SHA-256 与冻结源文件 0 差异（`copies.json`）。
- 终稿基线在 v3 基础上修正了**真实缺陷**：`01_作品及成果文件/demo-web/DISTRIBUTION.txt` 原文声明「INTERNAL VERIFICATION ONLY / 不授予竞赛提交授权」，与参赛用途冲突；v4/v5 仅改文本并重生成包清单，功能、评测数据、媒体未变。
- **v5 是唯一上传基准**；v0–v4 全部作废，不得上传。
- 仍缺的只有真人动作：系统上传（ZIP / 10 张截图 / 评审视频 / PPT）与「提交审核 + 回执」。

## 2. v5 终稿基准

| 项 | 值 |
| --- | --- |
| 根目录 | `PrivacyTrace_322234/` |
| ZIP | `PrivacyTrace_322234.zip`，41,917,846 B |
| ZIP SHA-256 | `559f14f147449aa6eb0293f5489bede1fd0e98d634fc4b3e3fb530c6b45c59e5` |
| 包内容 | 632 文件 / 97 目录；清单 631 条（`00_材料清单.md` 自身不计） |
| 解压字节 | 46,352,382 B（不含清单）；46,448,940 B（含清单） |
| 结构 | 01–08 八类目录齐备；`08_学籍等专项材料/` 为空目录（国内赛道非缺件） |
| 加密 / CRC | 无加密条目；`testzip()` 通过 |
| 离线回放 | `demo-web/viewer.py` 启动前文件集与逐文件 SHA-256 校验通过（反转 1 字节即抛 `Offline package hash mismatch`） |

## 3. v3 → v5 变更（全部为文本，无功能/数据/媒体变更）

**v4：授权声明**

| 文件 | 变更 |
| --- | --- |
| `01_作品及成果文件/demo-web/DISTRIBUTION.txt` | 删除「INTERNAL VERIFICATION ONLY / grants no … competition-submission authorization」，改为参赛包与专家评审用途的声明 |
| `01_作品及成果文件/demo-web/README.txt` | 第 5 行改为「Competition entry package (2026); for expert review and local reproduction.」 |
| `01_作品及成果文件/demo-web/manifest.json` | 重算上述两文件 SHA-256（viewer 校验依赖） |
| `01_作品及成果文件/source/scripts/export-offline.py` | 生成器同步输出新声明 |
| `00_材料清单.md` | 重新生成 631 条逐文件哈希 |

**v5：状态与许可口径对齐**

| 文件 | 变更 |
| --- | --- |
| `01_作品及成果文件/source/README.md` | L5/L111 改为「已完成开发与内部验收（R01–R04 全部 PASSED；pytest 1578 passed / 179 skipped；四入口 4/4）」；L11 删除内部 Issue `#128` 引用；L156 改为「源码随参赛包提供供评审复现，未另行声明开源许可证」 |
| `01_作品及成果文件/demo-web/DISTRIBUTION.txt` | 删除 v4 新增的、指向 06 目录的悬空许可指针 |
| `01_作品及成果文件/demo-web/manifest.json` 等 | 同步哈希与文本 |
| `00_材料清单.md` | 重新生成 |

v3 ZIP `804a8e93…b5aa` 与 v4 ZIP `6934841f…7a67d` 保留在本机作为历史证据，**不再作为上传件**。

> 已知非阻塞残留（v5 接受）：`source/scripts/export-offline.py` 的生成器模板仍保留一行已从交付 `DISTRIBUTION.txt` 删除的悬空许可指针。它只影响未来重建时会把该行带回交付面；整脚本重跑会同步重算 `demo-web/manifest.json`，不会造成 viewer 校验失败。评审可见面不含该行。

## 4. 上传套件（`.scratch/upload-kit/`）

| 顺序 | 系统栏目 | 文件 | 大小 | SHA-256 |
| :---: | :--- | :--- | ---: | :--- |
| 1 | 参赛打包文件 | `01_打包文件/PrivacyTrace_322234.zip` | 41,917,846 B | `559f14f1…c59e5` |
| 2 | 作品截图 ≤10 | `02_作品截图/01_…10_…png` | 5,677,918 B 合计 | 逐张见套件 `上传清单.md` |
| 3 | 作品评审视频 | `03_评审视频/PrivacyTrace-Review-1080p.mp4` | 16,559,914 B | `51d512af…0cee602cc5` |
| 4 | 作品汇报 PPT | `04_汇报PPT/PrivacyTrace-Review.pptx` | 297,911 B | `72f05277…4b504de4f` |

- 10 张截图清单与逐张哈希见套件内 `上传清单.md`；另外 4 张失败态截图留在包内，不进入独立上传栏。
- 承诺书不在套件内（含个人信息，已由负责人单独上传；系统状态待 #202 核验）。
- 套件为复制件，源文件未改；`copies.json` 记录 13/13 `match=true`。

## 5. 核验证据

| 证据 | 位置 | 结论 |
| --- | --- | --- |
| v5 独立核验（最终） | `docs/acceptance/issue202/verify-v5-20261023.md` | 可作最终上传件；交付面 0 硬性不符 |
| v4 独立核验（历史） | `docs/acceptance/issue202/verify-v4-20261023.md` | 机械通过；发现状态口径残留，已被 v5 取代 |
| v3 独立核验（历史） | `docs/acceptance/issue202/verify-v3-20261023.md` | 可上传；授权声明缺陷已被 v4/v5 取代 |
| 套件复制件 | `.scratch/upload-kit/copies.json` | 13/13 哈希一致 |
| v5 构建报告 | `.scratch/package-v5/v5-report.json` | ZIP / 清单 / viewer / 禁用短语校验通过 |

## 6. 上传顺序（人执行）

1. 系统在线填报复核：赛道、赛项、团队、作品名称、**AI 使用 = 是**。
2. 承诺书（已上传；如需重传用系统生成签章版）。
3. 10 张截图（仅套件内 10 张）。
4. 评审视频（优先）与汇报 PPT（可同时上传）。
5. 打包 ZIP（**不设解压密码**；至少留 2 小时余量）。
6. 全部上传后点击 **【提交审核】**，记录系统状态、编号、时间、回执与可重新下载件哈希（#202）。

## 7. 边界

- 上传 ≠ 提交；本记录不构成「已上传 / 已提交 / 已参赛」声明。
- 官方文件（2026-10-15《参赛作品材料提交规范》、评分标准、参赛指南、AI 模板）的逐条对照见 `docs/acceptance/issue202/official-spec-audit-20261023.md`。
- 本记录由主代理整理；子代理仅承担只读核验。
