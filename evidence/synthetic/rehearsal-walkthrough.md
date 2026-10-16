# 理解测试准备包 · 演练记录（#23 PT-907 / Issue #62）

> **SYNTHETIC ONLY / 演练**：本记录包含的全部数据都是 `scripts/generate-synthetic-pt907.py` 生成的演练数据（假包名 `synthetic.example.invalid`），不代表任何真实用户、真实 App 或真实研究结论，不得用于证明真实效果，也不得用于关闭 Issue #23。
> 本文件已列入 `evidence/synthetic/freeze-manifest.json` 的 `excluded`，不参与准备包冻结（自引用问题）；它只记录此次演练的执行情况，并不属于被冻结的材料。

## 0. 先说边界（本记录的效力范围）

- **历史事实**：本演练记录由准备包作者会话（DSH `session-68819f85-…`）执行，反映当时实际运行结果。**现行流程**：Issue #62 已于 2026-10-16 验收关闭，项目负责人正式取消指定其他成员执行演练及签署要求；本历史记录不再产生任何待完成的验收义务。
- 操作检查表 `evidence/user-study-rehearsal-checklist.template.md` 是空白模板，保持未勾选代表模板本身未记录执行结果，不构成验收阻塞。本记录按编号保留当时实跑证据。
- 本次演练 **未联网**、**未 `git add` / `commit` / `push`**、**未写任何真实参与者数据**。
- 演练链路的「材料效果 / 顺序效果」数字是**刻意平衡的演练数据**（每个条件各 3 人、每个等价题组各一次），只用来验证命令能跑通、分母口径清楚，**不构成任何结论**。

## 1. 演练环境与版本

| 项 | 值 |
|---|---|
| 仓库根 | `G:\GZQ\session-files\work\PrivacyTrace-pt907` |
| 分支 | `codex/pt-907-user-study` |
| 提交 | `210c941e64d2872a01d169069d65b28bf3b8728e`（`git rev-parse HEAD`，演练前后一致） |
| Python | `apps/api/.venv/Scripts/python.exe` |
| 执行时间（本地） | 2026-10-15T23:08:29+08:00 |
| 实跑日志 | 本会话工作目录 `_pt907_walkthrough\walkthrough-20261015.log`（262 行，含每条命令原文、stdout 与退出码），未随仓库提交 |

演练时工作树包含本准备包的**未提交**改动（已冻结为下方哈希）：`M evidence/README.md`、`M evidence/synthetic/README.md`、`M evidence/synthetic/user-study.csv`、`M evidence/user-study-comparison.template.md`、`M evidence/user-study-consent.template.md`、`M samples/synthetic/*`（4 个 csv + README + 4 个 trace + manifest）、`M scripts/check.sh`、`M scripts/generate-synthetic-pt907.py`，以及 `??` 新增的 `evidence/synthetic/freeze-manifest.json`、`evidence/synthetic/user-study-{question-bank,answer-key,assignment}.csv`、`evidence/user-study-{question-bank,answer-key,assignment}.template.csv`、`evidence/user-study-facilitator-script.template.md`、`evidence/user-study-records-policy.template.md`、`evidence/user-study-rehearsal-checklist.template.md`、`scripts/verify-user-study-pack.py`、`apps/api/tests/test_user_study_pack.py`。

### 1.1 本机沙箱边界（实测，非准备包缺陷）

DSH 沙箱下 `tempfile.TemporaryDirectory()` 的 `mkdir(mode=0o700)` 会得到当前令牌不在其安全描述符里的目录，数据集重建检查因此报 `[manifest-dataset-rebuild] … PermissionError: [WinError 5] 拒绝访问。: '<TEMP>\pt907-pack-xxxx'`。处置：把 `TMPDIR`/`TEMP`/`TMP` 指到可写目录，并用一个**只在本进程内**把 `os.mkdir` 的 mode 强制为 `0o777` 的启动器（`_pt907_walkthrough\run_sandboxed.py`，28 行）加载脚本；**脚本自身逻辑未做任何改动**，Linux/CI（`scripts/check.sh`）无此问题。本次演练的所有 Python 步骤都经该启动器执行。

