# PrivacyTrace 品牌资产（Concept C）

状态：2026-10-22 用户采纳 Concept C / Core App Mark，图标包 v1.0 已按原字节入库；Web、Tauri 与 Android 资源引用同一份文件。

## 1. 来源与边界

| 项 | 记录 |
| --- | --- |
| 图标包 | PrivacyTrace · Concept C 品牌 Logo / Android Icon v1.0 |
| 采纳日期 | 2026-10-22 |
| 原始归档 | `PrivacyTrace-Logo-Kit.zip`（SHA-256 `7205576DA89C5DBF4DDA39447F20280A749A07B4B1ADC57F7B9C4B89818D4ADF`） |
| 设计基座 | [`docs/design/concept-foundation/README.md`](../docs/design/concept-foundation/README.md) @ `f3db2b0125ee03eee9083de54ea5702b6bb372ad` |
| 入库方式 | 从图标包逐字节复制；未重绘、未改路径、未改颜色。逐文件校验值见 [`SHA256SUMS`](SHA256SUMS)。 |
| 未入库 | 压缩包、解压目录 `tmp/`、图标包自带的 `design-tokens.json`、`scripts/` 与原 `README.md`；颜色只记录在本文件，不新增第二份 token 文件。 |

变更纪律：不在此目录上做像素级微调。需要改图形、颜色或尺寸时，先按同一流程取得新版图标包并核对归档哈希；新增颜色必须先改设计基座，不在 `brand/` 内另立色值。

## 2. 变体与用途

| 文件 | 内容 | 用途 |
| --- | --- | --- |
| `svg/privacy-trace-symbol.svg` | 标记本体，无四色条；viewBox `215 135 823 823` | 导航、顶栏品牌位、Web 分发副本 |
| `svg/privacy-trace-primary.svg` | 标记 + 四色条；viewBox `205 174 843 850` | 完整品牌图形 |
| `svg/privacy-trace-horizontal.svg` | 标记 + 可编辑 “PrivacyTrace” 字标 + 四色条；viewBox `0 0 1540 430` | 横向品牌签名、宽幅版式 |
| `svg/privacy-trace-reverse.svg` | 深底反白版本，底色 `#252A2E` 已嵌入，四色条保留 | 深色背景展示 |
| `svg/privacy-trace-monochrome.svg` | 单色 `#252A2E` 标记 | 单色印刷、受限底色 |
| `web/favicon.svg` | 与 symbol 同几何的 favicon 矢量 | 浏览器标签页 |
| `web/icon-192.png` / `web/icon-512.png` | 192×192 / 512×512 RGBA 位图 | apple-touch-icon、PWA/主屏图标 |
| `android/res/**` | Adaptive Icon XML + 各密度位图 | Android 8.0+ 启动器 |
| `tauri/icon.png` | 512×512 RGBA | Tauri 平台图标源；已替换 `apps/mobile/src-tauri/icons/icon.png` |

标志图形均为真实 SVG 矢量路径（横向版本的字标例外，见第 7 节），不含嵌入位图、滤镜或伪渐变。反向标志内嵌深色底，放置时不要再叠第二层底色。

## 3. 颜色

以下 10 个值全部来自设计基座，本资产不引入其他颜色。标志文件实际使用白、墨、结构、定位红与四色条；`header` 与 `rule` 只属于产品界面 token，不进入标志文件。

| 角色 | 值 | 用途 |
| --- | --- | --- |
| `paper` | `#FFFFFF` | 阅读工作面、Android 图标背景、反白图形 |
| `header` | `#ECE5D6` | 产品顶栏；不进入标志文件 |
| `ink` | `#252A2E` | 正文；单色标志与反向标志底色 |
| `structure` | `#4C5A68` | 标志主结构；四色条第 1 段 |
| `rule` | `#BFC7CF` | 产品次级分隔；不进入标志文件 |
| `action` | `#D63A2C` | 定位红点；唯一鲜艳色 |
| `stripe-1` | `#4C5A68` | 四色身份条第 1 段 |
| `stripe-2` | `#7A7F4E` | 四色身份条第 2 段 |
| `stripe-3` | `#D2A85E` | 四色身份条第 3 段 |
| `stripe-4` | `#A8432F` | 四色身份条第 4 段 |

