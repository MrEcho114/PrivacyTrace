# #136 最终 head 包冷启动通过（e17d2e3）

- 源码：`e17d2e3535ab295cb4905e18f56e309c02c95174`（#157/#148/#160/#163/#168 合并后的 main）
- 包：`PrivacyTrace_322234-final-e17d2e3.zip`
- 生成/验证：2026-10-22（UTC 10:15–11:20）

## 1. 包身份

| 项 | 实测 |
| --- | --- |
| SHA-256 | `fa8ceb5f2dac95568d9a8e9bed4cec3581286396b7cfa8f534ddf179c40cd94a` |
| 字节数 | 41,038,618 |
| ZIP 条目 | 590 |
| 解压后 | 45,224,737 字节；95 个目录 |
| CRC | `zipfile.testzip()` → None |
| 包内清单 | `00_材料清单.md` 逐文件 SHA-256 |
| 解压冷启动 | 590 条目全部落盘；包内源码 `.gitignore`、`docs/deployment/acceptance-scope.json` 就位 |

首轮 `e17` 包冷启动曾因两个**执行机问题**失败，均已修复并保留记录：

1. Docker 构建代理指向旧的 `172.20.10.3`，而 WSL 当前 IP 为 `10.155.217.182`；更新 relay 后 PyPI 可达。
2. 为提速曾把 `docker` 包装脚本放进 PATH，`check_acceptance.sh` 的 `cp "$(command -v docker)"` 把包装脚本复制进 Runner 镜像，导致 Runner 启动 `docker image inspect` 失败（`/usr/bin/docker` 不存在）。移除包装、使用真实 `/usr/bin/docker` 重建后恢复。

## 2. 离线回放

- `demo-web/web/comparison.html`，Playwright 1.64 + Chromium 1248，`setOffline(true)` + 中止全部 http(s)。
- 结果：HTTP 200、标题/H1 正确、18 行、0 外部请求、0 页面错误；390px 表格横向溢出 1848px 作为桌面页面边界保留。
- 收据与截图：`demo-receipt.json`、`demo-1440.png`、`demo-390.png`。

## 3. 包内源码部署冷启动（R04）

- 包内源码不含 `.git`；为满足 `deploy/check_acceptance.sh` 的基线 `201d34da…` 要求，从本机干净克隆导入基线对象后提交包内源码，包内提交 `99598d0e8108e40d37d2ad66a979bbf1630ef509`。
- 结果：`acceptance-summary-20261022T032013Z.json`，退出码 0，**40 pass / 0 fail / 0 skip**（R1 1 / R2 13 / R3 1 / R4 12 / R5 4 / R6 9），`pass_rate_of_verified=1.0`。
- R3 覆盖单 APK 与 base+splits 的真实受限扫描；R4 覆盖停启、故障注入与恢复；R5 覆盖备份恢复与删除重放；R6 覆盖容量与秘密审计。
- 唯一既有豁免 `dedicated-scan-host-verification`（`blocks_this_acceptance=false`）。
- 收据：`r04/`（summary + R1–R6 + topology），`source_sha=99598d0` 为包内提交，不是原仓库 `e17d2e3`；包内产品代码与 `e17d2e3` 同源。

## 4. Android 竖屏

- 11 张原生 1080×1920 截图已随 #168 合并（候选 APK `8BB257DF…`，调试签名，`org.privacytrace.mobile` 1000/0.1.0）。
- 158 MB APK 本体超上传上限 157,286,400 B；改用 29 MB 系统设置包上传成功后，分析启动返回 `UPLOAD_CONFLICT_REFRESH`，任务/报告界面未取得。
- 按 #136 补充说明，条件不足时提交已获得证据和清晰缺口；**最终 APK 完整竖屏链路仍为 PARTIAL/NOT_RUN**，不伪造。

## 5. 与 H 票清单

| 清单项 | 结论 |
| --- | --- |
| R01–R04 最终组合本机证据 | **PASSED**（`65b49f7`，见 `execution-20261022.md`；#160 合并后本包冷启动再次验证部署面） |
| 最终压缩包新目录可安装/运行/停启；单包/splits 报告非空 | **PASSED**（本包，R04 40/0/0） |
| 产物/材料清单、哈希、脱敏、未验证边界 | 清单/哈希/CRC/脱敏通过；若冻结 head 再变，需按同流程重建并复跑 |
| 每个变体预期/实际/证据 | R01–R04 + 本包冷启动记录 |
| 原始状态保留 | 00f9263/112c9e4/e17 的失败尝试均保留，不冒充一次通过 |
| 代码/配置修复复测 | 本包只修执行机 relay/CLI 环境，不改产品代码；复跑全绿 |

## 6. 结论

`e17d2e3` 的最终候选包已完成解压、离线回放和包内源码 R04 冷启动，H 的 R01–R04 与包运行/停启/单包+splits 均已具备本机证据；竖屏证据按补充说明为 PARTIAL。该记录不关闭父票 #128，也不证明 D/E/F 的缺口。
