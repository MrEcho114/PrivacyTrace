# PR #148：Oasis review 后的轮询修订

来源：[OasisViridis 的 review](https://github.com/MrEcho114/PrivacyTrace/pull/148#pullrequestreview-5600338024)，
审阅 head `4f88ac18c28ae270559af9217ecacaa1ff7cb451`。用户随后明确要求按 review 修复。
审查者没有提出确定性合并阻断；本次落实其共享配额、退避与抖动建议。
仍由原会话在本 PR 单点修改 flow/守卫，不改服务端限额、原生桥接契约或其他前端 PR 的文件。

## 修改与行为

- 首次自动进度读取仍为10秒；后续稳定读取间隔为25秒加0–4秒抖动。
  按当前实测每轮5次原生HTTP读取，降低两个客户端共享60/min出口时的自动请求占用，
  为显式刷新和取消留预算。不是面向任意客户端数量或任意服务端限额的全局配额保证。
- `SERVER_BUSY` 后保持错误可见和原任务状态，60、120、240秒分级退避，另加0–10秒抖动；
  最大不足250秒。成功读取后恢复普通频率并重置退避。
  非busy错误与终态停止自动读取，停止/删除会清除等待中的定时器。
- 自动恢复只调用原有 `job`/`read` 读取，恢复材料阶段还会读取 `taxonomy`。显式取消若被拒绝，不显示已取消，也不重放该写操作；
  start、retry、delete 同样不会由恢复定时器调用。重试建立新任务仍须用户显式操作。
- 集中调度先检查 generation，再操作 timer。旧请求在停止/重新恢复之后完成时，
  不得清掉新 generation 的有效定时器。
- 恢复时已取得服务器确认的材料上下文，但read/taxonomy/job首次读取遭busy，
  也保留可恢复的读取阶段并退避。未读到job时保持未知，不编造状态；稍后仅重读该上下文，
  不重开原生恢复对话框。草稿尚无job时读回材料即停表，不创建分析。

## Retry-After 的实际边界

当前 `AnalysisTransport` 与其默认拦截器将429/503统一映射成 `SERVER_BUSY`，
原生桥接没有向页面暴露响应头。本次未扩展该共享契约，采用与当前 API 限流响应
`Retry-After: 60` 一致的保守默认等待，而非声称解析/尊重了任意 Retry-After 值。
若将来传递该头，需要独立验证秒数/HTTP日期、异常值和有界等待；503的不同建议值目前也不可见。
抖动只能降低同步重试概率，不保证消除所有出口竞争。

## 回归与复核

`mobile-polling.test.cjs` 加载真实 TypeScript flow 和 Vue，在共享滚动HTTP预算和固定随机样本中运行。
它建模当前原生fan-out，不是真实双Android设备或完整业务栈验收。

1. 旧head对两个恢复客户端共享60/min、限流后恢复、重复限流退避三项测试失败。
   并核对冷启动首分钟与稳定窗口：20秒间隔仍不足以在首分钟保留两人各自刷新并取消的预算，
   调整至25秒后两个窗口均通过。
2. 修订后12项守卫通过：双客户端持续读取后各自显式刷新/取消；busy期间不读取、稍后恢复原ID；
   分级有界退避及成功后重置；取消不自动重放；stop/remove停表；非busy错误/终态停表；
   旧generation的迟到读取不能清新timer。
   独立复核还发现首次恢复的job busy被旧catch吞掉；新增read/taxonomy/job三阶段及无job草稿
   的busy回读守卫，先复现4项失败，再修正为保留错误和读取阶段，全部通过。
3. 迟到generation守卫在将校验放在清timer之后时会失败，修正次序后通过。
4. 现有 `npm run acceptance:mobile` 通过，保留首次进度读取的浏览器流程预算，
   不修改 #154 owner 的共享执行脚本。该入口仍为受控 bridge 开发走查。
5. 独立Standards/Spec复核指出的首次恢复busy缺口已修复并复核；无未处理finding。
   本机完整入口首个新helper漏接Docker入口，出现8项隔离检查失败（1514通过/196跳过）；
   该失败保留，修正专属helper的socket和同名挂载路径后，原失败位置先2项通过再跑完整入口。
   依赖直连与代理下载过慢的启动尝试在依赖准备阶段取消，复用本地锁定依赖镜像后继续，
   没有改测试、锁文件、隔离门槛或公共Docker daemon。
6. 修正环境后，`PRIVACYTRACE_DOCKER_TESTS=0 bash scripts/check.sh`完整通过：
   API1522 passed/196 skipped，e2e61 passed/4 skipped，Web123 passed/0 skipped；
   Ruff、契约导出无差异、类型和production build通过。跳过项单列，完整Docker配置另由新head CI核对。

本轮源码/测试/验证日志摘要哈希见 [review-verification.json](review-verification.json)。
最终 head 的CI另在PR和工单当前执行记录核对，不用旧head绿灯替代。

## 版本与验收状态

原22项证据及原APK身份仍绑定原运行/提交；没有修改它们的源码、客户端或哈希来冒充新行为通过。
本轮未重建Android APK、未重跑实际双设备或 N12/F05/F06 全链路。
**完整通过仍0/3，整例BLOCKED，#133/#128保持开放。**
最终组合全变体、初始APK独立身份、同作用域历史报告关联和新轮询策略的实际客户端复测仍须补齐。
