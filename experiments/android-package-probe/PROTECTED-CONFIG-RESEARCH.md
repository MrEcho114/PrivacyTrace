# 受保护配置：Android 平台调查

调查日期：2026-10-20。范围为 #71 独立 Android PoC 的本地配置边界；以下是官方资料调查与设计建议，不是已经完成的模拟器或真机验收。API 基线为 Android 7.0 / API 24。

本调查区分两个对象：**服务 API Key** 是用户输入的敏感文本；**AES 包装密钥** 是在 AndroidKeyStore 中生成、用于加密该文本的密钥。AndroidKeyStore 的非导出属性针对后者，不代表服务 API Key 不会在原生进程内短暂出现。[Android Keystore 系统](https://developer.android.com/privacy-and-security/keystore)

## 影响实现的结论

| 平台事实 | 本 PoC 的设计约束 |
| --- | --- |
| AES/GCM/NoPadding 可直接使用 AndroidKeyStore；相关 KeyGenParameterSpec API 自 API 23 提供。[KeyGenParameterSpec AES 示例](https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec) | 不引入已弃用的 Jetpack Security Crypto；API 24 基线可使用平台 API。 |
| 开启 randomized encryption 时，加密阶段拒绝调用方提供 IV；应让 Cipher 生成，再读取 IV。[Builder.setRandomizedEncryptionRequired](https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec.Builder#setRandomizedEncryptionRequired(boolean)) | 每次保存独立初始化 Cipher，保存生成的 IV，不从端点、Key、时间或固定值派生 IV。 |
| GCM 的 AAD 必须在密文处理之前提供；最终验证失败会抛出 AEADBadTagException。[Cipher](https://developer.android.com/reference/javax/crypto/Cipher) | 用版本与端点的确定性编码作为 AAD，认证完成前不返回可用状态或明文。 |
| AtomicFile 不包含线程或进程锁。[AtomicFile](https://developer.android.com/reference/android/util/AtomicFile) | 一个 store owner 串行访问；取消、生命周期失效和最终写入通过同一门控排序。 |
| allowBackup=false 在部分 Android 12+ OEM 上不能关闭 D2D 迁移。[Auto Backup](https://developer.android.com/identity/data/autobackup#EnablingAutoBackup) | 使用 noBackupFilesDir，保留 manifest 禁止备份；不宣称所有 OEM 迁移路径均已验证。 |
| Autofill 和 IME 禁止学习标志自 API 26 才提供，且 Autofill importance 在 API 34+ 不是保密边界。[View](https://developer.android.com/reference/android/view/View#isImportantForAutofill())、[EditorInfo](https://developer.android.com/reference/android/view/inputmethod/EditorInfo#IME_FLAG_NO_PERSONALIZED_LEARNING) | 按版本门控，Key 使用无 Autofill 值的原生输入控件；不能只设置 importance 后声称已禁止泄漏。 |

## 密钥与密文记录

1. AES 包装密钥采用 `KeyGenerator.getInstance("AES", "AndroidKeyStore")`；用途仅 encrypt/decrypt、GCM、NoPadding，显式要求 randomized encryption。平台提供的 AES-GCM 示例不依赖 Jetpack。[KeyGenParameterSpec](https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec)、[KeyGenParameterSpec.Builder](https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec.Builder#setRandomizedEncryptionRequired(boolean))
2. 使用 provider 生成 IV；解密使用记录中的 IV 与 `GCMParameterSpec(128, iv)`。调查到的 AOSP 实现使用 12 字节 IV、默认 128 位 tag，并拒绝不支持的长度；这是实现证据，仍应在目标设备验证。GCMParameterSpec 的 tag 长度单位是 bit，IV 是 byte array。[AOSP 固定提交的 AndroidKeyStore GCM](https://android.googlesource.com/platform/frameworks/base/+/4e6b2d3e7d2c78c0575c14045469c36ab09a6a4e/keystore/java/android/security/keystore/AndroidKeyStoreAuthenticatedAESCipherSpi.java)、[GCMParameterSpec](https://developer.android.com/reference/javax/crypto/spec/GCMParameterSpec)
3. `Cipher.doFinal()` 的加密输出已含认证 tag，解密时验证它；不要自行追加第二份 tag。AAD 在 `update` / `doFinal` 之前提供。[Cipher](https://developer.android.com/reference/javax/crypto/Cipher)
4. **设计建议**：使用有版本、字段长度上限和明确编码的 envelope，保存 endpoint、IV、ciphertext-with-tag；服务 API Key 不以明文写入普通文件。AAD 使用固定域分隔符、版本、精确的规范化 endpoint UTF-8 字节；解析与保存调用同一规范化规则。不要把 AAD 当作加密或服务器认证：它只绑定这些字节与密文的完整性。[Cipher 的 AEAD/AAD 语义](https://developer.android.com/reference/javax/crypto/Cipher)
5. **设计建议**：如果需求连 endpoint 元数据也不允许明文落盘，则 envelope 仅保留必要的非敏感格式信息，另设计可验证的加密载荷；不要在“普通文件只有密文”表述中遗漏 plaintext endpoint。当前设计允许 JS 知道 endpoint，但这不自动决定磁盘元数据策略。

## 不可用状态与设备边界

- 不存在的 alias 可能使 `KeyStore.getKey()` 返回 null；恢复失败也可抛出异常。[KeyStore.getKey](https://developer.android.com/reference/java/security/KeyStore#getKey(java.lang.String,%20char[])) **设计建议**：已有密文时缺 alias、恢复失败、坏 tag、记录截断或未知格式一律视作不可用，提示重新配置；禁止静默生成替代密钥后继续宣称旧配置 ready。
- `KeyPermanentlyInvalidatedException` 表示密钥已永久失效，其典型锁屏/生物识别条件针对需要用户认证的密钥。默认授权不要求用户认证；不应把本 PoC 的原生保存确认描述为系统生物识别认证。[KeyPermanentlyInvalidatedException](https://developer.android.com/reference/android/security/keystore/KeyPermanentlyInvalidatedException)、[Builder.setUserAuthenticationRequired](https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec.Builder#setUserAuthenticationRequired(boolean))
- AndroidKeyStore 不保证每个设备、算法组合均硬件支持。硬件保护要查询 KeyInfo，并按 API 能力处理；StrongBox 自 API 28 才存在且不是所有设备都有。进程被攻陷后仍可能使用密钥。[Android Keystore 安全特征](https://developer.android.com/privacy-and-security/keystore#SecurityFeatures) 因此模拟器通过不能证明 TEE、StrongBox、root 环境或 OEM 的防护。
- 服务 API Key 的原生 Editable、编码数组、加解密输入或 HTTP 头准备都可能产生进程内副本。Java String 不可变；缩短持有时间、清空可变 buffer 和输入框只能降低暴露时间，不能承诺彻底擦除所有副本或已受控进程中的数据。[String](https://developer.android.com/reference/java/lang/String)、[Keystore 的 extraction prevention 边界](https://developer.android.com/privacy-and-security/keystore#ExtractionPrevention) 后一句是根据这些平台性质作出的安全推论，不是 Android 的擦除保证。

## 文件提交与取消

AtomicFile 通过完整写入、同步和替换文件降低半写风险；`startWrite()` 必须配对 `finishWrite()` 或 `failWrite()`，不要直接关闭返回流。它不提供加密、锁或跨 Keystore 与文件的事务。[AtomicFile](https://developer.android.com/reference/android/util/AtomicFile)

`noBackupFilesDir` 自 API 21 提供，是应用私有存储位置并排除自动远程备份。Auto Backup 也明确排除该目录；它不是文件加密或对 root/调试权限的防护机制。[Context.getNoBackupFilesDir](https://developer.android.com/reference/android/content/Context#getNoBackupFilesDir())、[Auto Backup 文件范围](https://developer.android.com/identity/data/autobackup#Files)

**建议的应用状态协议（不是平台自动保证）**：

1. 原生保存点击读取输入，验证 HTTPS endpoint 与长度；仅用合成测试 Key 验证，不调用真实服务。
2. worker 只制备密文，不覆盖当前记录、不删除或覆盖现有 AES alias。包装密钥可以复用；每次加密仍必须新 IV。
3. 结果回主线程，核对请求 token、Activity 实例、resumed 状态、取消标志和当前配置 generation，再执行唯一提交。取消/失活先被处理时，迟到结果必须丢弃。
4. 取消、清除、替换、读取和提交共用单 owner 的互斥规则。若最终文件提交选择留在 UI 线程，应严格限制记录大小，并记录同步 I/O 可能造成停顿；若改为后台提交，必须有等价的不可分割门控，不能“检查 token 后再无保护写入”。
5. 提交成功才返回 endpoint / configured；失败保持之前已提交的有效配置或明确不可用，绝不返回半保存的 ready。

主线程分发应用组件事件，但不会自动替应用解决 worker 与生命周期之间的竞争；Android 官方同时要求避免在主线程进行长耗时工作。[进程与线程](https://developer.android.com/guide/components/processes-and-threads)、[Looper](https://developer.android.com/reference/android/os/Looper)

端点绑定的需求应明确为：**地址改变必须重新输入服务 API Key，不允许取出旧 Key 自动重新绑定到新地址**。这是本 PoC 的协议约束；GCM AAD 只能阻止已有 envelope 被直接改绑，不能阻止持有合法包装密钥的代码解密后重加密。此语义不要求每次换地址都覆盖 AES alias。[Cipher AAD 机制](https://developer.android.com/reference/javax/crypto/Cipher)

## 原生输入与显示

| 控制 | 官方事实与限制 | 建议 |
| --- | --- | --- |
| 密码输入 | InputType 提供文字密码类型和关闭建议标志；它们配置输入行为，不隔离输入法进程。[InputType](https://developer.android.com/reference/android/text/InputType) | Key 用原生 password EditText、单行、长度上限，不提供显示明文切换，不复制到剪贴板。 |
| 自动保存状态 | `setSaveEnabled(false)` 关闭该 View 状态保存；`setSaveFromParentEnabled(false)` 控制父树遍历。[View 状态 API](https://developer.android.com/reference/android/view/View#setSaveEnabled(boolean)) | Key 控件同时关闭两者；不得另写 Bundle、SavedStateHandle 或 Web 状态；失活清空字段。 |
| Autofill | API 26 的 importance 是提示；API 34+ 即使 NO 类节点也可能进入 Autofill ViewStructure。TextView 默认 getAutofillValue 返回可编辑文本。[View.isImportantForAutofill](https://developer.android.com/reference/android/view/View#isImportantForAutofill())、[TextView.getAutofillValue](https://developer.android.com/reference/android/widget/TextView#getAutofillValue()) | API 26+ 设置 NO_EXCLUDE_DESCENDANTS，并使用 getAutofillType=NONE、getAutofillValue=null 的 SecretEditText；覆盖提供结构时清空 text/value，验证生成结构没有 Key。不能仅依靠 importance。 |
| 输入法学习 | `IME_FLAG_NO_PERSONALIZED_LEARNING` 自 API 26 提供，语义是请求输入法不要更新学习数据。[EditorInfo](https://developer.android.com/reference/android/view/inputmethod/EditorInfo#IME_FLAG_NO_PERSONALIZED_LEARNING) | API 26+ 设置；API 24/25 不声称此功能存在。恶意或不遵循请求的输入法不在保证范围。 |
| 屏幕保护 | FLAG_SECURE 阻止正常截图/非安全显示；官方提醒它并不可靠阻止 overlay，旧系统设备覆盖也有限。[WindowManager.LayoutParams](https://developer.android.com/reference/android/view/WindowManager.LayoutParams#FLAG_SECURE)、[敏感 Activity 防护](https://developer.android.com/security/fraud-prevention/activities#flag_secure) | 打开原生配置窗口时设置并正确恢复原值；不声称防物理拍照、IME、无障碍、root 或所有录屏实现。 |

Autofill 结构建议需要实现与设备测试；这里不宣称自定义控件已经覆盖所有 OEM/服务。官方的结构提供方法与 ViewStructure 字段使应用能够控制提供的值。[View.onProvideAutofillStructure](https://developer.android.com/reference/android/view/View#onProvideAutofillStructure(android.view.ViewStructure,%20int))

Jetpack Security Crypto 的全部 API 已弃用，官方迁移方向是平台 API 与直接使用 Android Keystore，本 PoC 不应新依赖 EncryptedSharedPreferences / MasterKey。[AndroidX Security 发布说明](https://developer.android.com/jetpack/androidx/releases/security#1.1.0-alpha07)

## 应留存的后续验证

以下是建议验证清单，不是本调查的通过结果：

- 同输入两次保存使用不同 IV；重启/杀进程后仍能读取；普通文件与备份候选中不存在测试 Key 明文。
- 改 endpoint、IV、ciphertext、tag 任一项或删除 alias 后都不可用；缺失/截断/超限记录不得返回 ready。
- BACK、HOME、显式取消、Activity 重建、清除与 worker 迟到按上述提交协议执行；取消已经先发生时不得写入。
- JS 命令/参数/响应、Web localStorage/sessionStorage、logcat、错误与 receipts 无 Key；JS 仅取得允许的 endpoint 与配置状态，不取得密文、alias 或密钥材料。
- 结构级验证 Autofill 输出没有测试 Key；API 24/25 路径不调用 API 26 接口；API 34 的真实 Autofill 行为另验。
- 模拟器只支持功能证据；真机/OEM、设备迁移、硬件 Keystore、安全键盘与锁屏策略的证据仍保留未验状态。

本轮不验证真实 HTTPS 上传，不发送配置或 APK，不解除 #71 其余生产整合、网络取消/背压和真机验收项。
