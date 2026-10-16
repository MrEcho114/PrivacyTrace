# 理解测试准备包 · 演练走查清单 · 模板（#23 PT-907）

> 用途：在真实研究启动前，用**演练数据**把准备包从生成到归档走完一遍，确认命令、字段与口径确实可用。
> **本清单为可选的操作核对参考，不是验收门槛**；无需指定其他成员或取得人工签名。以 `scripts/check.sh`、`scripts/verify-user-study-pack.py` 及可复算的冻结材料作为技术验收依据。
> **不得伪造走查结果**：未执行就保持未勾选，不要凭预期打勾；只有真的执行过、并在条目下写明证据链接或输出摘要的条目才可以勾选。
> 演练数据一律标注 **SYNTHETIC ONLY / 演练**，不得冒充真实用户研究，不得用于关闭 Issue #23。
> 用词要求：客观中立，不出现"偷数据 / 窃取 / 泄露 / 违法 / 违规"等定性词。

执行环境（Windows，仓库根 `work/PrivacyTrace-pt907`）：

- Python：`apps/api/.venv/Scripts/python.exe`（下称 `python`）；不联网。
- 本清单不涉及 `git add` / `commit` / `push`。

## 0. 前置说明

- [ ] 0.1 （可选）记录演练执行环境、操作者和日期；不作为准备包验收条件。
- [ ] 0.2 已确认本清单与准备包模板文件的 `git_commit` 一致（`git rev-parse HEAD`）。
- [ ] 0.3 已确认第 1 节各条的期望结果是在提交 `210c941` 实测的；若演练链路脚本在此期间被改动，以实际生成的演练包内容为准，并把差异记入第 3 节可选记录区。

## 1. 演练链路（逐条勾选）

- [ ] 1.1 生成演练包

  命令（在仓库根执行）：

  ```
  python scripts/generate-synthetic-pt907.py --root .
  ```

  期望结果：退出码 0，输出 JSON 含 `"synthetic_only": true`，并列出 `samples/synthetic/manifest.csv`、`samples/synthetic/runs.csv`、`samples/synthetic/trace`、`samples/synthetic/policies.csv`、`evidence/synthetic/user-study.csv`、`evidence/synthetic/user-study-question-bank.csv`、`evidence/synthetic/user-study-answer-key.csv`、`evidence/synthetic/user-study-assignment.csv`、`samples/synthetic/README.md`、`evidence/synthetic/README.md`。
  证据：___

  说明：生成器是确定性的（同参数重复生成，内容与其他生成物逐字节一致，仅行尾可能不同）；如果不想改动工作树，可改用 `--root <临时目录>` 并把后续命令里的 `samples/synthetic`、`evidence/synthetic` 换到该临时根下。

- [ ] 1.2 账本校验

  ```
  python scripts/verify-run-ledger.py --ledger samples/synthetic/runs.csv --manifest samples/synthetic/manifest.csv
  ```

  期望结果：退出码 0，输出 `{"verified": [...]}`，含 4 条 run（`run-syn-cam-1`、`run-syn-contact-1`、`run-syn-map-1`、`run-syn-wallet-1`），每条带 `outcome`、`report_sha256`、`evidence_count`。
  证据：___

- [ ] 1.3 trace 校验（四个样本各一次）

  ```
  python scripts/validate-trace.py samples/synthetic/trace/syn-cam-v1.jsonl
  python scripts/validate-trace.py samples/synthetic/trace/syn-contact-v1.jsonl
  python scripts/validate-trace.py samples/synthetic/trace/syn-map-v1.jsonl
  python scripts/validate-trace.py samples/synthetic/trace/syn-wallet-v1.jsonl
  ```

  期望结果：每条退出码 0，输出 `{"valid_lines": 4}`。
  证据：___

- [ ] 1.4 数据集构建

  ```
  python scripts/build-dataset.py --ledger samples/synthetic/runs.csv --trace-dir samples/synthetic/trace --manifest samples/synthetic/manifest.csv --out <输出路径>/dataset.json
  ```

  期望结果：退出码 0（无 stdout），`<输出路径>/dataset.json` 被写出且非空；构建同时复用 1.2 的账本校验与 1.3 的 trace 契约。
  证据：___

