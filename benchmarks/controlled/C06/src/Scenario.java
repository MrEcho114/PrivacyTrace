package org.privacytrace.controlled.c06;

import android.media.AudioRecord;

/** A different API trace whose policy applicability deliberately remains unknown. */
public final class Scenario {
    public static void microphoneAccess(AudioRecord recorder) {
        recorder.startRecording();
    }
}
