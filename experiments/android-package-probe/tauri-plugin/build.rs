fn main() {
    tauri_plugin::Builder::new(&[
        "inspect_selected",
        "cancel",
        "model_status",
        "configure_model",
        "clear_model",
        "check_server",
    ])
    .android_path("android")
    .build();
}
