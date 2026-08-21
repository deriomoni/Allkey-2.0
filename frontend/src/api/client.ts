import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Add token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Handle 401 errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      // Don't redirect - auth modal handles this
    }
    return Promise.reject(error)
  }
)

export interface LoginData {
  username: string
  password: string
}

export interface RegisterData {
  email: string
  password: string
  full_name: string
}

export interface User {
  id: number
  email: string
  full_name: string
  role: string
  is_active: boolean
  created_at: string
  license_status: 'active' | 'trial' | 'expired' | 'none' | null
  license_plan_name: string | null
  license_expires_at: string | null
  license_badge_color: string | null
}

export interface LicensePlan {
  id: number
  name: string
  description: string
  price: number
  duration_days: number
  is_active: boolean
  is_default: boolean
  badge_color: string
  created_at: string
  updated_at: string | null
}

export interface UserLicense {
  id: number
  user_id: number
  plan_id: number
  plan_name: string
  starts_at: string
  expires_at: string
  is_active: boolean
  created_at: string
}

export interface PublicSettings {
  whatsapp_number: string
  telegram_link: string
  kaspi_payment_url: string
}

// Service registry
export interface Service {
  code: string
  title: string
  description: string
  status: 'beta' | 'production'
}

export interface ServiceOverride {
  user_id: number
  allow: boolean
}

export interface ServiceAdmin {
  code: string
  title: string
  description: string
  status: 'beta' | 'production'
  is_enabled: boolean
  sort_order: number
  created_at: string | null
  roles: string[]
  overrides: ServiceOverride[]
}

export interface UploadResponse {
  session_id: string
  files: Record<string, string>
  message: string
}

export interface PreviewResponse {
  columns: string[]
  data: (string | number | null)[][]
  total_rows: number
}

export interface ReconciliationSummary {
  total_1c_entries: number
  total_esf_invoices: number
  matched_count: number
  match_rate: number
  total_1c_amount: number
  total_esf_amount: number
  total_difference: number
  has_discrepancies: boolean
}

export interface Case1DataRow {
  date: string
  document: string | null
  counterparty_6010: string | null
  recipient_esf: string | null
  amount_6010: number | null
  amount_esf: number | null
  esf_number?: string
  esf_reg_number?: string
  difference: number
  status: string
}

export interface Case3DataRow {
  date: string
  document: string | null
  tru: string | null
  sender_esf: string | null
  recipient_esf: string | null
  amount_3310: number | null
  amount_esf: number | null
  esf_number?: string
  esf_reg_number?: string
  difference: number
  status: string
}

export interface Case3Summary {
  total_3310_entries: number
  total_esf_invoices: number
  matched_count: number
  match_rate: number
  total_3310_amount: number
  total_esf_amount: number
  total_difference: number
  has_discrepancies: boolean
}

export interface Case2DataRow {
  date: string
  document: string
  our_doc_number: string | null
  cp_document: string | null
  cp_doc_number: string | null
  our_debit: number | null
  our_credit: number | null
  cp_debit: number | null
  cp_credit: number | null
  debit_diff: number
  credit_diff: number
  match_phase: string | null
  status: string
  // Act-reconciliation fields (upgraded case 2)
  category?: string
  num1?: string
  num2?: string
  amount1?: number | null
  amount2?: number | null
  esf1?: string
  esf2?: string
  note?: string
  match_method?: string
  status_code?: string
  status_detail?: string
  row1?: number | string
  row2?: number | string
}

export interface Case2Summary {
  total_entries_act1: number
  total_entries_act2: number
  matched_count: number
  match_rate: number
  has_discrepancies: boolean
  auto_detected?: boolean
}

