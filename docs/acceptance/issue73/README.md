# PT-MOB-301 本机端到端验收

对应 [#73](https://github.com/MrEcho114/PrivacyTrace/issues/73)。按本次要求，所有测试在本机执行，#81 完成并关闭后即开始最终端到端验收。**当前状态：HANDOFF（按用户指示暂停执行，整票未通过，剩余矩阵移交后续 issue）**；已完成 R01/R04、BUG-01 修复与复验、H01/H02 主链路、N05/N09 服务端负向；H03–H12、N01–N04/N07/N08/N10–N12、F01–F10、R02/R03 未执行，逐条原因见执行记录第 7 节。

## 当前入口与版本

- [本机执行记录（2026-10-21）](execution-20261021.md) 是本轮实际执行的产物身份、通过项、失败项与未执行项；**结论以上述记录为准**。
- [Issue 当前测试要求](https://github.com/MrEcho114/PrivacyTrace/issues/73)管理当前范围；[原准备记录](https://github.com/MrEcho114/PrivacyTrace/issues/73#issuecomment-6270680123)保留当时的交付和证据。
- [baseline.json](baseline.json) 是 2026-10-19 的历史快照，保留原 SHA 和哈希；不能当作当前依赖状态或已部署组合。
- [local-environment.md](local-environment.md) 定义本机拓扑、工具准备、HTTPS 信任与启动门槛。
- [scenarios.md](scenarios.md) 提供主流程矩阵、越权和故障步骤、观察点与通过条件。
- [materials.md](materials.md) 列出可复用的受控源码、样本缺口、设备和网络条件。
- [bugs.md](bugs.md) 定义 BUG 的复现、影响、证据及汇报方式；本轮已登记 BUG-01。
- [evidence/](evidence/) 保存本轮可公开的脱敏证据（R1–R6 摘要、BUG-01 复现输出）。
- [run-template.json](run-template.json) 是单次场景记录模板，没有通过结果。复制到忽略目录后填写真实值。
- [release-readiness.md](release-readiness.md) 给出权限用途、数据流、签名和许可的准备草稿及未满足条件，不是商店申报结果。

本轮以 main `aa414073859463abfaa133c1d12ac1f24c93eeb7` 为被测版本。#81 已关闭，#72/#71/#79 已关闭；#79 的便携 Skill 仍为非阻塞扩展。物理设备与公网路径仍列未验证，历史收据保持原文。

## 执行顺序

1. 重新读取 #73、#81、#72 的当前执行记录、原生依赖、最新 main 与关联 PR。先确认上游要求的产物、验收和 owner 交接均已完成；仅 closed 或 CI 绿灯不足以放行。
2. 以实际可用的同一组合新建运行记录，锁定 Android 安装产物、模拟器、两套本机 HTTPS 实例、API/编排/Runner/扫描镜像、迁移和协议。保留历史快照原值。
3. 按材料清单准备专用测试环境、受控安装包、两套互不共享访问材料的任务作用域。记录材料许可及哈希；真实 APK 的解析和扫描只走原有受限 Docker。
4. 使用同一客户端主流程完成 12 个组合；随后按场景表在该流程上注入负向、故障和恢复条件。注入仅限专用测试环境，不操作生产服务。
5. 为每个案例填写实际设备/网络/处理方式、输入、动作、外部结果、脱敏证据和 SHA。失败、未执行、依赖阻塞分别保留；不能用截图外观、预制报告或组件测试补成端到端通过。
6. 在本机运行仓库权威检查及全部相关专项；远端 CI 只作交付 SHA 核对，不能补成本机执行。逐项汇总通过、失败、阻塞和跳过；合并、生产部署、商店提交和公开分发仍分别授权。

依赖查询（只读，仓库根目录）：

```powershell
gh issue view 73 --repo MrEcho114/PrivacyTrace --comments
gh api repos/MrEcho114/PrivacyTrace/issues/73/dependencies/blocked_by --jq '.[] | {number,state,title}'
gh api repos/MrEcho114/PrivacyTrace/branches/main --jq .commit.sha
```

## 结果与证据约束

`NOT_RUN` 表示没有执行；`BLOCKED` 需记录实际缺失的前置；`FAILED` 需有实际执行与失败观察；`PASSED` 需满足案例全部条件并有可读回的版本绑定证据。扩展案例可标 `NOT_APPLICABLE` 并说明理由，必测案例不能靠排除或缩小分母通过。

每个案例独立复制模板，实际运行后将 `record_kind` 改为 `EXECUTED_CASE`；未运行的阻塞记录仍保持模板类型并填写原因。`case_id` 使用场景表 ID，`device_kind` 和 `network_kind` 写实际环境类型。`components` 每项记录 `{name, size_bytes, sha256}`，`evidence` 每项记录 `{ref, sha256, scope}`；引用只指向已审查的脱敏附件，不放原始秘密。运行记录内 `source_commit` 是被测组合主提交，客户端及各镜像另记精确身份。单个案例通过时也保持 `final_acceptance_passed=false`，整票结论需另行汇总全部必测项与依赖。

准备完成不等于上述场景完成。设备类型、系统/WebView、网络路径、模型端点类型与容器隔离按实际记录，未知值留 null。模拟器必须安装实际客户端，使用真实业务/持久队列/受限 Docker；bridge 替身、离线回放和预置报告只能证明各自范围。物理设备、公网路径、外部模型能力和商店审核单列未验证，不作为本次本机组合通过的门槛。

原始 APK、完整真实政策、抓包、数据库、签名材料、访问令牌、个人 Key 和身份信息留在受保护的本机证据区；公开记录只包含受控样本别名、摘要、脱敏观察及可访问的脱敏附件。含凭证的 URL、header、命令行和原始截图不能直接上传。代理负责生成和检查记录，用户不需要重复填表。

静态权限是能力，invoke 是潜在线索；政策原句是声明，上下文推断单列。UNKNOWN / PARTIAL / UNREVIEWED 及附件未检查状态保持真实，不因验收准备或辅助补入自动提升。

## 本轮完成边界

本次交付测试要求和本机环境准备，最终案例仍待 #81 交付后执行。实际构建、安装、TLS、扫描与恢复结果逐项记录，不把环境启动或模板空值当作最终通过；上架准备仍按其独立材料评估。
