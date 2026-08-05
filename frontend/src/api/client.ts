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
  acts_on_basis: string
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
  currency: string
  allowances: string
  rate: string | number
  salary_words_override: string | null
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
}

export default api
