# 评测基线

当前后端测试验证纯规则语义与证据契约；它们不是 Android 测试 App 的端到端 Controlled Benchmark，也不代表真实 App 精度。

## Controlled Benchmark（待构建）

目标 20–30 个行为测试用例，人工 Ground Truth 后再自动评测。覆盖 exact/category/not-declared、政策模糊/冲突、Permission/API/SDK、静态与动态差异、明文/编码/hash 外传和第三方传输。动态相关用例随 P1 另行实施。

`ground-truth.example.json` 是空模板，不包含测试结果。评测需按行为/问题类型匹配预期与实际，报告 TP/FP/FN、Precision/Recall/F1、失败样本和规则版本；没有预测正例或预期正例时说明分母约定。

## Real-world Benchmark（待采集）

7 个 App：5 代表 + 2 挑战。分析单位为 App × 官方发行渠道 × 指定版本。登记表在 `samples/real-world/manifest.csv`，原始 APK 和政策在私有本地目录，人工复核记录在 `evidence/`。

## 用户实验（待开展）

对照原始权限与政策，排除隐私/安全专业背景被试，保存匿名记录与 Ground Truth。记录正确率、完成时间、自评理解和证据定位；不以 UI 美观代替有效性。模板为 `evidence/user-study.template.csv`。
