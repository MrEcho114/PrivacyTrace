# PT-907/2 · Issue #63 复杂挑战补充归档（2026-10-16）

本轮从 [Telegram 官方下载入口](https://telegram.org/android) 取得新 APK，并经现有受限 Docker pipeline 确认身份及生成报告。结合 [2026-10-15 归档](../issue63-20261015/README.md)，现有 **3 个代表性 App + 1 个复杂挑战 App**，其中历史保留 App 1 个、新增确认 App 3 个。样本执行与归档目标已达到；政策事实仍保持受限状态。当前执行记录见 [Issue #63](https://github.com/MrEcho114/PrivacyTrace/issues/63)，本结果不关闭父任务 #23。

## 实际覆盖

| 范围 | 确认 App | pipeline 尝试 | 可用报告（端到端 partial） | 失败 | 确认复杂挑战 App |
| --- | --- | --- | --- | --- | --- |
| 2026-10-15 历史归档 | 3，其中新增 2 | 4 | 3 | 1 | 0 |
| 本轮新增 | 1 | 1 | 1 | 0 | 1 |
| 累计 | 4，其中新增 3 | 5 | 4 | 1 | 1 |

本轮样本为 Telegram 网站分发版：`org.telegram.messenger.web`，版本 **13.0.2**，versionCode **71759**。输入为 **70,358,849 字节**，SHA-256 为 `a995a057e655be77907f9ceec52953edd213c05050102e2924f29bf903e91e64`。官方入口重定向到 `cdn4.telesco.pe`；公开获取记录删除了 CDN 临时 query，仅保留官方请求地址、最终主机/路径、响应信息、时点和字节哈希。没有执行发布签名指纹或可重复构建认证。

沿用 GKD（无障碍/截图）、NewPipe（媒体）、K-9 Mail（邮件）三个代表性输入，本轮补充复杂通信客户端。选择差异可从报告核对：4 个 DEX，以及通讯录、位置、相机/麦克风等能力和有限规则 API 线索，行为线索数高于既有各样本。这里的“代表性”仅指功能差异，不代表统计抽样；复杂挑战也不等于发现加固。未安装或动态运行 APK。

本轮 job 为 `issue63-telegram-20261016-01`，pipeline `SUCCEEDED`，耗时 **24.953 秒**。报告包含 **43 条证据、41 条行为线索、1 条政策候选、41 项规则结果**，规则结果全部为 `INSUFFICIENT_EVIDENCE`。`classes.dex` 至 `classes4.dex` 均处理完成，failed DEX 为空，未报告输出上限截断。DEX `COMPLETE` 仅描述 DEX 处理；JADX 不可用而保留字节码定位，规则覆盖、Native、反射、动态加载及跨过程分析局限仍在摘要中。

历史 Telegram 候选输入仍为 `ZIP_INVALID`，package/version UNKNOWN，保留原失败 job 与哈希。新输入没有替换其字节或倒改失败结论；此前备用 HTML 页也没有变成 scan job。历史 GKD 是保留 APK 的新扫描，不计为新增 App，也不是把历史报告回放计成新扫描。本轮旧原件复核同样不增加尝试数。

## 政策与引用

本轮重新获取 [Telegram 政策](https://telegram.org/privacy)，没有沿用昨日政策。保存原 HTML、确定性提取文本及捕获包，分别登记获取和捕获时点与 SHA-256。文本转换沿用 lxml 6.1.3：UTF-8 解码，删除 script/style/nav/footer/header，取首个 main/article/dev_page_content（无则用全文档），strip 非空文本节点，以 LF 连接并追加 LF；**本轮文本按 UTF-8/LF 保存**，不改变历史归档的 CRLF 口径。

只选取通讯录同步原句作为待复核候选。候选的 action/subject/polarity 均为 UNKNOWN，未调用外部模型。快照 `completeness=COMPLETE` 只表示捕获文本与哈希/区间一致；来源文档与抽取仍为 **PARTIAL**，复核为 **UNREVIEWED**，链接条款/附件为 **NOT_CHECKED**，精确 APK 版本适用性及地区为 **UNKNOWN**。网站分发包身份与官方服务政策来源均已登记，不据此宣称精确版本政策适用性已确认。

[summary.json](summary.json) 给出本轮**全部**静态定位、行为 ID、规则结果引用及政策证据定位；每个 API locator 含输入哈希、DEX、caller、字节偏移和 target。权限表示能力，invoke 表示静态潜在线索，均不证明运行时实际访问、收集或外传。原句偏移和原句哈希可按受限捕获包复核，未引用的候选不作为自动匹配依据。

[previous-reference-supplement.json](previous-reference-supplement.json) 追加旧公开摘要未选出的 **3 条 locator**：NewPipe `issue-4`、K-9 `issue-2`/`issue-5`。本轮从受限原报告逐字节复核 input、政策、报告、存储记录和隔离收据，原索引全部匹配；旧 12 项 issue→behavior/evidence/policy 引用闭合，仍为 `INSUFFICIENT_EVIDENCE`。这属于旧原件复核与报告回放，历史 2026-10-15 文件和报告哈希保持原样。

## 文件与复算

- [manifest.csv](manifest.csv) / [candidates.csv](candidates.csv)：本轮已确认的 1 个挑战样本，含 package/version、官方来源、时点、输入/政策哈希与状态。
- [runs.csv](runs.csv)：本轮唯一实际扫描，含 job、原报告哈希、partial 原因、计数和代码版本。
- [acquisitions.json](acquisitions.json)：本轮 APK 与政策的实际 HTTP 获取记录。
- [summary.json](summary.json)：分轮/累计计数、版本、完整引用白名单、覆盖、工具和脱敏隔离收据。
- [restricted-index.json](restricted-index.json)：组员按 `index_id` 向负责人索取原件；不含本机路径、APK、完整政策、完整报告或临时下载令牌。
- [verification.json](verification.json)：本轮实际验证、工具候选、日志哈希与公开文件哈希。

宿主 pipeline 固定 main `f54fdb26d5674dbf41a965716ddcca5e78af844b`；worker 镜像固定 `sha256:6400ad5a4f1bbc8136cf544795eae66c02d9eb813bc1190bf666fb7d5144a875`，来源为 `4cae1fd7e2ddb68345f389aa19535d2fc3db26ec`。两提交间的 `apps/api/src`、worker Dockerfile、Python 锁与依赖、rules 零差异，故沿用原固定镜像，不将旧镜像冒称为重新构建。运行时实际 inspect：network none、只读根目录、非 root、单 APK 只读挂载、cap-drop ALL、no-new-privileges、1 GiB 内存及交换上限、1 CPU、PID 32。输入副本删除与容器清理均已验证。

`report_sha256` 绑定私有 `JobStore.report(job_id)` 导出的完整对象：`json.dumps(model_dump(mode="json"), ensure_ascii=False, indent=2)` 后追加 LF，UTF-8/LF 编码。读取时 `delivery_mode=PERSISTED_REPLAY`，来源仍为 `REAL_SCAN`；它不是脱敏摘要哈希或语义哈希。原存储记录与隔离收据另有哈希。

账本复用 **PR #61 未合入固定候选** `210c941e64d2872a01d169069d65b28bf3b8728e`；仅运行原脚本，不接管共享格式或新增平行工具。已取得该 Git 对象后，分别复算新旧目录：

```bash
set -euo pipefail
for archive in issue63-20261015 issue63-20261016; do
  git show 210c941e64d2872a01d169069d65b28bf3b8728e:scripts/verify-run-ledger.py |
    uv run --project apps/api --locked --extra worker python - \
      --ledger samples/real-world/$archive/runs.csv \
      --manifest samples/real-world/$archive/candidates.csv
done
```

公开文件哈希可从本目录复算，不读取受限原件：

```bash
python - <<'PY'
import hashlib, json
from pathlib import Path
root = Path('samples/real-world/issue63-20261016')
v = json.loads((root / 'verification.json').read_text(encoding='utf-8'))
for name, expected in v['files_sha256'].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
print('public file hashes verified')
PY
```

取得受限原件后先按索引核对字节哈希，再使用新的 job ID 和冻结镜像调用现有 pipeline。不要把今天的政策替换冻结捕获包后称为复现；不要在宿主运行 `scripts/verify-real-samples.py` 解析 APK。该登记校验器本轮也在受限容器中执行。格式通过仅证明格式；实际扫描、字节哈希与引用复核分别记录。

## 验收与交接

#63 五项验收均有对应材料：选样差异与身份/来源登记、实际隔离运行账本、静态定位及政策缺证据边界、脱敏摘要与受限索引、分轮和累计实际数量。数据中的 partial、旧失败、未检查附件和适用性 UNKNOWN 均已保留，无须用政策已复核或挑战分析全覆盖来换取任务完成。

本轮仅新增此结果目录，未改历史归档、产品/扫描器、共享工具/格式、CI、受控场景或用户测试。未生成新截图或进行浏览器流程验收；交付形式为可复查的脱敏报告摘要。完整工程检查与绑定最终交付 SHA 的远端 CI 见 verification 和 PR；合并由用户决定。父任务 #23 及 #62/#64/#65 的验收不在本票完成结论内。
