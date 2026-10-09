> 历史验证/流程记录：其中 A/B 与 PENDING_HUMAN_AB 门槛已于 2026-10-09 撤销。当前接受状态见 [S1 接受决定](s1-acceptance-20261009.md)，不倒改当时结果或固定 SHA。

# S1：PR #27 与 #28 整合判断和验证（2026-10-09）

## 来源与交付范围

- 主线基线：`main` 的 `d4a685d65c9b57e765910b44d9ea9a0e05b1744c`（S0 PR #26 已合并）。
- PR #27：`b13b9548c49994de20ddf81e8c5e97b2dd71b08f`。
- PR #28：`15a090749c92c210f62a860ff16a3378b6dbe5e8`，共同祖先 `16223ce09b9a68f50b5a07182c3f59274010c09e`。
- 新分支 `codex/s1-integrated` 面向 `main`，保留两条来源历史，在独立受管工作树整合。原工作区的未跟踪研究、规划和配置文件未带入；不改写或推送原 PR 分支。
- 此次创建的是新的整合 Draft PR，不自动关闭、批准或合并 #27/#28。交付 SHA、实际 PR 链接和该 SHA 的 CI 在新 PR 描述/comment 中绑定，避免文档自身提交哈希循环。

## 取舍：不是一方覆盖另一方

| 改动 | 整合判断 |
|---|---|
| APK 复制/退出清理、累计配额、主错误与清理错误 | 保留 #27 最新实现，不回退到 #28 的旧生命周期；默认 DELETE_ON_EXIT、1 GiB、复制前跨进程预留，保留有界收据 |
| DEX COMPLETE 与行为识别边界、旧报告默认值 | 保留 #27 契约及 UI；有限规则不等于全面检测，原有存储证据不重写 |
| Manifest 直接子节点、android:name namespace、名称清洗、版本名截断、框架 URI 常量 | 保留 #27；不退回 Androguard 的宽泛权限 helper，也不移除已有 URI 回归 |
| 逐声明 SDK 条件 | 纳入 #28，按 `(name, tag, maxSdkVersion)` 去重，清单按 name 去重；locator/excerpt 保留 tag、SDK-23 下界及声明上界，仍是 CAPABILITY / STATIC_POTENTIAL，而非实际访问或设备 SDK 适用性裁决 |
| versionCode | 纳入 #28 的十进制前导零兼容，并补本轮 Review 范围限制与非法位模式回归，详见下节 |
| 原子作业登记 | 两方锁内实现等价，统一使用 #27 `create_if_absent`；#28 四进程竞争、已有/损坏记录保护和扫描前拒绝测试对齐此接口，不保留两个重复 API |
| 页面来源 | 保留 #27 的类型化 ReportSource 和显式命名空间；适配 #28 的真实 demo 作业、示例切换、备注和取消组件回归，不退回隐式 `slice(4)` 分派 |
| 前端测试/CI/检查脚本 | 同一 test 命令同时运行 `.test.ts` 与 `.test.cjs`，合并后 11 项，避免 JSON 同名 test 键或只跑其中一组；CI 保留一个测试步骤，check.ps1 也调用该入口 |
| 文档和旧 receipts | 保留 #28 的 10/05 报告/日志/截图和绑定原提交的 receipts，添加历史提示；README/backlog/M1/validation 更新当前索引，不将旧测试统计移作本轮结果 |

新扫描的 MANIFEST 定位符增加 tag/SDK 条件，因此对应 evidence/behavior ID 会按新定位符生成；同名双声明不合并成一个无条件能力。已有作业、政策版本和历史真实样本报告不迁移、不补造，也不自动重跑。分类和 API 映射规则本轮未变化。

## #28 Review 5458496992 的处理

### P2：versionCode 范围

本项目当前只支持普通 `versionCode` 的非负有符号 32 位范围 **0..2147483647**，不是 `versionCodeMajor` 或 64 位 longVersionCode；0 保留原有非负解析兼容性，不代表推荐发布版本。字符串十进制按 base10，`0x` 按 base16；AXML `TYPE_INT_HEX` 的 `0x80000000`/`0xffffffff` 不当作巨大正版本号，返回 `MANIFEST_INVALID`，不得继续生成行为事实。同步修正旧 challenger 测试中接受 unsigned/64 位大值的假设，保留对应拒绝回归。

