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

internal fun uploadOriginDialog(activity: Activity, action: String,
    submit: (String) -> Unit, cancel: () -> Unit): AlertDialog {
    val body = LinearLayout(activity).apply {
        orientation = LinearLayout.VERTICAL
        val pad = (20 * resources.displayMetrics.density).toInt()
        setPadding(pad, pad, pad, pad)
        isSaveEnabled = false; isSaveFromParentEnabled = false
        if (Build.VERSION.SDK_INT >= 26) importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
    }
    body.addView(TextView(activity).apply {
        text = "输入 HTTPS 分析服务根地址。先检查上传协议和限额；访问材料按精确地址与实例加密保存在本机。" +
            "不会发送模型 Key 或整机应用清单。一次仅保留此实例的一份当前上传；换应用前须主动删除旧材料。"
    })
    val address = EditText(activity).apply {
        hint = "HTTPS 分析服务根地址"
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        isSaveEnabled = false; isSaveFromParentEnabled = false; setSingleLine(true)
        filters = arrayOf(InputFilter.LengthFilter(1025))
    }
    body.addView(address)
    return AlertDialog.Builder(activity).setTitle(action)
        .setView(ScrollView(activity).apply { isSaveEnabled = false; isSaveFromParentEnabled = false; addView(body) })
        .setNegativeButton("取消") { _, _ -> cancel() }
        .setPositiveButton("检查并继续") { _, _ -> submit(address.text.toString()) }
        .setOnCancelListener { cancel() }.create().also { dialog ->
            dialog.setOnDismissListener { address.text.clear() }
        }
}