## 2. 逐条实跑结果（全部退出码 0）

| 清单条目 | 命令（仓库根执行） | 退出码 | 关键结果 |
|---|---|---|---|
| 0.2 | `git rev-parse HEAD` | 0 | `210c941e64d2872a01d169069d65b28bf3b8728e` |
| 1.1 | `python scripts/generate-synthetic-pt907.py --root .` | 0 | JSON 含 `"synthetic_only": true`，列出 11 个产物路径（4 个 samples 侧 + 4 个 evidence 侧 + 2 个 README + `policies`），`generated_at 2026-10-13T00:00:00+00:00` |
| 1.2 | `python scripts/verify-run-ledger.py --ledger samples/synthetic/runs.csv --manifest samples/synthetic/manifest.csv` | 0 | 4 条 run：`run-syn-cam-1` partial/sha `db2a5059…`/evidence 2、`run-syn-contact-1` success/sha `407f29f7…`/evidence 4、`run-syn-map-1` success/sha `3d0f3ccb…`/evidence 3、`run-syn-wallet-1` **failed/`report_sha256` 空**/evidence 1 |
| 1.3 | `python scripts/validate-trace.py samples/synthetic/trace/<sample>.jsonl` ×4 | 0,0,0,0 | 四条均 `{"valid_lines": 4}` |
| 1.4 | `python scripts/build-dataset.py --ledger … --trace-dir samples/synthetic/trace --manifest … --out <out>/dataset.json` | 0 | 无 stdout；产物 5154 字节；内部字段 `dataset_sha256 = 83907a2f8e422ebe4f5952af9fe7d93a81c4afef29edbbd6e32a55b9a6c18014` |
| 1.5 | `python scripts/metrics-user-study.py --input evidence/synthetic/user-study.csv --format markdown` | 0 | 72 条 / 6 名 / 未判 0；`baseline 30/36 = 0.8333`、`privacyTrace 30/36 = 0.8333`；`baseline_first 30/36`、`report_first 30/36`；四格交叉各 `15/18 = 0.8333`；定位证据耗时按成败分开统计：成功率 `0.8333`（成功 60 / 失败 12，未要求定位 0 不计入分母），成功定位耗时中位 `22.5`、定位失败尝试中位 `20.5`，两者各自给出最小/最大/均值/中位/P90（不分成败的旧混合口径 `14.0 / 31.0 / 22.166667 / 22.0 / 27.0` 仍随报告输出，但明示仅供对数、不得据此比较材料）；误解总计 7（权限=实际收集 2、权限=调用 3、法律判定 2） |
| 1.6 | `python scripts/verify-user-study-pack.py` | 0 | `rows: question-bank=14 answer-key=50 assignment=8 observations=0 (rehearsal-excluded=72)` / `issues: 0` / `result: OK` |
| 1.6 | `python scripts/verify-user-study-pack.py --json` | 0 | `{"ok": true, "issues": []}`（两空格缩进） |
| 1.7 | 冻结清单复核（见第 3 节） | 0 | 清单 29 个文件、13 条 `covered_globs`、9 个模板哈希逐条 `MATCH`；`dataset_sha256` 与 1.4 内部字段一致 |
| 1.8 | `git check-ignore -v evidence/private/user-study/rehearsal-01/user-study.csv` | 0 | 命中 `.gitignore:28:evidence/private/`；演练前后 `git status --porcelain` 无新增未跟踪私有记录文件 |

演练数据的复算口径（供任何复核者核对）：72 行观测中 `answer` 分布 A 30 / B 42，`is_correct` 60 true / 12 false；每行 `is_correct == (answer == answer_key.expected_answer)`（自洽违规 0 行）；`material` 与 `condition` 各 36/36。

## 3. 冻结清单：材料、工具与报告的版本／哈希

