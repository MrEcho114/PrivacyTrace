# 最小记录字段与保留／删除约定 · 模板（#23 PT-907）

> 用途：规定理解测试记录**最小记什么、怎么取值、放哪里、留多久、何时删**。
> 这是**模板**，不含真实参与者数据；演练记录一律标注 **SYNTHETIC ONLY / 演练**，不得冒充真实用户研究。
> 用词要求：客观中立，不出现"偷数据 / 窃取 / 泄露 / 违法 / 违规"等定性词。

配套文件：主持流程见 `evidence/user-study-facilitator-script.template.md`；材料与题集见 `evidence/user-study-comparison.template.md`；同意与退出口径见 `evidence/user-study-consent.template.md`；走查见 `evidence/user-study-rehearsal-checklist.template.md`。

## 1. 记录单位与文件

- 一行 = 一次作答（一个 `participant_id` + 一个 `question_id` + 一个 `material`）。
- 列顺序必须与 `evidence/user-study.template.csv` 表头逐字一致。
- **真实记录**与**演练记录**必须是两个不同的文件，演练文件不得混入真实记录文件；演练记录文件名或 `notes` 必须含 `SYNTHETIC`。

## 2. 最小记录字段集（逐列）

| 列名 | 含义 | 取值 | 必填 |
|---|---|---|---|
| `participant_id` | 匿名编号，不写真名 | 形如 `p-01`；同一参与者全表同值；不得含姓名/手机号/账号 | 是 |
| `background` | 参与者背景类别 | `ordinary-user`（非技术背景）/ `technical`（技术背景）/ `prefer_not_to_say` | 是 |
| `condition` | 阅读顺序 | `baseline_first` 或 `report_first` | 是 |
| `material` | 本题实际使用的材料 | `baseline`（材料 A）/ `privacyTrace`（材料 B） | 是 |
| `sample_id` | 本题对应的样本 | 真实样本 id 或演练样本 id（如 `syn-cam-v1`） | 是 |
| `ground_truth_version` | 真值版本 | 真值文件版本串（如 `0.1.0`）；未核真值就留空并在 `notes` 说明 | 是（无真值可空） |
| `question_id` | 题号 | `q01`…；A/B 组同号同题 | 是 |
| `answer` | 参与者作答原文 | 原话摘录，可加引号；不改写、不概括、不代为判断 | 是 |
| `is_correct` | 判断是否正确 | `true` / `false` / **空**；空 = 未判分 | 否（主观题必空） |
| `evidence_loc_seconds` | 定位证据耗时（秒） | 有限非负数，或留空（未测量） | 否 |
| `misconception` | 观察到的概念误解 | 简短描述；多个用 `;` 分隔；没有就留空 | 否 |
| `start_time` | 该题开始时间 | ISO 8601 含时区（如 `2026-10-13T03:00:00+00:00`） | 是 |
| `end_time` | 该题结束时间 | ISO 8601 含时区；不早于 `start_time` | 是 |
| `subjective_understanding` | 主观题作答原文（"说清楚"指什么） | 原话摘录；客观题留空 | 主观题必填 |
| `evidence_located` | 是否指出材料中的具体位置 | `true` / `false` / 空（没要求定位） | 否 |
| `git_commit` | 本场所用材料对应的提交 | 完整或短 SHA；同场同值 | 是 |
| `notes` | 客观备注 | 只写可核查的事实（如"该题用时明显偏长""未完成"）；演练记录写 `SYNTHETIC ONLY`；不写主观定性 | 否 |

指标脚本 `scripts/metrics-user-study.py` 的必需列是 `participant_id`、`condition`、`material`、`question_id`、`is_correct`；缺列会直接报错，因此本表 17 列必须整份保留，不得为了省事删列。

## 3. 空白与无效值口径

