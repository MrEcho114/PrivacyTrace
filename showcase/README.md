# 竞赛视频材料

本目录存放两支参赛片及其可复渲源文件。只有 `showcase/privacytrace-90s/` 与 `showcase/privacytrace-review/` 是交付材料；`showcase/privacytrace/` 是更早的产品演示片，保留作为历史材料。

| 目录 | 内容 | 入口 |
| --- | --- | --- |
| [`privacytrace-90s/`](privacytrace-90s/README.md) | 90 秒作品展示片 v0.2（真实界面录制 + 静态图版） | `README.md`、`delivery/qa.json` |
| [`privacytrace-review/`](privacytrace-review/README.md) | 120 秒作品评审片 v0.2 + 唯一汇报 PPT（PPT 由 #265 维护） | `delivery/README.md`、`delivery/manifest.json` |
| [`materials-20261023-v02/`](materials-20261023-v02/README.md) | v0.2 采集批次：批次号、可复跑脚本、素材清单生成器 | `README.md` |
| [`validate_materials.py`](validate_materials.py) | 材料级校验（手动入口）：哈希、采集提交、图注 token、QA 范围 | [`MATERIALS.md`](MATERIALS.md) |

## v0.2 口径（Issue #264）

- 冻结基线：`origin/main` @ `f81ca201b932a11e24a9f7175a9583150d44e9ed`；采集日 2026-10-23；批次 `20261023-v02`。
- 两支片子共用同一采集批次：同一提交、同一天、同一批界面素材。
- 片内图注统一为「日期 @ 短提交」；旧基线 `07b37b2` 与旧移动素材日期不再出现。
- 报告长图来自 `fixtures/acceptance-jobs/gkd-s1-first.json` 的持久化回放（原生成 2026-10-03），不是本批次新扫描。
- Android App 画面为 Chromium 390×844 移动视口模拟（生产移动壳 + 假原生桥），不是 Android 真机；片内与文档都标明这一点。

## 验证

```bash
python showcase/validate_materials.py
```

该脚本只断言外部可观察产物（文件哈希、清单、图注 token、成片规格与 QA 范围），不校验艺术质量；视觉复核见各片 README 的抽帧记录。
