# PT-401 代码审查 · 双轴（Standards / Spec）

固定点：`d410cae`（PR29 整合基线）→ HEAD `06c7b0b`
Diff：`git diff d410cae...HEAD`，9 文件 / +853 −7
Commit：`06c7b0b feat(PT-401): 识别常见第三方 SDK 特征签名`
日期：2026-10-10

Standards 来源：`AGENTS.md`、`CONTRIBUTING.md`、`docs/architecture.md`、`apps/api/pyproject.toml`
Spec 来源：[Issue #22](https://github.com/MrEcho114/PrivacyTrace/issues/22)

---

## Standards

### (a) 已记录标准的违规

**S1【硬】新增版本化规则集未纳入契约生成**
`CONTRIBUTING.md`：「分类或匹配规则改变时更新版本、迁移说明和语义测试」。diff 新增了 `rules/sdk-signatures.v1.0.json` + `resources.sdk_signatures()` + `load_index()` 校验，但该规则集**没有 Pydantic 模型**，`scripts/export-schema.py` 的 `MODELS` 未登记，`test_contracts.py::test_generated_contracts_match_authoritative_models` 也覆盖不到。
`load_index()`（`sdk_attribution.py:82-95`）手写字段校验，是在替本该由模型承担的契约职责。
→ 版本与语义测试有了，schema/契约这一环缺失。判定：真实缺口，非吹毛求疵。

**S2【判断】`SDK_SIGNATURE_FILES` 与 `TAXONOMY_FILES` 注册表模式重复**
`resources.py:29-42` 逐字复刻 `taxonomy()` 的 select/get/raise 形状。基线 **Duplicated Code**。
仓库认可版本化注册表这个**模式**本身（故不压制），但两份平行副本意味着将来新增规则族要散改多处。

### (b) 基线 smell（均为判断，非硬性）

**Duplicated Code** — `apk_worker.py:317` 用 `class_descriptor[1:-1].replace("/", ".")` 手工解析描述符，而 `sdk_attribution.py` 已有 `descriptor_to_class()` 干同一件事，却没被复用。

**Primitive Obsession** — 匹配结果是裸 `dict`（`match["id"]`、`match["package_prefixes"][0]`、`match["vendor"]`），worker 伸手进规则 JSON 字段。一个小的 `Attribution` 类型会更稳。

**Mysterious Name** — `apk_worker.py:316` 的 `attributed = {}` 实际只当 seen-set 用（`attributed[key] = True`），且带魔数 `500`。名字说的是"归属映射"，实为去重守卫。

**Shotgun Surgery（轻微）** — 加一个规则集要改 `apk_worker.py`、`resources.py`、`sdk_attribution.py`、`worker.Dockerfile` 四处，其中 Dockerfile 那行 `COPY rules/sdk-signatures.v1.0.json` 是手工维护清单，每加一个规则集都得改。

### 未违规（明确记下）

- `test_sdk_attribution_creates_no_privacy_behavior` + `STATIC_POTENTIAL` 符合「UNKNOWN 不编造」「权限/静态 invoke 不证明实际采集」。
- 归属是确定性前缀匹配，未触碰「不使用 LLM 作最终事实裁决」。

---

## Spec

### (a) 缺失或部分实现

- *Spec 输出-1「建立具有明确公开依据的有限 SDK 特征签名集合」* — 已实现。
  但 Spec 输入写的是 *「[PT-301 #11] 输出的代码类路径与调用特征」*：实际匹配跑在 `apk_worker.py:305-310` 的 `cls.get_name()` 上，是**类路径**而非 PT-301 的「调用点」。考虑到两者等价，可接受，但 Spec 用词"调用点"只是宽松兑现。
- 未做版本号级匹配（`docs/stages` 的「不做」第 4 条已自认），可接受。

### (b) 范围外增量（scope creep）

- `docs/backlog.md` 本次提交顺手把 **PT-402～PT-406 五行**从「待开发」改写成「已实现」——但本提交只做 PT-401。**这是越过工单边界替他项宣告完成，且未验证。**（见下方复核）
- `resources.sdk_signatures()` / `SDK_SIGNATURE_FILES` 注册表：Spec 未要求版本化资源加载器。
- 500 条截断机制 + warning：未要求，属额外行为。
- `package_of()`（`sdk_attribution.py:101-103`）**导出但从未被调用** —— 死代码。

### (c) 看起来实现了、但实现有问题

**SP1【真实缺陷】截断警告写错字段，语义误导**
`apk_worker.py:353-354` 把 "SDK attribution output truncated at 500" 追加进 `coverage["behavior_limitations"]`。
但本模块**明确不产生 behavior**（`test_sdk_attribution_creates_no_privacy_behavior` 断言的就是这点）。该字段在 `apps/web/src/App.vue:222` 被渲染，位于**行为识别局限**标题下 —— 等于在告诉用户"行为覆盖有缺口"，而实际缺口在 SDK 归属，没有任何行为参与。
→ 归错槽位，会让用户误读覆盖范围。
复核：已实际读取 `apk_worker.py:340-355` 与 `apps/web/src/App.vue:222`，确认成立。

**SP2 边界 #2/#3 只写进散文，未固化进结构**
Spec 要求「SDK 自身政策不能替代宿主 App 的声明」「启发式归属不构成法律主体认定」。代码确实设了 `status="STATIC_POTENTIAL"` 且不产 behavior（#1 硬守住）。但这两条只存在于 `boundaries[]` 文案里，schema 上没有字段（如 `not_a_policy_claim`）阻止下游把 `potential_data_types`（`IMEI`/`OAID` 等）读成政策声明。属"声称"而非"强制"。
复核：确认 `potential_data_types` 未进入 evidence 记录，故当前**不会**误传给一致性引擎；但防护靠的是"没接上"，不是"接不上"。

**SP3 正例覆盖只到 11 条签名中的 4 条**
`test_worker_labels_known_sdk_packages` 仅参数化 4 个包（Bugly / JPush / 高德定位 / 友盟）。另外 7 条签名（高德地图、极光 JCore、腾讯地图、微信 OpenSDK、Mob、TuringFD、TBS）**无 worker 层正例**。匹配层 `test_known_signatures_are_labelled` 有 13 例，但那是直调 `SdkIndex`，不经过扫描装配。
复核：实际读出参数表，确认 4 条。

### 确认无问题（复核通过）

- **负例是真的**：`test_structurally_similar_custom_classes_are_not_labelled` + worker 层 6 组不误碰用例，实测拒绝 `com.amap.api.locationx`、`com.tencent.buglyx`、`com.example.bugly.CrashHandler`、`androidx.*`、`com.android.*`。前缀边界逻辑 `_matches_prefix` 正确。
- 测试数量与文档一致：37 + 14 = 51 ✅。
- 「11 条厂商签名」与 JSON 实际条目数一致 ✅。

---

## 结论

- **Standards**：4 项（1 硬 S1 + 3 判断 S2/重复/smell 组）。最严重：**新增版本化规则集未纳入 `export-schema.py` 契约生成**。
- **Spec**：6 项（3 缺漏/越界 + 3 实现问题）。最严重：**SP1 截断警告归入 `behavior_limitations`，与"本模块不产生行为"直接矛盾，会误导用户读覆盖范围**。

两条轴线刻意不跨轴排名。若要修，SP1 与 S1 是实质项，`package_of` 死代码与 backlog 越界改写是顺手可清的。

---

## 追加：PR #34 review comment 三项（2026-10-10）

固定点：`49464a7`（PR34 第二提交）→ HEAD `bdee855`
来源：PR [#34](https://github.com/MrEcho114/PrivacyTrace/pull/34) COMMENT 评审
处理：三项全部修复，`rules/sdk-signatures.v1.0.json` 未改动（无新增前缀需求）。

### [P1] 上限截断会让某些 SDK 完全不可见

原先按 DEX 类遍历顺序填满 `MAX_SDK_ATTRIBUTIONS = 500`，不按签名保留名额。
若某厂商 SDK 的 500+ 个类排在前面，后续另一厂商即使已命中也不会输出任何
证据，报告只留一条通用截断警告 → 会被解读成"未检出该 SDK"。

修复：归属改为在 DEX 遍历时**只收集**（`sdk_matches: dict[str, SdkMatch]`），
循环结束后由 `_select_sdk_attributions()` 统一选择并输出：

- 每个命中的签名先保留 `reserved` 条代表性类路径；
  `reserved = clamp(MAX_SDK_ATTRIBUTIONS // 签名数, MIN_SDK_REPRESENTATIVES,
  MAX_SDK_REPRESENTATIVES)` — 下界保证不会被上限清空，上界
  （`MAX_SDK_REPRESENTATIVES = 100`）防止恶意 APK 用极多签名抬高保底。
- 剩余额度再按遍历顺序补类级明细（spill）。
- 截断警告改为同时报出命中总数。

**文案不得承诺付不起的保证**：签名数 > 上限时，数学上做不到「每种各留一条」。
截断文案因此按 `_per_sdk_floor_is_achievable()` 分支：只有
`签名数 × MIN_SDK_REPRESENTATIVES <= MAX_SDK_ATTRIBUTIONS` 时才写入
「已保证每个命中的 SDK 至少保留 N 条」；否则只陈述截断事实。

注意上限是「类路径条数」而非「SDK 种类数」。`reserved` 是配额而非硬性每种一条。

新增测试：`test_a_large_sdk_cannot_crowd_a_second_sdk_out_of_the_cap`（前一 SDK
占满额度时后一 SDK 仍须出现在报告中）、
`test_cap_below_the_sdk_count_does_not_claim_an_unpayable_guarantee`（签名数超上限时
文案不得出现「已保证」）、`test_truncation_note_advertises_the_floor_only_when_the_budget_allows_it`、
稳定性与契约测试。

### [P2] 证据文案使用固定索引 0，而非实际命中的包前缀

`match_descriptor()` 只返回签名，worker 用 `match.package_prefixes[0]` 写 excerpt。
规则集中**友盟、极光 JCore、Mob、腾讯 TBS 各有两个前缀**，第二个前缀命中时
excerpt 仍声称匹配第一个 → 可追溯解释失真。

修复：`sdk_attribution.py` 新增 `SdkMatch`（`signature` / `prefix` / `class_name` / `dex`）
与 `match_prefix()`、`match_descriptor_with_prefix()`，携带真实命中的前缀。
excerpt 改写为实际命中前缀。`match()` / `match_descriptor()` 签名与返回值不变
（内部改为委托新方法），老调用方零改动。

新增测试：`test_match_reports_the_prefix_that_actually_matched`（参数化覆盖全部
多前缀签名）、`test_a_second_prefix_is_never_reported_as_the_first`（直接锁
index 0 回归）、`test_evidence_excerpt_names_the_prefix_that_actually_matched`、
`test_the_prefix_cited_is_always_a_published_prefix_of_the_labelled_sdk`。

### [P3] CLI 帮助与默认行为不一致

`--sdk-rules` 带非空默认值 → 省略即**启用**归属，但帮助写 `omit to disable
SDK attribution`；且 `type=Path` 下传空值不是可靠禁用方式。

修复：新增 `--no-sdk-attribution` 显式开关（`action="store_true"`），优先级高于
`--sdk-rules`；修正 `--sdk-rules` 帮助文案为 `(default: the shipped ruleset)`。
判定条件由 `if args.sdk_rules` 改为
`if args.sdk_rules is not None and not args.no_sdk_attribution`。

新增测试：默认启用 + `--no-sdk-attribution` 关闭、关闭优先于显式 `--sdk-rules`、
`--help` 含新开关且不再含 `omit to disable`。

### 顺带

输出改在 DEX 循环结束后统一发出，故报告对同一输入保持字节一致
（`test_same_bytes_produce_same_ids_and_locators` 与新增
`test_attribution_selection_is_stable_across_runs` 锁定）。

### 测试夹具容量（新发现，非本次评审提出）

`test_sdk_worker.minimal_dex()` 的 `class_def_item` 映射由**单个** class-data
偏移构造（`(0x2000, n_classes, class_data_offsets[0])`），故它可靠承载的类数
上限是 **4**。传 5 或 6 个类时 DEX 解析失败 → `failed_dex=["classes.dex"]` →
所有 SDK 断言退化成「无证据」而**静默通过**，是个容易写出假绿测试的陷阱。
（既有正例测试最多只用到 3 个类，因此此前未暴露。）

新增 `test_minimal_dex_fixture_capacity_matches_what_the_tests_assume` 显式锁定
该边界：4 个类必须全部产出证据，5 个类必须报 DEX 解析失败。本次新增的多类
用例（稳定性、前缀可追溯）已全部收敛到 ≤ 4 个类。

### 验证

- `ruff check apps/api/src apps/api/tests scripts/export-schema.py` → All checks passed。
- `python scripts/export-schema.py` → 与 `packages/contracts`、`contracts.generated.ts`
  零差异（契约与模型一致）。
- 定向：`pytest test_sdk_worker.py test_sdk_attribution.py` → **87 passed**（6.81s）。
- 全量 `pytest apps/api/tests` → **413 tests / 400 passed / 11 skipped / 2 failed**。

**差分对照（同一环境，先后独占运行）**

| 提交 | 用例总数 | 通过 | 失败 | 跳过 |
| :--- | :--- | :--- | :--- | :--- |
| 本 PR HEAD `802f300` | 413 | 400 | 2 | 11 |
| 基线 `49464a7`（改动前） | 389 | 376 | 2 | 11 |

本 PR 净增 24 个用例、全部通过，**新增失败为 0**。

**那 2 项失败的归属（已证清）**

两项均为 `test_job_creation.py`，报错与基线**逐字一致**：

- `test_one_reservation_wins_across_processes_and_survives_restart` → `_queue.Empty`
- `test_concurrent_pipeline_never_scans_both_inputs_for_one_id` →
  `PermissionError: [Errno 13] Permission denied: ...\.lock`

根因是 `job_store.JobStore._transaction()` 的 `os.open(O_CREAT|O_RDWR)` 无重试，
Windows 对并发 `CreateFile` 返回瞬态共享冲突；与本 PR 无关（`job_store.py`、
`pipeline.py`、`test_job_creation.py` 均不在 `git diff origin/main...HEAD` 内），
且二者**单独运行必过**（7 passed / 2.05s）。已在 `docs/backlog.md` 另记，本 PR 不修。

**一处需纠正的前次记录**：初次全量运行时曾观察到 `test_governance_cli.py` ×2 失败，
当时记为「既有失败」。后续定位为**并发争用假象**——那次运行与另一批 pytest 同时进行。
独占运行时 `test_governance_cli.py` **4 passed**，全量套件下亦通过。该文件确未被本 PR
触及，但此前的「既有失败」结论不成立，特此更正。

