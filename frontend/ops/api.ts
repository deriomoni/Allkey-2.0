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
  legal_name: string | null
  drive_url: string | null
  bin: string | null
  aliases: string[]
  folder_name: string | null
  tax_regime: string | null
  vat_payer: boolean | null
  responsible: string | null
  active: boolean
  missing_in_repo: boolean
  suspected_count?: number
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

export interface ObligationFlag {
  idx: number
  form: string
  status: 'suspected' | 'confirmed' | 'dismissed'
  period: string | null
  trigger: string[]
  source: string | null
  raised_at: string | null
  decided_by: string | null
  decided_at: string | null
  reason: string | null
}

export interface CompanyDetail extends CompanyRow {
  obligations: ObligationFlag[]
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

export interface PlanRow {
  id: number
  company_id: number
  company: string
  slug: string
  bin: string | null
  regime: string | null
  vat: string | null
  form: string
  period: string
  period_code: string
  due_date: string | null
  status: string
  plan_status: string | null
  clarify_reason: string | null
  basis: string | null
  info_source: string | null
  registry_sheet: string
  decision: 'confirmed' | 'not_required' | null
  decision_basis: string | null
  decided_by: string | null
  decided_at: string | null
}
export interface PlanCounters {
  total: number
  due: number
  clarify: number
  not_required: number
  companies: number
  companies_without_forms: number
  companies_without_forms_ids: number[]
}
export interface PlanLoadResult {
  created: number
  updated: number
  conflicts_with_history: number
  unknown_company: number
  invalid: number
}
export interface Discrepancy { company_slug: string; company: string; discrepancy: string; source: string }
export interface PlanFilter { period?: string; form?: string; status?: string; regime?: string; without_forms?: boolean }

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
  // Файл (xlsx) — тем же запросом с токеном, затем сохранение через ссылку.
  async function download(path: string, fallbackName: string) {
    const headers = new Headers()
    const token = ctx.getToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const r = await fetch(ctx.apiUrl + '/api/ops' + path, { headers })
    if (!r.ok) throw new ApiError(r.status, `Ошибка ${r.status}`)
    const m = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '')
    const url = URL.createObjectURL(await r.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = m ? m[1] : fallbackName
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return {
    plan: () => req<{ items: PlanRow[]; counters: PlanCounters }>('/reports/plan'),
    loadPlan: () => req<PlanLoadResult>('/reports/plan/load', { method: 'POST' }),
    decide: (id: number, decision: 'confirmed' | 'not_required', basis: string) =>
      req<{ ok: boolean; status: string; proposal_id: number }>(`/reports/${id}/decision`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, basis }),
      }),
    discrepancies: () => req<{ file: string | null; items: Discrepancy[] }>('/reports/discrepancies'),
    exportPlan: (kind: 'registry' | 'flat', f: PlanFilter) => {
      const q = new URLSearchParams()
      if (f.period) q.set('period', f.period)
      if (f.form) q.set('form', f.form)
      if (f.status) q.set('status', f.status)
      if (f.regime) q.set('regime', f.regime)
      if (f.without_forms) q.set('without_forms', 'true')
      const qs = q.toString()
      return download(`/reports/export/${kind}${qs ? '?' + qs : ''}`, `reports-plan-${kind}.xlsx`)
    },
    status: () => req<Status>('/status'),
    admins: () => req<AdminsInfo>('/admins'),
    companies: () => req<{ items: CompanyRow[] }>('/companies').then((d) => d.items),
    company: (id: number) => req<CompanyDetail>(`/companies/${id}`),
    sync: () => req<SyncResult>('/companies/sync', { method: 'POST' }),
    raiseObligation: (id: number, body: { form: string; period: string; trigger: string[] }) =>
      req<{ ok: boolean; commit: string }>(`/companies/${id}/obligations`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }),
    decideObligation: (id: number, f: ObligationFlag, action: 'confirm' | 'dismiss', reason?: string) =>
      req<{ ok: boolean; commit: string }>(`/companies/${id}/obligations/${f.idx}/${action}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ form: f.form, period: f.period, reason }),
      }),
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
  clarify: 'уточнить',
}

export const OBLIGATION_SOURCE: Record<string, string> = {
  'bank-align': 'скилл bank-align',
  'subconto-analysis': 'скилл subconto-analysis',
  'knp-watch': 'скилл knp-watch',
  employee: 'сотрудник',
  admin: 'админ',
}

export const MATCH_BY: Record<string, string> = {
  name: 'по названию',
  alias: 'по алиасу',
  folder_name: 'по папке',
}
