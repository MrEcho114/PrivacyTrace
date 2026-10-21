# #132 独立环境复建配方

本配方描述本轮实际装配方式，复跑须新建资源、UTC、实例 UUID、PKI、令牌和输出目录，
不能复用旧摘要当新运行。材料身份见 [source-and-build-identity.json](evidence/source-and-build-identity.json)，
生产配置仍以 [部署说明](../../deployment/README.md)、`deploy/compose.yaml`、
`deploy/runner.compose.yaml`、`deploy/relay.py` 为准。本票未修改这些共享文件。

## 两套根文件系统与本地 Docker

1. 从 Ubuntu 官方 rootfs 新建本票独有 Control/Scan WSL2 发行版，各自安装 Docker29.9.1
   与 containerd，使用自己的 `/var/run/docker.sock`、data-root、PID及工作目录。
   两套 WSL2 共享内核；确认根文件系统 ID、daemon ID、net/mount namespace 不同。
   不复制其他票文件系统、密钥或数据，不操作公共 daemon。
2. 为本票创建 control/scan 私网 namespace 与 veth。本轮 control142.2/29、
   scan143.2/29(I Runner)及143.3/29(J Runner)，宿主网关各为 `.1`。
   为每侧配置独有路由/DNS/iptables，拒绝向外暴露 socket、DB、broker等宿主管理入口。
   防火墙规则、PID与 marker 归属均另存私有记录，清理时逐项撤销。
3. 按固定源码构建 API、Runner、scanner和Web镜像，导出/加载到各自 daemon，记录实际
   image ID与构建源。控制端只运行 I/J 的 web/api/gateway/dispatcher/worker/postgres/redis；
   扫描端只运行两个 Runner。I/J Compose 项目、卷、队列、数据库角色、凭据和 PKI 各自独立。
   可使用既有 `deploy.acceptance.provision` 准备隔离控制面，再将扫描侧迁往真正独立发行版，
   最终必须 inspect 实际两侧拓扑，不能让 provision 的同宿主 Runner 算最终证据。
4. `PT_DEPLOY_MODE=isolated`、公网绑定仅回环；生产门禁保持关闭。一次性 migrate 使用
   独立迁移角色，结束后移除。API/worker不授 Docker socket或扫描路径。
   Scanner固定 immutable image ID。Runner通过本地 socket调用自己的 daemon，
   `PT_RUNNER_ROOT` 挂载必须与扫描 daemon 所见绝对路径相同，权限按 UID10001设置。
5. 按生产 runner.compose 启动，host networking 仅指扫描发行版的专用 net namespace。
   在控制 Docker bridge绑定 `relay.py --listen <bridge-ip> --allow <control-subnet>
   --target <runner-private-ip>`，TLS透传至真实 Runner；反向 Gateway经固定私网地址转发。
   两方向校验 CA/SAN与对端证书指纹，I/J分别授权。没有远程 Docker API。
6. 冷 WSL cgroupfs 可能让 daemon先缓存 SwapLimit=false。运行前实际检查 cgroup
   controllers、docker info 和一次受限扫描 inspect；若缺能力，停止本次案例并保留失败，
   仅在自己新建的 daemon上待控制器就绪后重启。要求实际 Memory=MemorySwap=1GiB，
   不能改断言接受-1。两端 readiness/mTLS health及镜像身份均成功后再建业务任务。

## Android、包集合与同任务政策

创建独立 LDPlayer14 Android14/API34 x86_64，显式 ADB server/serial；本轮2CPU、4GiB、
720×1280/dpi240、WebView146.0.7680.119。不能使用默认设备或日用实例。
按 `apps/mobile` 正常入口以0ad5f56构建debug客户端，临时研究签名仅存私有目录。
在生成构建文件中设置 allowBackup=false、cleartext=false，base信任仅system；
localhost的domain-config额外列出四个本票公开CA（旧I/J和新I/J，以复用同一负向证书
夹具）。链/时间/SAN校验不变，跟踪产品manifest不改。记录APK、签名DER和XML摘要。
默认信任构建单独作拒绝私有CA补充，不可将它代替已配置信任的正向对照。

使用 [fixture源码](../../../deploy/acceptance/issue132/fixtures/README.md) 构建并安装
base和真正的feature_camera，读取实际已安装两组件字节摘要。重建会因签名/ZIP时间
得到新APK摘要，必须重新记录。仅原生选择/确认包集合，不通过JS上传字节替身。
由独有ADB reverse连接本票HTTPS；本轮业务origin I44198/J41044，后端TLS41859/57313。
负向证书服务器另有专用端口，最终APK九项TLS检查和业务过程始终同一包。

I/J分别沿实际客户端选择→确认→上传→同任务辅助补政策/手动候选→启动→报告。
政策为自编研究声明，保留完整文本于私有证据区，公开只记哈希、准确短句偏移。
先固定预期：两manifest能力、Camera.open静态潜在线索；声明保留UNKNOWN，报告应
有非空可复核对照，不强求MATCH。记录已安装/native/server三方组件/指纹、outbox投递、
execution attempt/fence、扫描隔离及清理收据，真实原生报告与DOM政策/API下钻都读回。
通用H驱动若忙态早出UNKNOWN，保留原结果，另等待实际报告再独立取证。

## N05–N08 执行与清理

N05用同一J的独立A与Android B，N06用两个实例各自B。先准备可稳定读取的B草稿、
terminal提取attempt、已完成job/report/evidence，再用本票 `access_matrix.py` 执行
19端点×5材料。每次必须比对B完整状态；任何差异停止，不从变化后重取基线。
原ID双向另做19×2检查：不存在目标应精确404，不用它冒充现存目标403。
保留默认限流，本轮并行矩阵暂停1.3s，原ID暂停10s。实际Stop request和原生切换J时，
将I业务代理响应暂存60s后真正写出，记录当前J选中对象及前后DOM摘要；不能用组件mock
替代。UI驱动串行，避免多个驱动抢同一设备。

N07依次运行正常I/J、坏CA/错SAN/过期/TLS1.0/TLS1.1/降级redirect/HTTP输入。
正向到上传前capabilities对话框后取消；负向记录准确原生错误。显式强制TLS版本的
夹具自检与Android拒绝分开存，不允许坏服务器本来不可达却算拒绝通过。

N08按 [network-config.example.json](../../../deploy/acceptance/issue132/network-config.example.json)
设置显式设备/两实例/各自公开CA和token环境变量，`disposable=true`。准备四条仅操作者
可控的回环TCP隧道，分别连接真实I/J Gateway/Runner，ADB reverse到设备；`origin`
保留真实私网TLS/SAN地址，`connect-to`只改传输目标。此处不提供客户端证书，实际应
收到client certificate required告警。隧道注入是附加门控验证，不能混入普通端口暴露。
七个普通端口检查在各默认端口无这些reverse时运行，结合daemon监听与容器inspect。

```powershell
python -m deploy.acceptance.issue132.android_network --config tmp/issue132/network.json --output-dir tmp/issue132/network-first
```

输出目录必须新建；任务令牌仅stdin，原响应仅私有文件；公开子收据逐字节读回摘要。
最后原生删除I/J、各自材料删除A，检查旧draft/job/report404和cleanup_pending=false；
查询DB/材料/回收计数为0，删除仅本票Compose角色、卷、网、PKI和Runner目录。
撤销本票代理/端口/规则、设备CA/reverse/CDP，卸载app并移除专用模拟器。
核实marker/注册路径后注销仅本票新发行版；保留其他发行版和默认daemon。
失败轮与清理中断均另存新记录，不改写原收据。私有原始证明和构建缓存保留于忽略目录。