依据：[AOSP Android 10 PackageParser](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android10-release/core/java/android/content/pm/PackageParser.java#1952) 将普通 versionCode 读入 int，另处理 versionCodeMajor；[Android 版本文档](https://developer.android.com/studio/publish/versioning) 的正整数建议及 Google Play 2100000000 上限是发布口径，不把 Play 上限当成此离线分析器的 Android 字段上限。非负限制是本项目支持范围，不声称框架会拒绝所有超出该支持范围的 APK。

### P2：同名双声明

CLI 以同一 Manifest 的 CAMERA 普通声明（maxSdk=22）与 SDK-23 声明（minSdk=23/maxSdk=28）验证：权限清单只有一个 CAMERA，两条独立 MANIFEST evidence 与 CAPABILITY behavior，ID 不碰撞、互相引用准确，tag/上下界均保留，purpose 仍 UNKNOWN。

### 两项非阻塞建议

- 来源分派已采用 #27 类型化来源，不使用 #28 的裸 `slice(4)`；`parseSource` 对旧原始 job ID 的兼容入口未在本轮删除。未知/新增来源类型的严格校验与异常矩阵进入 S2，不声称已覆盖未来来源协议。
- 强制退出后非终态 Job 的识别/恢复进入 S2；原子登记不等于实现重启恢复调度器。

## 本轮验证

- 约定入口：APK 扫描 CLI、作业/复核 HTTP API、实际浏览器链路。二进制 AXML/DEX 是自行构造的可信 fixture，不在宿主解析未知真实 APK。
- 测试先复现：#28 独有权限条件/前导零在 #27 实现上 4 项失败；版本越界回归 4 failed / 4 passed；权限条件与同名双声明 4 failed / 1 passed。修复后 Manifest/CLI 定向套件 **93 passed**。
- 前端合并测试 **11 passed / 0 skipped**；Ruff、契约导出零差异、typecheck 与生产构建通过。
- 从最终整合源码重建 `privacytrace-worker:s1` 成功，`docker image inspect .Id`：`sha256:a6b92107f2cfbb4086e894998bdeeac1fe5435601dbeb65cfe792ac58ab44666`。
- Windows / Python 3.12.13，设置 `PRIVACYTRACE_DOCKER_TESTS=1`、`PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1` 后执行 `./apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests -q -p no:cacheprovider`：**306 passed / 0 skipped，exit 0，92.26 秒**。一条既有 Starlette TestClient 弃用警告。包含实际 Docker 与四独立进程竞争回归。
- 实际 Chromium + CLI 构造报告 + HTTP API + Vue 页面：无命中/缺主 DEX/坏次 DEX/split 四类覆盖展示（含旧报告默认值）、真实 `demo` 作业与示例切换、备注保存后刷新展示、非终态作业取消及原始 ID 请求路径均通过，**0 page errors**。浏览器 console 有一条资源 404 提示，未捕获到失败的 API response；不将此记录写成 console 零错误。截图与受控数据仅留本地 `tmp/`。
- 本轮没有使用原 PR 的 278/215 项测试或旧 CI 代替。新 PR 的 api/web/isolated-worker 必须按实际交付 SHA 完成远程验证；远程统计与本地统计分别列出，不把重叠测试相加。

## 未完成的验收与安全前提

状态仍为 **Draft / PENDING_HUMAN_AB**。Issue #15 需两位不同成员按最终实现/样本/政策版本和哈希逐条留 comment；工具代发、CI 或页面自动化备注不算人类复核。此次未重跑真实 GKD，不关闭阶段工单、不合并 PR。

APK 历史副本、崩溃/拒删残留不自动处理；Windows 私有目录 ACL 是部署前提。具体配置与清理边界见 [生命周期策略](s1-runtime-retention.md)。APK、政策全文、私有收据、临时截图/日志均不提交。

## 10/09 创建 PR 后的真实样本补充核验

上文“此次未重跑真实 GKD”描述 PR29 创建时的验证范围；随后已在整合实现 `bb342843b50dc45aec3df111a51537998c81a632` 上两次重跑同一真实 GKD APK，完成真实 HTTP/浏览器定位、备注写入与 API 进程重启后的报告留存。两次稳定语义相等，3 项仍为 INSUFFICIENT_EVIDENCE。详见 [新的版本绑定记录](s1-pr29-real-sample-verification-20261009.md) 与 [脱敏 JSON](s1-pr29-real-verification-20261009.json)。历史样本和 receipts 不重写；A/B comment 仍未收到，阶段不自动完成。
