# #129 可复用环境配方（I/J + 模拟器 + 受控政策/模型）

本配方是 2026-10-21 实际执行 #129 验收 A 时使用的环境骨架。脚本模板在 `harness/`，本机绝对路径已替换为占位符；占位符含义见文末。该配方只用于本机受控验收，不操作生产或他人栈。

## 1. 拓扑

```
MuMu Android VM（1080x1920, x86_64, adb serial <SERIAL>）
  adb reverse tcp:<DEV_I> tcp:<HOST_I>   # I 实例，用例 origin=https://localhost:<DEV_I>
  adb reverse tcp:<DEV_J> tcp:<HOST_J>   # J 实例，用例 origin=https://localhost:<DEV_J>
        |
Windows localhost:<HOST_I>/<HOST_J>
        |  WSL localhost forwarding
WSL distro <LAB_DISTRO>
  host relay 127.0.0.1:<HOST_I> -> 10.250.73.2:<HOST_I> -> I web 127.0.0.1:<I_WEB_PORT>
  host relay 127.0.0.1:<HOST_J> -> 10.250.73.2:<HOST_J> -> J web 127.0.0.1:<J_WEB_PORT>
  netns <LAB_NS> (10.250.73.0/24), dockerd in that namespace
  compose projects <I_PROJECT> and <J_PROJECT>
     api / worker / dispatcher / gateway / runner / web / postgres / redis
  policy source 10.250.73.1:8080, DNAT 1.1.1.1:80 -> 10.250.73.1:8080
```

两实例必须各自有 compose 项目、PostgreSQL/Redis/outbox、材料卷、PKI、Runner 容器和访问材料；只共享只读镜像和 docker daemon。端口、项目名、卷名、实例 UUID 均在创建时记录。

## 2. 前置

- Linux（本机为 WSL2 Ubuntu）root、docker 29.x、python3.12、openssl；dockerd 可运行在独立 netns。
- 宿主机：Node 24.17、PowerShell 5.1+、MuMu Player 12（或等价 Android 15 x86_64 模拟器）。
- 构建受控夹具：Android SDK platform 34/build-tools 34、JDK 17、Gradle 8.7 缓存可离线。
- 镜像：`privacytrace-api/web/runner/scanner` 与待测 `main` 同 revision；本记录为 `ffadeb0`。

## 3. 创建 I/J 实例

```bash
cd <REPO>/tmp/pt73-mobile-harness
PT_ACCEPTANCE_SOURCE_SHA=<MAIN_SHA> python3 - <<'PY'
from deploy.acceptance.provision import create
for label in ("I", "J"):
    lab = create("privacytrace-api:<TAG>", "privacytrace-web:<TAG>",
                 "privacytrace-runner:<TAG>", "privacytrace-scanner:<TAG>")
    print(label, lab.root)
PY
# 对每个 state 启动并等待 ready
python3 <LAB_HOST_DIR>/harness/lab-up.py <STATE>
# 适配手机可达：重签 web 叶证书（含 localhost SAN）并改写 Caddyfile
bash <LOCAL_ENV>/adapt-mobile-lab.sh <STATE> I <HOST_I>
bash <LOCAL_ENV>/adapt-mobile-lab.sh <STATE> J <HOST_J>
```

`adapt-mobile-lab.sh` 会：
- 用客户端内嵌的测试 CA 重签 `web_cert.pem`（SAN：localhost、privacytrace.test、127.0.0.1）；
- 让 Caddy 同时服务 `https://privacytrace.test:8443` 与 `https://localhost:8443`；
- 把 `deployment.env` 的 `PT_PUBLIC_HOST` 改为 `localhost` 并重建 api/web。

然后为每个实例建立宿主/命名空间中继（模板 `harness/relay-units.md`），把 `HOST_I/HOST_J` 转到各自 web 端口，并运行：

