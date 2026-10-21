# #132 受控 base + feature 样本源码

这三个源文件与本轮实际构建输入逐字节相同。包名 `org.privacytrace.probe.fixture`，
versionCode 132，安装名 PrivacyTrace132 fixture；base 和真正的 `feature_camera` split
使用同一临时研究签名，未提交 APK、私钥或口令。

`potentialCamera()` 保留 Camera.open 的静态线索，界面不会调用它；精确位置只有清单权限。
独立预期是非零且可定位的能力/API 证据，不能据此声称发生了采集。
无 DEX 的 feature 明确声明 `hasCode=false`，不得把改名的 base 当作 split。

复建使用 JDK17、Android platform36/build-tools36.0.0：javac `-source 8 -target 8`
编译 MainActivity，d8 `--min-api 24` 生成 classes.dex；aapt2 分别链接两个 manifest，
将 DEX 放入 base，再 zipalign、用新临时密钥同时签署两包，最后在专用设备执行
`adb -s <owned-target> install-multiple base.apk feature.apk`。
输出只放忽略目录；签名和 ZIP 时间会改变重建 APK 的摘要，应记录本次实际值。

实际输入组件、签名和安装/服务端指纹见
[输入与扫描身份](../../../../docs/acceptance/issue132/evidence/input-and-scan-identity.json)。
同任务辅助回填使用自编研究声明，原文保留本机，只公开其摘要及短原句的定位检查。
