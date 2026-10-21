# Issue #130 受控政策源（N09/N10）

`policy_service.py` 在**一次性实验室网络命名空间**内提供正常/失败/重定向/超大/
慢响应策略。它不是产品组件，不能部署到公网或共享环境。

## 拓扑

- 产品只访问全局可路由占位地址 `1.0.0.1:80`；实验室命名空间把它 DNAT 到
  服务所在的 `10.250.73.2:8082`。
- 内部标记监听绑定 API 容器网络命名空间的 `127.0.0.1:19090`；用于证明
  回环重定向没有真正连入。
- 所有来源保证 `http://`，产品侧 TLS 信任不受影响；测试 CA 只用于实验室
  HTTPS 实例。

## 启动（路径与网段按实际实验室替换）

```bash
# 在实验室 namespace 内
nsenter --net=/run/netns/<lab-netns> python3 policy_service.py &
# 只把占位地址定向到受控服务
nsenter --net=/run/netns/<lab-netns> iptables -t nat -A PREROUTING \
  -d 1.0.0.1/32 -p tcp --dport 80 -j DNAT --to-destination 10.250.73.2:8082
nsenter --net=/run/netns/<lab-netns> iptables -t nat -A OUTPUT \
  -d 1.0.0.1/32 -p tcp --dport 80 -j DNAT --to-destination 10.250.73.2:8082
# API 容器需要一条到占位地址的路由（网关 = 该容器网络的 .1）
nsenter --net=/proc/<api-pid>/ns/net ip route replace 1.0.0.1/32 via <lab-gateway>
```

负向用例：直接回环/私网/元数据；重定向到回环/私网/元数据；自循环重定向；
`/huge`（3 MiB）；`/slow`（30 s）；`/wrong-type`；`/fail`。正向基线：
`/policy.html`。逐变体实际结果见
[`docs/acceptance/issue130/execution-20261021.md`](../../../../../docs/acceptance/issue130/execution-20261021.md)。

注意：`/slow` 的产品抓取预算为 15 s；本记录实测 15.081 s 返回 `FETCH_TIMEOUT`，
没有无限等待。重定向链允许初始请求加 3 次跟随，第 4 个 Location 触发
`FETCH_REDIRECT_LIMIT`，因此请求日志增量为 4。