- [ ] 1.5 指标计算

  ```
  python scripts/metrics-user-study.py --input evidence/synthetic/user-study.csv --format markdown
  ```

  期望结果：退出码 0；Markdown 显示总记录 72 条、参与者 6 名、未判（`is_correct` 空）0 条；按 `material`、按 `condition`、以及两者交叉三组准确率都给出，且逐组带分母与未判条数。
  证据：___

- [ ] 1.6 准备包校验

  ```
  python scripts/verify-user-study-pack.py
  ```

  期望结果：退出码 0，stdout 形如（`root` 随执行机器变化；实测样例的 `root` 为 `G:/GZQ/session-files/work/PrivacyTrace-pt907`）：

  ```
  verify-user-study-pack: root=<仓库根绝对路径，正斜杠形式>
  rows: question-bank=14 answer-key=50 assignment=8 observations=72 (rehearsal-included=72)
  rehearsal rows: included in semantic verification
  issues: 0
  result: OK
  ```

  机器可读形态：`python scripts/verify-user-study-pack.py --json` 输出 `{"ok": true, "issues": []}`（两空格缩进）。退出码语义：`0` = 全部检查通过；`1` = 至少一个 issue（`issues: <n>`，其后逐条列出 `[code] path: detail`，末行 `result: FAIL`）；`2` = 用法或环境错误（stderr 以 `error:` 开头，例如 `--root` 指向的不是目录）。`rows:` 一行核对题库 / 答案键 / 分配表行数，并把标注 `SYNTHETIC_REHEARSAL` 的演练作答行全部纳入语义校验（`rehearsal-included=`）。
  证据：___

  备注 1（本机沙箱边界，实测）：在 DSH 沙箱下，脚本的 dataset 重建检查会用 `tempfile.TemporaryDirectory()` 建 0o700 目录，该目录在沙箱内不可访问，于是出现 `[manifest-dataset-rebuild] evidence/synthetic/freeze-manifest.json: dataset rebuild failed: PermissionError: [WinError 5] 拒绝访问。: '<TEMP>\pt907-pack-xxxx'`。这不是校验器不可用：把 `TMPDIR`/`TEMP`/`TMP` 指到可写目录，并用强制 0o777 建目录的启动 shim（如 `G:\GZQ\session-files\_pt907_walkthrough\run_pack_verifier.py`）即可让同一个脚本跑通，脚本自身逻辑不做任何改动。Linux/CI（`scripts/check.sh`）无此问题，不需要任何处理。

  备注 2（清单过期时的处置）：若本条的 issue 里出现 `manifest-hash-mismatch` / `manifest-bytes-mismatch` / `manifest-missing-file` / `manifest-extra-file` / `manifest-excluded` / `manifest-dataset-sha`，说明冻结清单与工作树已经不一致（例如被覆盖文件在清单写定后又被修改）。这类 issue 交给冻结清单责任人按 1.7 的 `--write-manifest` 重算后再复核；走查者不要顺手改清单、也不要改被覆盖文件，本条保持未勾选并把原文记入第 3 节。

