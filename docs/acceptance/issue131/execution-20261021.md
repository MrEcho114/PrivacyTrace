# 验收 C 执行记录：手机模型直连、执行器与 Key 去向

状态：**H03、H06、H09、H12 本机案例级 PASSED；N11 在已观察传输面 PASSED，分析服务 TLS 段未解密；原执行器覆盖缺陷已复现并修复。** 本记录只覆盖 #131 的 C 边界，不证明父票 #128 全矩阵通过，也不替代合并、部署或真机结论。

## 1. 范围

- 主责案例：H03、H06、H09、H12、N11（#131）。
- 入口：[移动验收执行器](../../../deploy/acceptance/mobile/README.md)、[C 运行说明](README.md)。
- 未执行：其他子票案例、父票矩阵汇总、真实物理设备、公网端点、外部模型质量、商店审核、合并与部署。

## 2. 候选与身份

| 项目 | 实际值 |
| --- | --- |
| 源码 | `ffadeb06af70072b5ee2d931ee565e5b7e546acd` |
| 客户端 APK（debug，仅 localhost 测试 CA） | `8bb257dfd3a63d295b858decba7ba0dcee44d6e20c063c01feb1813f4f3fddc8` |
| C fixture base | `07a6d14f0bfc3891e74fa585f93808ba6626967eebc20dd53c884ef33265f96e` |
| C fixture feature split | `e48bbeefcd84a2930949683ac9fb4cf0948663f180c8dee170c3f66ab7a7d7eb` |
| 本机测试 CA SHA-256 指纹 | `2D:43:3E:B9:FC:2B:B7:C6:E5:59:C4:1B:64:6C:93:31:44:E1:95:03:9D:3E:42:9C:09:8D:68:96:E2:85:D0:A0` |
| API 镜像 | `sha256:30825e3640138465446fdd1d05dde21529ab63db98f587387142e2b1ed3f6aa2` |
| Web 镜像 | `sha256:22a340efbcde68ab1b46fad3eec8a7f49658c9dba88cdf29b93207e4fefd26c5` |
| Runner 镜像 | `sha256:473975aeb2a77f115ec5d5c2b2ffc6b693add882a3001231ad7c6ec13c830c24` |
| 扫描镜像 | `sha256:1a36604312f9d1e6184dd1ab0e4b49fd6c0674842f478d79f8f6b54541f94354` |
| 实例 I | `a74aaab9-8f94-452b-9c89-a67163f5132a`，实验室 `pt81-9da08136acca`，宿主转发 `28444` → netns `60886` |
| 实例 J | `e4a864bc-d549-45af-98c3-43d524656bb6`，实验室 `pt81-0b0a74b989cc`，宿主转发 `28446` → netns `59002` |
| 模拟器 | MuMu 独立实例 index 5，Android 15 / API 35 / x86_64，`adb 127.0.0.1:16544`，竖屏 `1080x1920` |
| 受控模型响应 | `91a4bd6655096d2000ae8a1be0c9c07697415b68f8ee81cf95eead9c0d93581e` |
| 一次性 Key（手机 A/B） | 两个不同的随机测试值，仅私存；公开记录不保留 Key 或可复用的指纹 |

I/J 使用不同的 instance ID、端口、Compose 项目、数据卷和材料目录。手机侧仍以 `https://localhost:28443` 作为 origin；切换实例时只改 `adb reverse` 的宿主目标，客户端状态在每个案例前清空。

## 3. 案例状态与 H 结果

| 案例 | 状态 |
| --- | --- |
| H03 | PASSED |
| H06 | PASSED |
| H09 | PASSED |
| H12 | PASSED |
| N11 | PASSED（已观察面；分析服务 TLS 未解密） |

没有 skip、豁免或“主链路通过”折算；N11 的未观察 TLS 段在结论中单列，不升级为全路径结论。所有案例均使用实际 Android 客户端、真实上传/队列/Runner 扫描和报告下钻；模型请求由本机受控 HTTPS 接收器观察，服务端候选抽取使用独立的受控模型端点。

