import { invoke } from '@tauri-apps/api/core'
import { collectionInstructions } from '../policyAssist'

export type Upload = { origin: string; draft: string; state: string; cleanupPending: boolean }
export type ModelStatus = { configured: boolean; endpoint: string | null }
export type Envelope<T> = { origin: string; draft: string; data: T }
export interface MobileBridge {
  upload(): Promise<Upload>
  restore(): Promise<Upload>
  remove(): Promise<Upload>
  cancel(): Promise<void>
  modelStatus(): Promise<ModelStatus>
  configureModel(): Promise<ModelStatus>
  collect(model: string, app: string): Promise<string>
  request<T>(action: string, payload?: object): Promise<Envelope<T>>
}
const native = <T>(name: string, args?: Record<string, unknown>) => invoke<T>('plugin:package-probe|' + name, args)
export const mobileBridge: MobileBridge = {
  upload: () => native('upload_selected'), restore: () => native('refresh_upload'), remove: () => native('delete_upload'),
  cancel: () => native('cancel'), modelStatus: () => native('model_status'), configureModel: () => native('configure_model'),
  async collect(model, app) {
    const result = await native<{ text: string }>('collect_policy', { model, prompt: collectionInstructions(app) })
    return result.text
  },
  async request<T>(action: string, payload: object = {}) {
    const result = await native<{ json: string }>('workflow', { action, payload: JSON.stringify(payload) })
    return JSON.parse(result.json) as Envelope<T>
  },
}
