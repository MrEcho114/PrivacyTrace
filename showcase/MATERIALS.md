# 素材清单校验（validate_materials.py）

> v0.2 双片批次（Issue #264）。交付或上传前先跑一遍，确认 `materials.json` 和磁盘上的真实文件对得上。

## 用途

`materials.json` 把成片、截图/录屏素材、字幕源和 QA 报告绑成一份清单。脚本会从磁盘重新算一遍 bytes / SHA-256，核对 captureCommit 与批次日期，检查字幕里的日期/提交串，再用 ffprobe 和 QA 报告复核成片规格，防止过期或手改的清单混进交付。

## 用法

```bash
python showcase/validate_materials.py                 # 校验两片
python showcase/validate_materials.py --only 90s      # 只校验展示片
python showcase/validate_materials.py --only review   # 只校验评审片
python showcase/validate_materials.py --root PATH     # 指定仓库根（默认脚本所在目录的上一级）
```

- 仅用标准库；`ffprobe` 必须在 PATH 上（FFmpeg 自带）。缺失时按失败处理，不会静默跳过。
- `--only` 只跑一片的断言；若另一份 `materials.json` 可读，仍会做批次一致性对比（读不到时打印 note，不判失败）。

## 输入

| 片子 | 清单 | 路径基准（项目根） |
| --- | --- | --- |
| 90s | `showcase/privacytrace-90s/materials.json` | `showcase/privacytrace-90s/` |
| review | `showcase/privacytrace-review/delivery/materials.json` | `showcase/privacytrace-review/` |

> 清单里的 `path` 一般相对**片子的项目根**，不是相对 `materials.json` 所在目录。评审片的清单在 `delivery/` 里，但 `film.path` 仍写 `delivery/xxx.mp4`，字幕写 `delivery/film-review.html`。
>
> 当前批次生成器 `showcase/materials-20261023-v02/build-materials.cjs` 写的是**仓库根相对**路径（`showcase/privacytrace-90s/delivery/...`），并把 `qa` 嵌在 `film.qa` 下。脚本两种布局都接受：路径先按项目根解析，不存在再按仓库根解析（两者都存在时以项目根为准）；`qa` 先找顶层，没有再用 `film.qa`。

Schema：

```json
{
  "batch": "20261023-v02",
  "baselineCommit": "<40 位小写 hex>",
  "capturedAt": "2026-10-23",
  "film": {
    "path": "delivery/xxx.mp4",
    "bytes": 16559914,
    "sha256": "<64 位小写 hex>",
    "durationSeconds": 120.0,
    "fps": 30,
    "width": 1920,
    "height": 1080
  },
  "assets": [
    {
      "path": "assets/stills/android-import.png",
      "bytes": 131463,
      "sha256": "<64 位小写 hex>",
      "captureCommit": "<40 位小写 hex>",
      "capturedAt": "2026-10-23",
      "kind": "screenshot"
    }
  ],
  "captions": [
    {
      "path": "film-showcase.html",
      "required": ["2026-10-23 @ f81ca20"],
      "forbidden": ["07b37b2"]
    }
  ],
  "qa": { "path": "delivery/qa.json", "source": "showcase-qa" }
}
```

- `kind`：`screenshot` 或 `recording`；`qa.source`：`showcase-qa` 或 `review-manifest`。`qa` 也可以放在 `film.qa` 下（当前批次生成器的写法）。
- `fps` 允许数字或 `"30/1"`；commit 必须是 40 位、sha256 必须是 64 位**小写** hex，长度或大小写不对直接失败。
- `capturedAt` 只接受 `YYYY-MM-DD`。

## 断言

1. **素材**：`assets[]` 中每个文件存在，bytes 与 sha256 和文件一致；`captureCommit` 等于顶层 `baselineCommit`；`capturedAt` 等于顶层 `capturedAt`。
2. **字幕源**：每个文件存在；`required` 里的串必须逐字出现；`forbidden` 里的串一个都不能出现。
3. **成片**：文件存在且 bytes / sha256 匹配；ffprobe 的 duration 与 `durationSeconds` 相差 ≤ 0.2 s，width / height 相等，fps 相差 ≤ 0.01。
4. **QA 报告**：
   - `showcase-qa`：`probe.video` 的宽、高、帧率与成片一致，`probe.duration` 也在 ±0.2 s 内；黑场段数 ≤ 6；`loudness.integratedLufs`（兼容 `integrated_lufs`）落在 [-20, -12] LUFS；`frozenSegments` 必须是数组（静态停留是这类片的正常手法，只验存在）。
   - `review-manifest`：`file.sha256` / `file.bytes` 与 `film` 一致；`render.deterministic`、`render.exactPixels` 必须是 `true`；`missingAssets` 必须是空数组；`qa.ok` 必须是 `true`；黑场段数 ≤ 6；`qa.audio` 里 mean / peak 电平存在且为数字（兼容 `meanDb`/`peakDb` 与 `integratedLufs`/`truePeakDbfs`）。
5. **批次一致性**：两片的 `batch`、`baselineCommit`、`capturedAt` 必须完全相同，不一致会逐字段报 `batch mismatch`。

阈值 `±0.2 s`、`fps ≤ 0.01`、黑场 `≤ 6`、响度 `[-20, -12] LUFS` 是固定规则，写在脚本常量里；hash、日期、数量全部来自 JSON，脚本不预置任何一次采集的数据。

## 输出与退出码

| 退出码 | 含义 | 输出 |
| --- | --- | --- |
| `0` | 所有断言通过 | stdout 一行 `OK: ... (N film(s), N asset(s), ...)` |
| `1` | 至少一条失败 | stderr 每个失败一行（含 `materials.json` 路径、出错字段、实际值），末行 `FAILED: N failure(s)` |
| `2` | 参数错误 | argparse 用法提示（如未知 `--only`） |

```text
$ python showcase/validate_materials.py --root tmp/materials-validator-test/cases/mutated-hash
[90s] showcase/privacytrace-90s/materials.json: assets[0].sha256: sha256 mismatch: JSON 1f5f99…, file ff5f99… (showcase/privacytrace-90s/assets/stills/android-import.png)
FAILED: 1 failure(s)
$ echo $?
1
```

## 已知边界

- 只校验清单点名的文件，不扫描目录，也不校验 PPT / poster / README 等其他交付件。
- QA 数据取自清单引用的报告（不重跑 EAC）；ffprobe 只复核成片本身的容器/流元数据，不做艺术质量判断。
- 新增片子需要在脚本 `FILMS` 表里加一条（清单路径 + 项目根）。