红色只属于图形本身，不进入状态、风险或按钮语义；主操作仍由产品主题的 `--pt-action` 承担，两者不互相替代。

## 4. 尺寸规则

- 五个 SVG 都没有固定像素尺寸，按容器等比缩放，不单独拉伸某一个方向。
- `web/favicon.svg` 由浏览器在标签页尺寸下缩放；`icon-192.png`、`icon-512.png` 固定 192×192、512×512，不重采样。
- 横向版本包含未转曲字标；缩到文字不可辨时应改用 symbol，而不是继续压小。
- Tauri 源图固定 512×512 RGBA；平台图标由 Tauri 图标流程生成，不在本目录另存一套。
- Android Adaptive Icon：108×108 dp 视口、66 dp 直径安全圆，主图形边界约 `28.7,30.36`–`79.3,77.64` dp；旧版兼容位图按密度为 mdpi 48、hdpi 72、xhdpi 96、xxhdpi 144、xxxhdpi 192，`ic_launcher_foreground.png` 兼容位图为 108/162/216/324/432。

## 5. Android 资源命名与覆盖方式

| 资源 | 作用 |
| --- | --- |
| `drawable/ic_launcher_background.xml` | 固定纸白 `#FFFFFF` 背景层，无阴影、无预裁剪遮罩 |
| `drawable/ic_launcher_foreground.xml` | 108×108 dp 前景矢量，结构灰 `#4C5A68` + 定位红 `#D63A2C` |
| `drawable/ic_launcher_monochrome.xml` | 纯白 `#FFFFFFFF` 单色路径，由 Android 主题着色；不含红点 |
| `mipmap-anydpi-v26/ic_launcher.xml`、`ic_launcher_round.xml` | `<adaptive-icon>` 入口，引用上述 `drawable` 与 `monochrome` |
| `mipmap-{mdpi,hdpi,xhdpi,xxhdpi,xxxhdpi}/ic_launcher.png`、`ic_launcher_round.png` | 旧版启动器兼容位图 |
| `mipmap-*/ic_launcher_foreground.png` | 兼容 Tauri 模板的位图；Adaptive Icon XML 实际引用 `drawable` 矢量 |

覆盖步骤：

1. 在 `apps/mobile` 运行 `npm ci`、`npm run android:prepare`，由 Tauri Android init 与模板补丁生成 `apps/mobile/src-tauri/gen/android/app/src/main/res`。
2. 构建 APK 前把 `brand/android/res/**` 按相对路径覆盖到该 `res` 目录（同名替换）。仓库的 Android 覆盖管线 `scripts/apply-brand-android-icons.cjs`（同批 Android 品牌任务）执行同一覆盖，并在覆盖后校验文件集合、逐字节哈希与 adaptive XML 引用；`android:prepare` 完成后由该管线覆盖（以 `apps/mobile/package.json` 与脚本实际内容为准）。
3. `AndroidManifest.xml` 继续引用 `@mipmap/ic_launcher`（有圆形设置时同时引用 `@mipmap/ic_launcher_round`）；不要重命名资源。
4. 每次 `android:prepare` / `tauri android init` 重新生成 `gen/android` 后都要重新覆盖；`gen/android` 是生成目录，不入库。
5. 如果 Tauri 模板更新后资源命名不同，先核对生成清单与 Manifest，再调整映射；不要静默覆盖或跳过缺失资源。

## 6. Web 接入

`apps/web/index.html` 的 `<head>` 声明：

```html
<link rel="icon" type="image/svg+xml" href="/brand/favicon.svg" />
<link rel="icon" sizes="512x512" href="/brand/icon-512.png" />
<link rel="apple-touch-icon" href="/brand/icon-192.png" />
```

