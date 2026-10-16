# PT-904 / #18：完整受控离线包交付与核验

本任务沿用 #39/#47 已合入的 exporter、独立断网验证和六场景 runner。此前 Spec30 artifact 只有比较结果和证明文件，没有完整 `offline/` 包；本次让同一次运行的包与证明一起留存，不改变源码构建、算法、冻结输入或工具链。

## 当前状态与执行归属

2026-10-12，#17/#25 已 completed，#18 原生 open blocker 为 0。用户授权按 review 结论继续依赖链；MrEcho114 的唯一执行会话为 `01a12f34-0e5a-7aa3-86ca-960ae7005ec1`，当前记录见 [#18 执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/18#issuecomment-6125972199)。任务基线为 `686f2a2f186d75b2f07758a919af95e15e1b6b2c`，分支 `codex/pt-904-offline-delivery-20261012`。

2026-10-13 恢复时，#53/#42 已合入，main 为 `8c5262bd1c27a3143893376044205c03b02d6754`。本任务串行吸收新 main，保留原本地 commit `a8c6f94efed6b1ee4817e2b3798d6a50c4ed6b8d`，后续审查以该新 main 为固定点；新组合须重验，不复用合入前的本地检查。新增留存范围仍只有现有受控包，没有启用模型抽取或改变评测。

