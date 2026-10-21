# 材料、设备与网络准备

本清单完成来源和缺口盘点。当前采用[本机环境要求](local-environment.md)：专用模拟器、控制面/扫描面虚拟化环境和两个本机 HTTPS 实例。来源存在不等于产物已安装或业务已通过。所有材料仅用于内部核验；未经独立许可不公开分发 APK、政策或报告包。

## 可复用来源与待补材料

| 材料 ID | 可核对来源 | 当前可用性／下一步 |
| --- | --- | --- |
| M01 普通分析 APK | [controlled 源码、工具锁和构建说明](../../../benchmarks/controlled/README.md)；C01 权限无调用、C02 精确声明、C06 部分政策 | 源码与锁已在 main，APK 为分析用未签名产物。可按既有离线容器构建复建；本轮未构建，不能直接当手机已安装样本 |
| M02 自建政策与候选 | [controlled/features](../../../benchmarks/controlled/features)、[controlled/policies](../../../benchmarks/controlled/policies)及冻结输入锁 | 是自建受控文本，已有提交授权；真值仅供对应既有评测，不把受控完整性标签注入普通 HTTP 任务，不作真实 App 政策 |
| M03 可安装普通包 | [已合入平台样本源码及构建入口](../../../experiments/android-package-probe/README.md) | 在本次 checkout 构建并向专用模拟器安装，记录新 SHA、版本及证书；不得套用 M01 未签名哈希或旧安装收据 |
| M04 可安装 base/splits | [已合入 fixture/fixture-feature](../../../experiments/android-package-probe/README.md) | 从本次源码生成真实包集合并安装；记录全部已安装 split 名称、版本、单文件哈希和集合摘要，不用单包改名模拟 splits |
| M05 负向包集合 | 从 M03/M04 的专用测试副本制造缺包、错版本、摘要错配和不可读条件 | 依赖原始可安装产物。原件及正常基线留存；一变体一个别名，记录改动而不篡改冻结真值；真实解析只在受限 Docker |
| M06 正式客户端 | [apps/mobile](../../../apps/mobile/README.md)，复用已合入 #71 桥接和 #72 主流程 | 源码已合入；需本机实际构建安装和原生 UI/IPC 验证。PoC 和 Web bridge 替身不能代替。记录安装包/源码 SHA、版本、证书指纹、Manifest/SDK/WebView |
| M07 分析和部署镜像 | main 的 `deploy/` 与 #80/#81 最终交接 | API/Web registry digest、编排/Runner/扫描 digest 与最终迁移/协议仍待填写。image ID 与 registry digest 分别记录，不能互换 |
| M08 私有证据与许可 | 每个样本的来源、允许内部测试的依据、可公开内容范围 | 公开本包仅含自建来源指针；不导入其他工作区未知研究资料、不使用未授权商业 App 或私人材料 |

M01 的既有构建命令（在满足原说明 Docker/工具条件的专用 checkout 执行；输出目录须不存在）：

```powershell
uv run --project apps/api --locked --extra worker python scripts/build-controlled-apks.py --output tmp/issue73-build-a
uv run --project apps/api --locked --extra worker python scripts/build-controlled-apks.py --cached --output tmp/issue73-build-b
```

先核对两个 `build-receipt.json` 的 `apks` 与 `benchmarks/controlled/artifacts.lock.json`，再使用既有扫描入口。构建成功也不证明手机安装、splits 或远程上传成功。[受控评测说明](../../../benchmarks/controlled/README.md)保留工具、授权及来源边界。

## 每份安装材料的最小记录

代理在受保护证据区保存材料清单：受控别名、来源源码 SHA、构建工具版本、许可依据、包名/versionCode、base/split 名称、文件大小、每文件 SHA256、签名证书公开指纹及客户端/服务端集合摘要。安装前后重新读取已安装集合，验证没有版本竞争。不要将实验本机指纹当作 #70 的线上协议摘要。

重新签名或安装拆包需要按实际 Android 构建/安装工具处理并留下新哈希，不能从未签名锁推导签名包一致。错误样本单独列出原件和变体关系，测试结束后仅清理本次专用安装及临时文件，不修改用户应用或他人测试环境。

## 设备与网络条件

| 条件 | 要记录的实际值／放行依据 | 本轮状态 |
| --- | --- | --- |
| 设备 | 专用本机模拟器别名、类型、Android API/系统版本、ABI、WebView、权限/包可见性、固定 ADB 目标；不公开序列号/整机清单 | 环境探针与实际安装收据分别记录；物理设备不在本次通过门槛 |
| 客户端 | M06 安装来源、源码/包哈希、正式 Manifest、支持系统范围；能选包、确认、取消并上传 | 未交接 |
| 本机官方配置/自托管 HTTPS | 两个独立实例身份、凭据和卷；Android 实际可达且正常校验证书/主机名；记录本机 CA 信任范围 | 等 #81 交接后按本机配置启动并验证，公网不在本次通过门槛 |
| 控制面 | Linux/VM 版本、CPU/内存/磁盘、API/编排镜像 digest、DB migration、Redis/Celery 配置哈希、角色命令及健康检查 | 等 #80/#81 同版本交接 |
| 扫描面 | 独立扫描主机/VM、实际 Runner 认证/协议与扫描镜像 digest、隔离限额和 inspect、任务只读输入、无外网/秘密 | 等 #80/#81 同版本交接 |
| 模型路径 | 本机独立 HTTPS 协议测试端点、一次性测试凭据、客户端出站与分析服务入口观察 | 不使用个人真实 Key；受控响应不证明外部模型或联网查找能力 |
| 恢复与负向 | 独占可销毁栈、合成材料、可恢复快照、删除记录、明确资源配额；故障注入对象属于本次运行 | 未建立，不在共享/生产栈注入 |

若只有部分条件可用，只执行其可证明的案例并准确记录环境和未测项。不得借用 #81 只读合成 smoke 的 `SUCCEEDED` 数据或关闭生产门禁拼接假主链路。无账号约束仍需任务级访问材料；不能为测试新建登录体系。

## 证据区与脱敏

每次运行使用新的 `tmp/issue73-<run-alias>/`，原始收据、容器 inspect、抓包和截图均视作可能含敏感内容。该忽略目录不提供访问控制，含秘密的原始资料须另设受保护权限，不能直接归档上传。公开导出逐文件审查，移除身份、绝对私有路径、令牌/headers/查询串、密钥、原始 APK 和真实全文，只保留场景别名、版本哈希、固定错误码及必要的脱敏观察。

公开附件重新计算 SHA256 并在运行记录引用；不能对原始秘密求哈希后公开当作脱敏。个人 Key 只由手机受保护设置消费；签名私钥不进仓库、镜像、日志或本包。缺少材料时保持明确缺口，由代理在交接记录维护，不要求用户填写新表。
