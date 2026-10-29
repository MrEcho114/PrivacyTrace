# 赛务核对清单

依据用户提供的《2026 年第十四届全国大学生数字媒体科技作品及创意竞赛参赛指南》整理；正式信息以赛事报名系统和最新官方通知为准。**全国正式提交截止为 2026 年 10 月 23 日 23:59:59（已结束）**，不另设未经证实的校内提交日期。

## 已核对的规则

- [x] 已取得本届参赛指南，并核对团队学生人数上限为 **5 人**（指南“团队组成”）；[官方赛事通知](https://www.cmit.cn/wap/tongzhigonggao/show-144-45826-1.html)。
- [x] 已核对指南载明的正式提交截止日期；2026-10-23 平台显示通过审核（[#107](https://github.com/MrEcho114/PrivacyTrace/issues/107)），实际附件取回与哈希比对归 [#196](https://github.com/MrEcho114/PrivacyTrace/issues/196)/[#197](https://github.com/MrEcho114/PrivacyTrace/issues/197)。
- [x] 已归档 2026-10-15 官方《参赛作品材料提交规范》（11 页）与《人工智能工具使用情况说明（参赛团队参考模板）》；见 [官方文件归档](source/competition/README.md)。

## 已确定的项目许可

- [x] **项目源码与自写文档采 MIT**（2026-10-23，见 [LICENSE](../LICENSE) 与 [ADR 0006](adr/0006-source-license-mit.md)）。
- [x] 运行期依赖中没有会强制本项目改用 GPL 的强 copyleft 组件：psycopg 为 LGPL-3.0 且只作未修改的 Python 依赖使用，Redis 7.4.8 服务端按 RSALv2/SSPLv1 另按部署条件评估，清单见 [依赖与来源](dependencies.md)。
- [x] 提交候选包已重建并清理 `demo-web/DISTRIBUTION.txt` 旧文案（v5–v7）；[#224](https://github.com/MrEcho114/PrivacyTrace/issues/224) 已于 2026-10-22 关闭，冻结状态见 [#307](https://github.com/MrEcho114/PrivacyTrace/issues/307)。

## 待核定的报名与申报信息

- [ ] 报名学校、组别、最终参赛类别：按赛事指南及报名系统核定，不能以“软件设计与信息安全赛道”作为已确认名称。
- [ ] **实际参赛学生名单**：待成员确认；不得超过 5 人。GitHub 项目六名贡献者不等于六名正式报名学生。
- [ ] 指导教师姓名、单位、实际审核意见与签署日期：目前状态为**待审核／待签署**，不预填完成态承诺。
- [ ] 官方评分项：待逐项对照正式评分要求与作品材料验证。
- [ ] 作品内部 AI 能力要求：待按实际报名类别与作品演示结果独立核验。
- [x] **项目内部 AI 工具使用披露草稿已编制**：见 [披露记录](ai-usage-disclosure.md)；此项“已编制”不代表作者归因已验证、官方表格已填报或教师已审核。
- [ ] AI 使用披露最终版本：待工具使用记录、学生贡献与提交文本核对并由申报人确认；官方模板见 [归档](source/competition/README.md)，按其填写。
- [ ] 原创与第三方依赖、素材、样本使用及 AI 工具来源清单核验。
- [ ] 在线演示、仓库可见性、评委访问方式。
- [ ] 文档页数、视频时长、提交文件格式与大小。
- [ ] APK 采集、政策引用、用户实验流程与授权记录。
- [x] 最终官方系统提交／回执确认：2026-10-23 平台显示「通过审核」（[#107](https://github.com/MrEcho114/PrivacyTrace/issues/107)）；回执与附件字节归 [#196](https://github.com/MrEcho114/PrivacyTrace/issues/196)。

用户于 2026-10-03 授权将仓库改为公开并重命名为 [PrivacyTrace](https://github.com/MrEcho114/PrivacyTrace)，供组员查看和克隆。组员写入权限仍需按仓库设置另行配置。
