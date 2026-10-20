# 原生 HTTPS health：#71 部分交付

本轮在 `104f34d`（PR #90 合并后）继续独立 Android 实验，不接入生产 Web 或上传。
唯一执行记录见 [#71](https://github.com/MrEcho114/PrivacyTrace/issues/71#issuecomment-6214077158)。
版本/API 事实及取舍的一手来源见 [调查](HTTPS-RESEARCH.md)。

## 行为与返回

网页只能调用无参数的 `checkServer()`。用户在原生窗口输入 HTTPS 根 origin，确认后
原生只发一次固定 `GET /api/v1/health`：无 body、Authorization、Cookie、模型 Key、
整机清单或 APK。地址不持久保存，不接受 user-info、路径、query、fragment、空白或非法端口。
原生只返回 `{ origin, version, mode, scope: 'HEALTH_ONLY' }`。version/mode 是服务声明。

主线 health 只有 status/version/mode，没有能力、实例身份、限额和保留规则的机器可读契约。
收到健康响应不表示服务兼容、允许上传、具有可信实例身份或生产 ready；尚未实现任务/凭据实例隔离。
未来接线应由服务 owner 提供这些契约，再单独确认目标实例、材料和保留规则。

独立 OkHttp 4.12 客户端保留系统 TLS 与默认主机名校验，只用 HTTP/1.1，禁用两类重定向、
连接重试、cookie 与认证续接；429/503 在 network interceptor 里关闭并拒绝，避免
`Retry-After: 0` 引起库内 follow-up。不设置 trust-all、跳过主机名或网页可达的信任选项。
默认系统代理仍可能生效；无自动代理认证。

连接/读/写超时 5 秒，完整调用超时 10 秒。同步系统 DNS 用内部单 daemon worker 包装，
调用方最多等待 3 秒；无等待队列，槽位被占时新查询失败。系统解析器可能忽略 interrupt，
继续占用唯一槽，不能保证底层查询已终止或后续查询仍可用。
用户取消、HOME、Activity 销毁主动取消 Call 与 DNS 等待；UI 门控拒绝旧操作结果。
这不提供后台任务、自动重试或任意系统回收后的网络恢复。

仅接受 HTTP 200/application-json，有界读取解压后的 body（最多 16 KiB，额外一字节判超限），
严格 JSON 拒绝字段缺失、重复、未知、类型错误及尾随文档；status 必须 ok，mode 为 remote/local-jobs，
version 为 1–64 可见 ASCII 字符。原始 body 不跨桥；返回数组解析后清零，不保证所有内存副本擦除。
预算不等于 wire bytes、headers/TLS 或进程内存的硬上限。

错误仅为固定白名单：INVALID_SERVER_ORIGIN、SERVER_TLS_REJECTED、SERVER_REDIRECT_REJECTED、
SERVER_BUSY、SERVER_REJECTED、SERVER_RESPONSE_INVALID、SERVER_RESPONSE_TOO_LARGE、
SERVER_TIMEOUT、SERVER_UNREACHABLE 和 CANCELLED，不包含平台异常、Location 或原始响应。

## 权限和验证

两个实验壳新增普通 INTERNET 权限；不新增存储、安装、跨用户或 QUERY_ALL_PACKAGES。
cleartext 与备份继续关闭；网页 CSP 仍只允许本地 IPC，无外部网络来源。
测试 CA 只在 test/androidTest 的内部 client 注入，不进入产品默认客户端、Manifest 或 JS 接口。

原生构建命令见 [README](README.md)。58 项 JVM 包括既有 39 项、15 项真实 TLS socket 和
4 项 DNS 等待/取消/饱和回归。Android instrumentation 另外在普通 UID 下执行 TLS15、DNS4、
严格 JSON12；测试成功只说明临时私有 CA 接缝及系统信任的拒绝行为，不表示系统已信任该 CA。

构建原生/测试/Tauri APK 后，在仓库根运行（cryptography 使用 API 工作区既有依赖）：

```powershell
uv run --project apps/api python experiments/android-package-probe/verify-https.py --serial '<专用模拟器>'
```

此入口只接受模拟器，安装实验 APK，启动独占的随机 loopback 端口，临时生成证书/私钥并清理，
通过真实 Vue/Rust/Kotlin 验证输入取消、HTTP 在连接前拒绝、系统信任拒绝私有证书且未发 HTTP、
握手等待时取消/HOME、旧回调不能覆盖后续错误、字号重建清空地址与大字体取消操作。
临时 UI XML 在 finally 清理，字号恢复；不保存设备序号/端口/私钥或 UI 清单。
可加 `--screenshots '<已有目录>'`，只截空地址窗口和固定错误，不截 Key 或整机清单。
失败不向 stdout 输出成功 JSON。收据须绑定干净源码与实际 APK 哈希，历史收据不改绑。

公网受系统信任证书的正向桥接、真实分析服务、能力协商、实例凭据、上传、真实模型和真机仍未验收。
本轮不能关闭 #71，也不改变 #80/#81/#72/#73 的共享归属和生产门禁。
