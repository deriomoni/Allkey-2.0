export interface Ctx {
  apiUrl: string
  getToken: () => string | null
  basePath: string
  view?: 'page' | 'settings'
}

export interface CompanyRow {
  id: number
  slug: string
  name: string
  name_official: boolean
  bin: string | null
  aliases: string[]
  folder_name: string | null
  tax_regime: string | null
  vat_payer: boolean | null
  responsible: string | null
  active: boolean
  missing_in_repo: boolean
}

export interface Report {
  id: number
  form: string
  period: string
  status: string
  raw_value: string | null
  source: string
  evidence_url: string | null
  updated_at: string | null
}

export interface CompanyDetail extends CompanyRow {
  card: any
  onec: { kind: string | null; url: string | null; login: string | null; note: string | null; run_on: string | null; closed_through: string | null }
  inactive_reason: string | null
  inactive_since: string | null
  drive: { folder_name: string | null; root_url: string | null; agent_url: string | null }
  reports: Report[]
  synced_at: string | null
}

export interface SyncResult {
  ok: boolean
  validator_ok: boolean
  validator_errors: string[]
  created: number
  updated: number
  unchanged: number
  missing_in_repo: number
  total: number
  active: number
  inactive: number
  error: string | null
}

export interface Status {
  total: number
  active: number
  inactive: number
  last_synced_at: string | null
  repo_configured: boolean
}

export interface OpsAdmin {
  user_id: number
  email: string | null
  full_name: string | null
  is_active: boolean
  granted_by: string | null
  granted_at: string | null
  is_env_admin: boolean
}
export interface AdminsInfo {
  items: OpsAdmin[]
  env_admin_user_id: number | null
  visible_to_non_admin: boolean
}

export interface PreviewCell { period: string; raw: string; status: string }
export interface PreviewRow {
  row_id: string
  form: string
  row_number: number
  company_text: string
  cells: PreviewCell[]
  match: { company_id: number; name: string; by: string } | null
  candidates: { company_id: number; name: string }[]
}
export interface Preview {
  sheets: { form: string; rows: number; periods: string[] }[]
  rows: PreviewRow[]
  warnings: string[]
  companies: { id: number; name: string; active: boolean }[]
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

export function makeApi(ctx: Ctx) {
  async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers)
    const token = ctx.getToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const r = await fetch(ctx.apiUrl + '/api/ops' + path, { ...init, headers })
    if (!r.ok) {
      let msg = `Ошибка ${r.status}`
      try {
        const j = await r.json()
        if (typeof j.detail === 'string') msg = j.detail
      } catch { /* ignore */ }
      throw new ApiError(r.status, msg)
    }
    return r.json()
  }
  return {
    status: () => req<Status>('/status'),
    admins: () => req<AdminsInfo>('/admins'),
    companies: () => req<{ items: CompanyRow[] }>('/companies').then((d) => d.items),
    company: (id: number) => req<CompanyDetail>(`/companies/${id}`),
    sync: () => req<SyncResult>('/companies/sync', { method: 'POST' }),
    importPreview: (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      return req<Preview>('/reports/import/preview', { method: 'POST', body: fd })
    },
    importCommit: (rows: { company_id: number; form: string; cells: PreviewCell[] }[]) =>
      req<{ created: number; updated: number; skipped: number }>('/reports/import/commit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows }),
      }),
  }
}

export type Api = ReturnType<typeof makeApi>

export const REGIME: Record<string, string> = {
  general: 'ОУР',
  simplified: 'Упрощёнка',
  retail: 'Розничный',
}

export const REPORT_STATUS: Record<string, string> = {
  due: 'к сдаче',
  submitted: 'сдан',
  accepted: 'принят',
  rejected: 'отклонён',
  not_required: 'не требуется',
}

export const MATCH_BY: Record<string, string> = {
  name: 'по названию',
  alias: 'по алиасу',
  folder_name: 'по папке',
}
