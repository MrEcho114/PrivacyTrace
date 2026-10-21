# BUG-01 修复后复验（API 层，同一实验室实例）

- 执行时间：2026-10-21 12:58 +08:00
- 被测镜像：`privacytrace-api:issue73-bug01`（镜像 id `sha256:6c0f7db2…`，`org.opencontainers.image.revision=058435d`，
  对应修复分支 `codex/issue73-discover-inspector-fix` 的产品源码；分支随后 rebase 为 `0a3d61e`，产品源码未变，仅测试文件重排）
- 实例：`d37dbfa8-a9cf-4817-b6da-87ee9f177920`（实验室 `/var/tmp/pt81-329038aa0719`）
- 复现脚本：`replay-discover.py`（与产生 503 证据的同一脚本、同一夹具 APK）
- 夹具：`fixture-base-policy.apk` sha256 `1d14eaddecd7ed2d32a1afe491a8f996e23c76ef30e9330842315e47a13408bf`

## 原始输出（去二进制转义后节选）

```text
create 200      {"id":"31438b402c374b5ba37dc771b5781773","revision":1,…}
package-set 200 {"id":"31438b402c374b5ba37dc771b5781773","revision":2,…,"uploaded":true}
read 200        {"id":"31438b402c374b5ba37dc771b5781773","revision":2,…}
discover 200    {"sources":[{"id":"pending",… },
                            {"id":"src-auto-27314142","title":"Auto Discovered Policy",
                             "url":"http://1.1.1.1/policy.html","source_type":"IN_APP_POLICY",…}]}
read2 200       {"id":"31438b402c374b5ba37dc771b5781773","revision":3,…,"sources":[…, src-auto-27314142 …]}
DRAFT 31438b402c374b5ba37dc771b5781773
```

## 对照

| 项目 | 修复前（`aa41407` + `privacytrace-api:issue81-test`） | 修复后（`058435d` 源码 + `privacytrace-api:issue73-bug01`） |
| --- | --- | --- |
| `POST /api/v1/web/drafts` | 200 | 200 |
| `POST /api/v1/web/drafts/{id}/package-set` | 200（经 Runner） | 200（经 Runner） |
| `POST /api/v1/web/drafts/{id}/sources/discover` | **503** `{"detail":"ISOLATED_INSPECTION_UNAVAILABLE"}` | **200**，新增来源 `src-auto-27314142`（`Auto Discovered Policy`，`http://1.1.1.1/policy.html`） |
| `GET /api/v1/web/drafts/{id}` revision | 2（无新来源） | 3（含自动来源） |

## 说明与边界

- 本证据只证明「自动政策发现不再因控制面无 Docker socket 而 503」这一条；
  来源抓取（政策正文）在实验室中仍依赖受控政策源的连通性，属实验室拓扑，不是产品行为。
- 未修改证书链、未关闭主机名校验；客户端仍为仅信任本机测试 CA 的 debug 构建。
- 该复验在**服务端 API 层**完成；同一修复在 Android 客户端链路上的复验见执行记录 H01 部分。
