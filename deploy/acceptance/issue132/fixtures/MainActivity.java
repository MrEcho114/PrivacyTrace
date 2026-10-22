package org.privacytrace.probe.fixture;
public class MainActivity extends android.app.Activity {
  @Override public void onCreate(android.os.Bundle state) { super.onCreate(state); }
  // Static research clue. This method is never called by the fixture UI.
  public void potentialCamera() { android.hardware.Camera camera = android.hardware.Camera.open(); camera.release(); }
}
