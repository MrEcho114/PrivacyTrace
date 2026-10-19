use tauri::Runtime;
use tauri::plugin::{Builder, TauriPlugin};

#[cfg(target_os = "android")]
use tauri::{Manager, plugin::PluginHandle};

#[cfg(target_os = "android")]
struct NativeProbe<R: Runtime>(PluginHandle<R>);

// No input can name a package or path. Selection and confirmation happen natively.
#[tauri::command]
async fn inspect_selected<R: Runtime>(app: tauri::AppHandle<R>) -> Result<ProbeResult, String> {
    #[cfg(target_os = "android")]
    {
        let handle = app.state::<NativeProbe<R>>().0.clone();
        handle
            .run_mobile_plugin_async("inspectSelected", ())
            .await
            .map_err(native_error)
    }
    #[cfg(not(target_os = "android"))]
    {
        let _ = app;
        Err("ANDROID_ONLY".into())
    }
}

#[tauri::command]
async fn cancel<R: Runtime>(app: tauri::AppHandle<R>) -> Result<(), String> {
    #[cfg(target_os = "android")]
    {
        let handle = app.state::<NativeProbe<R>>().0.clone();
        handle
            .run_mobile_plugin_async("cancel", ())
            .await
            .map_err(native_error)
    }
    #[cfg(not(target_os = "android"))]
    {
        let _ = app;
        Err("ANDROID_ONLY".into())
    }
}

#[cfg(target_os = "android")]
fn native_error(error: tauri::plugin::mobile::PluginInvokeError) -> String {
    if let tauri::plugin::mobile::PluginInvokeError::InvokeRejected(error) = error {
        if let Some(code) = error.code {
            match code.as_str() {
                "BUSY_OR_INACTIVE"
                | "NOT_VISIBLE_OR_MISSING"
                | "UNREADABLE"
                | "INCOMPLETE_SET"
                | "INSTALLATION_CHANGED"
                | "LIMIT_EXCEEDED"
                | "CANCELLED" => {
                    return code;
                }
                _ => {}
            }
        }
    }
    // Never propagate platform messages, private paths, or JNI diagnostics to the webview.
    "NATIVE_PROBE_FAILED".into()
}

#[derive(serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PartDigest {
    pub split_name: Option<String>,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProbeResult {
    pub package_name: String,
    // Decimal string prevents truncation by JavaScript's Number for Android longVersionCode.
    pub version_code: String,
    pub parts: Vec<PartDigest>,
    pub total_bytes: u64,
    pub local_set_sha256: String,
}

pub fn init<R: Runtime>() -> TauriPlugin<R> {
    Builder::new("package-probe")
        .invoke_handler(tauri::generate_handler![inspect_selected, cancel])
        .setup(|_app, _api| {
            #[cfg(target_os = "android")]
            {
                let handle =
                    _api.register_android_plugin("org.privacytrace.probe", "PackageProbePlugin")?;
                _app.manage(NativeProbe(handle));
            }
            Ok(())
        })
        .build()
}