```bash
MOBILE_LAB_STATE=<STATE> bash <LAB_HOST_DIR>/harness/policy-egress.sh
```

## 4. 受控政策与自动候选

政策正文固定为 UTF-8（`http://1.1.1.1/policy.html`），声明两条与静态线索对应的条目；哈希在运行前记录。

自动候选必须走既有服务端提取路径。本机用**容器内回环**的确定性 OpenAI 兼容 mock（`harness/pt129-llm-mock.py`），不能由 UI 手工添加候选冒充：

```bash
# 把 mock 注入 api 容器并启动
docker exec -i <API> sh -c 'cat > /tmp/pt129-llm-mock.py' < harness/pt129-llm-mock.py
docker exec -d <API> /opt/venv/bin/python /tmp/pt129-llm-mock.py
# 远程模式禁止 HTTP settings；直接通过产品的 Postgres 文档存储写 model.json
docker exec -i <API> /opt/venv/bin/python - < harness/configure-model-db.py
```

前置检查（`harness/preflight.sh` / `preflight-j.sh`）会验证：健康 200、mock 可达、DB 中 `enabled=true`、政策抓取 200。

## 5. 设备

```bash
# 创建/启动一个独立 VM（不要复用他人的设备）；分辨率为 1080x1920 竖屏
MuMuManager.exe setting -v <VM_INDEX> -k resolution_mode -val phone.1
MuMuManager.exe control -v <VM_INDEX> restart
adb connect 127.0.0.1:<ADB_PORT>
adb -s <SERIAL> shell wm size          # 1080x1920
adb -s <SERIAL> shell wm density       # 480

# 安装客户端（内嵌测试 CA）与受控 base/split
adb -s <SERIAL> install -r client-local-ca.apk
adb -s <SERIAL> install-multiple -r fixture-base.apk fixture_feature.apk
adb -s <SERIAL> shell pm path org.privacytrace.probe.fixture   # 单 APK 时 1 行，splits 时 2 行
```

H01/H07 需要 **只装 base**；H04/H10 需要 **base+split**。N02 的卸载/版本/不可读变体分别在同一确认窗口注入。

## 6. 运行

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File harness/run-case129.ps1 `
  -CaseFile harness/cases/H01-I.json -EvidenceDir <EVID> `
  -DevicePort <DEV_I> -HostPort <HOST_I>
# J 用例换 DevicePort/HostPort=<DEV_J>/<HOST_J> 且 -PreflightScript preflight-j.sh
```

每条客户端用例前执行 preflight；I 的看门狗（`harness/lab-watchdog.sh`）在共享 daemon 重启后自动 `lab-up` 并重启 relay，J 的 relay 由 `pt129-j-*` 单元恢复。N01/N02 用 `run-n-case.ps1 -Mode n01a|n01b|n01c|n02|n02v|n02u`；N03/N04 直接对真实 HTTPS 入口执行 `n03-packageset.py` / `n04-limits.py`。

## 7. 清理

- 用例 `cleanup: true` 走客户端原生两步删除；N03/N04 每个草稿用能力令牌删除。
- 不删除共享镜像；不 prune 他人容器/卷；不重启宿主公共 WSL/daemon（故障恢复只动本票项目）。
- 证据目录保留 result JSON、报告正文、截图与 SHA-256；原始日志/APK/完整政策留在私有运行区。

## 8. 占位符

`<REPO>` 仓库根；`<LAB_DISTRO>` 实验室 WSL 发行版；`<LAB_HOST_DIR>` 实验室宿主目录；`<STATE>` 创建的实验室状态目录；`<API>` `<I_PROJECT>-api-1` 等容器名；`<SERIAL>`/`<ADB_PORT>` 模拟器显式 adb 目标；`<TAG>` 镜像标签；`<I_/J_WEB_PORT>` 实验室 web 端口；`<HOST_I/J>` 宿主转发端口；`<DEV_I/J>` 设备端口。
