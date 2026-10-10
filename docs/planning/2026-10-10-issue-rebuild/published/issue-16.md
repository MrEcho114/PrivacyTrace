## Parent

[#4](https://github.com/MrEcho114/PrivacyTrace/issues/4)。统一验收规范：[#30](https://github.com/MrEcho114/PrivacyTrace/issues/30)。

## What to build

**PT-902：扩至六个源码构建受控场景。** 在 [#31](https://github.com/MrEcho114/PrivacyTrace/issues/31) 已贯通的C02/C06路径上补齐C01/C03/C04/C05，六场景均从源码编译、隔离扫描到HTTP/浏览器可复查。保留原工单编号；两个最小场景不重复开发。目标10/13–14，构建队友主责，用户协助受控输入与整合。

| ID | 场景 | 本系统预期 |
|---|---|---|
| C01 | 权限但无对应敏感调用 | INSUFFICIENT_EVIDENCE |
| C02 | 明确类型声明对应调用，继承PT-910 | EXACT_MATCH |
| C03 | 仅上位类别声明 | CATEGORY_MATCH |
| C04 | 实际核对、完整适用政策无声明 | NOT_DECLARED |
| C05 | 否定描述与静态调用并存 | AMBIGUOUS_DISCLOSURE |
| C06 | 政策/适用信息不全，继承PT-910 | INSUFFICIENT_EVIDENCE |

人工候选与独立标签分开，新增场景真值在运行前冻结。C04以实际政策完整性/适用性核对为条件；C05不证明承诺已被违反。只覆盖5类状态；C07多来源冲突/C08 Multidex为保底稳定后扩展，未实施不计数。

## Acceptance criteria

- [ ] 六场景都有独立可核对定义、源码/构建配置、配对政策与输入/标签哈希；可共用构建工程，但场景对应与差异明确，不以同模板副本增加数量。
- [ ] C01/C03/C04/C05按与C02/C06相同入口实际构建、隔离扫描、对照并展示；状态、代码定位及原句/缺失边界可复查。
- [ ] 三方案能消费六场景同一材料并导出逐场景输出供#25正式比较；异常/partial/弃判保留，不预写优于基线结论。
- [ ] 工程fixture数量与受控源码场景分开统计；输入预期不混入算法，不放宽真实样本限制。
- [ ] 记录产物、政策、候选、真值、环境和规则版本；必要行为回归与权威工程检查绑定交付SHA。

## Blocked by

[#31](https://github.com/MrEcho114/PrivacyTrace/issues/31)。只依赖已可用的最小受控路径；旧S0/S1前置均已完成。

<!-- privacytrace-plan:2026-10-10:PT-902 -->
