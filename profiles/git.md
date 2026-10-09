# Git Profile：发布执行

> 本文件规定 Git 工具下发布事务的安全执行方式，是 `core/policy.md` 的
> profile 层：Core 规定何时需要人类批准、聚合授权如何生效、何时失效；
> 本文件规定 Git 下具体如何安全执行。

## 职责

- 确认候选 commit 等于最新 `origin/main`；
- 创建普通 annotated tag 并 push；
- 检查现有 tag；
- 避免强推；
- 避免覆盖现有 tag；
- 发布后验证 commit 对齐（tag 使用 peeled SHA）。

## 发布顺序（tag-only）

与 [docs/release-channels.md](../docs/release-channels.md) 一致，固定顺序为：

```text
创建并 push tag → 固定 tag 消费者 smoke test → 创建 GitHub Release → 最终远端验证
```

tag 先行：tag 是不可变锚点，先建立并让消费者验证，smoke 通过前不得创建
Release。`v1` 兼容线已冻结（指向承载 v2.0.0 内容的提交），**tag-only 发布
不推进 v1、不执行 @v1 smoke、不要求 v1 与候选对齐**。上述全部步骤属于
**一次聚合授权**（`core/policy.md` §2）：人类批准完整发布事务后连续执行，
不在步骤之间重复询问。任何步骤失败都按 `core/policy.md` 停止并重新审核。

## 阶段 A：发布前检查（只读）

以下命令全部在最终发布审核前完成，不产生远端写入。使用 `set -euo pipefail`
或每条检查 `|| exit 1`：任何一项不符合预期都严格失败退出，不得继续：

```bash
set -euo pipefail
git fetch origin

# 候选 commit：必须等于最新 origin/main（SOURCE_BRANCH 固定为 main，
# 不允许使用任意远端 ref 引用的 commit）
SOURCE_BRANCH=main
CANDIDATE=$(git ls-remote origin "refs/heads/$SOURCE_BRANCH" | awk '{print $1}')
[ -n "$CANDIDATE" ] || exit 1

# 目标 tag 与 Release Notes 已在最终审核中列明。
# 运行示例前显式注入，避免文档携带可误执行的历史版本号。
TAG="${TAG:?set TAG to the approved release tag}"
NOTES_FILE="${NOTES_FILE:?set NOTES_FILE to the approved notes file}"

# 1. 目标 tag 必须不存在（远端）
if git ls-remote --tags origin "refs/tags/$TAG" | grep -q .; then
  echo "tag already exists: $TAG" >&2 && exit 1
fi

# 2. 目标 Release 必须不存在
if gh release view "$TAG" >/dev/null 2>&1; then
  echo "release already exists: $TAG" >&2 && exit 1
fi

# 3. 检查本地 tag 状态（tag-only 发布不需要本地分支；仅当本地 tag
#    已存在时触发退出，存在残留时停止并向人类报告，不自行删除）
git show-ref --verify "refs/tags/$TAG" >/dev/null 2>&1 \
  && { echo "local tag already exists: $TAG" >&2 && exit 1; } || true

# 4. 记录审核基线（写入最终发布审核）
#    候选 SHA 必须固定：
APPROVED_CANDIDATE_SHA="$CANDIDATE"
```

任一检查失败即停止：报告给人类并等待重新审核。

### 最终发布审核必须包含

- 发布版本号（`$TAG`）；
- 候选 commit SHA（`APPROVED_CANDIDATE_SHA`，等于最新 `origin/main`）；
- Release Notes 状态与 `NOTES_FILE` 路径；
- 即将执行的全部外部写操作与顺序（tag-only：push tag → smoke → Release）；
- 当前验证结果；
- 停止条件；
- 已知风险。

缺少关键目标或操作范围时，不得请求发布授权。

## 阶段 C：执行已批准操作

仅在人类批准完整发布事务后执行。使用 `set -euo pipefail`，任何失败立即
退出，不猜测、不重试；同一聚合授权范围内连续执行，不重复请求批准：

```bash
set -euo pipefail

# 0. 执行前重新 fetch 并核验授权基线（core/policy.md §4 失效检测）
git fetch origin
CUR_MAIN=$(git ls-remote origin "refs/heads/main" | awk '{print $1}')
[ "$CUR_MAIN" = "$APPROVED_CANDIDATE_SHA" ] \
  || { echo "origin/main moved since approval" >&2 && exit 1; }
# 目标 tag 或 Release 在授权后被创建也构成失效（core/policy.md §4）：
if git ls-remote --tags origin "refs/tags/$TAG" | grep -q .; then
  echo "tag created since approval: $TAG" >&2 && exit 1
fi
if gh release view "$TAG" >/dev/null 2>&1; then
  echo "release created since approval: $TAG" >&2 && exit 1
fi

# 1. 创建普通 annotated tag（必须带注解，禁止轻量 tag 用于发布；
#    不强制要求 GPG 签名）
git tag -a "$TAG" -m "Release $TAG" "$APPROVED_CANDIDATE_SHA"

# 2. push tag（tag 先行：先建立不可变锚点）
git push origin "$TAG"

# 3. 固定 tag 消费者 smoke test
#    在消费者环境验证 tag 指向的提交（@$TAG 可用）；
#    测试未通过时停止并重新审核，不得创建 Release

# 4. 创建 GitHub Release
#    --verify-tag：若 "$TAG" 尚未存在于远端则中止（gh CLI 选项，
#    与本地 GPG 验证无关）
gh release create "$TAG" \
  --verify-tag \
  --title "$TAG" \
  --notes-file "$NOTES_FILE"
```

## 阶段 D：发布后验证

```bash
set -euo pipefail
git fetch origin

# 1. Release：tagName == "$TAG"，且已发布（非 Draft）
gh release view "$TAG" --json tagName,isDraft,isPrerelease
# 核对：tagName == "$TAG"；isDraft == false
# 不要求 targetCommitish == CANDIDATE（Release 的 target 可能关联
# tag 对象，提交对齐以 peeled SHA 验证为准）

# 2. tag 的 peeled commit SHA 等于候选 commit
#    （annotated tag 的 ls-remote 显示 tag 对象 SHA，必须使用
#    refs/tags/<tag>^{} 才能得到 commit SHA）
TAG_COMMIT=$(git ls-remote --tags origin "refs/tags/$TAG^{}" | awk '{print $1}')
[ "$TAG_COMMIT" = "$APPROVED_CANDIDATE_SHA" ] || exit 1

# 3. 无意外 tag 或额外修改（与审核列明的 refs 逐一核对）；
#    v1 兼容线已冻结，不参与本发布验证
```

必须确认：

- Release 的 `tagName` 等于 `$TAG`，且 `isDraft == false`；
- `refs/tags/$TAG^{}` 的 peeled commit SHA 等于候选 commit；
- 不存在意外 tag 或额外修改。

任何差异都构成停止条件：停止并重新提交审核，不猜测、不重试、不掩盖。

## 禁止

- 强推（`--force`、`--force-with-lease`）或任何非快进推进；
- 覆盖或删除现有 tag；
- 使用非 `origin/main` 的候选 commit 发布；
- 创建未经审核列明的 tag 或 Release；
- 在最终发布审核前创建 tag 或创建 Release；
- 在固定 tag 消费者 smoke test 通过前创建 Release；
- 推进、修改或移动 `v1`（兼容线冻结，tag-only 发布不涉及 v1）；
- 删除远端分支或资源（`core/policy.md` §7.1 已合并任务分支清理豁免除外）。

需要执行以上任何操作时，按 `core/policy.md` 的授权失效条件停止并重新审核。
