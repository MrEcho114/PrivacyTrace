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