| 案例 | 输入 / 实例 | job | 政策对照 | 模型原句在报告 | 扫描范围 | 删除 | 结果 JSON SHA256 | 报告文本 SHA256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H03 | 单 APK / I | SUCCEEDED | PRESENT | 是 | `base:classes.dex` | DELETED | `a1f2089b6136edaa9cab39a3297c9ada89d751de66381f5f734db199dff09372` | `bcce57b7f8ae245c92eb2cf1b9e8a51f5a62514a79c892de61486da62ade23aa` |
| H06 | base＋全部已安装 splits / I | SUCCEEDED | PRESENT | 是 | `base:classes.dex`、`split:fixture_feature:classes.dex` | DELETED | `16d9a89c86672ab003efa3e9aceaf42c5a4b378f1fae36bf501c626b0e1556fe` | `68d50e91e2aa075f737545b68fe109376ac7b2bab8bb7f77eff24183038e8bb4` |
| H09 | 单 APK / J | SUCCEEDED | PRESENT | 是 | `base:classes.dex` | DELETED | `67f3abbd7e9b4f27f220d8b27a08b16c30d59d2a2809555ab5d239fa2cd62a3a` | `824f0603ceab95df47955aeb1a1d884134e43aecd5d99aa43abeb96a6ae7363c` |
| H12 | base＋全部已安装 splits / J | SUCCEEDED | PRESENT | 是 | `base:classes.dex`、`split:fixture_feature:classes.dex` | DELETED | `ca0482af826fcf8dfb68834d7571f9846ab52372ebdfcf293e9caa27037ff1df` | `7ccacf5413431d33e56cf78a8e1bf81de44c5f88edcb11f84c6cb3fefac5d986` |

补充证据：

- H12 的 `pm path`/`dumpsys` 包集合快照显示 `splits=[base, fixture_feature]`，SHA256 `edb303839912f9f7d2e089bd199c78e6d947f7b950ed4ff53d17373e272042d7`；H09 的单包快照 SHA256 `cbfa8021afc46e82f82db0e07c50d823a293ef5d58f05d1049309a534e35e401`。
- H03/H06 首次运行时执行器尚未加入包集合快照；其报告正文的“已扫描 base…”/“已扫描 base、split:fixture_feature…”行作为单包/splits 的扫描证据。H09/H12 已用加入快照后的版本重跑，上表取重跑结果；首次 H09/H12 也已得到 SUCCEEDED/PRESENT，旧文件保留不覆盖。
- 四个案例的模型结果均为 363 字符、SHA256 `5fb8c1a95f23381bb6cdb51c63adde9b831f1cf335a23b613f9556a1a57364dc`；候选页出现“受控模型政策样本”，报告正文出现原句“我们访问精确位置。”及证据下钻，静态 assist 标题“受控政策样本”未出现。
- 报告对照行为“精确位置｜有政策快照 · 对应条款未确认｜证据不足 · 待复核”，展开证据后可见 `web-claim-…`、原句位置 `[25,34)` 和来源全文。
- 实例侧：I 数据库保留 2 个 job（`32be23cb…`、`a4c138da…`），J 保留 2 个 job（`c91e0624…`、`e95335ba…`）；两实例最终 drafts 均为 0。

## 4. 原缺陷复现（保留失败）

旧执行器在模型收集后仍调用 `importAssist(cdp, POLICY_JSON)`。用同一客户端/接收器执行旧序列，得到：

| 观察 | 值 |
| --- | --- |
| 模型结果 textarea | 363 字符，SHA256 `5fb8c1a95f23381bb6cdb51c63adde9b831f1cf335a23b613f9556a1a57364dc` |
| 覆盖后 textarea | 355 字符，SHA256 `631972f71e33c811242029b189a8d688a2a57f70cd0e77016aee0d6c55b67b0f` |
| `textarea_replaced` | `true` |
| 覆盖后页面含模型标题 / assist 标题 | `false` / `true` |
| 复现结果 SHA256 | `ff0506bac47914097a2d279d5ae65bae6d37251efab0483e938c42787158b016` |

