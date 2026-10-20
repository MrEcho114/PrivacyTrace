# PT-MOB-301 验收准备包

对应 [#73](https://github.com/MrEcho114/PrivacyTrace/issues/73)，本包完成当前允许前置的准备工作。**状态为 PREPARATION_ONLY，最终端到端验收未执行，工单保持 Open。** 所有操作和记录由交付代理维护，不增加人工签字表。

## 当前入口与版本

- [当前执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/73#issuecomment-6270680123)管理负责人、授权、交付 PR 和后续交接。
- [baseline.json](baseline.json) 固定本轮读取的 main、上游候选、契约/规则/依赖字节哈希。它是准备时的快照，不是已部署的版本组合。
- [scenarios.md](scenarios.md) 提供主流程矩阵、越权和故障步骤、观察点与通过条件。
- [materials.md](materials.md) 列出可复用的受控源码、样本缺口、设备和网络条件。
- [run-template.json](run-template.json) 是单次场景记录模板，没有通过结果。复制到忽略目录后填写真实值。
- [release-readiness.md](release-readiness.md) 给出权限用途、数据流、签名和许可的准备草稿及未满足条件，不是商店申报结果。

准备基线为 main `90aaa2ccc2a537f5f6480085744eb3a44816cb22`。直接硬前置仍是 #81、#72，均 Open；#79 是独立扩展，不计入主流程通过分母或关闭门槛。#81 的 PR #109 已合入该 main，但生产启动仍受 `deploy/runtime-contract.json` 门禁阻止；#80/#71/#72 的 PR #112/#90/#110 尚未合入。本包不吸收这些分支或修改其 owner 的文件。

## 执行顺序

1. 重新读取 #73、#81、#72 的当前执行记录、原生依赖、最新 main 与关联 PR。先确认上游要求的产物、验收和 owner 交接均已完成；仅 closed 或 CI 绿灯不足以放行。
2. 以实际可用的同一组合新建运行记录，锁定 Android 安装产物、设备、官方/自托管实例、API/编排/Runner/扫描镜像、迁移和协议。保留本快照原值，不把历史记录改成当前版本。
3. 按材料清单准备专用测试环境、受控安装包、两套互不共享访问材料的任务作用域。记录材料许可及哈希；真实 APK 的解析和扫描只走原有受限 Docker。
4. 使用同一客户端主流程完成 12 个组合；随后按场景表在该流程上注入负向、故障和恢复条件。注入仅限专用测试环境，不操作生产服务。
5. 为每个案例填写实际设备/网络/处理方式、输入、动作、外部结果、脱敏证据和 SHA。失败、未执行、依赖阻塞分别保留；不能用截图外观、预制报告或组件测试补成端到端通过。
6. 运行仓库权威检查及相关既有专项，绑定实际交付 SHA 的远端 CI。对照全部缺口再形成阶段结论；合并、部署、商店提交和公开分发仍按各自授权执行。

依赖查询（只读，仓库根目录）：

```powershell
gh issue view 73 --repo MrEcho114/PrivacyTrace --comments
gh api repos/MrEcho114/PrivacyTrace/issues/73/dependencies/blocked_by --jq '.[] | {number,state,title}'
gh api repos/MrEcho114/PrivacyTrace/branches/main --jq .commit.sha
```

## 结果与证据约束

`NOT_RUN` 表示没有执行；`BLOCKED` 需记录实际缺失的前置；`FAILED` 需有实际执行与失败观察；`PASSED` 需满足案例全部条件并有可读回的版本绑定证据。扩展案例可标 `NOT_APPLICABLE` 并说明理由，必测案例不能靠排除或缩小分母通过。

每个案例独立复制模板，实际运行后将 `record_kind` 改为 `EXECUTED_CASE`；未运行的阻塞记录仍保持模板类型并填写原因。`case_id` 使用场景表 ID，`device_kind` 和 `network_kind` 写实际环境类型。`components` 每项记录 `{name, size_bytes, sha256}`，`evidence` 每项记录 `{ref, sha256, scope}`；引用只指向已审查的脱敏附件，不放原始秘密。运行记录内 `source_commit` 是被测组合主提交，客户端及各镜像另记精确身份。单个案例通过时也保持 `final_acceptance_passed=false`，整票结论需另行汇总全部必测项与依赖。

准备完成不等于上述场景完成。设备类型、系统/WebView、网络路径、实际模型调用、容器隔离和物理设备覆盖均按实际记录，未知值留 null。浏览器、离线回放、预置数据与平台专项只证明各自范围，不能推导未经执行的组合结论。

原始 APK、完整真实政策、抓包、数据库、签名材料、访问令牌、个人 Key 和身份信息留在受保护的本机证据区；公开记录只包含受控样本别名、摘要、脱敏观察及可访问的脱敏附件。含凭证的 URL、header、命令行和原始截图不能直接上传。代理负责生成和检查记录，用户不需要重复填表。

静态权限是能力，invoke 是潜在线索；政策原句是声明，上下文推断单列。UNKNOWN / PARTIAL / UNREVIEWED 及附件未检查状态保持真实，不因验收准备或辅助补入自动提升。

## 本轮完成边界

本包交付可复用的准备材料和源版本核对。未生成可安装的正式 Android 客户端，未部署官方/自托管服务，未执行本表的最终设备、真实外网、模型和恢复验收，也未取得商店审核或分发许可。真实运行结果及 CI 链接写入当前执行记录与 PR，不把模板中的空值当作通过证据。
