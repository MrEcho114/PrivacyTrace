# B lane cases（Issue #130）

这四个 JSON 只覆盖 B 的 H 组组合：

| 文件 | 输入 | 实例 | 预期 |
| --- | --- | --- | --- |
| `case-H02.json` | 单 base APK | 本机官方配置 I（`https://localhost:28544`） | 非空对照、原句 `[25,34)`、`INSUFFICIENT_EVIDENCE` |
| `case-H05.json` | base＋`fixture_feature` split | I | 2 个数据类型、通讯录原句 `[34,42)`、split 字节码 |
| `case-H08.json` | 单 base APK | 自托管配置 J（`https://localhost:28545`） | 同 H02 |
| `case-H11.json` | base＋split | J | 同 H05 |

运行前：

1. 模拟器为专用目标，固定 1080×1920 竖屏（`wm size 1080x1920`，
   `user_rotation=0`），并设置 `PT_ADB_SERIAL`。
2. 按用例安装 base 或 base＋split；不能把 base 改名当 split。
3. 对应实例的 `adb reverse tcp:<port> tcp:<port>` 已建立，TLS 证书由客户端
   信任的测试 CA 签发；不要关闭主机名/证书校验。
4. `PT_EVIDENCE_DIR` 指向本票独立目录；每个用例结束通过客户端原生双确认
   删除远端材料。

`client-case.cjs` 的 B 相关契约：

- `policyText`：覆盖辅助导入的受控政策正文（默认只含精确位置句）。
- `candidates` / `addCandidate`：保存一条或多条候选；每条的原句必须是来源
  正文的逐字子串，保存失败会令用例失败。
- `expected`：记录本票预先固定的独立预期；执行器忽略该字段，供评审对照。
- 报告页和证据面板的等待/捕获逻辑见
  `../../../../docs/acceptance/issue130/execution-20261021.md` 第 3 节。

这些用例不是 A/C/D/E/F/G 的输入，也不改变 #128 的案例分母。最终结果与证据
见 [`docs/acceptance/issue130/`](../../../../docs/acceptance/issue130/README.md)。