- **空白 `is_correct` = 未判分**，计为缺失，既不计入准确率分子也不计入分母，**不得当作错误**；汇总时单列未判条数。
- `is_correct` 只接受 `true` / `false` / 空；写别的词（如 `yes`、`对`）会让脚本报错，必须改成合法值或留空。
- **非有限耗时不得计入任何分母**：`evidence_loc_seconds` 只接受有限非负数；显式写 `nan` / `inf` / 负数会被 `scripts/metrics-user-study.py` 拒绝（`evidence_loc_seconds must be finite`）。未测量的题**留空**，不要写 `0`、`nan` 或占位符。
- 空白 `evidence_located` = 本题没要求定位，不等同于"没找到"。
- 证据引用缺失时记 `UNKNOWN`，不允许猜：材料里找不到能支撑判断的原句时，`answer` 写参与者原话、`misconception` 或 `notes` 记 `UNKNOWN`（未知就是未知，不推断、不补全）。
- 任何字段拿不准就留空并写进 `notes`，不要用默认值填空。

## 4. 存放位置与 Git 现状

- 真实记录、同意书、含参与者身份信息的任何副本只放**被 Git 忽略的私有目录**：`evidence/private/user-study/<study-id>/`（`<study-id>` 自定，如 `pt907-2026-10`）。
- 演练记录同样只放私有目录，文件名或 `notes` 标注 `SYNTHETIC`。
- **不提交仓库**：`evidence/` 公开目录下只允许模板（`*.template.md`、`*.template.csv`）与标注 SYNTHETIC ONLY 的生成物。
- 参与者身份与本机私有路径（绝对磁盘路径、用户名目录、内网地址）不得写进任何提交进仓库的文件，也不得写进记录表的任何字段。

`.gitignore` 现状（本次核实，2026-10-13）：

| 证据 | 结果 |
|---|---|
| `.gitignore` 第 27 行 | `samples/private/` |
| `.gitignore` 第 28 行 | `evidence/private/` |
| `git check-ignore -v evidence/private/records.csv` | 命中 `.gitignore:28:evidence/private/` |
| `git check-ignore -v samples/private/x.apk` | 命中 `.gitignore:27:samples/private/` |

结论：**私有记录目录的忽略规则已存在，无需新增条目**，本次不修改 `.gitignore`（`evidence/private/` 目录本身尚未创建，归档时再建；忽略规则不依赖目录是否存在）。

说明：上表两条 `git check-ignore -v <路径>` 用任意探针路径演示规则命中，探针文件本身不必存在——`git check-ignore` 只按规则匹配路径，不检查文件是否存在。

## 5. 保留期限、删除时点与方式

| 数据 | 保留期限 | 删除时点 | 删除方式 |
|---|---|---|---|
| 参与者退出前的已记行 | 不保留 | **要求退出时立即删除**（当场） | 删掉该参与者在该场的全部行；同意书副本一并删除 |
| 原始逐题记录（真实） | 最长 90 天 | 汇总指标产出并复核后 **30 天内**删除原始记录 | 删除记录文件本体及其所在场次目录 |
| 汇总数据（匿名、无身份信息） | 研究报告生命周期内 | 报告定稿后按项目归档规则处理 | 只保留汇总表与脚本复算输出 |
| 演练记录 | 最长 30 天 | 走查结论签署后 **14 天内**删除 | 删除演练记录文件与临时输出目录 |
| 计时/日志等中间文件 | 不保留 | 该场记录归档当天 | 删除 |
| 备份或同步副本 | 与源同期限 | 与源同时删除 | 同步删除，不留在其它机器或云端 |

删除必须**删文件本体**，不只清空内容；删除后不复述、不引用其个体字段。

## 6. 汇总产出与复核

- 汇总指标一律由 `scripts/metrics-user-study.py` 从记录 CSV 复算，禁止手填汇总数字。
- 汇总至少同时给出：按 `material`（材料效果）、按 `condition`（顺序效果）、以及两者交叉的准确率，并单列未判（`is_correct` 留空）条数。
- 记录 CSV 与汇总输出都要写明数据来源（哪几场、哪个 `git_commit`）；演练数据必须写明 `SYNTHETIC ONLY`。

## 7. 本模板状态

- 本文件是约定模板；删除/保留承诺在真实研究启动前由主办方确认。
- 演练走查由**另一名成员**按 `evidence/user-study-rehearsal-checklist.template.md` 独立执行并留证。
