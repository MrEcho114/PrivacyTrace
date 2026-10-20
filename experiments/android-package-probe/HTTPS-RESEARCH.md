# 原生 HTTPS 健康检查：一手来源调查

调查日期：2026-10-20。范围为 #71 的独立 Android PoC，只读访问用户选择的服务；本文件记录实现取舍，不构成设备、公网或生产验收。协调记录见 [#71 当前执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/71#issuecomment-6214077158)。

## 选择与版本

本轮选择 **OkHttp 4.12.0**，生产代码仅引入 `com.squareup.okhttp3:okhttp:4.12.0`；JVM 与 Android 测试分别使用同版本 `mockwebserver`、`okhttp-tls` 的测试依赖，不打入产品信任配置。

| 核验事实 | 对本实验的含义 | 一手来源 |
| --- | --- | --- |
| 4.12.0 支持 Android API 21+、Java 8+；该 tag 使用 Kotlin 1.8.21、Okio 3.6.0，JVM target 1.8。 | 与本实验 minSdk 24、Kotlin 1.9.24、Java 17 的基线相符，不需要升级 AGP 8.4.2。Tauri Kotlin 2.2.x 消费旧依赖是本轮兼容性推断，仍须实际构建验证。 | [4.12.0 README](https://github.com/square/okhttp/blob/parent-4.12.0/README.md)、[4.12.0 构建配置](https://github.com/square/okhttp/blob/parent-4.12.0/build.gradle) |
| 核验时最新稳定版为 5.5.0；其版本化构建使用 Kotlin 2.2.21、Kotlin 核心库 2.1.21、Okio 3.18.1。 | 5.x 仍支持 API 21；本轮排除它的理由是现有 Kotlin 1.9.24 工具链与变体依赖的额外兼容工作，不能将 5.x 一概描述为 Android 版本不兼容，也不以新编译器构建版本冒充精确最低消费者版本。 | [当前官方 README](https://github.com/lysine-dev/okhttp/blob/main/README.md)、[5.5.0 版本表](https://github.com/lysine-dev/okhttp/blob/parent-5.5.0/gradle/libs.versions.toml)、[5.5.0 发布记录](https://github.com/lysine-dev/okhttp/blob/parent-5.5.0/CHANGELOG.md) |
| 当前上游安全政策列出 4.x 支持至 **2028-08-31**；4.12.0 发布于 2023-10-16。 | 固定版本适合这个受限 PoC，不能称其为最新安全实现；后续产品接入前重新检查版本、依赖与上游修复。支持承诺不等于所有 5.x 修复已回移。 | [当前政策的固定快照](https://github.com/lysine-dev/okhttp/blob/ba92108a334394a9fb2ee27858f35375cffa6cae/docs/security/security.md)、[4.x 发布记录](https://github.com/lysine-dev/okhttp/blob/parent-5.5.0/docs/changelogs/changelog_4x.md) |

原 `square/okhttp` 仓库当前重定向至 `lysine-dev/okhttp`；上述新地址沿用官方上游，历史行为引用固定 `parent-4.12.0` tag，避免把 5.x 文档当作 4.12 API。[官方仓库](https://github.com/square/okhttp)

未选择平台 `HttpsURLConnection`：它本身可以正确验证 TLS，但实例会继承静态默认 `HostnameVerifier` / `SSLSocketFactory`；Android 明确不鼓励修改全局 verifier。独立 OkHttp Builder 更便于明确审查 cookie、认证、重定向和完整调用超时，并复用其真实 TLS 测试工具。这是本轮工程取舍，不是声称平台 API 不安全。[Android API](https://developer.android.com/reference/javax/net/ssl/HttpsURLConnection)、[4.12.0 Builder](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/OkHttpClient.kt)

## 必须保留的边界

| 边界 | 实现要求与来源 |
| --- | --- |
| TLS 与主机名 | 用全新 `OkHttpClient.Builder()`；生产不设置自定义 `sslSocketFactory`、`trustManager` 或 `hostnameVerifier`。4.12 默认创建平台 trust manager，并使用 `OkHostnameVerifier`；不改 `SSLContext` / `HttpsURLConnection` 全局默认值、不添加安全 provider、不实现跳过校验选项。[客户端源码](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/OkHttpClient.kt)、[握手与主机名核验源码](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/internal/connection/RealConnection.kt) |
| 平台信任含义 | Android 默认信任系统 CA；target API 24+ 默认不信任用户新增 CA。实际行为仍取决于宿主 Network Security Config 和系统，不把“默认 TLS”说成证书固定或自有实例身份认证。[Android 网络安全配置](https://developer.android.com/privacy-and-security/security-config) |
| 凭据隔离 | 独立客户端显式使用 `Authenticator.NONE`、`proxyAuthenticator(Authenticator.NONE)`、`CookieJar.NO_COOKIES`、无 cache；不从已有客户端 `newBuilder()` 继承拦截器/连接配置，不采用 `JAVA_NET_AUTHENTICATOR`。请求固定为 GET，无 body，不设置 Cookie、Authorization 或 Proxy-Authorization；只接收严格无 user-info 的 HTTPS origin，再由原生拼接 health 路径。默认系统代理选择仍可能生效，`NONE` 不表示绕过代理。[Builder 默认值](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/OkHttpClient.kt)、[Authenticator](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/Authenticator.kt) |
| 重定向 | `followRedirects(false)` 与 `followSslRedirects(false)`；所有 3xx 作为失败，不消费 Location 继续请求。这样同源与跨源重定向均不跳转。[重定向分支源码](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/internal/http/RetryAndFollowUpInterceptor.kt) |
| 重试 | 设置 `retryOnConnectionFailure(false)`，但 **4.12 对 503 + Retry-After: 0 仍会再请求一次**，该分支不检查此开关。本轮在 network interceptor 内关闭并拒绝 429/503，以固定 `SERVER_BUSY` 错误终止，避免 503 进入 follow-up；用真实服务端请求计数回归，不能只检查 Builder 字段。若要求所有状态严格一次 GET，还需处理 HTTP/2 coalescing 后的 421 follow-up，或仅使用 HTTP/1.1。[版本化源码](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/internal/http/RetryAndFollowUpInterceptor.kt) |
| 时间与取消 | 设置非零 `connectTimeout`、`readTimeout`、`writeTimeout` 和 `callTimeout`；持有当前 `Call`，取消、离开前台或销毁时执行 `cancel()`，同时抑制过期结果。Call 文档的完整超时覆盖 DNS 到 body；实现通过取消活动连接中止 IO。默认 DNS 是同步 `InetAddress.getAllByName`，所以不能保证底层 DNS 调用立即退出，也不能把线程 interrupt 当作取消请求。设置本地预算并拒绝过期结果，不能声称所有系统阻塞都存在硬截止。[Call API](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/Call.kt)、[RealCall.cancel](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/internal/connection/RealCall.kt)、[系统 DNS](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/Dns.kt) |
| 响应与资源 | 不直接对未知 body 调用 `string()` / `bytes()`；检查声明长度，并对实际读取计数，最多读取本地预算加一字节判超限，关闭 Response。无 Content-Length、分块及解压后的 body 都受实际字节预算约束；只解析有界 JSON，严格检查字段类型及完整文档，不回显原始 body / URL /异常文本。[ResponseBody 内存与关闭契约](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/ResponseBody.kt) |

针对同步 DNS，本轮实施取舍是内部 `HealthDns`：共享单个 daemon worker，以 `SynchronousQueue` 保持无等待队列，调用线程通过有界 `Future.get` 等待（默认 3 秒），超时/取消后取消 future；worker 被占用时新查询失败，不继续积压。该包装限制本地等待与资源数量，不改变系统解析器；底层查询可能忽略 interrupt 并继续占用唯一槽，不能宣称 OS 查询被强制终止、即时 DNS 停止或此时后续查询仍可用。DNS 超时、取消与槽位饱和需单独测试；本文件不预先声称测试通过。参照 [OkHttp 同步 DNS 接口](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/Dns.kt)。

限制：body 预算不等于所有 wire bytes、响应头、TLS 内存或进程内存的硬上限。5.4.0 新增 HTTP/2 响应头总量限制，5.5.0 新增 IP canonicalization 失败时的主机名拒绝修复；不能把这些 5.x 行为宣称为 4.12 保证。官方 advisories 核验时没有已发布条目，也不能据此推导“没有漏洞”。[5.x 变更记录](https://github.com/lysine-dev/okhttp/blob/parent-5.5.0/CHANGELOG.md)、[官方安全公告页](https://github.com/lysine-dev/okhttp/security/advisories)

本轮已将产品客户端固定为 `Protocol.HTTP_1_1`，避免 HTTP/2 连接合并及 421 follow-up；这也排除了上文 HTTP/2 headers 行为，不等于消除所有 HTTP/1.1 资源限制。协议列表设置依据 [4.12.0 Builder](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp/src/main/kotlin/okhttp3/OkHttpClient.kt)。

## 真实 TLS 测试接缝

4.12 的 `HeldCertificate.Builder` 在内存生成密钥和 X.509 证书，支持 `certificateAuthority`、`signedBy`、SAN 和 `validityInterval`；`HandshakeCertificates` 可以分别配置服务端证书链和客户端受信根；`MockWebServer.useHttps(factory, false)` 提供真实 TLS。`start(loopbackAddress, 0)` 使用显式 loopback 与系统分配端口，不占共享固定端口。无需 OpenSSL、写入 PEM、提交私钥或安装 CA。[HeldCertificate](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp-tls/src/main/kotlin/okhttp3/tls/HeldCertificate.kt)、[HandshakeCertificates](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp-tls/src/main/kotlin/okhttp3/tls/HandshakeCertificates.kt)、[MockWebServer](https://github.com/square/okhttp/blob/parent-4.12.0/mockwebserver/src/main/kotlin/okhttp3/mockwebserver/MockWebServer.kt)、[TLS 官方示例](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp-tls/README.md)

测试客户端只信任本用例生成的 CA，通过 **internal 原生构造接缝** 注入 transport；保留默认 hostname verifier。不要使用 `addInsecureHost`、全信任 manager、返回 true 的 verifier、产品 manifest CA 或 JS 可达参数。私有 CA 只让正确 SAN 的证书通过，错误主机名与不受信 CA 必须仍失败。[HandshakeCertificates 的受信根 API](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp-tls/src/main/kotlin/okhttp3/tls/HandshakeCertificates.kt)、[TLS 示例](https://github.com/square/okhttp/blob/parent-4.12.0/okhttp-tls/README.md)

应分别验证 JVM 原始有界 transport 与普通 Android 应用 UID 的 TLS/JSON 解析：受信且 SAN 正确成功；产品默认客户端拒绝测试 CA；SAN 错误失败；3xx 不命中第二个服务；503/Retry-After:0 不重复请求；401/407/Set-Cookie 不带入后续凭据；错误状态、非 JSON、超限/未知长度、慢响应、取消与关闭均有可观察结果。JVM PASS 不替代 Android TLS provider、生命周期或真实公网验证；本调查没有执行设备测试。

## health 能证明什么

当前源码 [main.py](../../apps/api/src/privacytrace/main.py) 的 `GET /api/v1/health` 只返回 `status: ok`、`version: 0.1.0`、`mode: remote | local-jobs`。它没有能力、实例身份、限额或保留规则协商。成功结果只描述本次 HTTPS 访问及 health 响应；版本与 mode 是服务声明，不能作为兼容、生产 ready、上传许可、任务归属或服务实例隔离证明。本轮不实现上传。
