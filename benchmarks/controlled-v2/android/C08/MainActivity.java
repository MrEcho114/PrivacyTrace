package org.privacytrace.controlled.c08;

public final class MainActivity extends android.app.Activity {
    @Override public void onCreate(android.os.Bundle state) {
        super.onCreate(state);
        android.widget.TextView text = new android.widget.TextView(this);
        text.setText("PrivacyTrace controlled static fixture");
        setContentView(text);
    }

    // This static invocation is intentionally not called by the welcome screen.
    // Static evidence does not prove execution or collection.
    public android.location.Location readLocation(android.location.LocationManager manager) {
        return manager.getLastKnownLocation("gps");
    }
}
