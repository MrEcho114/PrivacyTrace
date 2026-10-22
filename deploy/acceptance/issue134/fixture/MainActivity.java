package org.privacytrace.issue134.fixture;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

public final class MainActivity extends Activity {
    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        TextView label = new TextView(this);
        label.setText("PrivacyTrace F synthetic input. No identifier access is executed.");
        setContentView(label);
    }
}
