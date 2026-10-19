fn main() {
    tauri_plugin::Builder::new(&["inspect_selected", "cancel"])
        .android_path("android")
        .build();
}
