# #80 候选实现验证收据

这些收据记录2026-10-19真实执行结果，原始日志保留在仓库外；仅将本机绝对路径替换为
`<repo>`／`<evidence>`。原始与公开版本SHA256及候选源码摘要在[validation.json](validation.json)。
它们是提交冻结前的收据；最终确切head、远端检查和逐项验收由
[#80唯一执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/80#issuecomment-6248982344)与最终PR给出，不能用旧收据代替新head验证。

清单中的候选源码摘要对应`d786ec31235b5a311ad850153d6a15d3c3d97581`；之后的Runner
空闲缓存回收、终态回调修正及最终head验收另见执行记录，不能把原收据当作修正后的验证。

| 收据 | 实际结果与性质 |
| --- | --- |
| [权威检查](authority.txt) | 原样check.sh；API1643通过／17跳过、Web53通过，含真实PG／Docker／恢复／ENOSPC与新鲜受控源码产物；Ruff、契约零差异及构建通过 |
| [联合组件](components.txt) | 230通过／无跳过；真实PG／Redis／TLS／Docker加配置协议单测，非230项系统端到端 |
| [恢复组合](recovery.txt) | 22通过；两个测试库、不同runtime／migration角色，真实COMMIT拒绝、独立删除重放、显式JSON导入、真实8MiB tmpfs ENOSPC |
| [Runner](runner.txt) | 10通过；真实APK解析、mTLS授权、实际OOM／超时／畸形输出、进程kill孤儿回收、在途取消／删除 |
| [系统链路](system.txt) | 5通过；普通Windows控制进程、真实PG／Celery／Redis／专用WSL2 Runner、重启与重投、权限与终态竞争、两个独立实例并发实际扫描 |
| [源码产物构建](controlled-build.txt) | 固定摘要官方工具链，在无网络受限构建容器中实际编译本仓库冻结的合成APK；不是真实用户APK或动态采集证明 |

权威检查17项跳过：Redis独立专项11、Windows系统专项4、未安装runtime extra的Celery模块1、
Windows路径预检1；相应实际组件／Windows系统在独立入口运行，不能把跳过用例称为此权威
命令运行。后加第五个系统用例在system收据独立运行，最终全仓收据另绑定最终head。

Runner中的故障镜像只制造OOM／超时／畸形输出，明确不分析APK。备份提交后清理错误是
文件系统接口故障注入；COMMIT拒绝由真实PG deferred trigger产生。协议用例、受控契约
事实与真实组件严格区分。没有生产部署、Android真机试用、私人模型或物理断电验收。

失败也已保留：官方JDK首次下载断流（日志SHA256
`722c181862b80c48223a34e9c9571ddcf60cc13ab97dbfba0460ad2bf9004da7`）；第一次构建代码
副本根目录不可读（`c3a6e941bb1aa65c35283fa0475cc0afdce020f2e619001bb2a97c4723b93663`）。
按固定官方摘要重试并仅开放非敏感验证源码副本的目录读取后成功；没有放宽私有材料权限。
大材料恢复夹具初次未递增revision被正确拒绝，随后改为新revision并通过，不弱化不可变性。

最终边界、运行配置与恢复操作见[运行时说明](../../issue80-runtime.md)。静态证据仍只代表
潜在线索／能力，政策保留UNREVIEWED／PARTIAL／NOT_CHECKED，未知不被提升为已发生行为。
