# PrivacyTrace Android 客户端开发入口

接续 #71 / PR #119 的原生读取、确认、上传和受保护配置，复用生产 Web 的候选、复制回填与报告组件。
当前执行归属与最终交付见 [#72 唯一执行记录](https://github.com/MrEcho114/PrivacyTrace/issues/72#issuecomment-6282283742)。

## 开发链路

1. 在原生窗口选应用、目标实例并确认上传。
2. 自动发现、抓取政策并尝试既有服务端提取；失败时可复制指令/回填，或选择个人模型辅助。
3. 候选可修改或直接继续，不强制逐条勾选。启动分析后读取实际阶段，完成后打开同一任务的报告与证据。
4. 恢复当前实例材料可重新打开已有任务；删除复用原生确认和服务端回执。

分析地址、实例和访问材料在 #71 原生模块内管理。JS 仅调用固定 workflow 动作；报告以只读快照交给现有组件，不由 WebView 再次发送 HTTP 凭据。

个人模型使用设备中保存的完整 HTTPS Chat Completions 地址和 Key。页面只提供模型名称、#79 原指令与主动输入的应用线索；发送前另行原生确认，不自动重试，不发送 APK 或任务访问材料。模型端点不得与当前分析实例同源。配置、请求、返回均不把 Key 交给 JavaScript。
当前适配单次非流式 Chat Completions（`max_tokens=8192`），只接收完整文本响应；不自动调用模型工具，不把普通生成称为联网抓取。回填仍须既有格式/原句校验，完整度/复核/附件未知状态保留。协议字段参考[官方接口文档](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。

## 启动与构建

仓库根目录运行 `npm ci`、`npm run build`。普通浏览器仍打开 Web 工作台；Tauri 中自动进入移动流程。

本目录的 Tauri 配置直接使用 `apps/web/dist`，原生插件按路径复用实验目录中的同一实现，不复制读取器或分析引擎。已有 Rust/Android 工具链时运行：

```text
npm ci
npm run android:prepare
npm run android:build
```

固定版本沿用 #71：Tauri 2.12.4、CLI 2.12.3，Android 初始化脚本固定 API36，并关闭备份和明文传输。本轮不以补齐额外工具链或物理设备矩阵阻塞开发交付；完整 APK/实际设备验证结果须单独记录。

## 本轮关键验证

- `npm run build` 与原有 Web 98 项回归通过。
- `npm run acceptance:mobile` 使用真实生产 Vue 和受控 native bridge 替身，走上传→个人模型/JSON→政策准备→未勾选候选→启动→报告证据→恢复，检查浏览器不发送 API 请求，并输出390/1440px与大字号截图。
- 新 `MobileWorkflowTest` 以实际 Kotlin 核心和临时 TLS 测试服务，验证政策导入/start/report 路径与草稿访问材料，以及模型请求仅到模型服务、分析服务收到0请求。两项通过；测试注入私有CA只存在测试代码，不改变产品系统信任。
- 浏览器 bridge 替身不等于实际 Tauri IPC/Android UI、真实 APK 扫描或实际付费模型。完整APK、真机和部署组合保持独立验收。

按本轮用户要求，以完成开发主链为先，仅做必要验证，不扩展异常矩阵。PR #118 的提取 attempt 协议由原 owner 维护，本轮消费既有兼容端点、不修改其文件或擅自合并。
