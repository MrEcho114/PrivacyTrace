package org.privacytrace.issue134.fixture;

import android.telephony.TelephonyManager;

// Never executed: a fixed, independently expected static invoke for acceptance.
public final class IdentifierFixture {
    public static String potentialIdentifierAccess(TelephonyManager manager) {
        return manager.getDeviceId();
    }
}
