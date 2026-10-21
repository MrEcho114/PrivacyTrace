# 验收 C：手机模型直连、执行器与 Key 去向

本目录记录 [#131](https://github.com/MrEcho114/PrivacyTrace/issues/131) 的执行入口、环境前置和证据边界。它只负责 H03/H06/H09/H12 与 N11，不改变 #128 的完整矩阵、其他子票的收据或最终放行结论。

## 入口

| 入口 | 用途 |
| --- | --- |
| `deploy/acceptance/mobile/client-case.cjs` | 单用例驱动；`policyMode: "model"` 现已导入 textarea 中的真实模型结果，不再追加静态 assist 文本 |
| `deploy/acceptance/mobile/model-receiver.cjs` | 受控 HTTPS Chat Completions 接收器；固定响应、一次性 Key、Key 指纹/请求体日志 |
| `deploy/acceptance/mobile/n11-model-key-destinations.cjs` | N11 手机侧：A/B 两个模型端点、地址切换、旧 Key 不复用、输入最小化观察 |
| `deploy/acceptance/mobile/repro-model-overwrite.cjs` | 原缺陷复现：模型收集后仍执行静态 assist 导入，保留覆盖前后 textarea 哈希 |
| `deploy/acceptance/mobile/client-case.test.cjs` | 执行器回归：模型模式只导入一次、静态 assist 不得覆盖 |
| `deploy/acceptance/mobile/cases/case-H03.json` 等 | H03/H06/H09/H12 的 case 契约；含 `modelExpect` 断言 |

## 运行前置

1. 一台独立 Android 模拟器已安装实际客户端，固定 `PT_ADB_SERIAL`；H03/H09 只装 C fixture base，H06/H12 用 `install-multiple` 装 base＋feature split。
2. 两个独立实例 I/J（不同 instance ID、端口、数据卷）；本执行使用 `https://localhost:28443` 作为设备侧 origin，通过 `adb reverse` 指向当前实例宿主端口。
3. 手机侧模型接收器使用客户端信任的 CA 签发 `localhost` 证书；Key 为一次性测试值，不写入公开记录。
4. 服务端自动候选抽取使用独立的受控模型端点；它与手机 Key 无关，只用于让报告产生可复核对照。该路径不能替代手机模型传输证据。
5. 模拟器按竖屏 `1080x1920` 操作；坐标由 uiautomator 动态读取，不写死。

示例（`<...>` 为本机实际值）：

```bash
export PT_ADB_SERIAL=<serial>
export PT_EVIDENCE_DIR=<ignored-evidence-dir>
export PT_MODEL_ENDPOINT=https://localhost:19543/v1/chat/completions
export PT_MODEL_KEY=<one-time-test-key>
node deploy/acceptance/mobile/client-case.cjs deploy/acceptance/mobile/cases/case-H03.json
```

接收器示例：

```bash
PT_MODEL_PORT=19544 PT_MODEL_KEY=<same-one-time-key> \
PT_MODEL_CERT=<localhost-cert> PT_MODEL_KEY_FILE=<localhost-key> \
PT_MODEL_RESPONSE_FILE=<collector-response.json> PT_MODEL_LOG=<ignored-log> \
node deploy/acceptance/mobile/model-receiver.cjs
```

## C model fixture

受控 fixture 从 `experiments/android-package-probe/fixture` 与 `fixture-feature` 派生，不复制读取器或分析引擎；本票只做以下最小差异：

1. 在 fixture manifest 增加 `android.permission.ACCESS_FINE_LOCATION`，使静态扫描得到可对照的 `PRECISE_LOCATION` 能力。
2. 将 `applicationId`/`namespace` 改为 `org.privacytrace.probe.cfixture`，feature 改为 `org.privacytrace.probe.cfixture.feature`，标签改为 `C model fixture`，避免与共享 fixture 安装态互相干扰。
3. 用本机 JDK/Android SDK/Gradle Wrapper 构建 debug APK，记录 base/feature SHA256；不把 APK、签名材料或本机路径提交仓库。

本次实际产物：

| 产物 | SHA256 |
| --- | --- |
| `fixture-debug.apk`（base） | `07a6d14f0bfc3891e74fa585f93808ba6626967eebc20dd53c884ef33265f96e` |
| `fixture_feature-debug.apk`（split） | `e48bbeefcd84a2930949683ac9fb4cf0948663f180c8dee170c3f66ab7a7d7eb` |

## 证据边界

- 受控模型响应只证明协议、Key 去向、输入最小化和“报告使用本次模型来源”；不证明外部模型质量、联网检索能力或公网路径。
- N11 的客户端出站由接收器日志观察；手机到分析服务的 HTTPS 未解密。分析服务侧只能证明其环境、日志、材料卷和数据库中未出现一次性 Key，且服务端抽取请求没有 Authorization；不能写成“全路径无泄露”。
- 本机模拟器、debug 客户端和 localhost 测试 CA 的结论不外推到真机、其他 ABI、商店审核或生产部署。
- 证据原文、截图、Key、证书和本机路径只在本机忽略目录；公开目录只保留脱敏结果、哈希和边界说明。
