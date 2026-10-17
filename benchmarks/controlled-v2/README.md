# PT-907：12 个源码受控场景（Issue #64）

这是独立的新评测版本。C01–C06 的源码、政策和候选逐字节复用 `../controlled`，只计为既有 6 项；C07–C12 新增 6 项，总分母为 12。原版本的真值、输入及产物锁保持不变。复制既有输入是为了形成可独立复建的版本快照，不计为新增场景。

| ID | 独立问题／输入差异 | 预期目标 |
| --- | --- | --- |
| C01–C06 | 复用已验收的权限无调用、精确／类别／缺失／否定／政策不全 | 沿用原真值 |
| C07 | 同一完整政策同时肯定和否定精确位置访问，保留两条候选 | AMBIGUOUS_DISCLOSURE |
| C08 | 精确位置声明仅在启用附近功能时成立，候选保留 condition | AMBIGUOUS_DISCLOSURE |
| C09 | 精确位置声明的主体仅为第三方服务，不能作为清楚的宿主声明 | AMBIGUOUS_DISCLOSURE |
| C10 | 政策完整且无位置声明，但适用地区未知；单独隔离范围缺口 | INSUFFICIENT_EVIDENCE |
| C11 | `getLastKnownLocation("network")`、粗略定位权限和粗略位置声明 | EXACT_MATCH（COARSE_LOCATION） |
| C12 | provider 为方法参数，不能静态确定；政策明确声明位置类别 | EXACT_MATCH（LOCATION，不提升为精确位置） |

C07 是同一来源内的矛盾，**不是**多渠道 `POLICY_SOURCE_CONFLICT`；本版不覆盖多来源冲突、Multidex、运行时采集或外传。C12 仍保留精确定位权限的 CAPABILITY 结果，计分目标只取通用 LOCATION/ACCESS。所有静态方法均不由启动页面执行；没有运行时采集或合法性真值。

`ground-truth.json` 在本版首次算法运行前根据上述问题、源码及自建政策冻结，`.sha256` 固定其字节，`inputs_lock_sha256` 固定候选与源码；旧真值哈希记录在 `reused_truth_sha256`。算法容器不挂载本目录，不读取标签。后续修订须另建版本，不能按系统输出修改预期。

三个方案共用同一 APK、权限、完整政策、人工候选、适用范围和 invoke/descriptor/context。权限＋关键词方案仅使用权限和精确短语；API＋扁平方案使用完整描述符及上下文和同一文本；本系统仍用既有规则。候选为 agent 辅助人工整理并核对原句，非自动语义抽取或独立人类签字。

复用现有入口并选择 `--suite pt907`：

```bash
uv run --project apps/api --locked --extra worker python scripts/build-controlled-apks.py --suite pt907 --output tmp/pt907-build-a
uv run --project apps/api --locked --extra worker python scripts/build-controlled-apks.py --suite pt907 --cached --output tmp/pt907-build-b
uv run --project apps/api --locked --extra worker python -m privacytrace.benchmark run --suite pt907 --artifacts tmp/pt907-build-a --output tmp/pt907-evaluation
uv run --project apps/api --locked --extra worker python scripts/validate-spec30.py --suite pt907 --output tmp/pt907-acceptance
```

前两次构建的 APK 字节哈希必须一致并匹配本版 `artifacts.lock.json`，之后才能进入隔离扫描。完整验收包含 12 场景、36 行比较、HTTP 和 Chromium 逐项证据定位；原 Spec30 六场景及离线回放继续使用默认 suite 单独回归。本版不扩展正式离线交付范围。

失败、partial、弃判与截断留在全分母；状态分类／混淆、API 映射与定位、处理覆盖分别报告。没有二元采集或合法性标签，P/R/F1 为 N/A，不能从状态一致率推导实际采集精度。CPU／峰值内存和候选准备工时未测，保留 null。APK、原始 job、完整运行日志与缓存只存忽略目录；提交的自建政策仅用于这个源码受控任务，真实政策仍不提交。
