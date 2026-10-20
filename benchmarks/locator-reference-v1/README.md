# 独立 DEX 定位参考 v1（#89 / PT-907）

此版本只补充定位参考，不修订 `controlled` 或 `controlled-v2` 的冻结输入、真值、APK 锁及历史报告。`reference.sha256` 固定本版本字节；以后调整须新增版本。

参考来自固定 `toolchain.lock.json` 的 Android Build Tools `dexdump -d`，独立于被测扫描器的 Androguard。生成器只读取源码、锁和已匹配 APK 哈希的自建产物，不读取预测、报告、扫描器偏移或状态标签。它保存 APK SHA256、DEX SHA256、caller/target descriptor、invoke opcode/原始字节、方法内字节偏移、code-unit PC、指令序号和 DEX 文件内字节地址，并把反汇编指令字节与实际 DEX 字节重新比对。

`offset_bytes` 是相对方法指令区起点的字节偏移，等于 dexdump 的十六进制 **16-bit code-unit PC × 2**，不是指令序号，也不是 DEX 文件地址。例如 C02–C11 的目标 invoke 为 code-unit PC 2 / 字节偏移 4 / 指令序号 1；C12 为 0 / 0 / 0。同一方法的多个 invoke 分别保留，评分按调用点多重集合比较，重复引用不能代替另一个调用点。

context 单独对照已冻结的自建 Java 方法：C02–C10 为字面值 `gps`，C11 为 `network`，C12 为未解析的参数，保留 `{}`。参考保留类内的其他 invoke，计分只选与冻结目标、caller 和 context 对应的调用。C01 没有目标 invoke：共享扫描核对其缺席，三个方案的 API 定位均为 N/A。

生成／复核均在同一无网络、只读、非特权 builder 中完成。初始参考来自匹配原锁的十二个 APK；完整验收在两次源码构建和原锁校验后，再对新建 APK 独立复核本参考，导出 `evaluation/location-reference-check.json`，并在整合回执记录哈希。复核不会更新参考：

```bash
uv run --project apps/api --locked --extra worker python scripts/verify-controlled-locations.py \
  --suite pt907 --artifacts tmp/build-a --output tmp/location-reference-check.json
```

生成新版本时，使用 `scripts/controlled/location_reference.py --suite <frozen-suite> --artifacts <locked-build> --output <new-reference.json>`；入口拒绝覆盖已有文件。工具二进制 SHA256、原工具归档锁和源码哈希保存在 JSON 中。没有提交 APK、DEX 或反编译全文。

边界：仅验证这十二个 hash-locked 自建单 DEX 产物的静态位置；context 的来源核对不代表独立运行时数据流验证。Multidex、其他编译器/构建版本、任意真实 APK、动态行为和合法性不在本版本内。没有独立人类签字或测量人工成本。

## 结果字段兼容约定

六／十二场景的 CLI 主字段均为 `scenarios_passed: bool`，总数读取 `scenario_count`。CLI 退出码只消费主字段；验收 runner 继续以该退出码判断比较阶段。比较 JSON schema v3 增加 `api_location_reference` 来源元数据，保留已有计分／定位／覆盖字段；离线和浏览器消费者按现有字段读取，不修改历史 schema v2 文件。

`six_scenarios_passed` 是**已弃用但保留**的 CLI 别名，在两个 suite 下都严格等于 `scenarios_passed`；十二场景下也表示整套通过，绝不表示只验证了六项。JSON 的 `deprecated_fields` 明示迁移方向，不改变 stdout 的可解析性。不在兼容版本中删除别名；删除只能随明确公告的破坏性 CLI 版本进行。仓库内主消费者和回归已迁移，兼容断言继续覆盖旧键。
