# #133 lane E：实际客户端生命周期实验

只操作本票独立 AVD、Compose 项目、端口、卷和合成任务。复用
`deploy.acceptance.provision` 的实际 PostgreSQL/outbox/Redis/Celery/Runner
部署配方；不增加分析 pipeline，不改共享终态或协议。

## 前提与边界

- Windows 的 Android SDK/JDK17/Node；专用 AVD 名必须为
  `privacytrace-issue133-e`，每个调用显式设置 `PT_ADB_SERIAL`。
- Linux 控制容器名 `pt133e-controller`，只供本票使用。挂载 Docker socket
  与同名宿主路径 `/var/tmp/pt133e`；仓库只读挂载并作为工作目录。
  宿主和容器路径必须一致，否则 Runner 的 bind mount 不是同一输入。
- API/Web/Runner/scanner 镜像来自明确源码，使用已构建的镜像 ID。
  不允许操作其他项目、重启公共 daemon/WSL 或全局 prune。
- `fixture/` 是自己编写且固定预期的受控源码；只编译和安装到测试设备。
  APK 元数据和静态分析只在受限 Docker 中执行。静态 invoke 不代表运行时采集。
- 合成政策候选保留 UNREVIEWED；不使用模型 Key，不升级复核状态。

## 执行入口

在 Linux 控制容器执行：

```sh
python -m deploy.acceptance.issue133.provision \
  --api-image "$API_IMAGE_ID" --web-image "$WEB_IMAGE_ID" \
  --runner-image "$RUNNER_IMAGE_ID" --scanner-image "$SCANNER_IMAGE_ID" \
  --port 28443 --capture-synthetic-capabilities
python -m deploy.acceptance.issue133.control observe
```

`--capture-synthetic-capabilities` **仅用于本票新建合成任务**：为了删除后用旧访问材料
重放，独立代理在自己的 tmpfs 记录合成 Authorization。脚本将其提取到 Linux
700/600 私有目录，只输出单向别名、路由模板、状态和哈希。默认不启用。
严禁接入真实用户、公开日志或导出原始代理文件；清理时销毁整个私有实验目录。

配置客户端调试 APK 的 exact `127.0.0.1` 测试 CA 信任，保留 TLS 验证和
cleartext 禁止；产品默认 manifest 不改。使用真实 Tauri Android 构建、原生包选择器
和确认 UI，不能以 bridge harness 或独立 Gradle 旧资源代替重建后的 APK。
CA/signing/APK 哈希另记，全部原件留私有区。

Windows 先设置 SDK PATH、`PT_ADB_SERIAL`，再创建**忽略目录**中的 client JSON：

```json
{"origin":"https://127.0.0.1:28443","port":28443,"cdpPort":9333,
 "avdName":"privacytrace-issue133-e","runId":"candidate","output":"ABSOLUTE_PRIVATE_OUTPUT"}
```

```powershell
node deploy/acceptance/issue133/client.cjs upload $config
node deploy/acceptance/issue133/client.cjs prepare $config
node deploy/acceptance/issue133/client.cjs begin $config
```

`client.cjs` 复用已有 ADB/CDP 入口。动作还包括 `report`、`refresh`、`background`、
`reclaim`、`force-stop`、`restore`、`offline`/`online`、`cancel-offline`、
`retry-offline`、`cancel`、`retry`、`delete`、`watch`、`snapshot`。
`reclaim` 只向经核对的 debug app UID/PID 发 SIGKILL，并核对 PID 替换；
这是进程死亡注入，不是 LMKD/OEM 的自然回收证明。离线只移除本 AVD 的端口 reverse。
私有 UI 原文、截图和 capability 不进入 Git。

阶段控制：

1. 排队：`control stop-worker` → 客户端 begin → 观察 QUEUED → cancel/delete →
   `control start-worker` → 核对无旧结果和孤儿扫描。
2. 扫描：`control delay-scanner --delay-seconds 20` → begin → `wait-scan` →
   cancel/delete → 观察实际隔离、撤销 fence、资源回收、旧请求。
3. 提交前：`precommit.ps1 -Action cancel|delete -StartAction begin|retry
   -ConfigFile ... -Scope Dn -OutputDirectory NEW`。检测真实扫描后暂停**本票 worker**，
   等待 Runner 对应 operation 的真实结果与 receipt，再操作原生 UI；finally 恢复 worker，
   让旧消费者继续并回读，不能用注入假报告代替真实迟到结果。
4. 上传检查中：`delay-scanner --delay-seconds 80`，客户端 `upload-pending` →
   `wait-scan` → `stop-upload` → `restore-pending` → delete → 迟到回读。
   原生“停止当前操作”只取消传输，已收到材料须显式删除。必须核对删除发生在检查仍运行时；
   本次 40 秒窗口过短的记录保留为局部观察，没有算作上传中删除通过。

`control scope --scope Dn` 在删除前保存旧 job 列表；删除后用
`replay-deleted --scope Dn` 真实 HTTPS 重放旧草稿/启动/任务/报告/取消/重试。
观察器通过正常 instance/RLS 事务查询 PostgreSQL，不修改数据库或终态。
HTTP 观察器请求单列为 OBSERVER，不能计入 Android 原生请求次数。

## 导出和清理

```sh
python -m deploy.acceptance.issue133.cleanup > PRIVATE_CLEANUP_JSON
```

先撤销全部合成作用域、回读 tombstone/材料/容器状态，再删除本票 Compose/卷和私有根目录。
同时停止经核对的专用 AVD。保留只读镜像缓存不代表业务数据残留。
检查过程意外退出时先核对 worker 没有暂停，按 current marker 恢复/清理；不重建其他栈。

宿主私有证据目录中包含执行日志后：

```sh
python -m deploy.acceptance.issue133.export PRIVATE_RUN NEW_PACKET_DIRECTORY
python -m deploy.acceptance.issue133.verify NEW_PACKET_DIRECTORY
```

导出白名单记录，拒绝原始 task ID/Authorization，附原始私有记录哈希；公开包只含
摘要。`verify` 回读全部公开引用和 SHA256。任何脚本的 `OBSERVED`、哈希正确、
单阶段成功或 CI 绿色均不自动提升 N12/F05/F06 整例为 PASSED。

本次结果与仍待最终组合补跑的范围见
[`docs/acceptance/issue133/20261021.md`](../../../docs/acceptance/issue133/20261021.md)。
