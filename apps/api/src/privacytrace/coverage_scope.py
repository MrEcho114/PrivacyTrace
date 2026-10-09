"""Conservative recognition boundaries shared by new scans and old reports."""


def behavior_limitations():
    return [
        "仅识别当前规则集支持的静态特征，未命中规则不代表没有隐私行为。",
        "不保证覆盖反射、动态加载及运行时生成的调用。",
        "不保证覆盖 Native、加壳、Flutter 或其他第三方与混合运行时。",
        "复杂控制流、跨过程参数与数据流不在当前有限局部常量分析范围。",
        "静态潜在行为不能证明实际访问、收集或外传。",
    ]
