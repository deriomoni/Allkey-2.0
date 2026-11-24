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
  hidden?: boolean           // только у admin
  suspected_count?: number    // только у admin
  forms: string[]
  plan_missing?: boolean   // живая компания без плана отчётов на текущий год
  vat_date: string | null
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
  raised_by?: string | null
  decided_by: string | null
  decided_at: string | null
  reason: string | null
}

export interface StaffNote { at: string; author: string; form?: string | null; period?: string | null; text: string }
export interface Profile {
  source?: string
  date?: string
  bank_accounts?: { bank?: string; bic?: string; iban?: string; currency?: string }[]
  cash_registers?: { reg_number?: string; model?: string; serial?: string; registered?: string; ofd?: string; address?: string }[]
  ugd?: { code?: string; name?: string; type?: string; from?: string }[]
  head?: string
  address?: string
  oked?: { code?: string; name?: string; type?: string; from?: string }[]
  discrepancies?: unknown[]
}

export interface CabinetReport {
  form?: string; period?: string; due?: string; cabinet?: string; accepted_at?: string
  drive?: { form_file?: boolean; notice_file?: boolean; added?: unknown[] }
}
export interface Cabinet {
  checked_at?: string
  status?: string
  statement?: { ordered_at?: string; from?: string; ready?: boolean } | null
  saldo?: {
    date?: string; fresh?: boolean; pages?: string; debt_total?: number; overpaid_total?: number; file?: string
    rows?: { kbk?: string; ogd?: string; tax?: number; penalty?: number; fine?: number }[]
  } | null
  notices?: { from?: string; items?: { date?: string; type?: string; number?: string; read?: boolean; due?: string; summary?: string; red?: string | null }[] } | null
  reports_checked_through?: string
  reports?: CabinetReport[]
}
export interface CabinetQueueEntry {
  id: number; company_id: number; reason: string; reason_label: string; note: string | null
  requested_by: string | null; requested_at: string | null; done_at: string | null; done_by: string | null; result: string | null
  slug?: string; name?: string; bin?: string | null; hidden?: boolean; checked_at?: string | null
}

export interface CompanyDetail extends CompanyRow {
  cabinet?: Cabinet | null
  cabinet_queue?: CabinetQueueEntry | null
  staff_notes: StaffNote[]
  profile: Profile | null
  profile_url: string | null
  obligations: ObligationFlag[]
  card: any
  onec: { kind: string | null; url: string | null; login: string | null; note: string | null; run_on: string | null; closed_through: string | null }
  inactive_reason: string | null
  inactive_since: string | null
  drive: { folder_name: string | null; root_url: string | null; agent_url?: string | null }
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
  hidden?: number  // только у admin
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
  staff: { user_id: number; email: string | null; full_name: string | null; is_active: boolean; granted_by: string | null; granted_at: string | null }[]
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

export interface FormsChange { company_id: number; slug?: string; name?: string; bin?: string | null; add: string[]; remove: string[] }
export interface FormsPreview {
  file_name: string
  companies_in_file: number
  matched: number
  changes: FormsChange[]
  unmatched: { row: number; bin: string; name: string; reason: string }[]
  discrepancies: { company: string; bin: string | null; field: string; file: string; card: string }[]
  blocked: { company: string; bin: string | null; form: string; reason: string }[]
  warnings: string[]
  totals: { companies_changed: number; forms_added: number; forms_removed: number }
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
  // Файл (xlsx) ответом на POST с токеном → сохранение через ссылку.
  async function downloadPost(path: string, body: unknown, fallbackName: string) {
    const headers = new Headers({ 'Content-Type': 'application/json' })
    const token = ctx.getToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const r = await fetch(ctx.apiUrl + '/api/ops' + path, { method: 'POST', headers, body: JSON.stringify(body) })
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
    me: () => req<{ role: 'admin' | 'staff' }>('/me'),
    updateOnec: (id: number, body: { url?: string; kind?: string; note?: string; reason: string }) =>
      req<{ ok: boolean; commit: string }>(`/companies/${id}/onec`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }),
    addNote: (id: number, body: { text: string; form?: string; period?: string }) =>
      req<{ ok: boolean; commit: string }>(`/companies/${id}/notes`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }),
    exportCompanies: (ids: number[]) => downloadPost('/companies/export', { ids }, 'companies.xlsx'),
    formsImportPreview: (file: File) => {
      const fd = new FormData()
      fd.append('file', file)
      return req<FormsPreview>('/companies/forms-import/preview', { method: 'POST', body: fd })
    },
    formsImportApply: (p: FormsPreview) =>
      req<{ ok: boolean; commit: string | null; companies_changed: number; forms_added: number; forms_removed: number }>(
        '/companies/forms-import/apply', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            file_name: p.file_name,
            changes: p.changes.map((c) => ({ company_id: c.company_id, add: c.add, remove: c.remove })),
            companies_in_file: p.companies_in_file, unmatched: p.unmatched.length,
            discrepancies: p.discrepancies.length, blocked: p.blocked.length,
          }),
        }),
    cabinetQueue: () => req<{ items: CabinetQueueEntry[] }>('/cabinet-queue').then((d) => d.items),
    cabinetQueueAdd: (id: number, note?: string) =>
      req<{ ok: boolean; created: boolean; entry: CabinetQueueEntry }>(`/companies/${id}/cabinet-queue`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note }),
      }),
    cabinetQueueDone: (entryId: number, result?: string) =>
      req<{ ok: boolean }>(`/cabinet-queue/${entryId}/done`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ result }),
      }),
    status: () => req<Status>('/status'),
    admins: () => req<AdminsInfo>('/admins'),
    companies: () => req<{ items: CompanyRow[] }>('/companies').then((d) => d.items),
    company: (id: number) => req<CompanyDetail>(`/companies/${id}`),
    sync: () => req<SyncResult>('/companies/sync', { method: 'POST' }),
    setHidden: (id: number, hidden: boolean) =>
      req<{ ok: boolean; hidden: boolean; commit: string }>(`/companies/${id}/hidden`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hidden }),
      }),
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
