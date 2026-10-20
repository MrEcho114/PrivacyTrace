# 主持脚本 · 模板（#23 PT-907）

> 用途：让主持人对每一场理解测试使用同一套口径，减少主持人差异带来的偏差。
> 这是**模板**，不含真实参与者结果，也不构成任何研究结论；实际使用前按被测 App 与题集填写。
> 用词要求：客观中立，不出现"偷数据 / 窃取 / 泄露 / 违法 / 违规"等定性词，不暗示本系统做合法性或安全性判定。
> 演练相关内容一律标注 **SYNTHETIC ONLY / 演练**，不得冒充真实用户研究；本文件不声称任何真实参与者测试已完成。

配套文件：

- 对照材料与示例题：`evidence/user-study-comparison.template.md`
- 匿名知情同意书：`evidence/user-study-consent.template.md`
- 记录表骨架：`evidence/user-study.template.csv`
- 最小记录字段与保留/删除约定：`evidence/user-study-records-policy.template.md`
- 演练操作检查表：`evidence/user-study-rehearsal-checklist.template.md`

## 0. 开场前准备（每场开始前）

1. 打印或打开本节第 2 步指定的两份材料，**按平衡顺序表分好先后**，不要在现场临时决定。
2. 打开 `evidence/user-study-consent.template.md`，请参与者阅读后签署；参与者不同意就当场结束，不记录任何题目数据。
3. 打开记录表 `evidence/user-study.template.csv` 的表头，逐题一行登记。
4. 确认计时方式（同一只表 / 同一台设备），并在 `notes` 记下计时工具。
5. 若本场是演练，所有记录必须标注 **SYNTHETIC ONLY / 演练**，且不得与真实记录写进同一个 CSV 文件。

## 1. 开场念白（约 2 分钟，逐字念）

> 谢谢你来参加。这是一项关于「手机应用隐私说明是否好懂」的简短测试，全程约 10–20 分钟。
> 我会先给你两份材料，请你按我给的顺序阅读，然后回答几个问题。
> 这不是考试，也没有标准答案；答不上来也请直说"不知道"，这同样是有用的信息。
> 我不会评价你的回答，也不会解释材料内容。
> 全程自愿，任何时候都可以停止，不需要说明理由，也不会有任何损失。
> 我们只记录一个匿名编号，不记录姓名、手机号或账号。

## 2. 平衡顺序表（材料发放顺序 = 实际阅读顺序）

| 参与者序号 | `condition`（阅读顺序） | 先发／先读 | 后发／后读 | 顺序字段值 |
|---|---|---|---|---|
| 奇数（1、3、5…） | `baseline_first` | 材料 A = `baseline` | 材料 B = `privacyTrace` | `baseline;privacyTrace` |
| 偶数（2、4、6…） | `report_first` | 材料 B = `privacyTrace` | 材料 A = `baseline` | `privacyTrace;baseline` |

- 条件名只用 `baseline_first` / `report_first`，材料名只用 `baseline` / `privacyTrace`，与 `evidence/user-study-comparison.template.md` 第 4 节、记录表 `condition`/`material` 两列逐字一致。
- **顺序和材料是两件事，必须分别记**：`condition` 只说明先后，`material` 说明这道题实际用的是哪份材料。
- 发放顺序必须与实际阅读顺序一致：先读哪份，就先答该 `material` 的题；不得先发 A 却先答 B 的题。
- 如果改用"等价案例"安排（A、B 用不同但难度等价的 App/题目），仍按本表分配先后，并在 `notes` 注明等价性依据。

## 3. 计时与题序

1. 题集在开始前就固定；材料 A 与材料 B **共用同一组题**（同号同题），题干取自 `evidence/user-study-comparison.template.md` 第 3 节。
2. 顺序固定为：读第一份材料 → 回答该 `material` 的全部题 → 换第二份材料 → 回答剩余题。
3. 逐题记录 `start_time` / `end_time`（含时区）。
4. 只有定位类题目才计 `evidence_loc_seconds`（从主持人念完题干到参与者指出位置为止，单位秒）；不要求定位的题留空，不得填 0 充数。
5. 不设每题限时。参与者长时间停顿时，只可复述题干一次，不做提示。

