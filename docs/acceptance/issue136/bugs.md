# 缺陷记录（验收 H）

记录口径沿用 [issue73/bugs.md](../issue73/bugs.md)：每条包含编号、严重程度、类别（产品缺陷／环境问题／测试设施缺口）、被测版本、关联场景、前置条件、最短复现、预期／实际、脱敏证据及 SHA256、影响、复现次数与处理状态。未经复现的疑点不计作 BUG。

本票（#136）在本机执行中确认 1 条**测试设施缺口**，不涉及产品行为。

## BUG-136-01 `scripts/check.sh` 在 Windows 上无法自举（2026-10-21）

- **编号**：BUG-136-01
- **严重程度**：中（阻断本机权威检查入口，不影响产品运行）
- **类别**：**测试设施缺口**（检查入口脚本的平台假设错误）
- **被测版本**：`ffadeb06af70072b5ee2d931ee565e5b7e546acd`
- **关联场景**：R01（`bash scripts/check.sh` / `scripts/check.ps1`）
- **前置条件**：Windows + Git Bash，且机器上未预装 `uv`（`command -v uv` 失败）
- **最短复现**：

```text
cd <repo>
bash scripts/check.sh
# → 首次运行进入 bootstrap 分支
#   python3 -m venv .themasterplan/cache/check-tools
#   .themasterplan/cache/check-tools/bin/python -m pip install ... uv==0.11.23
# → /path/to/repo/.themasterplan/cache/check-tools/bin/python: No such file or directory
```

- **预期结果**：脚本完成工具引导并继续执行后续检查
- **实际结果**：在引导阶段立即退出（`set -euo pipefail` 生效），后续任一检查都未执行
- **根因**：`scripts/check.sh:6–10`

```bash
if ! command -v uv >/dev/null 2>&1; then
  python3 -m venv .themasterplan/cache/check-tools
  .themasterplan/cache/check-tools/bin/python -m pip install --disable-pip-version-check uv==0.11.23
  export PATH="$PWD/.themasterplan/cache/check-tools/bin:$PATH"
fi
```

Windows 的 `venv` 只生成 `Scripts/`，不生成 `bin/`。实测该目录为 `Include/ Lib/ Scripts/ pyvenv.cfg`，因此第 8 行的 `bin/python` 必然不存在；第 9 行的 `PATH` 追加同样指向不存在的 `bin/`。

- **脱敏证据**：本机目录结构观察 `Include/ Lib/ Scripts/ pyvenv.cfg`（不适用私有路径）
- **影响**：`docs/agents/local-environment.md` §2 把 Git Bash 的 `bash scripts/check.sh` 列为**权威检查入口**，但该入口的自举分支只对 POSIX 有效。结果是：任何未预装 `uv` 的 Windows 机器都无法通过官方入口跑 R01，只能手工等价拆步（本次即以手工拆步完成，见 [execution-20261021.md](execution-20261021.md) §2）。
- **复现次数**：3（三次独立执行均在同一行失败；其中一次为首次创建 venv，另两次目录已存在）
- **建议修复**：按平台选择解释器路径，例如

```bash
venv=.themasterplan/cache/check-tools
python3 -m venv "$venv"
if [ -x "$venv/bin/python" ]; then py="$venv/bin/python"; bindir="$venv/bin"
elif [ -x "$venv/Scripts/python.exe" ]; then py="$venv/Scripts/python.exe"; bindir="$venv/Scripts"
else echo "venv layout not recognised" >&2; exit 2; fi
"$py" -m pip install --disable-pip-version-check uv==0.11.23
export PATH="$PWD/$bindir:$PATH"
```

或统一改用 `uv` 自带安装器（`python -m uv` 不可用时不引导）。

- **处理状态**：**待修**（本次未提修复 PR；修复属共享入口文件 `scripts/check.sh`，按协作约定应由该文件 owner 串行整合，不在本票直接修改）

## BUG-136-02 静态演示版引用包内不存在的字体文件（2026-10-21）

- **编号**：BUG-136-02
- **严重程度**：低（不影响功能与布局，视觉差异已在包内说明中声明）
- **类别**：**交付包缺陷**（HTML 引用了未随包提供的资源）
- **被测版本**：交付包 `SHA-256 6ba1fbde366fb6acc8ff3054313c7177f43141d08620cf228c9f82b1e9e46967`（源码 `ffadeb06`）
- **关联场景**：交付包离线回放（R03 配套）
- **前置条件**：以 `file://` 打开 `01_作品及成果文件/demo-web/demo.html`
- **最短复现**：

```text
打开 01_作品及成果文件/demo-web/demo.html
控制台：Failed to load resource: net::ERR_FILE_NOT_FOUND   ×2
Network：fonts/NotoSansSC-Variable.woff2    -> 404
         fonts/NotoSerifSC-Variable.woff2   -> 404
```

- **预期结果**：页面引用的字体文件随包提供，或 HTML 不引用包外资源
- **实际结果**：`demo-web/` 下只有 `assets/`（`index-*.css`、`index-*.js`），**无 `fonts/` 目录**；两个字体请求 404，浏览器回退到系统字体
- **脱敏证据**：`evidence/demo-offline-receipt.json` 的 `failed_requests` 中两条 `declared-font-fallback`
- **影响**：功能、布局与可读性不受影响；`说明.txt` 末尾已声明字体回退，属已知差异。但"HTML 引用包内不存在的文件"是包完整性瑕疵，评审逐项核对资源时会看到 404
- **复现次数**：3（三次离线验证结果一致）
- **建议修复**：打包时把构建产物的 `fonts/` 一并复制进 `demo-web/`；或在 `demo.html` 中移除这两个 `@font-face` 引用。修复后应删除 `verify-demo-offline.cjs` 的 `declared-font-fallback` 白名单，使该规则收紧为零
- **处理状态**：**待修**（属交付包打包流程，不在本票直接修改；已在本记录中如实登记）
