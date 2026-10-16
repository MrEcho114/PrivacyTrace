# 非技术人员理解测试 · 对照材料模板（#23 PT-907）

> 用途：让不熟悉隐私技术的参与者对比「普通权限清单 + 政策原篇」与本系统报告。
> 这是**模板**，不含真实 App 数据；每测一个 App 就按它填一份。
> **用词要求**：客观中立，不出现"偷数据 / 泄露 / 窃取 / 违法 / 违规"等词，不暗示本系统做合法性或安全性判定。

## 0. 被测 App（填写）

| 字段 | 值 |
|---|---|
| App 名称 | |
| 包名 / 版本 | |
| APK SHA-256 | |
| 政策来源 URL / 版本 | |
| 分析 job_id / 报告哈希 | |

## 1. 材料 A：普通权限清单 + 政策原篇（基线）

### A1. 权限清单
（从 Android 系统权限页或商店页摘录，逐条列出，不加解释）

### A2. 政策原篇
（逐句粘贴原文，注明出处与版本；不删改、不加总结）

### A3. 给参与者的说明
> 请阅读上面两份材料，然后回答第 3 节的题目。

## 2. 材料 B：本系统报告（PrivacyTrace）

### B1. 报告主体
（粘贴本系统生成的报告：结论、证据定位、政策原句高亮；保留"证据不足/未复核"等原始状态，不美化）

### B2. 给参与者的说明
> 请阅读这份报告，然后回答第 3 节的题目。

## 3. 题目（A、B 两组共用同一组题）

> 示例题，可按 App 替换；**同一 App 的 A/B 两组必须用完全相同的题目**。

1. 这个 App 会不会用到你的【定位】？请说出你的判断，并指出你在材料里看到的具体位置/原句。
2. 材料里有没有把【定位】说清楚？"说清楚"是什么意思，请用你自己的话讲。
3. （定位题）如果要求你找到"证据在哪里"，你花了多长时间？请记录在 `evidence_loc_seconds`。

## 4. 交叉顺序安排（防学习偏差）

- 一半参与者**先 A 后 B**，一半**先 B 后 A**；分配后把顺序写进记录表的 `condition` 字段（建议值：`baseline_first` / `report_first`）。
- **顺序和材料是两件事，必须分别记**：`condition` 只说明先后，说明不了这道题用的是哪份材料；每份记录还要在 `material` 字段写本题实际使用的材料（`baseline` = 材料 A，`privacyTrace` = 材料 B）。指标脚本按 `material` 出材料效果、按 `condition` 出顺序效果，并给出两者交叉表；缺 `material` 时只能看到顺序效果，无法说明报告相对基线的效果。
- 若用"等价案例"替代同人重复测：A、B 用不同但难度等价的 App/题目，避免同一人两次看到同一题。

## 5. 记录字段说明（对应 `evidence/user-study.template.csv`）

| 字段 | 含义 |
|---|---|
| participant_id | 匿名编号（不写真名） |
| condition | 阅读顺序：`baseline_first` 或 `report_first` |
| material | 本题实际使用的材料：`baseline`（材料 A）或 `privacyTrace`（材料 B） |
| question_id | 题号（A/B 组同号同题） |
| is_correct | 判断是否正确：`true` / `false`；**没判分就留空**（计为缺失，不进准确率分母，也不影响其他记录） |
| evidence_loc_seconds | 定位证据耗时（秒），没要求定位就留空；必须是有限非负数（不接受 `nan` / `inf`） |
| misconception | 观察到的概念误解；多个用 `;` 分隔；没有就留空 |
| start_time / end_time | 该题起止时间 |
| notes | 客观备注，不写主观定性 |

指标由 `scripts/metrics-user-study.py` 复算，禁止手填汇总数字。准确率同时按 `material`（材料效果）、`condition`（顺序效果）和两者交叉给出，并单列未判（`is_correct` 留空）的条数。

## 6. 配套材料（题目表 / 独立答案键 / 顺序安排表）

本节只新增交叉引用，不改变上文任何比较口径、题面与条件名。

- 题目表：`evidence/user-study-question-bank.template.csv`，表头 `question_id,dimension,equivalent_set,stem,notes`。`equivalent_set` 标明等价题组，同组题面不得出现答案泄露词。
- 独立答案键：`evidence/user-study-answer-key.template.csv`，表头 `sample_id,question_id,equivalent_set,scorable,expected_answer,evidence_location_baseline,evidence_location_report,scoring`。`expected_answer` 取值 A = 该样本会用到该类别，B = 不会用到；`scorable=false` 时留空 `expected_answer` 并在 `scoring` 写明不判分理由。判分只看答案键，不看记录表已填的 `is_correct`。
- 顺序安排表：`evidence/user-study-assignment.template.csv`，表头 `participant_id,condition,material_order,equivalent_set,notes`。`material_order` 写实际阅读顺序（`baseline_first` → `baseline;privacyTrace`，`report_first` → `privacyTrace;baseline`）；两种条件人数差不超过 1，每个等价题组内部同样平衡。
- 演练实例（**SYNTHETIC ONLY，不是真实证据**）：`evidence/synthetic/user-study-question-bank.csv`、`evidence/synthetic/user-study-answer-key.csv`、`evidence/synthetic/user-study-assignment.csv`，与 `evidence/synthetic/user-study.csv` 自洽，由 `python scripts/generate-synthetic-pt907.py` 生成。
## 6. 指标复核与原始记录关联

- 统计脚本保留 `sample_id`、`ground_truth_version`、`answer`，供依据独立答案键抽查 `is_correct`。聚合指标只包含完整性数量，不输出参与者回答原文。
- 不同 App 的相同题号可重复；同一 `(participant_id, sample_id, question_id, material)` 不得重复。同一轮实验的参与者只能分配一个 `condition`。
- 正式实验使用 `python scripts/metrics-user-study.py --input <私有记录路径> --require-provenance`；旧版最小 CSV 仅保留历史兼容能力。
