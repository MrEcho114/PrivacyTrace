# PrivacyTrace S1 阶段技术交付与核验报告

- **日期**：2026-10-03（原计划 10-05 ~ 10-08，提前实施）
- **基线与分支**：分支 `codex/s1-e2e`，基于提交 `7cee0d06bc9c1c8afe7f00ba97bbc73be54bab0e`。
- **PR 关系**：依赖前序 PR #26（未合并），以 [Stacked Draft PR #27](https://github.com/MrEcho114/PrivacyTrace/pull/27) 形式提交；关联工单 Refs #3, #10, #11, #12, #13, #14, #15，不代表相关工单已完结。
- **状态判定**：端到端技术链路已在本地跑通，当前处于 `PENDING_HUMAN_AB` 状态，待技术成员 A 与 B 完成逐行人工核验并签字。

## 1. 任务交付与边界对照

| 任务编号 | 任务定义 | 已实现技术点 | 尚未支持与待办事项 |
| :--- | :--- | :--- | :--- |
| **#10 PT-101** | APK清单/元信息+隔离输入/资源安全 | 解析 AXML 权限；实现 Docker 严格沙箱（只读根目录、仅挂载只读输入、Drop ALL、1 CPU/1GiB 限制） | 生产 Worker 无 JADX，采用字节码兜底；WSL2 下 AppArmor 未开启，依赖 Docker 默认 seccomp |
| **#11 PT-301** | DEX敏感调用证据及locators | 扫描全部 classesN.dex，定位 6 大类敏感调用；提取无分支局部常量 | 复杂控制流保留为 UNKNOWN；未覆盖 Native 库与加壳分析 |
| **#12 PT-503** | 政策离线摄取与切片存储 | 离线摄取 UTF-8 文本，按码点半开区间切片，生成不可变快照与审计日志 | 需人工提供候选列表，无 NLP 自动抽取；不虚构未映射的负向声明 |
| **#13 PT-004** | 作业流水线与审计数据面 | CLI 作业调度、5 秒跨进程文件锁、写入原子化；提供回环审查接口 | SQLite 模式未接运行时；无 HTTP 上传 APK 接口；事件为 `UNAUTHENTICATED_LOCAL_EVENT` |
| **#14 PT-807** | 报告界面与审查交互 | 真实作业展示、代码证据与候选条款对照、Unicode 原文定位、复核备注 | 不作目的与接收方的综合判定，不作合法性或安全性裁决 |
| **#15 PT-901** | 真实样本端到端核验 | GKD v1.12.1 隔离扫描比对，生成确定性哈希，双次运行结果一致 | 仅证明开发者发布关联，未证明运行时展示或同意；双人人工复核待签字 |

## 2. GKD 样本（v1.12.1）核验事实

- **APK 静态数据**：包名 `li.songe.gkd`，versionCode `92`，体积 3,287,479 字节，SHA256 为 `edcc03be24bc54d44c04746b46e2e33244120638e2199450b4407195447466a6`。处理 `classes.dex`，提取 15 项权限声明。APK 未在测试中安装或执行。
- **证据构成（共 6 条）**：
  - 3 条代码事实证据：`AccessibilityService.takeScreenshot`（调用方 `Lr2;->p` 偏移 2）、`UiAutomation.takeScreenshot`（调用方 `Lyw;->A` 偏移 3936）及 1 条 `WRITE_EXTERNAL_STORAGE` 能力声明（标为 `CAPABILITY_ONLY`，不代表已发生实际访问或采集）。
  - 3 条政策证据：1 条快照索引证据，2 条原文句子切片证据。
- **政策摄取状态**：文本 SHA256 为 `bf5917c5c4e9fa2e0700f25db7c17fc0672de0c48de04f6e84e01053871374ea`，快照状态为 COMPLETE，提取状态 PARTIAL，复核状态 UNREVIEWED，附件状态 NOT_CHECKED，适用地区 UNKNOWN。包含 2 条候选声明（分别附带仅调试、旧设备导出条件）。原文中广泛的否定表述未作规则映射，未虚构各类型负向声明。
- **版本关联依据**：官方应用源码中路由 `r=11` 指向该政策页面，发布前文档路由与文件 blob `67021e0d0029251186d4fab2fa4ab2923bdb3411` 保持未变。这属于发布层面的版本对应关系，不证明实际运行中向用户展示或取得明示同意。
- **比对结果**：3 项议题判定均为 `INSUFFICIENT_EVIDENCE`。两次运行归一化哈希均为 `c82ef4d515d01691305fb51ac14cac5c6a9dbfb7837397045a0308014a6de6af`。