**权威记录**：`evidence/synthetic/freeze-manifest.json`（5853 字节，自身 `sha256 = d5b2f138ff0fba811148c11dbdb0ef141f72d867d86114eaad7e5d0a40922e0e`，2026-10-16 重算后）。
清单元数据：`kind=user-study-pack-freeze`、`schema_version=1.0.0`、`synthetic_only=true`、`hash_normalization=crlf-to-lf`、`dataset_schema_version=0.3.0`、`dataset_sha256=83907a2f8e422ebe4f5952af9fe7d93a81c4afef29edbbd6e32a55b9a6c18014`、`files=29`、`covered_globs=13`；`excluded` 固定两项（`evidence/synthetic/freeze-manifest.json`、`evidence/synthetic/rehearsal-walkthrough.md`）。
哈希口径：原始字节 → CRLF 归一为 LF → SHA-256（`bytes` 为归一后字节数）。**这份清单只证明归一化后的准备包内容一致，不证明磁盘上文件字节完全相同**（行尾差异不计入）；原始 Trace 文件另有清单内的逐文件哈希，见下。

九个提交材料模板（演练时逐个重算并与清单比对，全部 `MATCH`）：

| 文件 | 字节 | sha256（crlf-to-lf 归一后） |
|---|---|---|
| `evidence/user-study.template.csv` | 220 | `a094b93758d7d4e89d03f831262b8af33f6f589645bbc0b2f113614b4f275e38` |
| `evidence/user-study-question-bank.template.csv` | 484 | `b9ff02aa5a8810576210371508bdd5ceb55ccf8787fc4f65fdf6f45a85a68be2` |
| `evidence/user-study-answer-key.template.csv` | 467 | `a671d848b4fb61965cd50e1a5d11042ed328b6afbea96459d7039fd3209aa924` |
| `evidence/user-study-assignment.template.csv` | 371 | `804827b2ce5d99724bd36408be89b42c6b6a538fabb19cdadb2598a07bdad0a7` |
| `evidence/user-study-comparison.template.md` | 5122 | `50e3f12d9bd4ac07f9382f4c13582cdbc32f37ecafde10a5c8a9194f166dd2bc` |
| `evidence/user-study-consent.template.md` | 2067 | `76aebb5eda96d8a179a2ee04d494fed8a68583a9112be8bd84a91105c9e0d8ec` |
| `evidence/user-study-records-policy.template.md` | 7536 | `a9b45a168682e12fc783ca3b936e1a475425941fd5d1f4fdb0f08a806f86c546` |
| `evidence/user-study-facilitator-script.template.md` | 8035 | `407a47e3d55fdefe92a15541b3bda2f5af7478f8b8bdc41f8fdc6237a59c40f7` |
| `evidence/user-study-rehearsal-checklist.template.md` | 10910 | `c7663589a17d0f3fdecc8ac1ee9514627252bebe1cc00acfe5a6417844116b6e` |

演练材料、演练 Trace 与工具（`scripts/*.py`）的逐文件哈希共 29 条，全部记录在 `freeze-manifest.json` 的 `files[]` 中；重算方式：`python scripts/verify-user-study-pack.py`（全量比对）或 `--write-manifest`（由冻结责任人重算）。

## 4. 演练中发现并已处理的问题

1. **冻结清单过期**：清单写定后 `scripts/verify-user-study-pack.py` 又被修改（覆盖缺口修复），1.6 报 `manifest-bytes-mismatch`（36840 → 38143）与 `manifest-hash-mismatch`（`7f102ae0…` → `8d59bc67…`）。处置：由冻结责任人执行 `--write-manifest` 重算（同时重算 `dataset_sha256`），重算后 1.6 恢复 `issues: 0 / result: OK`。
2. **`evidence/user-study.template.csv` 曾不在冻结范围内**：`evidence/user-study-*.template.*` 匹配不到它（实测 fnmatch 为 False，`user-study*.template.*` 才为 True），而它是主持脚本第 5 节引用的 17 列观测表头契约；`--write-manifest` 也无法自愈。处置：校验器 `DEFAULT_COVERED_GLOBS` 追加该文件字面量，并新增必需材料清单（`REQUIRED_MANIFEST_PATHS`）——「文件存在但既不在 `files[]` 也不被任何 glob 覆盖」即报既有的 `manifest-missing-file`，陈旧 glob 不再能静默漏冻；`write_manifest` 同时归一化并补齐 `covered_globs`。修复后 `manifest files=29`，九个模板全部在册。
3. **本记录文件当时不存在**：演练开始前 `evidence/synthetic/rehearsal-walkthrough.md` 未落盘，而 `excluded` 必须保留它。处置：由原演练步骤创建（它本身不参与冻结）。
4. **沙箱 temp 边界**（环境性，非准备包缺陷）：见 1.1，处置为启动器 + `TMPDIR`/`TEMP`/`TMP` 重定向。

