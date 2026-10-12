# PT-904 / #18：完整受控离线包交付与核验

本任务沿用 #39/#47 已合入的 exporter、独立断网验证和六场景 runner。此前 Spec30 artifact 只有比较结果和证明文件，没有完整 `offline/` 包；本次让同一次运行的包与证明一起留存，不改变源码构建、算法、冻结输入或工具链。

## 当前状态与执行归属

2026-10-12，#17/#25 已 completed，#18 原生 open blocker 为 0。用户授权按 review 结论继续依赖链；MrEcho114 的唯一执行会话为 `01a12f34-0e5a-7aa3-86ca-960ae7005ec1`，当前记录见 [#18 执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/18#issuecomment-6125972199)。任务基线为 `686f2a2f186d75b2f07758a919af95e15e1b6b2c`，分支 `codex/pt-904-offline-delivery-20261012`。

2026-10-13 恢复时，#53/#42 已合入，main 为 `8c5262bd1c27a3143893376044205c03b02d6754`。本任务串行吸收新 main，保留原本地 commit `a8c6f94efed6b1ee4817e2b3798d6a50c4ed6b8d`，后续审查以该新 main 为固定点；新组合须重验，不复用合入前的本地检查。新增留存范围仍只有现有受控包，没有启用模型抽取或改变评测。

本文件记录交付方式与验收缺口，不是离线验收完成结论。新交付提交的 CI、完整包、artifact/manifest 哈希及独立断网证据必须取得后写入该工单唯一当前记录；不得借用旧 SHA 的成功结果。旧 main 的 [Spec30 运行](https://github.com/MrEcho114/PrivacyTrace/actions/runs/38259246772)虽通过断网验证，其 artifact 不含完整包，不能用于本次完整交付。#19 的 PR #41、#46 前端和 #53 共享指南/模板仍归各自负责人。

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
assert proof['page_errors'] == []
assert sha('offline-proof/offline-dom.html') == proof['dom_sha256']
assert sha('offline/manifest.json') == proof['package_manifest_sha256']
assert load('offline/comparison.json') == load('evaluation/comparison.json')
runpy.run_path('offline/viewer.py')['verify']((root / 'offline').resolve())
print('Package, proof and delivery SHA matched:', sys.argv[1])
PY
```

CI 复用 `scripts/validate-spec30.py` 的现有 11 阶段，在新容器中 `--network=none`、只读挂载包/验证脚本/浏览器及模块，没有仓库挂载或模型密钥。`scripts/verify-offline-container.py` 实测仅 `lo`、外部连接失败、六份 HTTP 报告及真实 Vue 浏览器来源切换；输出 DOM、浏览器版本/可执行文件摘要、测试镜像 ID、验证脚本和驱动摘要。`independent-offline.log` 保留该阶段的 stdout/stderr，包括 viewer 启动、HTTP 请求记录、证明输出及失败信息；其不存在时该阶段尚未执行，不能补造成功日志。浏览器依赖在断网前准备，不称无预装条件。

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

## 尚待当前交付版本完成的验收

- 完整包取得后核对代码/前端产物、六份报告、说明、许可和精确 manifest；记录实际 ZIP 与 manifest SHA-256。
- 取得新实际 SHA 的工程/浏览器/Spec30 CI，核对独立断网证明、环境、日志和失败留存，再实算上面的包/证明绑定链。
- 检查实际归档的排除项与许可，保存版本绑定的内部交付记录。全部满足前 #18 保持开放；包或冻结 SHA 变化后重验受影响路径。

#25 报告仍沿用原评测 SHA `323780c9a77d7de2bb1857b1b67b4f05fd94a525` 的 18 行。新 CI 的 comparison 是当前包来源验证，不替换原正式实验或填补其缺失原文件摘要。GKD 历史案例不打包，不称本轮重扫。这里不验收 #19 材料/演示或 #30 整体交付，也不授权合并、发布、部署。
