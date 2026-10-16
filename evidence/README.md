# 证据材料

APK、完整政策、反编译内容及本地报告只保存在被 Git 忽略的私有目录。

S1 强制双人核验表已取消，用户不用填写。代理保留可追溯输入/规则/测试与脱敏摘要；见 [接受决定](../docs/stages/s1-acceptance-20261009.md)。历史表与 receipt 不倒改成“已人工复核”。

## 准备包使用说明（#23 PT-907）

「匿名用户理解测试准备包」由下面几份**模板**组成；模板一律不含真实参与者结果，也不构成研究结论。真实测试启动前，逐份按被测 App 填写。

| 文件 | 用途 |
|---|---|
| [user-study-comparison.template.md](user-study-comparison.template.md) | 对照材料（材料 A `baseline` / 材料 B `privacyTrace`）、共用题目与平衡顺序安排 |
| [user-study-question-bank.template.csv](user-study-question-bank.template.csv) | 题库与等价题集：`question_id,dimension,equivalent_set,stem,notes`；`equivalent_set` 标明等价题组，同组题面不得出现答案泄露词 |
| [user-study-answer-key.template.csv](user-study-answer-key.template.csv) | 独立答案键：`expected_answer`、分段证据位置与判分口径；`scorable=false` 时留空并写明不判分理由 |
| [user-study-assignment.template.csv](user-study-assignment.template.csv) | 参与者与平衡顺序分配表：`participant_id,condition,material_order,equivalent_set,notes` |
| [user-study-consent.template.md](user-study-consent.template.md) | 匿名知情同意与自愿退出口径 |
| [user-study-facilitator-script.template.md](user-study-facilitator-script.template.md) | 主持脚本：念白、平衡顺序表、计时题序、记录口径、异常处置、禁止行为 |
| [user-study-records-policy.template.md](user-study-records-policy.template.md) | 最小记录字段（对应 `user-study.template.csv`）、空白/无效值口径、私有存放位置、保留与删除约定 |
| [user-study-rehearsal-checklist.template.md](user-study-rehearsal-checklist.template.md) | 可选人工演练核对清单：不要求指定成员、人工签署或作为验收前置条件 |
| [user-study.template.csv](user-study.template.csv) | 记录表骨架（一行一次作答，17 列） |

这 9 个文件由 `evidence/synthetic/freeze-manifest.json` 逐条登记 `path`/`sha256`/`bytes` 冻结。

演练产物与校验（**SYNTHETIC ONLY / 演练**，不是真实证据）：

| 文件 | 用途 |
|---|---|
| [synthetic/user-study.csv](synthetic/user-study.csv) | 演练作答记录；`SYNTHETIC_REHEARSAL` 仅标识模拟性质，默认必须全部接受答案键、顺序、重复作答语义校验 |
| [synthetic/user-study-question-bank.csv](synthetic/user-study-question-bank.csv) | 演练题库与等价题集 |
| [synthetic/user-study-answer-key.csv](synthetic/user-study-answer-key.csv) | 演练答案键与证据位置/判分口径 |
| [synthetic/user-study-assignment.csv](synthetic/user-study-assignment.csv) | 演练参与者与平衡顺序分配 |
| [synthetic/freeze-manifest.json](synthetic/freeze-manifest.json) | 演练准备包冻结清单（`kind=user-study-pack-freeze`）：登记被覆盖文件的 `path`/`sha256`/`bytes` 与数据集摘要 `dataset_sha256`，是准备包的哈希权威记录 |
| `evidence/synthetic/rehearsal-walkthrough.md` | 历史 Synthetic 演练运行记录，仅用于技术复核；无需补做其他成员人工走查 |

准备包校验器 `scripts/verify-user-study-pack.py`：`python scripts/verify-user-study-pack.py` 默认校验全部 Synthetic 观测（本版 72 条）并复核清单与文件（退出码 0 = 全部通过、1 = 至少一个 issue、2 = 用法或环境错误）；`python scripts/verify-user-study-pack.py --write-manifest` 由冻结责任人重算 `files[]` 与 `dataset_sha256`（清单不存在时拒绝创建）。

使用顺序：准备对照材料、题库/答案键与分配表 → 确认记录与保留约定 → 使用 `scripts/check.sh` 及 `scripts/verify-user-study-pack.py` 校验。可选参照走查清单排查操作问题；不设人工走查验收门槛。

私有记录：真实记录、同意书与演练记录只放被 Git 忽略的 `evidence/private/`（见 [.gitignore](../.gitignore) 第 27–28 行），**不提交仓库**，也不写真实姓名或本机私有路径。演练数据见 [synthetic/README.md](synthetic/README.md)，标注 **SYNTHETIC ONLY**，不得当作真实研究证据或用于关闭 Issue #23。
