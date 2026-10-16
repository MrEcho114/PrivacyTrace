---
status: proposed
---

# 公网服务以 Docker 部署 API，扫描执行使用独立信任边界

2026-10-16，用户选择公网多用户服务，并授权先完成方案和 Issues 更新。保留 Vue 3、Python/FastAPI/Pydantic、Androguard；推荐新增 Compose 控制面、PostgreSQL、Celery/Redis 及专用扫描主机或 VM 的可信 runner，公开 API 和编排进程不持有 Docker socket。原因是当前本机 API 的进程内队列和 JSON 存储无法直接承担远程访问及持久调度，daemon 控制权又能触及扫描宿主。仅将现有 API 装进容器并映射 socket 不能满足公网边界。

本决定沿用 #68 的免登录、任务访问保护、手机个人 Key 本地保存和长期材料保留约定，不新增账号体系。技术选型为后续实施的提案基线，尚未实现或实测；方案、取舍与验收见 [调研与实施方案](../planning/api-docker-20261016.md)。历史 ADR-0001 及当期竞赛验收保持原事实；本扩展另行排期，不改变保底交付范围或授予部署权限。