export interface Case2HeaderSummary {
  owner_act1: string
  owner_act2: string
  period_act1: string
  period_act2: string
  period_mismatch: boolean
  common_period: string
  names_consistent?: boolean
  opening_act1: number | null
  opening_act2: number | null
  opening_diff: number | null
  closing_act1: number | null
  closing_act2: number | null
  closing_diff: number | null
  turnover_debit_act1: number | null
  turnover_credit_act1: number | null
  turnover_debit_act2: number | null
  turnover_credit_act2: number | null
}

export interface ReconciliationResult {
  status: string
  total_records: number
  matched: number
  mismatched: number
  not_found_in_source1: number
  not_found_in_source2: number
  data: (Case1DataRow | Case2DataRow | Case3DataRow)[]
  summary?: ReconciliationSummary | Case2Summary | Case3Summary
  // Act-reconciliation extras (upgraded case 2)
  out_of_period?: Case2DataRow[]
  header_summary?: Case2HeaderSummary
  common_period?: string
  period_mismatch?: boolean
}

// ---- Currency reconciliation (USD 1С ↔ Нацбанк) ----
export interface CurrencyRow {
  date: string
  description: string
  usd: number | null
  kzt: number | null
  rate1c: number | null
  rate_nb: number | null
  diff: number | null
  expected_kzt: number | null   // для no_rate: сколько должно было быть по курсу НБ
  delta_kzt: number | null      // для no_rate: expected_kzt − kzt
  status: 'ok' | 'off' | 'no_nb' | 'no_rate' | 'no_val'
}

export interface BalanceCheck {
  date: string | null
  saldo_val: number | null
  saldo_kzt: number | null
  rate_nb: number | null
  implied_rate: number | null
  expected_kzt: number | null
  diff: number | null
  mismatch: boolean
}

export interface CurrencyResult {
  rows: CurrencyRow[]
  matched: number
  off_rate: number
  no_nb: number
  no_rate: number
  no_val: number
  total_rows: number
  total_usd: number
  total_kzt: number
  threshold: number
  balance_check: BalanceCheck | null
}

// ---- Bank statement reconciliation (1С ↔ банк) ----
export interface BalanceGap {
  from_date: string
  to_date: string
  amount: number
}

export interface BankRow {
  date: string
  date_c1?: string
  dir: 'in' | 'out'
  amount: number
  bank_no: string
  bank_party: string
  bank_purpose: string
  c1_no: string
  c1_party: string
  c1_purpose: string
  parts: number[]
  status: 'ok' | 'date_diff' | 'only_bank' | 'only_1c'
}

export interface BankResult {
  rows: BankRow[]
  matched: number
  only_bank: number
  only_1c: number
  bank_in: number
  bank_out: number
  c1_in: number
  c1_out: number
  open_bank: number | null
  open_c1: number | null
  close_bank: number | null
  close_c1: number | null
  balance_diff: number | null
  gaps: BalanceGap[]
  split_docs: string[]
  currency: boolean
  cp_mismatch: number
}

// ---- Changelog (раздел «Обновления», только admin/employee) ----
export interface ChangelogEntry {
  id: number
  date: string                 // ISO "2026-07-27"
  category: 'fix' | 'feature' | 'improvement'
  service_code: string | null
  title: string
  body: string
  created_by: number | null
  created_at: string | null
}

export interface ChangelogInput {
  date: string
  category: 'fix' | 'feature' | 'improvement'
  service_code?: string | null
  title: string
  body?: string
}

// Auth API
export const authApi = {
  login: async (data: LoginData) => {
    const formData = new URLSearchParams()
    formData.append('username', data.username)
    formData.append('password', data.password)

    const response = await api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    return response.data
  },

  register: async (data: RegisterData) => {
    const response = await api.post('/auth/register', data)
    return response.data
  },
}

