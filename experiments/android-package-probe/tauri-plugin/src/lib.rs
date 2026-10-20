use tauri::Runtime;
use tauri::plugin::{Builder, TauriPlugin};

#[cfg(target_os = "android")]
use tauri::{Manager, plugin::PluginHandle};

#[cfg(target_os = "android")]
struct NativeProbe<R: Runtime>(PluginHandle<R>);

#[derive(serde::Deserialize, serde::Serialize)]
pub struct ModelConfigStatus {
    pub configured: bool,
    pub endpoint: Option<String>,
}

#[derive(serde::Deserialize, serde::Serialize)]
pub struct ServerHealth {
    pub origin: String,
    pub version: String,
    pub mode: String,
    pub scope: String,
}

#[derive(serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UploadStatus {
    pub origin: String,
    pub draft: String,
    pub state: String,
    pub cleanup_pending: bool,
}

#[derive(serde::Deserialize, serde::Serialize)]
pub struct JsonResult { pub json: String }
#[derive(serde::Deserialize, serde::Serialize)]
pub struct PolicyResult { pub text: String }

#[tauri::command]
async fn workflow<R: Runtime>(app: tauri::AppHandle<R>, action: String, payload: String) -> Result<JsonResult, String> {
    #[cfg(target_os = "android")]
    { app.state::<NativeProbe<R>>().0.clone().run_mobile_plugin_async("workflow", WorkflowArgs { action, payload }).await.map_err(native_error) }
    #[cfg(not(target_os = "android"))]
    { let _ = (app, action, payload); Err("ANDROID_ONLY".into()) }
}
#[derive(serde::Serialize)]
struct WorkflowArgs { action: String, payload: String }

#[tauri::command]
async fn collect_policy<R: Runtime>(app: tauri::AppHandle<R>, model: String, prompt: String) -> Result<PolicyResult, String> {
    #[cfg(target_os = "android")]
    { app.state::<NativeProbe<R>>().0.clone().run_mobile_plugin_async("collectPolicy", CollectPolicyArgs { model, prompt }).await.map_err(native_error) }
    #[cfg(not(target_os = "android"))]
    { let _ = (app, model, prompt); Err("ANDROID_ONLY".into()) }
}
#[derive(serde::Serialize)]
struct CollectPolicyArgs { model: String, prompt: String }

async fn upload_command<R: Runtime>(app: tauri::AppHandle<R>, command: &'static str) -> Result<UploadStatus, String> {
    #[cfg(target_os = "android")]
    {
        app.state::<NativeProbe<R>>().0.clone().run_mobile_plugin_async(command, ())
            .await.map_err(native_error)
    }
    #[cfg(not(target_os = "android"))]
    {
        let _ = (app, command);
        Err("ANDROID_ONLY".into())
    }
}

#[tauri::command]
async fn upload_selected<R: Runtime>(app: tauri::AppHandle<R>) -> Result<UploadStatus, String> {
    upload_command(app, "uploadSelected").await
}
#[tauri::command]
async fn refresh_upload<R: Runtime>(app: tauri::AppHandle<R>) -> Result<UploadStatus, String> {
    upload_command(app, "refreshUpload").await
}
#[tauri::command]
async fn delete_upload<R: Runtime>(app: tauri::AppHandle<R>) -> Result<UploadStatus, String> {
    upload_command(app, "deleteUpload").await
}
#[tauri::command]
async fn forget_upload<R: Runtime>(app: tauri::AppHandle<R>) -> Result<UploadStatus, String> {
    upload_command(app, "forgetUpload").await
}

#[tauri::command]
async fn check_server<R: Runtime>(app: tauri::AppHandle<R>) -> Result<ServerHealth, String> {
    #[cfg(target_os = "android")]
    {
        app.state::<NativeProbe<R>>()
            .0
            .clone()
            .run_mobile_plugin_async("checkServer", ())
            .await
            .map_err(native_error)
    }
    #[cfg(not(target_os = "android"))]
    {
        let _ = app;
        Err("ANDROID_ONLY".into())
    }
}

async fn model_command<R: Runtime>(
    app: tauri::AppHandle<R>,
    command: &'static str,
) -> Result<ModelConfigStatus, String> {
    #[cfg(target_os = "android")]
    {
        app.state::<NativeProbe<R>>()
            .0
            .clone()
            .run_mobile_plugin_async(command, ())
            .await
            .map_err(native_error)
    }
    #[cfg(not(target_os = "android"))]
    {
        let _ = (app, command);
        Err("ANDROID_ONLY".into())
    }
}

#[tauri::command]
async fn model_status<R: Runtime>(app: tauri::AppHandle<R>) -> Result<ModelConfigStatus, String> {
    model_command(app, "modelStatus").await
}

#[tauri::command]
async fn configure_model<R: Runtime>(
    app: tauri::AppHandle<R>,
) -> Result<ModelConfigStatus, String> {
    model_command(app, "configureModel").await
}

#[tauri::command]
async fn clear_model<R: Runtime>(app: tauri::AppHandle<R>) -> Result<ModelConfigStatus, String> {
    model_command(app, "clearModel").await
}

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
                "INVALID_MODEL_CONFIG" | "MODEL_CONFIG_UNAVAILABLE" | "MODEL_ENDPOINT_MISMATCH" => {
                    return code;
                }
                "INVALID_SERVER_ORIGIN"
                | "SERVER_REDIRECT_REJECTED"
                | "SERVER_BUSY"
                | "SERVER_REJECTED"
                | "SERVER_RESPONSE_INVALID"
                | "SERVER_RESPONSE_TOO_LARGE"
                | "SERVER_TLS_REJECTED"
                | "SERVER_TIMEOUT"
                | "SERVER_UNREACHABLE" => return code,
                "INSTANCE_MISMATCH" | "SERVER_INCOMPATIBLE" | "ACCESS_REJECTED"
                | "UPLOAD_CONFLICT_REFRESH" | "EXISTING_UPLOAD_DELETE_FIRST"
                | "UPLOAD_RECEIPT_MISMATCH" | "NO_SAVED_UPLOAD"
                | "UPLOAD_STORAGE_UNAVAILABLE" | "UPLOAD_CLEANUP_FAILED" => return code,
                "WORKFLOW_INPUT_REJECTED" | "WORKFLOW_CONFLICT_REFRESH" | "WORKFLOW_NO_JOB"
                | "INVALID_MODEL_REQUEST" | "MODEL_ANALYSIS_ORIGIN_REJECTED" | "MODEL_REDIRECT_REJECTED"
                | "MODEL_BUSY" | "MODEL_REQUEST_REJECTED" | "MODEL_RESPONSE_INVALID" | "MODEL_RESPONSE_INCOMPLETE"
                | "MODEL_TLS_REJECTED" | "MODEL_REQUEST_FAILED" => return code,
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
        .invoke_handler(tauri::generate_handler![
            inspect_selected,
            cancel,
            model_status,
            configure_model,
            clear_model,
            check_server,
            upload_selected,
            refresh_upload,
            delete_upload,
            forget_upload,
            workflow,
            collect_policy
        ])
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
