# API 层负向检查（N05 / N09 可覆盖部分，2026-10-21）

- 执行时间：2026-10-21 13:30–13:39 +08:00（约 05:30–05:39Z；近似，未逐分钟记录）
- 实例：`d37dbfa8-a9cf-4817-b6da-87ee9f177920`（实验室 `/var/tmp/pt81-329038aa0719`）
- 脚本：`api-negative.py`（在实验室命名空间内用 `nsenter --net=/run/netns/privacytrace73` 执行）
- 说明：这两条只覆盖 **服务端 API 层**的拒绝行为；对应场景中客户端侧的表现（固定错误码、UI 状态）仍需在模拟器侧执行，未包含在本证据内。

## N05 访问材料隔离（跨草稿）

```text
drafts a2a95418a4404fe995b7a819ce520510 86f7f1160edb4fc5ba694fa4a00fe535
PASS N05-read-cross-draft     | status=403 body={"detail":"Draft access denied"}
PASS N05-delete-cross-draft   | status=403 body={"detail":"Draft access denied"}
PASS N05-owner-unaffected     | status=200
PASS N05-anonymous-rejected   | status=401
```

结论：用草稿 A 的访问材料读取/删除草稿 B 均被 403 拒绝，B 的持有者读取不受影响，匿名请求 401；未泄露目标资源。

## N09 政策地址指向回环地址

```text
import-external 200  (导入 source id=src-loopback, url=http://127.0.0.1:8080/policy.html)
PASS N09-loopback-fetch-blocked | status=200 rejected=True leaked=False
PASS N09-source-recorded-failed | status=failed error=PUBLIC_URL_REQUIRED
```

结论：服务端没有向回环地址发起抓取；请求被 `PUBLIC_URL_REQUIRED` 拒绝并记录在草稿来源上（`status=failed`），响应体里没有任何受控政策正文（`leaked=False`）。注意该端点对“被抓取目标被拒绝”的情况仍返回 200 + 更新后的草稿，判定要依据来源状态与错误码，而不是 HTTP 状态码。

## 汇总

```text
SUMMARY {"checks": 6, "failed": []}
```

清理：两个草稿均 `DELETE` 200 `{"deleted":true,"cleanup_pending":false}`，实例草稿配额归零。

## 边界

- 未覆盖：客户端在 N05/N09 场景下的固定错误码显示、跨实例（I→J）拒绝（N06）、私网/元数据地址、重定向到禁止目标、超大/慢响应等 N09 其余注入项。
- 本条不改变 #73 的结论：整票仍未通过，本轮按用户要求停止端到端验收执行，剩余矩阵移交后续 issue。
