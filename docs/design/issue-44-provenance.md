# 界面与文案来源

此次复用用户提供的 [Pioneer 当前设计](https://www.figma.com/design/EQis9ep9ZQsEenrUVXwlFU/Pioneer?node-id=824-1279)。颜色、字号与组件状态以 Figma 当前规范页和组件页为准，而非 Pioneer 较早的 HTML 规范。

| 来源节点 | 本次实现 |
| --- | --- |
| 824:1382 Color / Roles | workbench.css 颜色变量 |
| 824:1422 Typography / Read first | 本地 Noto 字体与字号层级 |
| 830:1276 Button | UiButton.vue，含主／次／轻／危险、焦点／禁用／等待状态 |
| 830:1353 Field | UiField.vue，标签、辅助文字、错误关联；页面使用原生可交互输入 |
| 830:1379 Status | StatusTag.vue，独立文字状态与语义底色 |

字体文件复用 Pioneer 现成 Noto Sans SC 与 Noto Serif SC 变量字体，随文件保留各自的 SIL Open Font License。前端使用本地文件，不请求字体 CDN；完整中文字体约 18.8 MB，浏览器按使用加载并缓存。

新页面文案由 Gemini `gemini-3.8-flash-medium` 在 2026-10-11 生成。第一次请求返回 SUCCESS，第二次针对上传／阶段／草稿／固定报告等事实修订后返回 SUCCESS；采用修订 JSON 中的原文，存放在 `apps/web/src/copy.ts`。发送范围由用户明确授权；材料仅为功能简报与文字风格，没有发送 APK、政策全文、代码、密钥或本机路径。

界面中的操作标签、固定示例材料与技术标识由实施代理按设计与项目术语组装。原报告页没有交给模型重新生成事实内容；它的说明改为可展开阅读，已有 API 生命周期保持不变。

纸舟地图与云点统计为人工构造的页面体验材料，网址使用 example.com，不对应真实产品。报告为固定内容；不会把浏览器中的候选编辑发送到模型或规则引擎。

## 2026-10-13 文案修订

用户要求在 PR #46 审查与界面打磨中使用三个去模板化文案技能，并在使用后全局安装。此次直接编辑现有文案，没有重新请求 Gemini。原始生成来源保留；当前 `copy.ts` 已包含这轮修改。技能来源、分工、固定版本和验证范围见 [本轮记录](pr46-review-20261013.md)。
