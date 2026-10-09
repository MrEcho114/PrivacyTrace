# S1 CodeReview 修复记录（2026-10-08）

对应 PR #27；修复前 HEAD 为 `16223ce09b9a68f50b5a07182c3f59274010c09e`。
本记录为 Codex AI 开发与技术复验，不是 Issue #15 的 A/B 人工证据复核。

## 修复范围

- PT-101：读取根级 `uses-permission-sdk-23`；普通权限与 SDK-23 权限统一仅采纳 `<manifest>` 直接子项和 Android namespace 的 `android:name`，不采信嵌套或伪命名空间声明。
- PT-101：接受二进制十进制/十六进制整数 versionCode；缺省 versionName 可空，支持最多 1024 字符并同步 JSON Schema、TypeScript 契约与 UI 回退。
- PT-301：解析 ContactsContract/MediaStore 的已知 framework URI 常量，通过 `sget-object` 传给 query 时匹配已有规则；未知值和分支情形不扩大推断范围。
- PT-004：首次登记使用事务内 `create_if_absent`，同一任务 ID 不再由不同进程共同覆盖。
- PT-807：将 synthetic 来源与任务 ID 分离，真实 `demo` 任务走作业接口；前端来源回归测试加入 CI。

## 本地复验

- 新增公共 APK CLI 嵌套权限负例：修复前两个参数化用例失败；根级约束修复后通过。合法 SDK-23 声明仍通过。
- 新增非 Android namespace 权限名负例：无 namespace 用例修复前失败，修复后通过；另覆盖 namespaced 元素和真实 TYPE_INT_DEC / TYPE_INT_HEX 编码。
- `PRIVACYTRACE_DOCKER_TESTS=1 python -m pytest apps/api/tests -p no:cacheprovider -q`：**253 passed / 0 skipped**，69.23 秒。存在 1 条已有 Starlette TestClient 弃用警告。
- 上述 Docker 测试使用本轮修复源码重建的 `privacytrace-worker:s1`，镜像 ID 为 `sha256:d22ae818ec4d1d4f055565193ff3f60ae2e7d28e2696320c791c24db84212587`。
- `npm run test --workspace apps/web`：**5 passed**。删除了一个只检验测试自身辅助函数、未覆盖产品代码的用例，不将它计入有效回归。
- Ruff、`npm run typecheck`、`npm run build`、契约重新生成后的一致性比对、`git diff --check`：通过。
- 真实 Chromium 页面 + 本地 API 的受控契约夹具验证：自动选择 `job:demo`、缺省版本显示 `v7`、切换人工示例、切回作业，共 4 项通过，无页面异常。该夹具不是新的真实 APK 分析或人工核验成果。
- 独立 AI 只读复查未发现本范围内新的可确认 P1/P2。

## 交付边界

远程 CI 以本次推送的实际 SHA 和 PR comment 中的 run 链接为准，不用历史 CI 代替。
未提交 APK、私有政策、临时浏览器夹具、截图或无关本地规划文件。
PR 保留 Draft，不合并；S0 PR #26 依赖和 `PENDING_HUMAN_AB` 不因修复或自动化测试通过而解除。
