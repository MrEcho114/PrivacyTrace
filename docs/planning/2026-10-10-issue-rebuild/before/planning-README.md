# [PrivacyTrace 研发与交付排期追踪](https://github.com/MrEcho114/PrivacyTrace/issues/1)

### 项目当前状态与基线
项目当前代码停留在 `ee23ddb854b506ff180c00271405e3dce7a9e9e7`，已具备 Vue + FastAPI + Pydantic 框架基础与 6 状态比对规则，且已有 35 个单测通过。但目前运行依赖于磁盘合成 demo 数据，真实的 APK/DEX 分析、长政策文本解析、分析作业持久化存储和基准评测均处于待做状态。

本期比赛的保底交付目标为：**1 个官方渠道国产 App + 6 至 8 个自建受控 APK 场景 + 证据可查的对照报告 + 完整提交包**。

---

### 阶段导航与关键时间节点
- [S0 #2](https://github.com/MrEcho114/PrivacyTrace/issues/2) **规范确认与契约改造**（2026-10-03 至 10-04，必做）：核验环境依赖，重构数据契约以支持长文本与原句切片。
- [S1 #3](https://github.com/MrEcho114/PrivacyTrace/issues/3) **单样本端到端跑通**（2026-10-05 至 10-08，必做）：**10/08 止损评估**。必须跑通 1 个真实样本全流程。3 至 5 条发现为预期目标，真实结果偏少则按事实交付，失败如实记录并不虚装通过。
- [S2 #4](https://github.com/MrEcho114/PrivacyTrace/issues/4) **受控场景与基准评测**（2026-10-09 至 10-16，必做）：**10/12 止损评估**。评估并冻结可复现范围，若进度紧张优先舍弃 SDK 与在线大模型，保留证据链与人工复核；保底 6 至 8 个受控 APK 场景可推进至 10/16 完成。
- [S3 #5](https://github.com/MrEcho114/PrivacyTrace/issues/5) **提交包与交付归档**（2026-10-17 至 10-22，必做）：**10/17 代码冻结**。停止增加新功能，全面转入离线运行验证、说明材料整理与审核提交流程。10/23 23:59:59 为官方平台截止时间，校内实际截止时间待确认且通常更早，严禁将 10/23 视作校内截止日。
- [P1 #6](https://github.com/MrEcho114/PrivacyTrace/issues/6) **进阶探索能力**（选做，主线通过后按余力推进）：包含大模型抽取插件、第三方 SDK 特征、样本扩充与赛后动态分析预研，绝不阻塞主线提交流程。

---

### 角色分工说明
- **角色 A（代码）**：负责 APK 清单与 DEX 字节码调用提取、受控测试 APK 编写。
- **角色 B（代码）**：负责数据模型契约、政策解析规范、对照判定规则与后端持久化支持。
- **角色 C（代码）**：负责前端证据下钻展示、复核交互、自动化测试脚本与离线环境验证。
- **角色 D（辅助）**：负责样本与公开政策采集录入、材料与视频模板整理。技术判断与事实核验由 A/B/C 完成。

<!-- privacytrace-plan:2026-10-03:overview -->

---

## [[S0] 规范确认与契约改造 (2026-10-03 ~ 10-04)](https://github.com/MrEcho114/PrivacyTrace/issues/2)

### 阶段目标
明确校内节点与开发环境，消除长政策文本与原句证据的字段限制，使数据模型支持证据不足和抽取失败状态。

### 阶段任务清单
- [ ] [PT-010 #7](https://github.com/MrEcho114/PrivacyTrace/issues/7)
- [ ] [PT-511 #8](https://github.com/MrEcho114/PrivacyTrace/issues/8)
- [ ] [PT-709 #9](https://github.com/MrEcho114/PrivacyTrace/issues/9)

返回总索引：[#1](https://github.com/MrEcho114/PrivacyTrace/issues/1)

<!-- privacytrace-plan:2026-10-03:S0 -->

---

## [[S1] 单样本端到端跑通 (2026-10-05 ~ 10-08)](https://github.com/MrEcho114/PrivacyTrace/issues/3)

### 阶段目标与止损说明
实现 1 个官方真实国产 App 的清单解析、DEX 调用提取、政策声明对照与本地结果保存。
**10/08 止损线**：必须跑通 1 个真实样本的完整链路。输出 3 至 5 条结果为目标指引，若样本规范无问题则按实际情况记录，绝不为凑数虚构问题；若遇到技术阻塞如实记录并缩减范围，不伪装通过。

### 阶段任务清单
- [ ] [PT-101 #10](https://github.com/MrEcho114/PrivacyTrace/issues/10)
- [ ] [PT-301 #11](https://github.com/MrEcho114/PrivacyTrace/issues/11)
- [ ] [PT-503 #12](https://github.com/MrEcho114/PrivacyTrace/issues/12)
- [ ] [PT-004 #13](https://github.com/MrEcho114/PrivacyTrace/issues/13)
- [ ] [PT-807 #14](https://github.com/MrEcho114/PrivacyTrace/issues/14)
- [ ] [PT-901 #15](https://github.com/MrEcho114/PrivacyTrace/issues/15)

返回总索引：[#1](https://github.com/MrEcho114/PrivacyTrace/issues/1)

<!-- privacytrace-plan:2026-10-03:S1 -->

---

## [[S2] 受控场景与基准评测 (2026-10-09 ~ 10-16)](https://github.com/MrEcho114/PrivacyTrace/issues/4)

### 阶段目标与止损说明
建立 6 至 8 个自建受控 APK 场景，开展基线对比实验，并在浏览器中验证异常降级。
**10/12 止损线**：评估整体进度并冻结可复现实验范围。若时间紧迫，直接砍掉 SDK 匹配与实时大模型任务，严保代码证据、状态降级与人工复核机制。受控场景编写可推进至 10/13，基准实验与浏览器测试至 10/16 完成。

### 阶段任务清单
- [ ] [PT-902 #16](https://github.com/MrEcho114/PrivacyTrace/issues/16)
- [ ] [PT-903 #25](https://github.com/MrEcho114/PrivacyTrace/issues/25)
- [ ] [PT-808 #17](https://github.com/MrEcho114/PrivacyTrace/issues/17)

返回总索引：[#1](https://github.com/MrEcho114/PrivacyTrace/issues/1)

<!-- privacytrace-plan:2026-10-03:S2 -->

---

## [[S3] 提交包与交付归档 (2026-10-17 ~ 10-22)](https://github.com/MrEcho114/PrivacyTrace/issues/5)

### 阶段目标与提交说明
**10/17 代码冻结**：停止功能开发。全员转入干净环境离线验证、文案事实审校与提交流程。
官方截止时间为 2026-10-23 23:59:59，但团队必须提前确认校内实际审核截止日，建议在 10/20 至 10/22 间完成提交，不把 10/23 当作无风险期限。

### 阶段任务清单
- [ ] [PT-904 #18](https://github.com/MrEcho114/PrivacyTrace/issues/18)
- [ ] [PT-905 #19](https://github.com/MrEcho114/PrivacyTrace/issues/19)
- [ ] [PT-906 #20](https://github.com/MrEcho114/PrivacyTrace/issues/20)

返回总索引：[#1](https://github.com/MrEcho114/PrivacyTrace/issues/1)

<!-- privacytrace-plan:2026-10-03:S3 -->

---

## [[P1] 进阶探索能力 (选做，不阻塞提交)](https://github.com/MrEcho114/PrivacyTrace/issues/6)

### 阶段说明
本阶段全部任务为选做项，仅在 S0 至 S3 核心任务验收且时间充裕时按需承接，任何选做任务未完成均不影响最终作品提交。

### 阶段任务清单
- [ ] [PT-506 #21](https://github.com/MrEcho114/PrivacyTrace/issues/21)
- [ ] [PT-401 #22](https://github.com/MrEcho114/PrivacyTrace/issues/22)
- [ ] [PT-907 #23](https://github.com/MrEcho114/PrivacyTrace/issues/23)
- [ ] [PT-908 #24](https://github.com/MrEcho114/PrivacyTrace/issues/24)

返回总索引：[#1](https://github.com/MrEcho114/PrivacyTrace/issues/1)

<!-- privacytrace-plan:2026-10-03:P1 -->

