package org.privacytrace.probe.fixture.feature;

import android.content.ContentResolver;
import android.net.Uri;

/** B acceptance split: a statically visible contacts query only present in the split. */
public final class ProbeBehaviorFeature {
    private ProbeBehaviorFeature() {}

    public static void accessContacts(ContentResolver resolver) {
        resolver.query(
                Uri.parse("content://com.android.contacts/contacts"),
                null,
                null,
                null,
                null);
    }
}
