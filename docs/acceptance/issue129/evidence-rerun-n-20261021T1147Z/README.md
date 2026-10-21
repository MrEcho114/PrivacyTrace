# A 组 N01/N02 变体补证（2026-10-21）

首轮 N01/N02 记录只有收据与“结果页”截图，缺少逐变体的安装快照、动作序列和请求计数；本目录是针对性补证，保留原记录不覆盖。

## 1. 补证内容

| 变体 | 新证据 | 结论 |
| --- | --- | --- |
| N01a 选择前取消 | `n01a-app-list.png`（取消前应用列表）、`n01a-after-cancel.png`、`n01a-body.txt`、`n01a-actions.txt`、`n01a-snapshot.txt` | 草稿 2→2，无新上传；动作日志记录“app list visible → tapping cancel → returned to material page” |
| N01b 确认时取消 | `n01b-confirmation.png`（确认对话框）、`n01b-after-back.png`、`n01b-actions.txt`、`n01b-snapshot.txt` | 草稿 2→2；动作日志记录“confirmation dialog visible → pressing back → returned” |
| N01c 取消后重选 | `n01c-first-app-list.png`、`n01c-after-reselect.png`、`n01c-actions.txt`、`n01c-snapshot.txt` | 草稿 2→2；两次取消后重选表单仍可用 |
| N02 卸载 | `n02-snapshot.txt`：`pm path failed`（包已不存在）、`n02-after-confirm.png` | `INSTALLATION_CHANGED`；无新草稿、无新 job |
| N02v 版本变化 | `n02v-snapshot.txt`：`versionCode=2`、`splits=[base]`、`lastUpdateTime` | `INSTALLATION_CHANGED`；无新草稿 |
| N02u 不可读 | `n02u-file-mode-unreadable.txt`：`mode=0`；`n02u-file-mode-restored.txt`：`mode=644`；`n02u-snapshot.txt` | `INSTALLATION_CHANGED`；随后恢复 644，无新草稿 |

每个目录的 `n-summary.json` 记录 `drafts_before/after`（均为 2，即运行期间没有新增草稿作用域）、`node_exit` 与 origin。

## 2. 请求计数的边界

本轮尝试用 CDP `Network.requestWillBeSent` 统计客户端 API 请求，但该客户端的 HTTPS 请求经原生传输层发出，WebView 的 CDP 网络域看不到；服务端 access log 也未开启。因此**不伪造请求计数**：以“草稿数 2→2、无新 job、逐变体动作日志/截图/安装快照”作为“无未确认上传”的观察，请求计数记为 `NOT_OBSERVABLE`。这比用 0 冒充“没有请求”更符合证据边界。

## 3. 复跑环境

- 设备：MuMu Android 15 / x86_64，`127.0.0.1:16512`，1080×1920。
- 实例 I：`pt81-c36811dfa963`，宿主转发 `28443`；客户端 origin `https://localhost:29443`。
- 用例：N01a/N01b/N01c/N02/N02v/N02u；N02 后已恢复 base v1，N02v 后已卸载并重装 base v1。
- 驱动：`n-cases.cjs` 本地补证版（增加 `snapshot()`、动作日志、取消前截图、`stat -c %a` 文件模式；不改变产品/服务端）。
