fn main() {
    tauri_plugin::Builder::new(&[
        "inspect_selected",
        "cancel",
        "model_status",
        "configure_model",
        "clear_model",
        "check_server",
        "upload_selected",
        "refresh_upload",
        "delete_upload",
        "forget_upload",
    ])
    .android_path("android")
    .build();
}
