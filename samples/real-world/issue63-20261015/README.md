# PT-907/2 · Issue #63 真实样本运行归档（2026-10-15）

状态：**部分交付，数量目标未全部达到**。本目录只提交登记和脱敏结果；当前执行记录在 [Issue #63](https://github.com/MrEcho114/PrivacyTrace/issues/63)。不关闭父任务 #23，不把真实样本数当作理解测试的前置门槛。

本轮确认 **3 个不同的真实 App，其中新增 2 个**：保留的 GKD、首次取得的 NewPipe 和 K-9 Mail。共执行 **4 次真实 Docker pipeline**，3 次生成报告，1 次失败。Telegram 是复杂通信场景候选，但下载内容未通过 ZIP 校验，package/version 均 UNKNOWN，**不计为第 4 个已确认 App，也没有完成复杂度验证**。另一次备用入口检查取得 HTML 下载页，没有当作 APK 再扫描。未取得一个可确认版本的复杂挑战 APK，故“3 个代表性 App + 1 个复杂挑战 App”尚未达标。

## 样本与结果

| 样本 | 本轮关系 | 容器确认的 package / version / code | DEX | 证据 / 行为 / 候选 / 结果 | 实际结果 |
| --- | --- | --- | --- | --- | --- |
| GKD | 历史 APK，本轮新扫描、新政策捕获 | `li.songe.gkd` / 1.12.1 / 92 | 1/1 | 5 / 3 / 1 / 3 | pipeline SUCCEEDED；对照 partial |
| NewPipe | 新增媒体客户端 | `org.schabi.newpipe` / 0.29.1 / 1015 | 3/3 | 6 / 4 / 1 / 4 | pipeline SUCCEEDED；对照 partial |
| K-9 Mail | 新增邮件客户端 | `com.fsck.k9` / 24.0 / 39046 | 2/2 | 7 / 5 / 1 / 5 | pipeline SUCCEEDED；对照 partial |
| Telegram candidate | 新增复杂通信候选尝试 | UNKNOWN / UNKNOWN / UNKNOWN | 未进入 DEX 处理 | 无报告，不填零条命中 | pipeline FAILED：ZIP_INVALID |

证据数包括每份报告的政策快照和一条政策候选原句。12 项规则结果全部为 `INSUFFICIENT_EVIDENCE`。账本把生成报告但存在政策边界的端到端结果记为 `partial`；`pipeline_status=SUCCEEDED` 与 DEX `COMPLETE` 分别保留，不能用它们声称政策对照完整。

GKD 覆盖无障碍/截图；NewPipe 覆盖媒体及设备相关静态线索；K-9 覆盖邮件客户端的通讯录/相机能力；Telegram 原拟补充复杂通信与云服务场景。这个选择只提供功能差异，不代表抽样具有统计代表性。未安装或动态运行任何 APK。

## 文件与哈希口径

- [candidates.csv](candidates.csv)：4 个候选，包括身份 UNKNOWN 的失败输入；不能作为“4 个真实 App”清单。
- [manifest.csv](manifest.csv)：只含容器确认的 3 个 App，沿用现有登记字段。根部历史登记没有改写。
- [runs.csv](runs.csv)：逐次 pipeline 账本，沿用 PR #61 模板的原始列。失败作业保留 job ID，报告哈希和计数留空。
- [acquisitions.json](acquisitions.json)：3 次 APK 地址获取、4 次新政策页获取，以及 1 次备用下载页检查。临时 CDN query 已删除；HTTP 200 只证明取得字节，不证明是完整 APK。
- [summary.json](summary.json)：来源时点、输入/政策/报告哈希、工具、DEX/截断边界、代码定位与政策原句定位、逐条结果引用及脱敏隔离收据。
- [restricted-index.json](restricted-index.json)：受限原件的非敏感索引。组员按 `index_id` 向本票负责人索取；不公布文件系统位置、APK、完整政策、反编译全文或临时下载参数。
- [verification.json](verification.json)：实际验证、固定工具候选和公开文件哈希。

`manifest.csv` 的 `apk_sha256` 是实际核验 APK 字节的 SHA-256。Telegram 候选的该字段留空；被拒绝输入的哈希保留在获取记录和摘要的 `input_sha256`，不能当作已确认 Telegram 发布包标识。官方 HTTPS 获取路径和容器元数据已核对；没有额外执行发布签名指纹或可重复构建认证。

`report_sha256` 是私有 `JobStore.report(job_id)` 导出对象的完整 JSON 字节哈希：`model_dump(mode="json")` → `json.dumps(..., ensure_ascii=False, indent=2)` → 追加一个 LF → UTF-8、LF 换行。该导出保留 `source_origin=REAL_SCAN`，读取方式为 `PERSISTED_REPLAY`；**不是**脱敏摘要或排除运行身份后的语义哈希。数据库存储记录另有 `stored_record_sha256`。原报告可能含私有工具路径，所以只公开哈希与白名单字段。

## 政策与代码的可回查边界

四个官方政策入口均于本轮重新请求，没有复用历史 GKD 政策。分别保存原 HTML、确定性提取的 UTF-8 文本与捕获包哈希；获取时点和捕获时点分开记录。HTML 提取使用 lxml 6.1.3，显式 UTF-8 解码；删除 script/style/nav/footer/header，取首个 main/article/dev_page_content（没有则取文档），去掉空文本节点，逐节点 strip 后以 LF 连接并追加 LF。本轮 Windows 文本写入将这些换行序列化为 CRLF；捕获包哈希和码点区间均以实际 UTF-8 / CRLF 字节解码后的文本为准，复算时须保留该步骤。

捕获包中的 `completeness=COMPLETE` 只指这份文本快照完整、哈希与分句一致；页面相关附件/链接、条款语义与发布版适用性没有因此完成。公开摘要统一保留来源文档 `PARTIAL`、抽取 `PARTIAL`、复核 `UNREVIEWED`、附件 `NOT_CHECKED`，精确 APK 版本适用性及地区 `UNKNOWN`。每页仅由代理选择一条待复核候选，action/subject/polarity 全部为 UNKNOWN；未调用外部模型，也不是完整条款抽取。

| 来源 | 本轮保留的局限 | 可回查的关系 |
| --- | --- | --- |
| [GKD 官网政策](https://gkd.li/guide/privacy) | 页面版本 1.0，生效日期依应用发布；未证实适用于旧版 1.12.1 | 截图候选的精确原句区间与 `takeScreenshot` 字节码位置分别保存；未认定为已确认匹配 |
| [NewPipe 项目政策](https://newpipe.net/legal/privacy/) | 主要覆盖项目服务；设备信息列表属于用户主动提交崩溃报告的上下文 | 设备信息候选没有被强行配给文件/位置/标识符线索；缺少适用且明确的对应声明仍是证据不足 |
| [K-9 政策](https://k9mail.app/privacy) | 页面说明 K-9/Thunderbird 关系，并限定最新通用版本；确切 24.0 适用性未确认；Play Store 崩溃报告条款不能无条件套给 GitHub 安装包 | 通讯录候选与 READ_CONTACTS 能力各有来源；清单权限不证明实际访问，也没有自动断言同义匹配 |
| [Telegram 服务政策](https://telegram.org/privacy) | 云消息服务政策；本轮 APK 身份未知 | 保留一条通讯录候选及其原句区间；没有生成 APK 与政策对照结果 |

代码线索包含 APK 哈希、DEX、caller、字节偏移、target、rule ID；政策线索包含文本哈希、精确码点区间和原句哈希。短引文只用于辨识位置，完整上下文留在受限原件。`summary.json` 的静态样例、结果引用和政策候选分别列出，结果没有引用的候选不是匹配依据。

NewPipe 和 K-9 的位置调用样例都来自 `androidx.appcompat...AutoTimeNightModeManager`。这是库代码中的潜在调用，不能解释为宿主运行时读取位置。全部报告使用 Androguard 4.1.3、规则 0.3.0、SDK 签名 1.0.0；JADX 不可用，保留字节码定位。此次 6 个 DEX 均处理完成，无 failed DEX，也未报告输出上限截断；有限规则、反射/动态加载/Native/跨过程分析等覆盖缺口仍在每份摘要中。

Telegram 的 261,439 字节首次下载在**受限容器**中得到 ZIP_INVALID，尚不能判断是下载、服务端内容还是其他原因，更不能称为“发现加固”。备用稳定入口返回 6,093 字节 HTML，登记为 `PAGE_ONLY_NOT_APK`，没有伪造第二个 scan job。确认包身份和复杂挑战分析均未完成。

## 固定版本与复核命令

扫描代码为 main `4cae1fd7e2ddb68345f389aa19535d2fc3db26ec`；本票只新增结果目录。独立构建的 worker 镜像 ID 为 `sha256:6400ad5a4f1bbc8136cf544795eae66c02d9eb813bc1190bf666fb7d5144a875`。4 次运行均经现有 `scan_isolated` 实际 inspect：network none、只读根目录、非 root、只读单 APK 输入、cap-drop ALL、no-new-privileges、1 GiB 内存及交换上限、1 CPU、PID 32；四次输入副本删除、容器清理均已验证，无清理错误。

账本校验复用 **PR #61 未合入候选** `bda03e5851b23e060a804b75d9392e7eb3d439ff`，当时仍为 CHANGES_REQUESTED。没有复制、修改其共享工具或建立第二套账本。只执行该提交的现有校验器：

```bash
git show bda03e5851b23e060a804b75d9392e7eb3d439ff:scripts/verify-run-ledger.py |
  uv run --project apps/api --locked --extra worker python - \
    --ledger samples/real-world/issue63-20261015/runs.csv \
    --manifest samples/real-world/issue63-20261015/candidates.csv
```

该格式检查不能证明真实扫描。候选校验器允许成功行没有报告哈希；本轮另核对 3 份实际报告哈希、引用闭合、全部原件哈希、政策原句区间与四份容器收据。扫描前下载失败没有 job，不能伪造 job 来满足格式；本轮备用 HTML 页仅放在获取记录中。工具缺口保留在交接，不在本票改其格式。

复跑时由受限索引取得原始 APK 与捕获包，先核对哈希；不要用今天的在线政策替换冻结输入后声称复现。以新的 job ID 调用现有 pipeline，并显式固定 worker，示意：

```python
from functools import partial
from privacytrace import pipeline
from privacytrace.isolated_scan import scan_isolated

pipeline.scan_isolated = partial(scan_isolated, image=FROZEN_IMAGE_ID)
result = pipeline.run(APK_PATH, CAPTURE_PATH, APP_NAME,
                      job_id=NEW_JOB_ID, timeout=180, store_dir=PRIVATE_JOB_DIR)
```

以上变量由组员的受限原件位置提供，不写入公开仓库。现有 `scripts/verify-real-samples.py` 也已在隔离 Docker 内对 `manifest.csv` 的三份输入执行，全部通过；不要在宿主运行它解析未知 APK。权威 `pwsh -NoProfile -File scripts/check.ps1` 已通过：API 617 passed / 20 skipped、Web 46 passed、Ruff、schema 零差异、类型检查与构建通过。20 个跳过项包含未在本地全量测试开启的 Docker 专项，不能表述为全量 Docker 回归；本目录的 4 次实际扫描独立记录。远端 CI 另绑定本票最终交付 SHA。

## 交接与剩余项

公开摘要可以复查选择、输入、job、输出哈希、代码/原句定位、限制和失败，原件索引可供具备权限的组员追溯。未执行新截图/浏览器流程，本票交付的是脱敏报告摘要。

后续需要取得可确认版本的复杂挑战 APK，再决定重试 Telegram 还是换官方来源；不得绕过现有隔离/输入限额。精确发布版政策、附件和语义复核仍待补充，不应把 UNKNOWN/PARTIAL 改成已确认。本票保持部分交付并保留 Issue open，PR 仅关联 #63，不使用 Closes；合并由用户决定。PR #61 的工具/格式修改仍归其原 owner，本票没有接管 #62 或用户测试。