分类：**执行器缺陷，不是产品行为错误**。模型请求本身成功到接收器；失败发生在执行器随后写入静态 assist 文本并导入。

## 5. 修复与回归

- `client-case.cjs`：模型模式改为 `applyPolicy` → 配置/收集 → `importModelResult`，只读取并导入 textarea 中的模型结果；不再在模型模式调用 `importAssist`。
- `modelExpect` 断言：模型来源标题进入任务 UI、报告有“隐私声明对照”、证据下钻可展开、模型原句在报告中、assist 标题不得出现。
- 执行器附带修复：模型面板关闭时先展开；密码框不回读伪造；等待按钮可用后再点击；报告页等待“隐私声明对照”而非泛化的“政策”；展开“查看 N 条证据”后再截取报告。
- 回归：`node --test deploy/acceptance/mobile/client-case.test.cjs`，3 项通过（模型模式只导入一次、assist 模式仍导入静态 payload、`importModelResult` 不覆写 textarea）。
- 仓库权威入口 `scripts/check.sh`（由 `scripts/check.ps1` 委托）通过：`1518 passed, 200 skipped`；Web 套件 `111 passed`；文档/契约检查通过。Docker 分支按入口记录的实际执行/skip 保留，未把 skip 计为通过。

## 6. N11（已观察面）

手机侧 A/B 两个一次性端点：

| 项 | A | B |
| --- | --- | --- |
| 端点 | `https://localhost:19543/v1/chat/completions` | `https://localhost:19545/v1/chat/completions` |
| Key | A 专用一次性测试值 | B 专用一次性测试值 |
| 接收 | A 端点收到 A Key | B 端点收到 B Key |
| 切换 | 切换后 A 端点无新请求 | B 端点未收到 A Key |

外部观察检查全部为真：A/B 端点各自收到预期 Key；B 未收到旧 Key；切换后 A 静默；两次模型响应均为 collector/1；请求体 10036 字节，无 APK `PK` 魔数、无 Bearer、无任务 token、无 `base.json`/split 名称，仅含允许的包名线索。

分析服务负对照（明文可观察面）：I/J API 容器环境、容器日志、材料卷、数据库中的 A/B Key 匹配数均为 0；两个实例的服务端抽取请求 `Authorization` 出现次数均为 0。N11 结果 SHA256 `bfd1c6fb20694e54804922b7ce4fc5357c5a5758a83f6125dba496cf5a225fa6`，负对照输出 SHA256 `6d2a2c78115802981da7cb7eeda5eba2d1f26c754549945e5a4d26992884e27e`，清理回执 SHA256 `6070d1e06abfe2d6eef1c21e72e45ee9c12026be903a06bf4b479032ca209b0a`。

边界：手机到分析服务的 HTTPS 未解密；本项只证明上述明文环境/日志/材料/数据库/服务端抽取请求面，**不能写成全路径无泄露**。模型接收器只证明协议、Key 去向和输入最小化，不证明外部模型质量或联网检索能力。

## 7. 结论与剩余边界

- C 工单的四个模型 H 案例已在本机实际客户端上得到 `SUCCEEDED`、非空政策对照、模型原句和证据下钻，删除均已确认；N11 的 Key 目的地、切换和输入最小化有外部接收器观察及服务端明文面负对照。
- 未覆盖：物理真机/OEM/其他 ABI、公网官方服务、外部真实模型质量、商店审核、生产部署、N11 分析服务 TLS 解密。模型响应为受控固定文本，受控响应不升级为外部能力。
- 本记录不关闭 #131 或 #128，不替代父票最终矩阵汇总；合并与发布需另行授权。

## 8. 证据位置

原始证据（客户端结果 JSON、报告正文、截图、接收器请求日志、服务端抽取日志、Key/证书、实验室状态）保存在本机 Git 忽略目录，未提交仓库。公开目录只保留本记录中的脱敏结果、身份和 SHA256；复核时需从对应运行目录读回文件并核对哈希。
