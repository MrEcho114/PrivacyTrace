package org.privacytrace.issue133.fixture;

import android.telephony.TelephonyManager;

// Trusted static-analysis input. This method is never executed by the fixture.
public final class IdentifierFixture {
    public static String potentialIdentifierAccess(TelephonyManager manager) {
        return manager.getDeviceId();
    }
}
