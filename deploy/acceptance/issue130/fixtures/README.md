# Issue #130 受控夹具

这两个 Java 文件是在 `experiments/android-package-probe` 的现有 Gradle 工程上
注入的 B 验收受控行为：

- base：`LocationManager.getLastKnownLocation("gps")`；
- feature split：`ContentResolver.query(content://com.android.contacts/contacts)`。

## 复现

1. 复制 `experiments/android-package-probe` 到独立临时目录（不要改动原工程）。
2. 把 `ProbeBehavior.java` 放到
   `fixture/src/main/java/org/privacytrace/probe/fixture/ProbeBehavior.java`，
   把 `ProbeBehaviorFeature.java` 放到
   `fixture-feature/src/main/java/org/privacytrace/probe/fixture/feature/ProbeBehaviorFeature.java`。
3. 修改 base 的 `fixture/src/main/AndroidManifest.xml`：
   - `<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />`
   - `android:label="Controlled B fixture"`
   - `<meta-data android:name="privacy.policy.url" android:value="http://1.0.0.1/policy.html" />`
4. 用 JDK 17、Android SDK 34 构建：

```powershell
$env:JAVA_HOME = '<JDK 17>'
$env:ANDROID_HOME = '<Android SDK>'
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:GRADLE_USER_HOME = '<Gradle cache>'
.\gradlew.bat --offline :fixture:assembleDebug :fixture_feature:assembleDebug -PfixtureVersionCode=130
```

本次实际产物：

| 产物 | SHA-256 | 大小 |
| --- | --- | --- |
| base | `51419844C6305B99EE930DD77D15162F606E39A94B57F1939858EDA43BEDC44F` | 7501 B |
| split | `9991311FB07B8EA2F595578F442E514BA138FA04B1367BCBB4F14FF114F848FF` | 7620 B |

安装态必须是真正的 `install-multiple base split`；把 base 改名不能当 split。
夹具只用于静态证据对照，不是对任何真实应用的评价。
