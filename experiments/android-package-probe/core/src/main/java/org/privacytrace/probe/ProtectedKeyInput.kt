package org.privacytrace.probe

import android.content.Context
import android.os.Build
import android.text.InputFilter
import android.text.InputType
import android.view.View
import android.view.ViewStructure
import android.view.autofill.AutofillValue
import android.view.inputmethod.EditorInfo
import android.widget.EditText

// Shared with the platform-only probe, which deliberately has no AppCompat dependency.
@android.annotation.SuppressLint("AppCompatCustomView")
private open class PrivateKeyInput(context: Context) : EditText(context) {
    override fun onProvideStructure(structure: ViewStructure) {
        super.onProvideStructure(structure)
        structure.setText("")
    }
}

@android.annotation.TargetApi(26)
private class NoAutofillKeyInput(context: Context) : PrivateKeyInput(context) {
    override fun getAutofillType() = View.AUTOFILL_TYPE_NONE
    override fun getAutofillValue(): AutofillValue? = null
    override fun onProvideAutofillStructure(structure: ViewStructure, flags: Int) {
        super.onProvideAutofillStructure(structure, flags)
        structure.setText("")
        structure.setAutofillValue(null)
    }
}

// Keep API26-specific class loading behind the runtime version check.
internal fun protectedKeyInput(context: Context): EditText =
    (if (Build.VERSION.SDK_INT >= 26) NoAutofillKeyInput(context) else PrivateKeyInput(context)).apply {
        isSaveEnabled = false
        isSaveFromParentEnabled = false
        // setSingleLine changes transformationMethod; set the password type afterwards.
        setSingleLine(true)
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        filters = arrayOf(InputFilter.LengthFilter(ModelConfiguration.MAX_KEY + 1))
        if (Build.VERSION.SDK_INT >= 26) imeOptions = imeOptions or EditorInfo.IME_FLAG_NO_PERSONALIZED_LEARNING
    }