## 3. 独立辅助工具核验记录

- **AAPT2 (9.4.1-15978811)**：在严格隔离辅助容器内导出权限，退出码为 0，导出的 15 条权限与分析数据集完全一致，无多余或缺失。
- **JADX (1.5.6)**：固定原有只读、非 root 及无网络等严格隔离条件，仅通过 `JAVA_TOOL_OPTIONS` 将 `user.home` 与 `java.io.tmpdir` 指向容器内有界 `/tmp`（此前首次因默认路径无写权限导致插件初始化失败）。采用官方参数 `--decompilation-mode fallback --no-inline-methods` 对 `r2` 与 `yw` 两个类导出成功（exit 0）。两处 `takeScreenshot` 调用参考均可清晰查见（注意 `yw` 中另有一条同名日志字符串，调用点仅计方法调用）。
- **定位与权威性说明**：辅助工具核验仅作为独立参考，DEX 原始字节码偏移量仍为系统权威证据，生产 Worker 镜像依然不包含 JADX（保持 `UNAVAILABLE_BYTECODE_FALLBACK`）。此项检查不替代人工 A+B 签字。

## 4. 安全、隔离与数据保留边界

- **容器资源限额**：网络配置为 none；用户固定为 non-root（USER 65534）；只读根文件系统，唯一挂载为只读输入文件；限制 1 CPU、1 GiB 内存与 swap、32 PIDs、16 MiB /tmp、8 MiB /dev/shm、stdout/stderr 各 4 MiB。输入 APK 上限 150 MiB，ZIP 解压上限 512 MiB，默认超时 120 秒（最大 180 秒）。
- **生命周期安全**：使用空 Docker 客户端配置，清除 Docker 重定向环境变量；启动前对容器有效配置进行 inspect 检查；容器退出时仅删除自身 UUID 容器，并再次 inspect 确认已移除。
- **宿主机边界**：WSL2 下 AppArmor 未开启，依赖 Docker 默认 seccomp 配置，容器并非虚拟机，不防范内核级逃逸。未修改宿主机全局环境与配置。
- **数据保留说明**：私有目录（`samples/private/`、`evidence/private/`、`data/`、`tmp/`）中的完整政策、APK 文件、日志及反编译文件均不公开。分析产生的 `tmp/` 目录副本长期保留供复核，无自动清理机制，亦无累计磁盘配额，单作业资源限制无法解决长期磁盘占用累积。
- **分析局限**：对运行时行为、目的、接收方、跨境传输及保存期限仍无法做完整推断；未做自动化 SDK 检测、LLM 自动政策提取、动态沙箱取证或用户实验。

## 5. 本地测试与资料索引

- **本地测试**：在启用 `$env:PRIVACYTRACE_DOCKER_TESTS='1'` 环境下，执行 `pytest apps/api/tests` 取得 204 项 passed（0 skipped，包含真实 Docker 容器测试），有 1 条 Starlette/HTTPX 弃用警告。Ruff、模式导出、TypeScript 类型检查及构建全部 PASS。
- **三处测试入口**：CLI 扫描器、HTTP 审查接口及前端端到端交互均验证通过。界面中的备注为 Codex 冒烟测试记录（非人工签字），服务重启后保留；受控的取消/失败测试用例与真实样本完全隔离。
- **远程 CI 说明**：GitHub Actions 单一工作流中包含 `api`、`web`、`isolated-worker` 三个作业。实现提交 `3ef27d050752c2194d64f972be363813ca28b8ff` 的 [GitHub Actions](https://github.com/MrEcho114/PrivacyTrace/actions/runs/37128232003) 已通过：`api`、`web`、`isolated-worker` 三个作业均 success。api 为 197 passed / 7 skipped（默认不启用容器测试）；isolated-worker 启用容器测试，27 passed / 0 skipped。两组测试有重叠，不能相加。记录见 `./s1-remote-ci.receipt.json`。
- **文件索引**：
  - 运行记录与核验摘要：[`./s1-verification.json`](./s1-verification.json)
  - 界面截图证明：[`./s1-report-proof.png`](./s1-report-proof.png)
  - 人工复核确认单模板：[`../../evidence/review.template.md`](../../evidence/review.template.md)
