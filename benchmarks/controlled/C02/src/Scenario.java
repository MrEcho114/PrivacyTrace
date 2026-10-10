package org.privacytrace.controlled.c02;

import android.hardware.Camera;

/** Source-owned static scenario. Never installed or executed by the benchmark. */
public final class Scenario {
    public static Camera cameraAccess() {
        return Camera.open();
    }
}