2026-10-13 08:22:12（香港时间），[#55](https://github.com/MrEcho114/PrivacyTrace/pull/55)已合并为 main `2e74276690a43e38c3b4b4ba44a0ba090e161e7a`；[Check #38326898243](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38326898243)、[Browser #38326897525](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38326897525)、[Spec30 #38326897496](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38326897496)均 success。本次仅核对这些运行元数据，未重新下载/复算该 main 的包，不把旧版 ZIP 摘要挪给它。#18 仍开放。

本次补充验证从上述 main 建立 `codex/pt-904-offline-evidence-20261013`，重放旧本地 `1b34a25` 的 driver/指南差异，并保留已合入的状态追踪。原分支和提交不重写。新实际候选 SHA、检查及后续补充 PR 指针在 #18 唯一当前记录维护；新的断网 CI、展开 proof/截图和完整归档尚未取得。

本文件区分**已验证的固定候选 SHA**与**后续待交付 SHA**，不把 CI success 等同于 #18 验收完成。以下 CI、归档与哈希事实以 2026-10-13 的 GitHub 运行元数据和 [#18 唯一当前执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/18#issuecomment-6125972199)为依据；本文档同步不代表重新下载归档或重做独立断网测试。旧 main 的 [Spec30 运行](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38259246772)其 artifact 不含完整包，不能用于本次完整交付。#19 的 PR #41、#46 前端和 #53 共享指南/模板仍归各自负责人。

### 已验证基准：`fb401cc24234d60ff94de772e0a40dd694d9e275`（历史固定候选）

| 证据 | 状态 / 版本绑定 |
| --- | --- |
| [Check #38278915899](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38278915899) | success；仅对应 `fb401cc` 的检查，不适用于后续提交 |
| [Browser Acceptance #38278914240](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38278914240) | success；仅对应 `fb401cc` |
| [Spec30 Integration #38278914343](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38278914343) | success；#18 执行记录确认 receipt 为 `fb401cc`、clean checkout、11 阶段 exit 0 |
| [Artifact #11760596470](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38278914343/artifacts/11760596470) | `spec30-integration-fb401cc24234d60ff94de772e0a40dd694d9e275`；GitHub ZIP SHA-256：`f87983f07d4fc0ab0ed6803bfbe49f5a14608bfc9647a3f17625c2a318d854d0`；2026-10-27 00:41:45（UTC+08:00）过期 |
| 下载后复核（#18 执行记录） | 原 ZIP 已在本地保存并复算，23 个归档文件；manifest SHA-256：`f31c4139f55744091d63931a3d3efed4b7471a572d2c131e3942b115394d6a5f`；六报告及来源摘要、文件/许可和受控内容排除项已核对 |
| 离线证明（#18 执行记录） | CI proof 支持 fresh `--network=none`、仅 `lo`、外联失败、六份 HTTP 报告、真实 Vue 六来源与零 page errors；`independent-offline.log` 同次留存 |

**剩余缺口：** #18 的独立 Spec 复查明确指出，历史 `fb401cc` 及 #55 已合入版本的断网浏览器 driver **尚未实测展开代码证据、政策引用句及政策全文**，不能用 HTTP 报告存在或联网浏览器通过代替。本补充候选虽增加了这些检查，仍须取得其实际 SHA 的独立断网结果。原始 ZIP 已本地留存不等于取得批准的长期内部归档位置；项目许可及正式分发授权仍待定，#18 保持开放。

**后续 SHA 边界：** 本地未推送的 `1b34a2530919afab7019477a485e283281e9534d` 是此次重放的来源，原提交继续保留。它**不是**上述成功 CI 的实际 checkout，也不是已验收交付；从新 main 重放后需使用新的实际候选 SHA。未来 PR head 变化（包括文档修复提交）后，应重新取对应 CI 与包摘要，重验受影响的断网浏览器证明和归档。不得把 `fb401cc` 或 main `2e742766` 的绿灯、ZIP、manifest 直接迁移到补充候选。

## 下载、断网与启动

1. 选择目标交付 SHA 的成功 `Spec30 Integration` 运行，核对 `head_sha`、`integration-receipt.json.commit_sha` 和工程/浏览器 CI 的实际版本；记录 artifact ID、GitHub 元数据中的 ZIP SHA-256 与有效期。下载 artifact 后实算 ZIP SHA-256，与元数据比较。ZIP 包含证据目录和 `offline/`；`offline/` 才是运行包。
2. 在联网准备阶段预装 Python 3.11+ 和本地浏览器，再把完整 `offline/` 目录复制到独立环境。查看下面的许可边界及包内 `DISTRIBUTION.txt`。不需要安装 Node、npm、API 服务、Docker、Playwright、模型 SDK 或模型密钥来回放。
3. 真正断网后在 `offline/` 内执行 `python -B viewer.py --port 8765`，浏览器打开 `http://127.0.0.1:8765`。服务启动前校验文件集合和 SHA-256；新增、遗漏或篡改文件会拒绝启动。证明文件放在 `offline/` 外，不向运行包添加临时文件或缓存。
4. 经 HTTP 查看 `/api/v1/health`、`/api/v1/jobs` 和六份报告；在浏览器切换六个来源并查看代码位置、政策原文、生成时点和 `OFFLINE REPLAY` 标识。三方案表在 `/comparison.html`，原始数据在 `offline/comparison.json`。POST 返回 405，未知报告返回 404。
5. 留存所用包/manifest 哈希、运行环境、断网方式、启动日志、HTTP/浏览器结果及所有失败。开发机启动和锁文件存在不替代独立断网验收。

交付只有既有受控报告回放。实时扫描任意 APK、源码编译、安装 Android SDK 或调用外部模型不包含在这份包中。报告原生成时点在 `tools.analysis_generated_at`，包生成时点在 `tools.offline_package_built_at` 及 manifest，原 APK/特征/政策摘要保留在报告和 comparison 中；离线查看不改写这些来源。

## 包、证明与交付 SHA 的绑定

`integration-receipt.json` 记录实际 checkout SHA、dirty 状态、每阶段退出码和证据摘要；其中的 `offline-proof/offline-proof.json` 摘要绑定断网证明。证明中的 `package_manifest_sha256` 绑定运行包的 manifest；manifest 的文件清单逐个绑定 `offline/` 中其余文件。artifact ZIP 的 GitHub 摘要绑定整个下载归档，包括同次运行的 `independent-offline.log`，不能把 ZIP 哈希与 manifest 哈希混用。

在 artifact 解压根目录执行以下标准库核对，命令末尾参数替换为实际交付 SHA。此核对只验证已留存证据的关联与文件完整性，实际断网结论仍来自同 SHA 的独立环境运行及其日志。

```bash
python - ACTUAL_DELIVERY_SHA <<'PY'
import hashlib, json, runpy, sys
from pathlib import Path

root = Path.cwd()
def load(name):
    return json.loads((root / name).read_bytes())
def sha(name):
    return hashlib.sha256((root / name).read_bytes()).hexdigest()

receipt = load('integration-receipt.json')
assert receipt['commit_sha'] == sys.argv[1]
assert receipt['passed'] and not receipt['dirty_checkout']
assert len(receipt['stages']) == 11
assert all(stage['exit_code'] == 0 for stage in receipt['stages'])
for name, expected in receipt['evidence_sha256'].items():
    assert sha(name) == expected, name
proof = load('offline-proof/offline-proof.json')
assert proof['passed'] and proof['interfaces'] == ['lo']
assert proof['external_network_blocked'] and proof['six_reports_http']
assert proof['real_browser_vue_loaded'] and proof['six_sources']
assert proof['code_evidence_expanded'] and proof['policy_quote_expanded']
assert proof['full_policy_expanded'] and proof['evidence_drilldown_scenario'] == 'C02'
assert proof['page_errors'] == []
assert sha('offline-proof/offline-dom.html') == proof['dom_sha256']
assert sha('offline/manifest.json') == proof['package_manifest_sha256']
assert load('offline/comparison.json') == load('evaluation/comparison.json')
runpy.run_path('offline/viewer.py')['verify']((root / 'offline').resolve())
print('Package, proof and delivery SHA matched:', sys.argv[1])
PY
```

CI 复用 `scripts/validate-spec30.py` 的现有 11 阶段，在新容器中 `--network=none`、只读挂载包/验证脚本/浏览器及模块，没有仓库挂载或模型密钥。`scripts/verify-offline-container.py` 检查仅 `lo`、外部连接失败、六份 HTTP 报告及真实 Vue 浏览器来源切换；driver 还在 C02 展开实际代码证据，核对完整 locator/descriptor、引用句的 Unicode 位置与高亮、政策全文与原报告文本，并保存 `offline-evidence-c02.png`。证明须包含上述三个展开字段和 C02 标识；旧 driver 仅来源切换的成功记录不能替代这些观察。

输出保留 DOM、浏览器版本/可执行文件摘要、测试镜像 ID、验证脚本和驱动摘要。`independent-offline.log` 保留该阶段的 stdout/stderr，包括断网前镜像/apt 准备及随后断网容器的 viewer 启动、HTTP 请求、证明和失败信息；准备过程不称断网。日志不存在时该阶段尚未执行，不能补造成功记录。浏览器依赖在断网前准备，不称无预装条件；这些新增展开检查仍须以实际交付 SHA 的 CI 结果验收。

`if: always()` 继续保留失败运行的已产生文件。包存在或 artifact 上传成功不表示验收通过；任一阶段失败、proof 缺失、SHA/hash 不一致或 dirty checkout 都保留为失败/未完成。14 天保存期届满前应把经过哈希核对的归档保存在批准的内部交付位置；不以过期下载链接充当长久交付。

## 内容与许可清单

| 内容/依赖 | 包内形态或预置条件 | 许可及使用边界 |
| --- | --- | --- |
| PrivacyTrace viewer、前端产物、taxonomy、comparison | 运行代码与静态产物；manifest 列全量文件和 SHA-256 | 项目许可证尚未决定；仅内部核验，未经授权不公开分发或正式提交参赛材料 |
| C01–C06 自建报告及配对政策 | 六份受控报告；政策原文属于自建材料，保留 APK/特征/政策摘要及原生成时点 | 本任务允许的自建核验材料；不包含真实 GKD APK、完整真实政策或真实作业报告 |
| Vue 3.5.43（锁定依赖） | 前端 JS 中的运行时；`Vue-LICENSE` 随包 | MIT，保留随包版权及许可文本 |
| Vite 7.3.6（锁定构建依赖） | 前端产物中的 preload helper；不分发构建工具或 node_modules；`Vite-LICENSE` 随包 | MIT 及该文件包含的第三方声明，保留完整许可文本 |
| Python 3.11+ | 使用者预装，不把解释器加入包 | 预置环境按 Python/PSF 及发行版许可安装；包内 viewer 仅使用标准库 |
| 本地浏览器 | 使用者预装，不把浏览器加入运行包 | 使用者所选发行版许可；CI 测试浏览器的版本/摘要另见 proof |
| Node、Playwright 1.62.1、Chromium 及测试镜像系统库 | 只在 CI 准备/独立测试环境使用；不在 `offline/` 分发 | 不作为包内离线依赖或捆绑素材；CI 证明不授权再分发这些测试环境 |

最终归档取得后逐项复核许可文件、manifest、报告来源及前端资产。未来 #46 若引入字体/素材或依赖版本变化，必须重新清点许可并重验包，不能继承这里的当前清单。项目许可和公开分发授权待团队决定，不在本任务擅自选择许可证。

exporter 只接受六个成功的自建受控场景，检查 APK/政策/特征与冻结摘要及三方案 18 行对应；不接纳真实 App 报告。输出去除本地用户备注，只保留工具字段白名单。CI 新增留存仅为现有受控 `offline/` 和独立断网阶段的 `independent-offline.log`，其他证据路径沿用；不扩大到 evaluation jobs、APK、数据库、政策抓取或扫描原始日志。拿到完整归档后仍须核对没有密钥、用户私人路径、数据库或未经授权材料；静态 allowlist 审查不冒充已完成归档检查。

## 验收追踪：已完成项与待完成项（2026-10-13）

本清单依据 [#18 当前执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/18#issuecomment-6125972199)，其“已完成”只适用于固定候选 `fb401cc`，不自动覆盖后来新增的提交：

- [x] `fb401cc` 的 Check / Browser Acceptance / Spec30 Integration 三项 GitHub CI success，记录运行 ID 与实际 SHA。
- [x] 该 SHA 的 artifact 已取得；#18 执行记录记载 ZIP 与 manifest 摘要复算、收据/证明绑定、六份受控报告、许可和归档排除项核对。此处转录结果，并非本次修复重新运行。
- [x] 该 SHA 的离线容器 proof 与阶段日志已有留存（断网预置前阶段不应算作断网执行）。
- [ ] **补齐独立断网浏览器的代码证据、引用句高亮与政策全文展开实测及对应 proof/截图**；已取得的历史断网 proof 未覆盖该交互，补充实现仍待其实际 SHA 的独立结果。
- [ ] 若 driver、指南、PR head 或打包产物发生变化：用新 SHA 重新执行适用 CI，下载新的 artifact，复算 ZIP / manifest / receipt / proof 哈希并核验许可和排除项；旧 SHA 成功不能替代新版本验收。
- [ ] 将经校验的版本绑定归档保存在批准的内部长期位置；14 天 GitHub artifact 链接和本地暂存不能替代该交付记录。
- [ ] 记录项目许可与公开分发授权决定。完成相关验收并经负责人确认前，#18 保持开放；#55 已合并为部分交付，补充验证候选需单独审阅，不由旧 PR 的合并推出工单完成，也不提前合并或关闭后续候选。

#25 报告仍沿用原评测 SHA `323780c9a77d7de2bb1857b1b67b4f05fd94a525` 的 18 行。新 CI 的 comparison 是当前包来源验证，不替换原正式实验或填补其缺失原文件摘要。GKD 历史案例不打包，不称本轮重扫。这里不验收 #19 材料/演示或 #30 整体交付，也不授权合并、发布、部署。
