> 本页是固定上游 v5.0.0 的通道说明，不是最新版声明；PrivacyTrace 当前采纳与版本检测见 [工作流](workflow.md)。

# 版本通道

TheMasterplan 中央 Actions 接口使用以下版本通道：

```text
main        TheMasterplan 开发与自测
v1          兼容线（已冻结，指向承载 v2.0.0 内容的提交，不再推进；工作流路径 aw-check.yml）
v5.0.0      当前版不可变 Release tag（工作流路径 themasterplan-check.yml）
v4.1.0      历史不可变 Release tag（工作流路径 themasterplan-check.yml）
v4.0.0      历史不可变 Release tag（工作流路径 themasterplan-check.yml）
v1.1.0      历史不可变 Release tag（工作流路径 aw-check.yml）
完整 SHA    最高可复现性和紧急固定
```

## 默认调用

v1 兼容线（`policy-ref` 默认 `v1`）：

```yaml
uses: OasisSaber/TheMasterplan/.github/workflows/aw-check.yml@v1
```

当前版（推荐新采用，tag-only 精确固定）：

```yaml
uses: OasisSaber/TheMasterplan/.github/workflows/themasterplan-check.yml@v5.0.0
with:
  policy-ref: v5.0.0
```

## 严格固定

当前版：

```yaml
uses: OasisSaber/TheMasterplan/.github/workflows/themasterplan-check.yml@v5.0.0
with:
  policy-ref: v5.0.0
  project-check-path: scripts/check.sh
```

v1 兼容线：

```yaml
uses: OasisSaber/TheMasterplan/.github/workflows/aw-check.yml@v1.1.0
with:
  policy-ref: v1.1.0
  project-check-path: scripts/check.sh
```

## 版本一致性

固定版本调用时，`uses` 引用版本必须等于 `policy-ref`：

```text
uses 引用版本 == policy-ref
```

不得出现 `uses: @v1.1.0` 与 `policy-ref: v1` 的组合。

## 发布流程（tag-only）

发布采用单一最终授权门（聚合授权语义见 [core/policy.md](../core/policy.md)，执行方式见 [profiles/git.md](../profiles/git.md) 与 [上游 jj Profile](https://github.com/OasisSaber/TheMasterplan/blob/20eee37922175ad443270e1ab38df7ab38ca5d7b/profiles/jj.md)）。`v1` 兼容线已冻结（2026-08-02，指向承载 v2.0.0 内容的提交），发布为 tag-only：不推进 v1、不执行 @v1 smoke、不要求 v1 与候选对齐。未来是否建立新版本通道作为独立发布任务处理：

```text
main 完成实现与验证
        ↓
独立消费者 smoke 测试
        ↓
最终发布审核（版本号、候选 = 最新 origin/main、tag、Release Notes、全部写操作与顺序）
        ↓
人类一次批准完整发布事务（一次聚合授权，不重复询问）
        ↓
Agent 连续执行：创建并 push annotated tag → 固定 tag 消费者 smoke test → 创建 GitHub Release（--verify-tag）
        ↓
最终远端验证（Release tagName/非 Draft、tag 的 peeled commit SHA）
        ↓
最终汇报
```

固定 tag 消费者 smoke test 通过前不得创建 Release。所有 tag 创建与 Release 发布必须经人类批准；批准后由 Agent 在已列明范围内连续执行，不要求用户逐步确认，也不转交用户手工执行。

## v1 更新规则

`v1` 兼容线已冻结，仅允许：

- 保持当前指向（承载 v2.0.0 内容的提交），不再推进、不再创建新 v1.x tag；
- 禁止 force push；
- 禁止删除或移动；
- 禁止 Agent 凭据更新；
- 禁止直接在 `v1` 开发。

`policy-ref` 默认值保持 `v1`：`@v1` 永远解析到冻结指向的 `aw-check.yml`，现有消费者无需改动。

## 回退流程

```text
消费者临时固定上一正常版本
        ↓
main 创建前向修复
        ↓
发布新的补丁版本
        ↓
新通道发布（v1 冻结期间不推进 v1）
```

不得通过强推 `v1` 回写历史。
