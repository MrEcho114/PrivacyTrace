package org.privacytrace.probe.fixture;

import android.location.LocationManager;

/** B acceptance fixture: a statically visible precise-location API call. */
public final class ProbeBehavior {
    private ProbeBehavior() {}

    public static void accessLocation(LocationManager manager) {
        manager.getLastKnownLocation("gps");
    }
}
