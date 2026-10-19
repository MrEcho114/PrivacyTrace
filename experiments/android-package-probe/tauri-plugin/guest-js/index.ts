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
