package org.privacytrace.probe

import android.app.Activity
import android.app.AlertDialog
import android.os.Build
import android.text.InputFilter
import android.text.InputType
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

internal fun serverHealthDialog(
    activity: Activity, check: (String) -> Unit, cancel: () -> Unit,
): AlertDialog {
    val body = LinearLayout(activity).apply {
        orientation = LinearLayout.VERTICAL
        val padding = (20 * resources.displayMetrics.density).toInt()
        setPadding(padding, padding, padding, padding)
        isSaveEnabled = false
        isSaveFromParentEnabled = false
        if (Build.VERSION.SDK_INT >= 26) importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
    }
    body.addView(TextView(activity).apply {
        text = "仅向此地址 GET /api/v1/health，不发送应用材料、模型 Key 或任务凭据。" +
            "地址不保存。成功仅表示健康响应，不代表兼容或允许上传。请输入 HTTPS 根地址，不含路径或凭据。"
    })
    val address = EditText(activity).apply {
        hint = "HTTPS 分析服务根地址"
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        isSaveEnabled = false
        isSaveFromParentEnabled = false
        setSingleLine(true)
        filters = arrayOf(InputFilter.LengthFilter(1025))
    }
    body.addView(address)
    return AlertDialog.Builder(activity)
        .setTitle("检查分析服务")
        .setView(ScrollView(activity).apply { isSaveEnabled = false; isSaveFromParentEnabled = false; addView(body) })
        .setNegativeButton("取消") { _, _ -> cancel() }
        .setPositiveButton("只读检查") { _, _ -> check(address.text.toString()) }
        .setOnCancelListener { cancel() }
        .create().also { dialog -> dialog.setOnDismissListener { address.text.clear() } }
}