`apps/web/public/brand/` 是分发副本，必须与 `brand/` 源逐字节一致：

| 分发副本 | 源文件 |
| --- | --- |
| `apps/web/public/brand/privacy-trace-symbol.svg` | `brand/svg/privacy-trace-symbol.svg` |
| `apps/web/public/brand/favicon.svg` | `brand/web/favicon.svg` |
| `apps/web/public/brand/icon-192.png` | `brand/web/icon-192.png` |
| `apps/web/public/brand/icon-512.png` | `brand/web/icon-512.png` |

不据此新增 manifest 或 service worker，也不修改 CSP；图标由 `default-src 'self'` 允许的同源路径提供。

## 7. 未转曲限制

`svg/privacy-trace-horizontal.svg` 中的 “PrivacyTrace” 是 `<text>` 元素（`Noto Sans SC, Microsoft YaHei, Arial, sans-serif`，字重 700），不是轮廓化路径。它在不同系统上的字形与字距可能有差异；需要精确视觉一致时应在最终输出中转为轮廓。仓库内保留图标包的可编辑文本形式，不做手工转曲，否则会破坏与图标包的逐字节一致性。

其余变体均为纯矢量路径，可安全缩放；不要用位图描摹件替代。

## 8. 校验

`SHA256SUMS` 覆盖 `brand/` 下除本 README 与 `SHA256SUMS` 自身外的 29 个资产文件，格式为 `sha256␠␠相对路径`，路径相对 `brand/` 并按路径排序。在 Git for Windows Bash 中可这样复核：

```bash
cd brand && sha256sum -c SHA256SUMS
```

Web 分发副本另可用逐字节比较确认：

```powershell
$pairs = @(
  @('brand/svg/privacy-trace-symbol.svg', 'apps/web/public/brand/privacy-trace-symbol.svg'),
  @('brand/web/favicon.svg', 'apps/web/public/brand/favicon.svg'),
  @('brand/web/icon-192.png', 'apps/web/public/brand/icon-192.png'),
  @('brand/web/icon-512.png', 'apps/web/public/brand/icon-512.png')
)
foreach ($p in $pairs) {
  $a = (Get-FileHash -Algorithm SHA256 -LiteralPath $p[0]).Hash
  $b = (Get-FileHash -Algorithm SHA256 -LiteralPath $p[1]).Hash
  "{0} -> {1}: {2}" -f $p[0], $p[1], $(if ($a -eq $b) { 'OK' } else { 'MISMATCH' })
}
```

## 9. 与 #165 品牌相关验收项的对应

- 单品牌图形：顶栏品牌位与离线报告（同批品牌位接入任务）统一复用 `apps/web/public/brand/privacy-trace-symbol.svg`，不内联第二份 SVG，也不各自写尺寸规则。
- 双端一致：Web favicon/PWA 图标、Tauri 源图与 Android 启动器资源来自同一图标包版本；不允许只改一端。
- 颜色克制：标志只用本文件列出的基座颜色；定位红不进入状态/风险语义，也不与唯一红色主操作抢视觉。
- 文档单点：品牌来源、替换流程和校验方式只记录在本文件与 `SHA256SUMS`，不新增第二份 token 文件。

## 10. NOT_RUN

以下项目尚未执行，不能用静态文件或浏览器合成材料代替：

- Android Gradle 构建、APK 打包与实机安装。
- 真实设备 Launcher 的圆形/圆角裁剪、主题图标（monochrome/themed icon）与不同厂商桌面效果。
- Tauri `android init` 重初始化流程的端到端验收（只验证了资源映射与替换后的文件）。
- Tauri 平台图标重新生成（`tauri icon`）；本轮只替换源 `apps/mobile/src-tauri/icons/icon.png`。
- 真实浏览器标签页、Safari apple-touch-icon、PWA 主屏图标的渲染截图；本轮只验证 link 路径与文件一致性。