- [ ] 1.7 冻结清单复核（哈希权威记录）

  命令（在仓库根执行）：

  ```
  git rev-parse HEAD
  python scripts/verify-user-study-pack.py --json
  Get-ChildItem evidence/user-study*.template.* | ForEach-Object { Get-FileHash -Algorithm SHA256 $_.FullName }
  ```

  期望结果：

  - 提交号与本清单 0.2 记录一致。
  - `evidence/synthetic/freeze-manifest.json` 是准备包的**哈希权威记录**，不是附加说明：`kind=user-study-pack-freeze`、`schema_version=1.0.0`、`synthetic_only=true`、`hash_normalization=crlf-to-lf`、`dataset_schema_version=0.3.0`；`files[]` 每项给出 `path`、`sha256`、`bytes`；`covered_globs` 覆盖 `evidence/user-study-*.template.*`、`evidence/synthetic/*.csv`、`evidence/synthetic/*.md`、`evidence/synthetic/README.md`、`evidence/trace.schema.md`、`samples/synthetic/**`，以及 1.1–1.6 用到的 `scripts/*.py`。
  - 9 个模板文件都在 `files[]` 里逐条列出：`evidence/user-study-answer-key.template.csv`、`evidence/user-study-assignment.template.csv`、`evidence/user-study-comparison.template.md`、`evidence/user-study-consent.template.md`、`evidence/user-study-facilitator-script.template.md`、`evidence/user-study-question-bank.template.csv`、`evidence/user-study-records-policy.template.md`、`evidence/user-study-rehearsal-checklist.template.md`、`evidence/user-study.template.csv`。把上面 `Get-FileHash` 的 9 个值与清单中同 `path` 的 `sha256` 逐条对照后抄录进走查记录，供真实研究启动时对照（真实研究期间这些文件不得改动）。注意清单的哈希按 `hash_normalization: crlf-to-lf` 归一化后计算：工作树若检出为 CRLF，直接比原始字节哈希会不同，需先归一化行尾再比。
  - `excluded` 固定保留两项且不得删：`evidence/synthetic/freeze-manifest.json`（自引用——清单不把自己的哈希写进自己）与 `evidence/synthetic/rehearsal-walkthrough.md`（演练走查记录本身不参与冻结）；任一项缺失，1.6 会报 `manifest-excluded`。
  - `dataset_sha256` 与 1.4 步产物核对：重跑 1.4 的 `build-dataset.py` 得到 `dataset.json`，其**内部字段** `dataset_sha256` 应与清单的 `dataset_sha256` 一致（当前冻结值 `83907a2f8e422ebe4f5952af9fe7d93a81c4afef29edbbd6e32a55b9a6c18014`）；不一致时 1.6 报 `manifest-dataset-sha`。注意 `dataset.json` 自身含 `generated_at`，文件级 sha256 每次都不同，不要拿文件哈希去比。
  - `--write-manifest` 语义（只由冻结清单责任人执行）：`python scripts/verify-user-study-pack.py --write-manifest` 重算 `covered_globs`、`files[]`（`path`/`sha256`/`bytes`）与 `dataset_sha256`，其余字段原样保留；**清单文件不存在时拒绝创建**（退出码 2，stderr 为 `error: evidence/synthetic/freeze-manifest.json is missing; refusing to create it (the rehearsal walkthrough step creates it)`）。因此不存在"先手写一份骨架再让脚本补全"的省事路径：骨架必须由演练走查步骤先落盘，`--write-manifest` 只负责重算。重算成功后 stdout 为 `freeze manifest rewritten: evidence/synthetic/freeze-manifest.json`，并紧接着再跑一遍完整校验。
  证据：___

- [ ] 1.8 记录归档

  ```
  git check-ignore -v evidence/private/user-study/<study-id>/user-study.csv
  ```

  期望结果：命中 `.gitignore:28:evidence/private/`（即私有记录目录确实被 Git 忽略）；`git status --porcelain` 中**不出现**任何你新写入的私有记录文件。
  证据：___

  说明：删除/保留时点按 `evidence/user-study-records-policy.template.md` 第 5 节执行；可选演练的临时记录在演练完成后 14 天内删除。`<study-id>` 是占位符，按第 4 节的命名规则替换；该目录应尚未存在，命令只用来确认忽略规则命中。

## 2. 走查中发现问题时的处置

- [ ] 2.1 任何一条命令非零退出或输出与期望不符：如实记录命令原文、退出码与报错原文，把对应条目保持未勾选。
- [ ] 2.2 发现字段名/条件名/材料名与 `evidence/user-study.template.csv` 不一致：记录不一致的两处原文，不要自行改准备包文件。

## 3. 可选执行记录

| 项 | 内容 |
|---|---|
| 执行者（可选） | |
| 执行日期 | |
| 结论（通过／不通过／部分通过） | |
| 证据链接（命令输出、日志、截图路径） | |

未执行的条目保持未勾选，不影响技术验收结论；自愿执行时应提供实际命令输出或证据，不得编造。
