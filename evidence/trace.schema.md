# trace 日志格式（#23 PT-907）

用途：把一次样本分析的关键节点记录成逐行 JSON（JSONL），作为数据集原料和问题定位依据。采集只发生在分析作业侧，不改变系统报告结论。

## 字段

| 字段 | 必填 | 含义 | 允许值/格式 |
|---|---|---|---|
| `ts` | 是 | 事件时间（带时区） | ISO-8601，如 `2026-10-10T01:00:00Z` |
| `sample_id` | 是 | 样本编号，对应 `samples/real-world/manifest.csv` | 字母数字 `_.-` |
| `job_id` | 是 | 本次作业 ID | 非空字符串 |
| `stage` | 是 | 阶段 | 建议：`intake`/`manifest`/`dex`/`sdk`/`policy`/`consistency`/`report` |
| `event` | 是 | 事件类型 | 只能取：`start`/`evidence`/`conclusion`/`error`/`done`（校验强制） |
| `status` | 是 | 状态 | `ok` / `partial` / `failed` / `skipped` |
| `evidence_ref` | 条件必填 | 证据编号 | `event=evidence` 时必须给；其他事件不得出现；同一 `sample_id`+`job_id` 内不得重复 |
| `data_type` | 否 | 数据类型 | 非空字符串 |
| `location` | 否 | 代码位置或政策切片摘要（不含全文） | 非空字符串 |
| `duration_ms` | 否 | 该步耗时 | 非负整数 |
| `detail` | 否 | 补充说明 | 非空字符串 |

## 示例（合成，非真实数据）

```json
{"ts":"2026-10-10T01:00:00Z","sample_id":"example-1","job_id":"job-example-1","stage":"dex","event":"evidence","status":"ok","evidence_ref":"ev-1","data_type":"定位","location":"com.example.App:onCreate","duration_ms":120}
{"ts":"2026-10-10T01:00:01Z","sample_id":"example-1","job_id":"job-example-1","stage":"consistency","event":"conclusion","status":"partial","detail":"政策适用信息不全"}
```

## 规则

- 每行一个 JSON 对象，不跨行；空行忽略。
- 校验用 `scripts/validate-trace.py`；数据集归一化用 `scripts/build-dataset.py`，构建时直接按同一份校验契约读取 trace（单一来源），未通过校验的行不会进入数据集。
- **引用必须闭合**：每行的 `sample_id` 必须出现在样本清单里，`(sample_id, job_id)` 必须出现在 run 账本里；对不上直接构建失败，不静默丢弃。`evidence_ref` 只允许出现在 `event=evidence` 行，同一作业内不得重复。
- **行数收敛**：每条 trace 行都会被归一成 `evidence`、`conclusion`，或计入 `trace_events.lifecycle`（`start`/`error`/`done`）；数据集里 `trace_events.total` 必须等于这三类计数之和，对不上就构建失败——不存在"读了却没进数据集"的行。
- 数据集 `schema_version` 为 `0.2.0`：`evidence`/`conclusions` 每条带 `event` 字段，新增 `trace_events` 计数，且参与 `dataset_sha256` 计算。
- **不写入** APK 字节、完整政策原文、反编译全文或任何凭据；`location` 只写定位摘要。

## 采集边界（当前状态）

- 本文件与 `scripts/validate-trace.py`、`scripts/build-dataset.py` 只交付 trace 的**格式、校验与归并**能力。
- **采集 hook 尚未接入**分析作业（`apps/api/src/privacytrace/apk_worker.py`、`pipeline.py`）——这是产品代码主链路改动，列入 S2 及之后，不在本 PR 范围。
- 因此，在接入 hook 之前，真实样本的 trace 需由以下任一方式产生：
  1. 从分析作业的运行输出中手工/半自动导出关键节点为 JSONL；
  2. 后续把采集 hook 接进分析作业（另开任务，不阻塞主线）。
- 在此期间，`build-dataset.py` 的 trace 输入为空属**预期**，不算校验失败。
