# R02 / R04 交接执行单

> 用于把 #136 中**本机无法执行**的两项交给具备条件的人或机器。写这份单子的原因：执行机是 Windows，`docker` 不存在、`wsl.exe` 被宿主策略禁用；而 R02 需要构建并运行受控镜像，R04 首行就要求 `id -u = 0`（Linux root）。这不是"再跑一次"能解决的。

## 0. 结论先行

| 案例 | 本机状态 | 交接后应得 |
| --- | --- | --- |
| **R02** Spec30 六 / 十二场景 | BLOCKED | `six scenarios` 与 `twelve controlled scenarios` 两套证据 |
| **R04** 部署专项 | BLOCKED | 真实部署与恢复收据 |

R03（浏览器与前端验收）、交付包复核与离线回放已在基线 `ffadeb06` 上取得 PASSED。**该结论仅对该基线成立**：最终交付 head 或包产物发生变化时，必须按影响范围重跑并重新绑定证据（至少重跑 `acceptance:browser`、`acceptance:frontend` 与 `verify-demo-offline.cjs`，并重新计算包哈希、条目数与材料清单）。不得把本基线的结果当作最终组合的验收结论。

## 1. 环境要求

| 项 | 要求 | 说明 |
| --- | --- | --- |
| 系统 | **Linux**（Ubuntu 22.04 / 24.04，与 CI `ubuntu-latest` 对齐） | R04 首行 `test "$(id -u)" = 0`，必须 root |
| 容器 | Docker Engine + `docker compose` v2 | 两项都要构建/运行镜像 |
| Python | 3.12 + `uv` 0.11.23 | 版本由 `apps/api/uv.lock` 锁定 |
| Node | 22+ | R02 需要 `playwright@1.62.1` + chromium |
| 磁盘 | ≥ 20 GB 空闲 | 镜像层 + `/var/tmp` 临时构建 |
| 工作区 | **干净且已提交**（`git status --porcelain` 为空） | R04 会检查，未提交会被直接拒绝 |
| 网络 | 能访问 PyPI、npm、Docker Hub | 首次准备需联网 |

## 2. 准备

```bash
git clone https://github.com/MrEcho114/PrivacyTrace.git
cd PrivacyTrace
git checkout <票面指定的最终交付 head>   # 必须用当下交付 SHA；不要沿用任何历史示例提交
git status --porcelain              # 必须无输出
git rev-parse HEAD                  # 记下这个 SHA，证据必须绑定它
date -u +%Y-%m-%dT%H:%M:%SZ         # 记下开始时间

pip install uv==0.11.23
uv sync --project apps/api --locked --extra worker
npm ci
```

## 3. R02：Spec30 两组场景

先装浏览器（CI 用独立目录，避免污染仓库依赖）：

```bash
npm install --prefix tmp/spec30-browser --no-save --package-lock=false playwright@1.62.1
node tmp/spec30-browser/node_modules/playwright/cli.js install --with-deps chromium
```

**六个场景**（suite `spec30`）：

```bash
uv run --project apps/api --locked --extra worker \
  python scripts/validate-spec30.py --suite spec30 --output tmp/spec30-ci
```

**十二个受控场景**（suite `pt907`）：

```bash
uv run --project apps/api --locked --extra worker \
  python scripts/validate-spec30.py --suite pt907 --output tmp/spec30-ci
```

脚本内部会先 `docker build` 受控镜像，再跑场景、导出离线包、做独立离线回放。**任何一步失败都会保留失败证据**，不要手工改写 `tmp/spec30-ci/` 下的产物。

## 4. R04：部署专项

```bash
sudo bash deploy/check_acceptance.sh
```

要求：

- **root**；
- 干净已提交源码；
- 会构建 `privacytrace-api:issue81-test`、`privacytrace-web:issue81-test`、runner 与 scan 镜像，并做上线/回滚/恢复；
- 脚本自己负责清理临时实验室（`tmp/deployment-acceptance/` 保留收据）。

## 5. 产物与交回方式

| 路径 | 内容 |
| --- | --- |
| `tmp/spec30-ci/evaluation/comparison.json` | 场景对比结果 |
| `tmp/spec30-ci/browser-proof/browser-proof.json` | 浏览器证据 |
| `tmp/spec30-ci/offline-proof/offline-proof.json` | 独立离线回放证据 |
| `tmp/deployment-acceptance/` | 部署与恢复收据 |

交回时请附：

1. `git rev-parse HEAD`
2. 开始 / 结束 UTC 时间
3. 两条 `validate-spec30.py` 与 `check_acceptance.sh` 的**退出码**
4. 产物目录（避免贴本机绝对路径）
5. 若有失败：原始失败输出，不要"顺手修好"后只交成功结果

## 6. 写入哪里

- 证据放 `docs/acceptance/issue136/evidence/` 下**自己的命名空间**（例如 `r02-spec30-<sha>/`、`r04-deploy-<sha>/`），不要改他人收据；
- 结果回写 `docs/acceptance/issue136/execution-20261021.md` 的 §6（BLOCKED 表），把对应行改为实际结果；
- 若由他人主责，请在本票评论说明执行人与会话，避免两个会话同时写同一目录。

## 7. 不要做的事

- 不要用 CI 的绿灯替代本机 / 本机所在机器的实际运行记录；
- 不要把 `Mock`、预置报告、`SUCCEEDED` 状态当作真实扫描结果；
- 不要为了让脚本通过而放宽 `deploy/` 或 `scripts/` 里的校验；
- 不要在本票直接修改共享入口文件（`scripts/check.sh`、`deploy/*`），缺陷按 `bugs.md` 的格式记录后交 owner 整合。
