# PT-903 可复算表

评测 SHA：`323780c9a77d7de2bb1857b1b67b4f05fd94a525`。由 recalculate.py 生成。

## 状态、失败、弃判与处理覆盖

| 方案 | 状态一致/分母 | 状态错误 | 执行失败 | 弃判 | DEX COMPLETE |
| --- | --- | --- | --- | --- | --- |
| permission_keyword | 2/6 | 4 | 0 | 0 | 6/6 |
| api_flat | 3/6 | 3 | 0 | 1 | 6/6 |
| privacytrace | 6/6 | 0 | 0 | 2 | 6/6 |

状态一致、失败、弃判和覆盖是不同统计；正确弃判也可计状态一致。

## 全部18行

| 场景 | 冻结目标 | permission_keyword | api_flat | privacytrace |
| --- | --- | --- | --- | --- |
| C01 | INSUFFICIENT_EVIDENCE | EXACT_MATCH | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE |
| C02 | EXACT_MATCH | EXACT_MATCH | EXACT_MATCH | EXACT_MATCH |
| C03 | CATEGORY_MATCH | NOT_DECLARED | NOT_DECLARED | CATEGORY_MATCH |
| C04 | NOT_DECLARED | NOT_DECLARED | NOT_DECLARED | NOT_DECLARED |
| C05 | AMBIGUOUS_DISCLOSURE | EXACT_MATCH | EXACT_MATCH | AMBIGUOUS_DISCLOSURE |
| C06 | INSUFFICIENT_EVIDENCE | NOT_DECLARED | NOT_DECLARED | INSUFFICIENT_EVIDENCE |

## 状态混淆

行是冻结预期，列是实际状态。失败单列；未删除样本。

### permission_keyword

| expected / actual | EXACT_MATCH | CATEGORY_MATCH | NOT_DECLARED | AMBIGUOUS_DISCLOSURE | INSUFFICIENT_EVIDENCE | FAILED_OR_NO_STATUS |
| --- | --- | --- | --- | --- | --- | --- |
| EXACT_MATCH | 1 | 0 | 0 | 0 | 0 | 0 |
| CATEGORY_MATCH | 0 | 0 | 1 | 0 | 0 | 0 |
| NOT_DECLARED | 0 | 0 | 1 | 0 | 0 | 0 |
| AMBIGUOUS_DISCLOSURE | 1 | 0 | 0 | 0 | 0 | 0 |
| INSUFFICIENT_EVIDENCE | 1 | 0 | 1 | 0 | 0 | 0 |

### api_flat

| expected / actual | EXACT_MATCH | CATEGORY_MATCH | NOT_DECLARED | AMBIGUOUS_DISCLOSURE | INSUFFICIENT_EVIDENCE | FAILED_OR_NO_STATUS |
| --- | --- | --- | --- | --- | --- | --- |
| EXACT_MATCH | 1 | 0 | 0 | 0 | 0 | 0 |
| CATEGORY_MATCH | 0 | 0 | 1 | 0 | 0 | 0 |
| NOT_DECLARED | 0 | 0 | 1 | 0 | 0 | 0 |
| AMBIGUOUS_DISCLOSURE | 1 | 0 | 0 | 0 | 0 | 0 |
| INSUFFICIENT_EVIDENCE | 0 | 0 | 1 | 0 | 1 | 0 |

### privacytrace

| expected / actual | EXACT_MATCH | CATEGORY_MATCH | NOT_DECLARED | AMBIGUOUS_DISCLOSURE | INSUFFICIENT_EVIDENCE | FAILED_OR_NO_STATUS |
| --- | --- | --- | --- | --- | --- | --- |
| EXACT_MATCH | 1 | 0 | 0 | 0 | 0 | 0 |
| CATEGORY_MATCH | 0 | 1 | 0 | 0 | 0 | 0 |
| NOT_DECLARED | 0 | 0 | 1 | 0 | 0 | 0 |
| AMBIGUOUS_DISCLOSURE | 0 | 0 | 0 | 1 | 0 | 0 |
| INSUFFICIENT_EVIDENCE | 0 | 0 | 0 | 0 | 2 | 0 |

## 计时（秒）

共享场景耗时每场景仅计一次；方案耗时为同次worker中的计算区间。

| 场景 | 共享端到端 | permission_keyword | api_flat | privacytrace |
| --- | --- | --- | --- | --- |
| C01 | 1.734175468 | 0.000009267 | 0.000002726 | 0.000174996 |
| C02 | 1.740038530 | 0.000009508 | 0.000006222 | 0.000209581 |
| C03 | 1.639982880 | 0.000007404 | 0.000007354 | 0.000207446 |
| C04 | 1.632249300 | 0.000007124 | 0.000007113 | 0.000248323 |
| C05 | 1.617379611 | 0.000009117 | 0.000006291 | 0.000208819 |
| C06 | 1.751266304 | 0.000007334 | 0.000007444 | 0.000213758 |
| 合计 | 10.115092093 | 0.000049754 | 0.000037150 | 0.001262923 |

runner六场景阶段实测：11.541916018 秒。两个计时边界不同，不补造差额分解；不是性能基准。

## 既有执行阶段

| 阶段 | 退出码 | 耗时秒 |
| --- | --- | --- |
| build-a | 0 | 27.951330124 |
| build-b | 0 | 10.798145563 |
| rebuild-hashes | 0 | 未测 |
| worker-build | 0 | 7.735544900 |
| six-scenarios | 0 | 11.541916018 |
| source-cli-regressions | 0 | 6.880118643 |
| web-build | 0 | 2.977361574 |
| export-offline | 0 | 0.214477156 |
| browser-fixtures | 0 | 0.214565161 |
| controlled-browser | 0 | 6.537827158 |
| independent-offline | 0 | 16.801275387 |
