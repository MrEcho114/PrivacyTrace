# Android 包集合上传（#71 阶段交付）

基线为 main `78ca8eed1591333746a9964a5ae1d3e5a8df09f4`。本阶段接续已经合入的
读取、原生确认、Keystore 配置和 HTTPS health，不改写历史设备收据。
最新 PR、交付 SHA 和验证状态统一见 [#71 当前记录](https://github.com/MrEcho114/PrivacyTrace/issues/71#issuecomment-6214077158)。

## 使用与数据流

验证壳提供无参数的 `uploadSelected`、`refreshUpload`、`deleteUpload` 和 `forgetUpload`。
网页不能传入地址、包名、路径、任务标识、Key、访问凭据或信任设置。

```text
原生输入 HTTPS origin → 读取上传能力 → 原生选应用
→ 确认实例、版本、全部包、大小和长期保留规则
→ 本机受限暂存并复核安装快照 → 再核对能力/实例
→ 创建草稿 → 加密保存访问材料 → 上传 → 校验逐包回执 → GET 读回
```

只有用户选中的 base 和全部已安装 splits 被读取。单 APK 原样上传，多包用平面 ZIP；
既有 `/api/v1/web/drafts/{id}/package-set` 消费原始请求流，由服务端独立解析 APK。
没有新增 multipart、客户端自报事实或另一套扫描链路。服务器返回的包名、版本、
每个角色/split、长度、SHA-256 和总量必须与本机快照一致，随后 GET 确认仍一致，
才显示 `SERVER_CONFIRMED`。这个状态只确认上传，尚未启动分析或完成政策/报告交互。

暂存位于应用私有 cache，取消/失败/完成均清理；清理失败明确报错，下次进程启动重扫。
安装变化发生在暂存期间时拒绝，暂存完成后上传的是已经确认的那一版字节。
本机预算仍为最多 64 包、单包 128 MiB、总量 256 MiB，并收紧至服务限额。
多包 ZIP 开销也占上传预算，不能把文件总量等于传输上限理解为一定可上传。

## 协议与实例

新增只读 `GET /api/v1/mobile-capabilities`，`Cache-Control: no-store`。
协议是 `privacytrace-mobile/1`。只有 remote + durable + PostgreSQL 且支持草稿主动删除时，
返回持久 `instance_id`、`apk-or-zip`、文件/总量/请求大小和数量硬上限、
`UNTIL_EXPLICIT_DELETE` 和删除能力；其余只返回 `supported:false`。
这是静态兼容契约，不能代替就绪、剩余容量、部署验收或服务器身份的独立认证。
原 health 保持原格式；客户端不从健康响应推导上传许可。

默认客户端沿用系统证书和主机名校验、HTTP/1.1、禁止重定向、cookie、认证续接及自动重传。
429/503 直接报告忙碌。连接 5 秒、读 180 秒、写 30 秒、单次调用 240 秒；响应最多 512 KiB，
严格 JSON 拒绝重复字段、无效 UTF-8、非整数数值及尾随文档。能力失败时不创建草稿或上传。

每个精确规范化 HTTPS origin 保存一份当前草稿。访问材料使用独立 Keystore alias 和
AES-GCM 文件，绑定 origin 与服务持久实例 UUID；不复用模型 Key、普通网页存储或 URL。
同域重装/实例变化时拒绝发送旧访问材料。实例 UUID 是服务声明，TLS 仍是连接的信任边界。
加密与网络 API 仍会产生 JVM 内存副本，不承诺全部内存可擦除。

## 中断、重试和删除

取消、HOME 和 Activity 销毁取消传输并拒绝迟到 UI 回调；没有后台上传或自动网络恢复。
原生窗口显示实际能力核对、包集合准备、草稿创建、访问材料保护、传输、读回或删除阶段，
每个阶段均可停止当前操作；没有按计时器推测完成或虚构百分比。
取消不等于服务端删除。访问材料在上传前保存，断连后刷新仅 GET，不重传、不假报成功。
再次主动选择上传时，只有同一实例、同一完整包指纹可使用现有草稿；服务器已有匹配材料时
直接读回确认。不同应用须先主动删除旧草稿。

远端删除需再次原生确认。只在收到有效 tombstone 回执后清本机访问材料，
`cleanup_pending:true` 显示物理清理仍待完成。删除响应丢失时无法证明远端已删除，
保留访问材料和失败状态。另有明确警告的“仅清除本机访问材料”，可在离线/实例更换时
释放本机记录；它不联系服务器、不删除远端材料，且旧草稿无法找回。无账号或找回流程。
创建草稿响应丢失可能遗留空草稿；本次不声称提供创建幂等或无凭据找回。

## 验证边界

JVM 和 Android ordinary UID 的 TLS 测试使用临时私有 CA 和受控 MockWebServer；
它们验证真实 socket、字节去向、回执核对、断连/取消/背压及实例隔离，
不作为真实 PostgreSQL/队列/runner 组合验收。产品没有测试 CA 或信任绕过入口。
Android 设备用例另读取真实安装的自建 base/split fixture，对照宿主构建摘要，检查实际
TLS 请求中的完整 ZIP 字节；Keystore 用例验证跨对象重开、实例隔离、密文与主动清除。

原生构建和 JVM 测试沿用 [README](README.md) 的 Gradle 入口；构建
`:app:assembleDebugAndroidTest :fixture:assembleDebug :fixture_feature:assembleDebug` 后，
先运行 `verify-device.ps1` 安装并核对受控 fixture，再调用 instrumentation：

宿主已确认是 MuMu 等模拟器时，运行 `verify-device.ps1` 加 `-Emulator`。
部分模拟器的 `ro.kernel.qemu` 为 0；该值只产生未知环境，不作为物理设备证明。

```text
adb -s <测试设备> shell am instrument -r -w -e mode upload_transport
  -e expectedBaseSha256 <fixture-base-sha256> -e expectedSplitSha256 <fixture-split-sha256>
  org.privacytrace.probe.test/org.privacytrace.probe.ProbeInstrumentation
```

上述为一条命令，换行仅为阅读。只有实际 `INSTRUMENTATION_CODE: -1` 与固定 PASS 标记均出现
才可记录成功。实际执行环境和产物哈希另随交付归档；模拟器结果保持其真实环境标记。

完整 Tauri APK、生产 #72 接线、真实部署实例的上传/背压/重启/删除、后台/切网和 OEM 范围
仍须分别验证；本阶段不关闭完整 #71，不部署或发布客户端。
