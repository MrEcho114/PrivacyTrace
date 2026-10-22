# #134：F 票独立执行入口

F01/F02/F03/F04/F07 的结果、失败和剩余变体见
[`docs/acceptance/issue134/20261021.md`](../../../docs/acceptance/issue134/20261021.md)。
本轮交付两个运行时修复和部分实际 Android 观察；完整案例通过数为 **0/5**。
组件回归、脚本退出 0、SUCCEEDED、截图或哈希通过都不能单独提升原案例状态。

## 环境与身份

- 使用本票专用 Linux 控制器、Docker daemon、数据根、队列、数据库、PKI、卷及输出目录。
  `/var/tmp/pt134f` 是本票的固定私有根；daemon 与控制器必须解析同一绝对 bind 路径。
- 本机运行使用独立嵌套 daemon，角色配方复用 `deploy.acceptance.provision`。
  它共用宿主内核，不能冒充独立 VM 或专用扫描主机。
- 控制器的本机 Unix socket 必须只连接本票 daemon；Runner 的 socket 组 ID
  必须来自该 daemon 的实际 socket。控制器转发器须保留 HTTP attach 半关闭语义。
  本轮环境失败、修正及原日志哈希保留在收据中。
- 仅 Windows loopback 暴露 HTTPS28453。专用 AVD 必须命名
  `privacytrace-issue134-f`，每次明确设置 `PT_ADB_SERIAL`。
- 使用真实 Tauri Android APK。debug overlay 仅给 exact `127.0.0.1` 增加本票 CA，
  保留链/主机名校验及 cleartext 禁止；这不证明默认系统信任或公网信任。
- 客户端、源码、镜像、签名、迁移、协议、规则和受控输入身份分别记录。
  镜像基线可只读复用，独立环境内的活跃数据和凭据不共享。

## 部署及阶段控制

先在专用 daemon 内准备明确的基线镜像。`Candidate.Dockerfile` 只替换三个被修复
的 Python 模块；其白名单 context 不包含 APK、PKI、日志或工作区缓存。构建时将
已核对的基线 image ID 固定到本票专属 tag，并记录实际输出 image ID，不能只凭 tag 放行。

在本票控制器中执行：

```sh
python -m deploy.acceptance.issue134.lab create \
  --api "$API_IMAGE_ID" --web "$WEB_IMAGE_ID" \
  --runner "$RUNNER_IMAGE_ID" --scanner "$SCANNER_IMAGE_ID"
python -m deploy.acceptance.issue134.lab observe > PRIVATE_OBSERVER_JSON
python -m deploy.acceptance.issue134.lab stop --role worker
python -m deploy.acceptance.issue134.lab start --role worker
```

角色限于 api/dispatcher/worker/runner/redis；pause/resume 也只作用于从本票持久 owner
记录解析、再次核对 Compose project 标签的单个容器。恢复后须等真实健康探针就绪。
`state_query.py` 经正常实例/RLS 事务读取数据库，报告摘要验证真实 invoke、政策原句、
非空对照及 Runner inspect/清理收据。它是内部观察器，不能计为 Android/Web 请求。

故障注入前先走通真实基线。F01 记录接收点、同一 task 和重启后客户端；F02 分别固定
PENDING/DELIVERED 后控制 publisher/broker；F03 分组件记录领取、实际租约到期前后
及旧执行权；F04 记录重复投递和新尝试完成后的旧结果；F07 分开记录超时、崩溃和
独立内核 VM 重启。一次只注入一个因素，恢复并读回后再继续。缺少资源只影响对应子步骤。

## 受控输入与客户端

`fixture/expected.json` 在运行前固定预期：一个未执行的 `getDeviceId` 静态 invoke、
DEVICE_IDENTIFIER 和一条自建合成政策原句。MainActivity 只显示文字，不调用该方法。
夹具必须含 launcher Activity，才能被实际原生选择器选到；首个无 launcher 的尝试未计通过。
`fixture/build.ps1 -OutputDirectory NEW_PRIVATE_DIRECTORY` 在新的目录编译、签名和哈希。

准备已安装正式移动壳的本票 AVD、反向端口和忽略目录中的配置：

```json
{"origin":"https://127.0.0.1:28453","cdpPort":9343,
 "runId":"candidate","output":"ABSOLUTE_PRIVATE_OUTPUT"}
```

```sh
PT_ADB_SERIAL=emulator-5640 node deploy/acceptance/issue134/client.cjs upload PRIVATE_CONFIG
PT_ADB_SERIAL=emulator-5640 node deploy/acceptance/issue134/client.cjs prepare PRIVATE_CONFIG
PT_ADB_SERIAL=emulator-5640 node deploy/acceptance/issue134/client.cjs start PRIVATE_CONFIG
PT_ADB_SERIAL=emulator-5640 node deploy/acceptance/issue134/client.cjs refresh PRIVATE_CONFIG
PT_ADB_SERIAL=emulator-5640 node deploy/acceptance/issue134/client.cjs report PRIVATE_CONFIG
PT_ADB_SERIAL=emulator-5640 node deploy/acceptance/issue134/client.cjs drill PRIVATE_CONFIG
```

原生选择/确认和传输来自实际应用；CDP 仅操作页面 DOM，不替换 bridge 或返回报告。
`prepare` 导入本票合成政策并保留未复核候选；source_type 是技术输入，不是官方核验。
原始页面、截图和作用域留私有区。输出的 OBSERVED 与 `case_passed:false` 保留脚本边界。
`delete` 走原生双确认删除；本轮最终由本票运维入口撤销所有合成作用域并读回，未计作 E 票验收。

## 清理和证据

先撤销本票草稿并读回墓碑、材料/上传预留、报告、真实扫描容器与临时输入状态，再执行：

```sh
python -m deploy.acceptance.issue134.lab clean
python deploy/acceptance/issue134/verify.py docs/acceptance/issue134/evidence/20261021
```

`clean` 只删除 owner 记录中的本票 Compose、卷及受限私有根；专用控制器/daemon/外层卷
和 AVD 由创建它们的 owner 按明确名字另行销毁、回读。保留私有审计材料，不提交 APK、
私钥、访问材料或数据库。禁止对共享 WSL、宿主、daemon、其他票的卷或收据执行重置。
公开 index 逐字节核对全部 JSON 与 SHA256；它验证收据完整性，不为原案例自动判定 PASSED。
