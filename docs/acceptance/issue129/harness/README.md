# 验收 A 执行器模板

本目录是 #129 实际执行所用脚本的脱敏模板。占位符与替换规则见 `../environment-recipe.md` 第 8 节；不要直接对这些模板中的占位符运行。

## 文件

| 文件 | 作用 |
| --- | --- |
| `lab-watchdog.sh` | I 实例看门狗：健康非 200 时 `lab-up`、重启 relay、修复政策出口；只操作 `mobile-lab.env` 指定的项目 |
| `preflight.sh` / `preflight-j.sh` | 用例前检查/修复：健康、api 容器、受控提取器 mock、DB model 设置、政策抓取、反向端口 |
| `pt129-llm-mock.py` | 容器内确定性 OpenAI 兼容提取器；只返回政策正文中逐字存在的候选，用于走通既有提取路径，不冒充外部模型 |
| `configure-model-db.py` | 远程模式下通过产品自己的 Postgres 文档存储写 `model.json`（HTTP settings 在 remote 模式被设计性禁止） |
| `count-drafts.sh` | 查询实例业务态中的 draft 作用域数，用于 N01/N02 的“无新草稿”判定 |
| `run-case129.ps1` | H 用例驱动：复位客户端、显式 adb 目标、枚举 WebView socket、反向后运行 `client-case.cjs` |
| `run-n-case.ps1` | N01/N02 驱动：记录前后草稿数并运行 `n-cases.cjs` |
| `n-cases.cjs` | N01a/N01b/N01c/N02/N02v/N02u 的真实客户端操作 |
| `client-case.patch` | 对 PR #137 `deploy/acceptance/mobile/client-case.cjs` 的两处本地修正 |
| `cases/` | H01/H04/H07/H10 用例 JSON（origin 需按 `<DEV_I>/<DEV_J>` 替换） |

## 对执行器的两处修正（建议上游化）

1. **自动准备按钮的重试**：上传完成后的页面切换期间，`prepare()` 可能因 `busy` 尚未清空而直接返回；原驱动只点击一次并等待 180 s，会误报超时。修正为“按钮可点击才点、点击后最多重试 5 次候选页”。
2. **报告页判定收紧**：进度页本身包含“证据/政策”等字样，原 `waitFor(body => body.includes('证据') || body.includes('政策'))` 会在进度页提前通过，把进度页当报告。修正为等待报告专属标题“隐私声明对照”，并最多重试 3 次打开报告。

这两项是执行器缺陷，不是产品缺陷；它们不改变产品结论。上游化由 PR #137 执行器 owner 决定，本票不直接改共享执行器文件。
