import { request } from '@/api/client';

export interface WeComSetupValues {
  ticket_api_url: string;
  notifications_enabled: boolean;

  statuses: string;
  ticket_limit: string;
  poll_interval: string;
  ticket_timeout: string;

  reply_bot_name: string;

  users_default: string;
  users_property: string;
  users_cleaning: string;
  users_police: string;
  users_hospital: string;
  users_community: string;
  users_human_review: string;

  export_dir: string;

  routing_mode: string;
  routing_confidence: string;
  routing_timeout: string;
}

export interface WeComBackgroundStatus {
  ok: boolean;

  installed: boolean;
  running: boolean;

  loaded?: boolean;
  state?: string;

  pid?: number | null;

  error?: string;

  /*
   * macOS
   */
  plist_path?: string;
  label?: string;

  /*
   * Windows
   */
  task_name?: string;
  script_path?: string;

  /*
   * Linux
   */
  unit_name?: string;
  unit_path?: string;

  log_path?: string;
  error_log_path?: string;
}

export interface WeComSetupStatus {
  /*
   * Settings are valid.
   *
   * This does NOT mean the background
   * service is currently running.
   */
  configured: boolean;

  ticket_api_token_configured: boolean;

  group_webhook_configured: boolean;

  values: WeComSetupValues;

  background?: WeComBackgroundStatus | null;
}

export interface WeComSetupInput extends Partial<WeComSetupValues> {
  ticket_api_token?: string;
  group_webhook?: string;
}

export function fetchWeComSetup(): Promise<WeComSetupStatus> {
  return request<WeComSetupStatus>('/api/reins/wecom/setup');
}

export function saveWeComSetup(
  values: WeComSetupInput,
): Promise<WeComSetupStatus> {
  return request<WeComSetupStatus>('/api/reins/wecom/setup', {
    method: 'POST',

    body: JSON.stringify(values),
  });
}

export function startWeComService(): Promise<WeComSetupStatus> {
  return request<WeComSetupStatus>('/api/reins/wecom/service/start', {
    method: 'POST',
  });
}

export function stopWeComService(): Promise<WeComSetupStatus> {
  return request<WeComSetupStatus>('/api/reins/wecom/service/stop', {
    method: 'POST',
  });
}