### 4.1 上游落地后的复核（2026-10-16）

并行执行会话把 `scripts/build-dataset.py`、`scripts/verify-run-ledger.py`、`scripts/metrics-user-study.py`、`evidence/trace.schema.md`、`apps/api/tests/*` 的修复提交为 `19daf93`、`e146dd2` 之后，本会话在 `e146dd2` 上复核：

- 冻结清单因被覆盖文件变动而失效（1.6 报 8 条 `manifest-bytes-mismatch`/`manifest-hash-mismatch`）；执行 `--write-manifest` 重算后 `issues: 0 / result: OK`，`files=29`、`covered_globs=13`、`dataset_sha256` **复核后不变**（`83907a2f…`），九个模板哈希不变。
- 演练链路 1.1–1.5 重跑全部退出码 0；`dataset_sha256` 仍为 `83907a2f8e422ebe4f5952af9fe7d93a81c4afef29edbbd6e32a55b9a6c18014`；准确率类指标不变，仅定位耗时的分组口径更新（见 1.5 行）。
- PT-907 七个测试文件 `133 passed`；全量 `apps/api/tests` 为 `10 failed, 740 passed, 20 skipped`，失败仍全部为本机沙箱/环境性（多进程命名管道、`cannot snapshot local source`、DNS/本地 HTTP loopback、Symlink 权限）；`ruff` `All checks passed!`。

## 5. 未验证 / 已知限制（如实保留）

- **流程修订（2026-10-16）**：不再设置其他成员执行演练和签署的验收义务。保留作者会话的历史实跑记录，配合 CI 与冻结证据完成技术核验。
- **`bash scripts/check.sh` / `pwsh -NoProfile -File scripts/check.ps1` 本机未跑通**：Git for Windows Bash 报 `couldn't create signal pipe, Win32 error 5`、`C:\Windows\system32\bash.exe` 返回 `E_ACCESSDENIED`（沙箱禁止命名管道），只能由 CI 执行；本地等价验证为 venv 内 `pytest` + `ruff` + 各校验脚本 + `themasterplan verify`。
- **真实样本与真实参与者流程未执行**：本记录只走演练链路；真实研究需按 `evidence/user-study-consent.template.md`、`evidence/user-study-records-policy.template.md` 与主持脚本执行。
- **原始 Trace 完整性边界**：`dataset_sha256` 只证明归一化数据集内容一致，不证明原始日志文件相同；原始 Trace 文件的哈希以本清单 `files[]` 中的逐文件 SHA-256 为准。
- 准备包尚未提交/合并：本次交付停在工作树（未提交），合入需独立授权。

## 6. 结论

**当时的技术演练已通过**（演练链路本身可执行、可复算：1.1–1.8 共 15 次调用全部退出码 0；当时冻结清单与 9 个模板哈希逐条吻合）。后续模板修订应以最新 `freeze-manifest.json` 为准。

现行验收不要求其他成员补做演练；`scripts/check.sh` 的权威入口由 CI 核验。演练数据的一切指标（各 30/36、四格 15/18）不得当作真实结论。


## 7. 后续修复记录（第 6 轮复审，2026-10-16）

此节是针对第 6 轮审查修复的**预期校验口径**说明，并非修改第 1–6 节的历史实跑记录；原作者会话的执行身份不变。校验器改为默认纳入所有 `SYNTHETIC_REHEARSAL` 行（当前 72 条）执行答案键、一人一顺序、重复作答检查，不再显示 `rehearsal-excluded=72`。规范化数据集内容和 `dataset_sha256` 预期不变。以上以更新提交的 CI 和可复核产物为准；历史作者会话运行记录不等于实际用户实验。
