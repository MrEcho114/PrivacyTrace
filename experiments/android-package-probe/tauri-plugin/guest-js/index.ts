import { invoke } from '@tauri-apps/api/core';

export interface PartDigest {
  splitName: string | null;
  bytes: number;
  sha256: string;
}

export interface ProbeResult {
  packageName: string;
  versionCode: string;
  parts: PartDigest[];
  totalBytes: number;
  localSetSha256: string;
}

/** Native selection and explicit local-read confirmation; no package or path input. */
export function inspectSelected(): Promise<ProbeResult> {
  return invoke('plugin:package-probe|inspect_selected');
}

/** Cancels the active native operation; no partial result is returned. */
export function cancel(): Promise<void> {
  return invoke('plugin:package-probe|cancel');
}

export interface ModelConfigStatus {
  configured: boolean;
  endpoint: string | null;
}

/** Only non-secret authenticated status crosses the bridge. */
export function modelStatus(): Promise<ModelConfigStatus> {
  return invoke('plugin:package-probe|model_status');
}

/** Endpoint and Key are entered in Android; JavaScript supplies neither. */
export function configureModel(): Promise<ModelConfigStatus> {
  return invoke('plugin:package-probe|configure_model');
}

/** Requires explicit native confirmation. */
export function clearModel(): Promise<ModelConfigStatus> {
  return invoke('plugin:package-probe|clear_model');
}

export interface ServerHealth {
  origin: string;
  version: string;
  mode: 'remote' | 'local-jobs';
  scope: 'HEALTH_ONLY';
}

/** Native origin input; no URL, headers, credentials, or trust override from JavaScript. */
export function checkServer(): Promise<ServerHealth> {
  return invoke('plugin:package-probe|check_server');
}

export interface UploadStatus {
  origin: string;
  draft: string;
  state: 'SERVER_CONFIRMED' | 'NOT_CONFIRMED' | 'DELETED' | 'LOCAL_ACCESS_FORGOTTEN';
  cleanupPending: boolean;
}

/** Native origin, application selection and upload consent; no caller input. */
export function uploadSelected(): Promise<UploadStatus> {
  return invoke('plugin:package-probe|upload_selected');
}
export function refreshUpload(): Promise<UploadStatus> {
  return invoke('plugin:package-probe|refresh_upload');
}
export function deleteUpload(): Promise<UploadStatus> {
  return invoke('plugin:package-probe|delete_upload');
}
/** Explicit warning: local revocation does not delete retained server material. */
export function forgetUpload(): Promise<UploadStatus> {
  return invoke('plugin:package-probe|forget_upload');
}
