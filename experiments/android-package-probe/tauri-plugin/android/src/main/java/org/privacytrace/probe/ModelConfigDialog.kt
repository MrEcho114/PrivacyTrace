package org.privacytrace.probe

import android.app.Activity
import android.app.AlertDialog
import android.os.Build
import android.text.InputFilter
import android.text.InputType
import android.view.View
import android.view.WindowManager
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

internal fun modelConfigDialog(
    activity: Activity, current: ModelConfigStatus,
    save: (String, CharArray) -> Unit, cancel: () -> Unit,
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
        text = "仅保存到本机。模型地址变化必须重新输入 Key；Key 不返回网页。调用前另行确认，可能产生费用。"
    })
    val address = EditText(activity).apply {
        hint = "完整 HTTPS Chat Completions 地址"
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        isSaveEnabled = false
        isSaveFromParentEnabled = false
        setSingleLine(true)
        // One overflow character remains invalid; never accept a silently truncated Key.
        filters = arrayOf(InputFilter.LengthFilter(ModelConfiguration.MAX_ENDPOINT + 1))
        setText(current.endpoint ?: "")
    }
    val secret = protectedKeyInput(activity).apply {
        hint = "重新输入模型 Key"
    }
    body.addView(address)
    body.addView(secret)
    val dialog = AlertDialog.Builder(activity)
        .setTitle("受保护模型配置")
        .setView(ScrollView(activity).apply { isSaveEnabled = false; isSaveFromParentEnabled = false; addView(body) })
        .setNegativeButton("取消") { _, _ -> cancel() }
        .setPositiveButton("保存到本机") { _, _ ->
            val bytes = CharArray(secret.text.length)
            secret.text.getChars(0, bytes.size, bytes, 0)
            save(address.text.toString(), bytes)
        }
        .setOnCancelListener { cancel() }
        .create()
    dialog.setOnDismissListener { secret.text.clear(); address.text.clear() }
    dialog.window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
    return dialog
}
