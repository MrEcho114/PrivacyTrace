# PT-910：两个源码受控场景

对应 [#31](https://github.com/MrEcho114/PrivacyTrace/issues/31)，验收规范为 [#30](https://github.com/MrEcho114/PrivacyTrace/issues/30)。这不是商业 App 评测集，也不代表实际运行时采集。

| 场景 | 独立定义 | API ACCESS 目标 |
|---|---|---|
| C02 | `Camera.open()`，相机权限、明确肯定宿主声明，包/版本/产品/测试地区已知 | `CAMERA` → `EXACT_MATCH` |
| C06 | `AudioRecord.startRecording()`，麦克风权限与明确声明，但分析输入缺少地区 | `MICROPHONE` → `INSUFFICIENT_EVIDENCE` |

源码只含静态调用，无启动 Activity；APK 不签名、不安装、不执行。`javac` → D8 → AAPT2 → 固定时间戳 ZIP 的产物必须经项目现有隔离扫描核对调用。两个场景不使用手工二进制 fixture。

## 工具链与构建

版本固定在 `toolchain.json`：JDK 24.0.2、Android platform `android-37.0` revision 2、Build Tools 36.0.0。Gradle 非必需；JDK/SDK 由调用者提供，不改全局配置。构建记录工具文件哈希和逻辑路径命令；哈希是实际安装文件的指纹，不冒充官方校验值。不同 OS/JDK 发行版可能产生不同 APK 哈希，同环境重复构建应一致。

```powershell
uv run --project apps/api --locked --extra worker python -m privacytrace.controlled_build `
  --case-dir benchmarks/controlled/C02 --sdk <SDK目录> --jdk <JDK目录> `
  --output-dir tmp/controlled-build/C02
```

将 `C02` 换成 `C06` 构建第二场景。输出目录必须不存在；产出 `scenario.apk`、`build.json` 与本地构建日志。APK/DEX/缓存均保持忽略，不进入 Git。

官方构建依据：[AAPT2 Link](https://developer.android.com/tools/aapt2#link)、[D8](https://developer.android.com/tools/d8)、[javac 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)。工具许可由各自发行方提供；仓库不分发 JDK、SDK 或商业 App 内容。

## 冻结、预测、比较

`input.json` 只含自建场景事实，拒绝额外字段；`policy.txt`、`candidates.json` 是人工准备的输入。本轮文本和候选由 Codex 辅助编写，未声称有真人核验，人工准备耗时未测。政策摄取仍是 `UNREVIEWED/PARTIAL/NOT_CHECKED`，C02 的明确对应也保留待复核标记。

先冻结独立真值和全部输入的哈希：

```powershell
uv run --project apps/api --locked --extra worker python -m privacytrace.controlled_compare freeze `
  --suite-dir benchmarks/controlled --output tmp/controlled-run/frozen.json
```

再运行预测。此 CLI 不接受真值路径，也不会打开 `ground-truth.json`：

```powershell
uv run --project apps/api --locked --extra worker python -m privacytrace.controlled run `
  --case-dir benchmarks/controlled/C02 --build-receipt tmp/controlled-build/C02/build.json `
  --output-dir tmp/controlled-run/C02 --store-dir data/controlled-jobs --job-id controlled-c02-001
```

为 C06 使用独立输出目录和 Job ID。真实扫描仍走受限容器；源文件、配置或 APK 不符合构建收据即拒绝。扫描后再次核对隔离器实际处理的 APK 哈希、包和版本。收据提供可核对的本地来源记录，没有数字签名，不提供防恶意作者伪造的认证。

预测产物落盘后，单独比较：

```powershell
uv run --project apps/api --locked --extra worker python -m privacytrace.controlled_compare compare `
  --freeze tmp/controlled-run/frozen.json --labels benchmarks/controlled/ground-truth.json `
  --predictions tmp/controlled-run/C02/predictions.json tmp/controlled-run/C06/predictions.json `
  --output-dir tmp/controlled-run/comparison
```

比较器要求冻结早于预测开始，输入哈希一致、真值未改，并核对成功预测的报告、构建收据及各方案输出。它读取标签，预测器不读标签。哈希不是签名；保存冻结记录和对应 commit 才能追溯版本。

## 三方案与计数口径

共同材料是相同 APK 扫描证据、权限、完整政策、候选、适用信息和政策状态；每个方案记录实际使用子集。

- 权限＋关键词：读取清单权限与政策原文，使用已版本化的权限和词映射。`EXACT_MATCH`/`NOT_DECLARED` 是此朴素基线的对照标签，不构成实际访问或完整政策核验。
- API＋扁平匹配：读取同一 API 证据、完整方法描述符和同一候选，按具体类型平面匹配明确肯定的宿主声明；不使用层级/适用性判定。没有人为删除 API、改错描述符或读取本系统判定再改名。
- PrivacyTrace：复用现有规则及完整输入，保留地区未知和政策未核验。

计数单位在真值中固定为 `(case_id, data_type, ACCESS)`。清单 CAPABILITY 行完整保留在报告中，不与 API ACCESS 目标混算；C02 整份报告仍可能包含权限行的证据不足。多个调用结果保留状态集合。每个目标、每个方案都有一行；失败/缺失目标为 `ABSTAIN`，PARTIAL 保留且不能记验收通过。两场景只做诊断比较，P/R/F1 为 N/A，不宣传精度优势。

## 验证与浏览器

- 权威工程检查仍是 `bash scripts/check.sh`。
- 显式设置 `PRIVACYTRACE_ANDROID_SDK` 和 `PRIVACYTRACE_JAVA_HOME`，可运行 `test_controlled_source_cli.py` 的真实重复构建及篡改拒绝检查。
- 再设置 `PRIVACYTRACE_DOCKER_TESTS=1`，执行同文件中的源码 APK → 隔离 CLI → HTTP 验收；测试输入目录不含真值文件。
- Linux 具备工具链与 Docker 后，`ANDROID_HOME`/`JAVA_HOME` 下执行 `bash scripts/validate-controlled.sh`。每次使用新检出或移走自己上次的输出；脚本不覆盖旧结果。
- `Controlled source scenarios` CI 对 PR head 执行上述链路并用 Chromium 查看两份真实生成的受控报告、代码目标和政策原句。截图、浏览器版本、错误与 commit 保存在 14 天 Actions artifact，只有测试文本/脱敏报告，没有 APK。该 artifact 不等于正式 Release 或比赛提交。
- `scripts/verify-controlled-browser.cjs` 只停止它自己启动的进程；8000/5173 被占用时退出，不终止别人的服务。

本机首次核查缺少扫描器指定的 `Ubuntu-24.04` WSL 发行版，源码构建已成功，隔离验收需用可用 Linux Docker 环境完成。工程 fixture/单测通过不替代源码 APK 端到端结果；实际通过状态以交付 SHA 的 CI 与浏览器收据为准。