// Users API
export const usersApi = {
  getMe: async (): Promise<User> => {
    const response = await api.get('/users/me')
    return response.data
  },

  updateMe: async (data: { full_name?: string; password?: string }): Promise<User> => {
    const response = await api.put('/users/me', data)
    return response.data
  },

  getAll: async (): Promise<User[]> => {
    const response = await api.get('/users')
    return response.data
  },

  create: async (data: RegisterData & { role?: string }): Promise<User> => {
    const response = await api.post('/users', data)
    return response.data
  },

  update: async (id: number, data: { full_name?: string; password?: string }): Promise<User> => {
    const response = await api.put(`/users/${id}`, data)
    return response.data
  },

  delete: async (id: number) => {
    const response = await api.delete(`/users/${id}`)
    return response.data
  },
}

// Reconciliation API
export const reconciliationApi = {
  // Case 1
  uploadCase1: async (account6010: File, esfReport: File): Promise<UploadResponse> => {
    const formData = new FormData()
    formData.append('account_6010', account6010)
    formData.append('esf_report', esfReport)

    const response = await api.post('/reconciliation/case1/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  previewCase1: async (sessionId: string, fileKey: string, headerRow: number): Promise<PreviewResponse> => {
    const response = await api.post('/reconciliation/case1/preview', {
      session_id: sessionId,
      file_key: fileKey,
      header_row: headerRow,
      num_rows: 20,
    })
    return response.data
  },

  processCase1: async (
    sessionId: string,
    account6010Settings: { header_row: number; column_mappings: Record<string, number>; doc_filter?: string },
    esfSettings: { header_row: number; column_mappings: Record<string, number> }
  ): Promise<ReconciliationResult> => {
    const response = await api.post('/reconciliation/case1/process', {
      session_id: sessionId,
      account_6010: account6010Settings,
      esf_report: esfSettings,
    })
    return response.data
  },

  downloadCase1: (sessionId: string) => {
    return `${API_URL}/reconciliation/case1/download/${sessionId}`
  },

  // Case 2
  uploadCase2: async (ourAct: File, counterpartyAct: File): Promise<UploadResponse> => {
    const formData = new FormData()
    formData.append('our_act', ourAct)
    formData.append('counterparty_act', counterpartyAct)

    const response = await api.post('/reconciliation/case2/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  previewCase2: async (sessionId: string, fileKey: string, headerRow: number): Promise<PreviewResponse> => {
    const response = await api.post('/reconciliation/case2/preview', {
      session_id: sessionId,
      file_key: fileKey,
      header_row: headerRow,
      num_rows: 20,
    })
    return response.data
  },

  processCase2: async (
    sessionId: string,
    ourActSettings: { start_row?: number; header_row: number; column_mappings: Record<string, number>; date_extract_from_text?: boolean; date_format?: string; date_source_column?: number },
    counterpartyActSettings: { start_row?: number; header_row: number; column_mappings: Record<string, number>; date_extract_from_text?: boolean; date_format?: string; date_source_column?: number }
  ): Promise<ReconciliationResult> => {
    const response = await api.post('/reconciliation/case2/process', {
      session_id: sessionId,
      our_act: ourActSettings,
      counterparty_act: counterpartyActSettings,
    })
    return response.data
  },

  downloadCase2: (sessionId: string) => {
    return `${API_URL}/reconciliation/case2/download/${sessionId}`
  },

  // Case 3
  uploadCase3: async (account3310: File, esfReport: File): Promise<UploadResponse> => {
    const formData = new FormData()
    formData.append('account_3310', account3310)
    formData.append('esf_report', esfReport)

    const response = await api.post('/reconciliation/case3/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  previewCase3: async (sessionId: string, fileKey: string, headerRow: number): Promise<PreviewResponse> => {
    const response = await api.post('/reconciliation/case3/preview', {
      session_id: sessionId,
      file_key: fileKey,
      header_row: headerRow,
      num_rows: 20,
    })
    return response.data
  },

  processCase3: async (
    sessionId: string,
    account3310Settings: { header_row: number; column_mappings: Record<string, number>; doc_filter?: string },
    esfSettings: { header_row: number; column_mappings: Record<string, number> }
  ): Promise<ReconciliationResult> => {
    const response = await api.post('/reconciliation/case3/process', {
      session_id: sessionId,
      account_3310: account3310Settings,
      esf_report: esfSettings,
    })
    return response.data
  },

  downloadCase3: (sessionId: string) => {
    return `${API_URL}/reconciliation/case3/download/${sessionId}`
  },

  // Currency: USD 1С vs Нацбанк
  uploadCurrency: async (card1c: File, nbRates: File): Promise<UploadResponse> => {
    const formData = new FormData()
    formData.append('card_1c', card1c)
    formData.append('nb_rates', nbRates)
    const response = await api.post('/reconciliation/currency/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  processCurrency: async (sessionId: string): Promise<CurrencyResult> => {
    const response = await api.post('/reconciliation/currency/process', { session_id: sessionId })
    return response.data
  },

  downloadCurrency: (sessionId: string) => {
    return `${API_URL}/reconciliation/currency/download/${sessionId}`
  },

  // Bank: карточка 1С vs выписка
  uploadBank: async (card1c: File, bankStatement: File): Promise<UploadResponse> => {
    const formData = new FormData()
    formData.append('card_1c', card1c)
    formData.append('bank_statement', bankStatement)
    const response = await api.post('/reconciliation/bank/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  },

  processBank: async (sessionId: string): Promise<BankResult> => {
    const response = await api.post('/reconciliation/bank/process', { session_id: sessionId })
    return response.data
  },

  downloadBank: (sessionId: string) => {
    return `${API_URL}/reconciliation/bank/download/${sessionId}`
  },
}

// Licenses API
export const licensesApi = {
  getPlans: async (): Promise<LicensePlan[]> => {
    const response = await api.get('/licenses/plans')
    return response.data
  },

  getAllPlans: async (): Promise<LicensePlan[]> => {
    const response = await api.get('/licenses/plans/all')
    return response.data
  },

  createPlan: async (data: Omit<LicensePlan, 'id' | 'created_at' | 'updated_at'>): Promise<LicensePlan> => {
    const response = await api.post('/licenses/plans', data)
    return response.data
  },

  updatePlan: async (id: number, data: Partial<LicensePlan>): Promise<LicensePlan> => {
    const response = await api.put(`/licenses/plans/${id}`, data)
    return response.data
  },

  getMyLicense: async (): Promise<UserLicense | null> => {
    const response = await api.get('/licenses/my')
    return response.data
  },

  assign: async (userId: number, planId: number): Promise<UserLicense> => {
    const response = await api.post('/licenses/assign', { user_id: userId, plan_id: planId })
    return response.data
  },
}

// Services (access registry) API
export const servicesApi = {
  getMe: async (): Promise<Service[]> => {
    const response = await api.get('/services/me')
    return response.data
  },

  getAll: async (): Promise<ServiceAdmin[]> => {
    const response = await api.get('/services')
    return response.data
  },

  update: async (
    code: string,
    data: Partial<Pick<ServiceAdmin, 'title' | 'description' | 'status' | 'is_enabled' | 'sort_order'>>
  ): Promise<ServiceAdmin> => {
    const response = await api.put(`/services/${code}`, data)
    return response.data
  },

  setAccess: async (code: string, roles: string[]): Promise<ServiceAdmin> => {
    const response = await api.put(`/services/${code}/access`, { roles })
    return response.data
  },

  setOverride: async (code: string, userId: number, allow: boolean): Promise<ServiceAdmin> => {
    const response = await api.post(`/services/${code}/override`, { user_id: userId, allow })
    return response.data
  },

  deleteOverride: async (code: string, userId: number) => {
    const response = await api.delete(`/services/${code}/override/${userId}`)
    return response.data
  },
}

// Changelog API
export const changelogApi = {
  getAll: async (): Promise<ChangelogEntry[]> => {
    const response = await api.get('/changelog')
    return response.data
  },

  create: async (data: ChangelogInput): Promise<ChangelogEntry> => {
    const response = await api.post('/changelog', data)
    return response.data
  },

  update: async (id: number, data: Partial<ChangelogInput>): Promise<ChangelogEntry> => {
    const response = await api.patch(`/changelog/${id}`, data)
    return response.data
  },

  delete: async (id: number) => {
    const response = await api.delete(`/changelog/${id}`)
    return response.data
  },
}

// Settings API
export const settingsApi = {
  getPublic: async (): Promise<PublicSettings> => {
    const response = await api.get('/settings/public')
    return response.data
  },

  getAll: async (): Promise<Record<string, string>> => {
    const response = await api.get('/settings')
    return response.data
  },

  update: async (settings: Record<string, string>) => {
    const response = await api.put('/settings', { settings })
    return response.data
  },
}

// ============================ Personnel (HR) ============================

export interface PersonnelCompany {
  id: number
  name_ru: string
  name_kk: string
  bin: string
  city: string
  legal_address: string
  actual_address: string
  director_fio_ru: string
  director_fio_kk: string
  director_gender: string
  signatory_position: string
  signer_position_kz: string
  acts_on_basis: string
  address_kz: string
  state_registration_date: string | null
  bank: string
  iik: string
  bik: string
  header_requisites: string
  logo_path: string
  created_at?: string
}

export interface PersonnelEmployee {
  id: number
  last_name: string
  first_name: string
  middle_name: string
  iin: string
  document_type: string
  document_number: string
  document_issued_by: string
  document_issue_date: string | null
  registration_address: string
  actual_address: string
  phone: string
  email: string
  birth_date: string | null
  gender: string
  iban: string
  citizenship: string
  fio_full_kz: string
  id_document_kz: string
  fio_genitive_override: string | null
  fio_dative_override: string | null
  fio_accusative_override: string | null
  warnings?: string[]
}

export interface PersonnelEmployment {
  id: number
  company_id: number
  employee_id: number
  position_ru: string
  position_kk: string
  department: string
  contract_type: string
  start_date: string | null
  end_date: string | null
  probation_months: number
  salary: string | number
  salary_kind: string          // gross (к начислению) | net (на руки) — метка суммы для ТД
  currency: string
  allowances: string
  rate: string | number
  salary_words_override: string | null
  workplace: string
  workplace_kz: string
  conditions: string
  hours_per_day: string | number | null
  hours_per_week: number | null
  work_time_from: string
  work_time_to: string
  lunch_from: string
  lunch_to: string
  days_off: string
  vacation_days: number
  material_liability: boolean
  confidentiality: boolean
  ipn_deduction: string
  contract_number: string
  contract_date: string | null
  order_number: string
  order_date: string | null
  application_date: string | null
  warnings?: string[]
}

export interface IinCheck {
  valid: boolean
  birth_date: string | null
  gender: string | null
  warnings: string[]
}

export interface PrikazPreview {
  context: Record<string, unknown>
  editable: {
    employee: { fio_genitive: string; fio_dative: string; fio_accusative: string }
    employment: { position_ru: string; salary_words_ru: string }
  }
  warnings: string[]
}

// The whole hiring, sent in the request body — the server stores nothing.
export interface PrikazBody {
  company: Partial<PersonnelCompany>
  employee: Partial<PersonnelEmployee>
  employment: Partial<PersonnelEmployment>
  hr_responsible_fio?: string
}

export interface InventoryItem {
  name: string
  code: string
  unit: string
  qty: string | number
  price: string | number
}

export interface CommissionMember {
  position: string
  fio_short: string
}

export interface InventoryColumn {
  index: number
  title: string
  samples: string[]
}

export interface InventoryParse {
  status: 'parsed' | 'needs_mapping'
  items: InventoryItem[]
  columns: InventoryColumn[]
  header_row: number | null
}

export interface InventoryMapping {
  header_row: number
  col_name: number
  col_qty: number
  col_price: number
  col_code?: number
  col_unit?: number
}

export interface LiabilityInput {
  number: string
  doc_date: string | null
}

export interface ActInput {
  number: string
  doc_date: string | null
  basis: string          // свободное «Основание» (напр. «приказ № 14 от …»); пусто → не выводится
  notes: string
  commission: CommissionMember[]
}

// Данные трудового договора (§4.2). kind: indefinite | fixed | task | substitute.
export interface ContractInput {
  number: string
  doc_date: string | null
  kind: string
  term_count: number | null      // для срочного: срок = term_count + term_unit
  term_unit: string              // year | month
  end_date: string | null
  task: string                   // для договора на время выполнения работы (ru)
  task_kz: string                // то же (kz, вручную)
  confidential_years: string
}

// Договор о неконкуренции (§4.5). Сроки/условия — поля, не константы.
export interface NonCompeteInput {
  number: string
  doc_date: string | null
  term_noncompete: string
  term_nonsolicit: string
  term_confidential: string
  territory: string
  activity: string
  competitors: string
  penalty: string
}

export interface PerechenPosition {
  name: string
  reason: string
}

// Приказ об утверждении перечня должностей (к договору о неконкуренции).
export interface PerechenInput {
  number: string
  doc_date: string | null
  responsible_fio: string
  responsible_position: string
  control: string
  positions: PerechenPosition[]
  acquainted: CommissionMember[]
}

// Согласие на сбор и обработку персональных данных (§4.7).
export interface RecipientInput {
  name: string
  bin: string          // необязательно
  purpose: string
  scope: string
}
export interface SoglasieInput {
  doc_date: string | null
  recipients: RecipientInput[]
  cross_border: boolean
  cross_border_countries: string
  cross_border_purpose: string
  responsible_position: string
  responsible_fio: string
  responsible_contacts: string
}

// Данные приказа об ответственном за ПД + Положения о ПД (§4.6).
export interface PolicyInput {
  order_number: string
  doc_date: string | null
  responsible_fio: string        // им.п. → склоняется в винительный на сервере
  responsible_position: string   // им.п. → склоняется в винительный
  deadline: string | null        // срок ознакомления
  control: string
  acquainted: CommissionMember[]
}

// Document package (ZIP) — everything in the body, server stores nothing.
export interface PackageBody {
  company: Partial<PersonnelCompany>
  employee: Partial<PersonnelEmployee>
  employment: Partial<PersonnelEmployment>
  hr_responsible_fio?: string
  documents: string[]
  deductions?: string[]
  apply_from?: string | null
  liability?: LiabilityInput | null
  act?: ActInput | null
  inventory?: InventoryItem[]
  policy?: PolicyInput | null
  contract?: ContractInput | null
  noncompete?: NonCompeteInput | null
  perechen?: PerechenInput | null
  consent?: SoglasieInput | null
}

// Trigger a browser download from a blob response, honouring the server filename.
function downloadBlob(blob: Blob, contentDisposition: string | undefined, fallback: string) {
  let filename = fallback
  const match = contentDisposition?.match(/filename\*=UTF-8''([^;]+)/i)
  if (match) filename = decodeURIComponent(match[1])
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

export const personnelApi = {
  // ИИН travels only in the request body (PII rule).
  validateIin: async (iin: string, birth_date?: string | null, gender?: string | null): Promise<IinCheck> => {
    const response = await api.post('/personnel/validate/iin', { iin, birth_date, gender })
    return response.data
  },
  validateBin: async (bin: string): Promise<{ valid: boolean }> => {
    const response = await api.post('/personnel/validate/bin', { bin })
    return response.data
  },

  // Company (employer requisites) is the only stored entity — kept so users
  // don't re-type the БИН and director every time.
  listCompanies: async (): Promise<PersonnelCompany[]> => (await api.get('/personnel/companies')).data,
  createCompany: async (data: Partial<PersonnelCompany>): Promise<PersonnelCompany> =>
    (await api.post('/personnel/companies', data)).data,
  updateCompany: async (id: number, data: Partial<PersonnelCompany>): Promise<PersonnelCompany> =>
    (await api.put(`/personnel/companies/${id}`, data)).data,

  // Stateless generation — the whole hiring is in the body, nothing is stored.
  prikazPreview: async (body: PrikazBody): Promise<PrikazPreview> =>
    (await api.post('/personnel/documents/prikaz/preview', body)).data,

  generatePrikaz: async (body: PrikazBody): Promise<void> => {
    const response = await api.post('/personnel/documents/prikaz', body, { responseType: 'blob' })
    downloadBlob(response.data, response.headers['content-disposition'], 'ПриказПриём.docx')
  },

  // Parse an .xlsx опись. Without a mapping the server auto-detects columns (by
  // synonyms) and the header row (below any 1С preamble); if it can't, it returns
  // status 'needs_mapping' with the columns so the client shows a mapping screen.
  parseInventory: async (file: File, mapping?: InventoryMapping): Promise<InventoryParse> => {
    const fd = new FormData()
    fd.append('file', file)
    if (mapping) {
      fd.append('header_row', String(mapping.header_row))
      fd.append('col_name', String(mapping.col_name))
      fd.append('col_qty', String(mapping.col_qty))
      fd.append('col_price', String(mapping.col_price))
      if (mapping.col_code != null) fd.append('col_code', String(mapping.col_code))
      if (mapping.col_unit != null) fd.append('col_unit', String(mapping.col_unit))
    }
    const r = await api.post('/personnel/parse-inventory', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    return r.data
  },

  generatePackage: async (body: PackageBody): Promise<void> => {
    const response = await api.post('/personnel/documents/package', body, { responseType: 'blob' })
    downloadBlob(response.data, response.headers['content-disposition'], 'Пакет.zip')
  },

  // Справочник должностей рус→каз: подбор по русской должности и сохранение пары.
  translatePosition: async (ru: string): Promise<{ position_ru: string; position_kk: string }> =>
    (await api.get('/personnel/positions/translate', { params: { ru } })).data,
  savePositionTranslation: async (position_ru: string, position_kk: string): Promise<void> => {
    await api.post('/personnel/positions/translate', { position_ru, position_kk })
  },
}

// ─── Помогайка по форме 101.04 (внутренняя бета) ───────────────────────────
// Пока только /meta: версия справочника и константы года. Движок расчёта —
// следующая фаза, налоговая логика живёт на бэкенде и на фронт не дублируется.

export interface F10104Meta {
  rules_version: string
  valid_from: string
  tax_code: string
  status: string
  refbooks: {
    kpn_rates: number
    service_kinds: number
    income_codes: number
    offshore_list: number
    conventions: number
    flags: number
  }
  constants: {
    source: string
    mrp: number
    mzp: number
    vat_rate: number
    vat_registration_threshold_mrp: number
    vat_registration_threshold_kzt: number
  }
  engine: string
}

export interface F10104Country {
  key: string
  name: string
  iso: string | null
  is_offshore: boolean
  offshore_no: number | null
  has_convention: boolean
  is_eaeu: boolean
}

export interface F10104ServiceKind {
  id: string
  label: string
  group: string
}

export interface F10104Flag {
  code: string
  severity: 'info' | 'medium' | 'high'
  title: string
  text: string
  basis: string | null
}

export interface F10104Refbooks {
  rules_version: string
  countries: F10104Country[]
  currencies: string[]
  service_kinds: F10104ServiceKind[]
  flags: Record<string, F10104Flag>
  vat_exemptions: { id: string; label: string }[]
  disclaimer: {
    text: string
    print_footer: string
    manual_review_banner: string
    // Свой текст для экрана выхода: там расчёта нет, и общая формулировка
    // «помогайка формирует расчёт» читалась бы несогласованно.
    out_of_scope_text: string
  }
  // Спорная ставка по дивидендам: обе позиции и условия выбора. Тексты
  // приходят с сервера — своей редакции спорной нормы у интерфейса нет.
  disputed_dividends: F10104DisputedDividends
  // Экраны выхода за периметр. Ключ — вид дохода, по которому помогайка
  // не считает; тексты только отсюда, своих в интерфейсе нет.
  out_of_scope: Record<string, F10104OutOfScope>
  // Подсказки под вопросами: ключ — идентификатор вопроса из ТЗ §4.
  question_hints: Record<string, string>
  // Памятка по документу о резидентстве. Отдельная страница: её отправляют
  // нерезиденту, поэтому она читается без контекста расчёта.
  cert_memo: F10104CertMemo
}

export interface F10104CertMemo {
  title: string
  sections: {
    heading: string
    lead?: string
    items?: string[]
    basis?: string
    note?: string
  }[]
}

export interface F10104OutOfScope {
  title: string
  lead: string
  forks?: { q: string; a: string; norms?: string | string[] }[]
  what_to_do: string
}

export interface F10104DisputedPosition {
  id: string
  rate: number
  basis: string
  argument?: string
  progressive?: { threshold_mrp: number; rate_above: number }
}

export interface F10104DisputedDividends {
  label: string
  positions: F10104DisputedPosition[]
  what_to_check: string | null
  money_at_stake: string | null
  user_resolution: {
    answer_key: string
    basis_answer_key: string
    requires_basis: boolean
    values: string[]
    rules: string[]
  }
}

// Ответы визарда: ключ — идентификатор вопроса из ТЗ §4 («S1.1», «S4.2»).
export type F10104Answers = Record<string, unknown>

export const f10104Api = {
  getMeta: async (): Promise<F10104Meta> => (await api.get('/f10104/meta')).data,

  getRefbooks: async (): Promise<F10104Refbooks> => (await api.get('/f10104/refbooks')).data,

  // Расчёт целиком на сервере: налоговой логики на фронтенде нет.
  evaluate: async (answers: F10104Answers): Promise<Record<string, any>> =>
    (await api.post('/f10104/evaluate', { answers })).data,

  // Текст статьи по ссылке вида «ст. 682 п. 1 пп. 5)». Тянется по клику,
  // а не заранее: файл статей — 417 КБ, грузить его ради двух ссылок незачем.
  getArticle: async (ref: string): Promise<F10104Article> =>
    (await api.get('/f10104/article', { params: { ref } })).data,
}

export interface F10104Article {
  kind: 'nk' | 'treaty' | 'other_code' | 'missing' | 'unparsed'
  ref: string
  title?: string | null
  text?: string | null
  note?: string | null
}

// ─── Курсы валют НБ РК ─────────────────────────────────────────────────────
// Общий сервис, не часть помогайки: доступен любому аутентифицированному
// пользователю и будет переиспользован отдельным модулем курсов.

export interface NbrkRateRow {
  date: string
  code: string
  name: string | null
  rate: number
  quant: number
  carriedForward: boolean
  sourceDate: string
}

export interface NbrkOfficialRate {
  code: string
  name: string | null
  rate: number
  quant: number
  requestedDate: string
  actualDate: string
  carriedForward: boolean
}

export const ratesApi = {
  getRange: async (codes: string[], from: string, to: string): Promise<NbrkRateRow[]> =>
    (await api.get('/api/rates', {
      params: { codes: codes.length ? codes.join(',') : 'ALL', from, to },
    })).data,

  getOfficial: async (code: string, date: string): Promise<NbrkOfficialRate> =>
    (await api.get('/api/rates/official', { params: { code, date } })).data,
}

export default api