## 4. 提问口径（只念题干）

- **只念题干**：逐字念 `evidence/user-study-comparison.template.md` 第 3 节的题目文字。
- **不解释**：不解释术语、不说明材料在哪一页、不补充背景。
- **不评价**：不说"对""不对""这个想法很好"。
- **不引导**：不举例、不暗示答案方向、不用语气提示。
- **不追问隐私经历**：参与者愿意讲就听，但不主动追问其个人经历细节。
- 参与者问"这题什么意思"：只重复题干原句，然后说"请按你的理解回答"。

## 5. 记录填写

字段与 `evidence/user-study.template.csv` **完全一致**（顺序也一致），逐题一行：

```
participant_id,background,condition,material,sample_id,ground_truth_version,question_id,answer,is_correct,evidence_loc_seconds,misconception,start_time,end_time,subjective_understanding,evidence_located,git_commit,notes
```

- 逐列含义、取值与必填要求见 `evidence/user-study-records-policy.template.md`。
- `answer` 记参与者原话；需要摘录时加引号，不改写。
- **主观题（"说清楚"是什么意思之类）不判分**：`is_correct` 留空，`subjective_understanding` 记原话；留空表示未判分，不得当作"答错"。
- 空白 ≠ 错误；拿不准的字段留空并写进 `notes`，不要猜。
- 汇总指标由 `scripts/metrics-user-study.py` 复算，主持人不得手填汇总数字。

## 6. 异常处置

| 情形 | 处置 |
|---|---|
| 参与者在阅读中要求退出 | 立即停止，不追问理由；当场删除该参与者已写入的全部记录行（含同意书复印件/照片），只在主持人日志留"已退出"一条，不留题目数据 |
| 参与者答到一半要求退出 | 同上：整行删除，不做"部分保留" |
| 某题超时（明显超过其余题用时数倍） | 不催、不提示；照常记 `start_time`/`end_time`，在 `notes` 写"该题用时明显偏长" |
| 设备/材料打不开导致中断 | 暂停计时，修复后继续；无法继续则整场作废并删除本场记录 |
| 中途放弃（非退出，例如临时有事） | 保留已完成题的记录并在 `notes` 写"未完成"，或整场删除；两者只能选一，且必须写进本场日志 |
| 参与者透露了身份信息 | 不写入任何记录字段；在 `notes` 也不写姓名，必要时删掉该句摘录 |
| 参与者情绪不适 | 立刻停止，按自愿退出处置 |

## 7. 收尾与致谢

念白：

> 问题就到这里。你的回答只会以匿名编号汇总使用，不会公布个人身份。
> 非常感谢你的时间；如果你之后想撤回，可以联系我，我们会删除你的记录。

收尾动作：

1. 核对记录表行数与题目数一致，缺行当场补齐或标注。
2. 核实没有身份信息写进任何字段。
3. 把记录表存入被 Git 忽略的私有目录（见 `evidence/user-study-records-policy.template.md` 第 4 节），**不要**放进 `evidence/` 公开目录。
4. 在 `notes` 为该场最后一行补记 `condition`、材料版本号与 `git_commit`。

## 8. 禁止行为（硬性清单）

- 不得提示答案：不指页、不指原句、不说"再看看第几段"。
- 不得追问参与者的个人隐私经历（自己或他人的数据经历都不追问）。
- 不得使用"泄露 / 窃取 / 违法 / 违规"等定性词，也不得暗示本系统在做合法性或安全性判定。
- 不得评价 App 好坏，也不得评价本系统报告好坏。
- 不得评价参与者，不说"对""错""这个很简单"。
- 不得由主持人代填答案、代猜 `is_correct`。
- 不得把演练数据写成真实研究数据，不得把演练记录混入真实记录文件。
- 不得把记录、同意书或本机私有路径提交进仓库。

## 9. 本模板状态

- 本文件是流程模板；准备包的技术验收以自动化检查、冻结证据和复算结果为准。
- 演练操作检查表只供可选操作核对，未执行不影响准备包验收；不得把未执行步骤记为已运行。
