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

/** Cooperative cancellation. The read promise rejects; it never returns partial digests. */
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
