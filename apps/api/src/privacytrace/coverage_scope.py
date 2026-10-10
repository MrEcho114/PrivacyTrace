"""Conservative recognition boundaries shared by new scans and old reports."""


def behavior_limitations():
    return [
        "仅识别当前规则集支持的静态特征，未命中规则不代表没有隐私行为。",
        "不保证覆盖反射、动态加载及运行时生成的调用。",
        "不保证覆盖 Native、加壳、Flutter 或其他第三方与混合运行时。",
        "复杂控制流、跨过程参数与数据流不在当前有限局部常量分析范围。",
        "静态潜在行为不能证明实际访问、收集或外传。",
    ]


def sdk_attribution_limitations():
    """Separate from behavior limitations: attribution produces no behavior."""
    return [
        "仅按已公开的包前缀做归属提示，未收录的 SDK 不会被标记。",
        "归属只说明包路径落在某个已公开范围内，不等于实际收集或外发。",
        "不识别包路径之外的 SDK 特征（如混淆后重命名、动态下发）。",
    ]
