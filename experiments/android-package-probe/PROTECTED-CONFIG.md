# 原生受保护模型配置（#71 部分交付）

本实验补 #71 的本机模型配置能力，供 #72 后续串行整合。只使用合成 Key，
不调用模型，不接入分析服务器。生产 Web、上传、实例任务材料保存及真机仍未完成。

## 使用与接口

独立 Vue 壳的“设置模型配置”打开 Android 原生窗口，输入 HTTPS 模型地址与新的
服务 Key，按“保存到本机”。网页只收到 `{ configured, endpoint }`，不能取回 Key、
密文、文件路径或包装密钥。三个无参数命令需要分别授权，且只对本地 Android 主窗口开放：

- `configureModel()`：原生输入；即使已有配置，也不预填 Key。
- `modelStatus()`：从密文验证成功后取得非秘密状态；文件缺失为未配置，损坏或密钥不可用为固定错误。
- `clearModel()`：原生确认后删除当前配置及其 AES 包装密钥；没有账号或找回功能。

地址按 HTTPS scheme、ASCII host、默认 443 端口和空路径规范化；路径及非默认端口
保留身份差异。拒绝 userinfo、query、fragment、空地址、控制字符及点段路径。
服务 Key 在本实验接受 1–4096 个无空白的可打印 ASCII 字符。改变实际端点必须重新输入 Key，
不能把旧 Key 自动绑定给新地址。模型地址可显示并作为受认证元数据落盘，不应在地址中放凭据。
地址最多 1024 字符；输入框最多接收上限加一字符，超限会拒绝而不会接受截短后的 Key。
原生表单可以滚动，保存与取消按钮独立于滚动内容。

## 保存与取消

`ModelConfiguration` 是两种实验壳共享的 Kotlin module；Android adapter 使用平台
AndroidKeyStore AES-256/GCM/NoPadding，Cipher 每次产生新 IV，版本与规范化地址参与 AAD。
服务 Key 仅以密文写入 `noBackupFilesDir/model-config-v1.bin`；地址、版本、IV 和长度是
明文 envelope 元数据。Keystore 的非导出属性针对 AES 包装密钥，服务 Key 仍会在原生进程短暂出现。

1. 原生输入框不保存 View 状态；密码遮罩、API26+ 无 Autofill 值/结构文本、禁止学习提示及
   FLAG_SECURE 限制常规输入/截屏路径。关闭窗口清空 Editable，不经过 WebView。
2. worker 仅验证并制备密文，不覆盖当前记录；消耗的 CharArray 和原生编码数组在 finally 清空。
   取消/销毁也主动清空尚未执行的输入，避免队列任务被丢弃时漏过 finally。
3. 主线程核对同一个 pending 操作及取消令牌后，串行完成小于 8 KiB 的 AtomicFile 提交及 Invoke。
   若取消/暂停/销毁先被处理，迟到密文丢弃；不会在 worker 做“检查后无保护写入”。
   最终小文件提交包含同步 I/O，仍可能短暂停顿，不声称零时延。
   进程内共享锁串行化不同 Activity 实例的 Keystore/文件操作；排队的制备在锁内检查取消，
   防止旧 worker 在新页面删除配置之后重新建立 alias。这不是跨进程文件锁。
4. 写失败回滚；adapter 读回核对字节后才报告保存成功。旧配置不会因尚未提交的新配置而改变。
   清除先删除 AES alias，再删除密文；残留密文因此不可解密，删除失败不报成功。
   读回核对不能证明断电或 fsync 故障时的持久性；不完整写入测试也不模拟所有文件系统故障。

`modelStatus` 不为已有密文自动生成新密钥。缺 alias、坏 tag、错误/截断/超限记录或
平台错误不成为 configured=true；用户先确认删除再重新配置。原生错误仅使用固定白名单码，
不附带异常文本、Key、平台路径或解密内容。

## 验证入口

JVM 使用真实 JCA AES-GCM 和内存文件/key adapter，验证绑定、随机 IV、输入/解密 buffer
清空、篡改、密钥丢失、删除、未提交与失败替换等行为；不能替代真实 AndroidKeyStore。
Android instrumentation 的 `model_store`、`model_store_seed`、`model_store_reopen` 则运行平台实现。

构建原生探针/测试 APK 及 Tauri APK 后，在仓库根目录运行：

```powershell
uv run --project apps/api python experiments/android-package-probe/verify-model-config.py --adb '<adb程序>' --serial '<专用模拟器>'
```

该命令只接受明确选择的模拟器，会安装本实验 debug 包，重置本实验自身的合成模型配置，
在测试 app 内注入缺 alias/坏记录/不完整写入。不要在装有个人配置的环境运行。
它用固定 `.test` 地址和合成 Key；只有完整成功才向 stdout 输出 JSON，无设备 ID、Key 或私有路径。
UI 临时 XML 在 finally 清理，断开设备时清理只能尽力完成；请独占设备顺序执行。
实际检查包括普通 UID Keystore、进程重启、取消/字号重建、键盘与大字体操作、原生文件及
本实验 UID logcat 中合成 UI Key 的缺席，以及原生控件无 Autofill type/value。
这不构成完整 Autofill 服务、ViewStructure、输入法、JS 存储或全部日志出口审计。
可加 `--screenshots '<已有目录>'` 保留只有端点/状态的网页截图，密码窗口不截图。

现有包读取/确认桥接另用 `verify-device.ps1` 与 `verify-bridge.py --verify-recreation` 验证，
存储通过不代表包读取或网络主流程通过。各次实际收据按 [evidence/README.md](evidence/README.md) 绑定其源码。

## 保证范围

平台事实与一手来源见 [调查](PROTECTED-CONFIG-RESEARCH.md)。不保证所有进程内副本被彻底擦除，
也不保证恶意输入法、无障碍、root/已受控进程、所有 OEM 迁移路径或硬件 Keystore。
API24/25 没有 API26 的 Autofill/IME 标志；API24/36 构建配置不代表各版本均已实测。
不为测试关闭 FLAG_SECURE，密码窗口不提交截图。实际请求去向、TLS/重定向与 Key 不到分析实例的
网络证据由后续 #72/#71 真实接线验证；当前没有网络权限，不能将“没有网络调用”包装为已完成模型直连。
