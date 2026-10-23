# 视频材料批次 20261023-v02

两支影片共用同一批 Android App 界面素材。冻结前端提交 `f81ca201b932a11e24a9f7175a9583150d44e9ed`，采集日期为 2026-10-23（Asia/Shanghai）。本轮文案与剪辑打磨沿用该批素材，没有重采集或扫描。

| 素材 | 实际尺寸 / 时长 |
| --- | --- |
| `android-import.png` | 780×1688，390 CSS px |
| `android-candidates.png` | 780×1688，390 CSS px |
| `android-report-full.png` | 780×4438，390 CSS px |
| `android-evidence-full.png` | 780×6258，390 CSS px |
| `recording-android.mp4` | 390×844，30 fps，16.833008 s |

素材来自生产 `MobileApp.vue` 加假原生桥的 Chromium 移动视口，不是 Android 真机。报告为 `fixtures/acceptance-jobs/gkd-s1-first.json` 持久化回放（原生成 2026-10-03）。

采集脚本为 `capture-android-flow.cjs`，详细原始来源与动作见两片 `capture-provenance.json`。本轮只复用已采集的文件；重新采集需要使用冻结版本的前端、临时 fixture store 与相应 API。没有把开发服务器的启动视作新采集证据。

成片复现见 `showcase/privacytrace-90s/README.md` 与 `showcase/privacytrace-review/delivery/README.md`。运行 `python showcase/finalize-films.py` 更新当前清单后，执行 `python showcase/validate_materials.py`。

第二轮仍复用原录制，渲染帧库重新派生为 30 fps / 505 帧；配乐源保留，新混音由 `showcase/mix-film-sound.py` 生成。没有产生新的前端采集批次。
