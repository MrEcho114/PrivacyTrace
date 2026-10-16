package org.privacytrace.controlled.c01;

public final class MainActivity extends android.app.Activity {
    @Override public void onCreate(android.os.Bundle state) {
        super.onCreate(state);
        android.widget.TextView text = new android.widget.TextView(this);
        text.setText("PrivacyTrace controlled static fixture");
        setContentView(text);
    }
}
