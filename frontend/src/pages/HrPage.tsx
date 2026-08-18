import { useEffect, useRef, useState, type CSSProperties } from 'react'
import {
  personnelApi,
  type PersonnelCompany,
  type PersonnelEmployee,
  type PersonnelEmployment,
  type IinCheck,
  type PrikazPreview,
  type PrikazBody,
  type PackageBody,
  type InventoryItem,
  type InventoryColumn,
  type CommissionMember,
  type PolicyInput,
  type ContractInput,
} from '../api/client'

const CATEGORY_OPTIONS: [string, string][] = [
  ['ignore', '— игнорировать —'],
  ['name', 'Наименование'],
  ['qty', 'Количество'],
  ['price', 'Цена'],
  ['code', 'Код / инв. номер'],
  ['unit', 'Ед. изм.'],
]

// The module is STATELESS: employees' personal data is never sent to storage.
// The whole draft lives on the client (localStorage) and is POSTed only to render
// a document. It survives a reload and auto-clears after a day.
const DRAFT_KEY = 'hr_priem_draft_v2'
const DRAFT_TTL_MS = 24 * 60 * 60 * 1000

type ActDraft = {
  number: string; doc_date: string | null; basis: string; notes: string; commission: CommissionMember[]
}

type Draft = {
  company: Partial<PersonnelCompany>
  employee: Partial<PersonnelEmployee>
  employment: Partial<PersonnelEmployment>
  companyId?: number
  savedAt?: number
  documents: Record<string, boolean>
  liability: { number: string; doc_date: string | null }
  act: ActDraft
  inventory: InventoryItem[]
  deductions: string[]
  applyFromMonth: string          // 'YYYY-MM'; пусто → месяц приёма
  policy: PolicyInput
  contract: ContractInput
}

const EMPTY_DRAFT: Draft = {
  company: { director_gender: 'male', signatory_position: 'Директор', acts_on_basis: 'Устава' },
  employee: { document_type: 'id_card', gender: 'male', citizenship: 'Республики Казахстан' },
  employment: {
    contract_type: 'indefinite', rate: '1', probation_months: 0, currency: 'KZT',
    work_time_from: '09:00', work_time_to: '18:00', lunch_from: '13:00', lunch_to: '14:00',
    days_off: 'суббота, воскресенье', vacation_days: 24, ipn_deduction: 'base_30_mrp',
  },
  documents: { prikaz: true, zayavlenie: false, td: false, matotvet: false, akt: false, polozhenie_pd: false, prikaz_pd: false },
  liability: { number: '', doc_date: null },
  act: { number: '', doc_date: null, basis: '', notes: '', commission: [] },
  inventory: [],
  deductions: ['base_30_mrp'],
  applyFromMonth: '',
  policy: {
    order_number: '', doc_date: null, responsible_fio: '', responsible_position: '',
    deadline: null, control: 'оставляю за собой', acquainted: [],
  },
  contract: {
    number: '', doc_date: null, kind: 'indefinite', term_count: null, term_unit: 'year',
    end_date: null, task: '', task_kz: '', confidential_years: '3',
  },
}

const num = (v: string | number | null | undefined): number => {
  const n = parseFloat(String(v ?? '').replace(/\s/g, '').replace(',', '.'))
  return Number.isFinite(n) ? n : 0
}
const fmt = (n: number): string => n.toLocaleString('ru-RU').replace(/,/g, ' ')

const cellS: CSSProperties = { padding: '4px 6px', borderBottom: '1px solid #f1f5f9' }
const inS: CSSProperties = { width: '100%', padding: '4px 6px' }

const PACKAGE_DOCS: [string, string][] = [
  ['prikaz', 'Приказ о приёме на работу'],
  ['zayavlenie', 'Заявление на налоговые вычеты (ИПН)'],
  ['td', 'Трудовой договор (двуязычный)'],
  ['matotvet', 'Договор о полной материальной ответственности'],
  ['akt', 'Акт приёма-передачи ценностей'],
  ['polozhenie_pd', 'Положение о персональных данных'],
  ['prikaz_pd', 'Приказ об ответственном за персональные данные'],
]

const CONTRACT_KINDS: [string, string][] = [
  ['indefinite', 'Бессрочный'],
  ['fixed', 'Срочный (на срок)'],
  ['task', 'На время выполнения работы'],
  ['substitute', 'На время замещения'],
]

const DEDUCTION_OPTIONS: [string, string][] = [
  ['base_30_mrp', 'Базовый вычет 30 МРП (за каждый месяц)'],
  ['social_payments', 'Соц. платежи (ОПВ, ВОСМС)'],
  ['social_882', 'Социальный вычет 882 МРП'],
  ['social_5000', 'Социальный вычет 5 000 МРП'],
]

// 'YYYY-MM-DD' | 'YYYY-MM' → 'YYYY-MM' (для input type=month и apply_from по месяцу)
const monthOf = (d: string | null | undefined): string => (d ? String(d).slice(0, 7) : '')

function loadDraft(): Draft {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (raw) {
      const d = JSON.parse(raw) as Draft
      if (d.savedAt && Date.now() - d.savedAt > DRAFT_TTL_MS) {
        localStorage.removeItem(DRAFT_KEY)   // gigiene: auto-clear stale drafts
        return EMPTY_DRAFT
      }
      return { ...EMPTY_DRAFT, ...d }
    }
  } catch { /* ignore */ }
  return EMPTY_DRAFT
}

function errText(e: unknown, fallback: string): string {
  // @ts-expect-error narrow axios shape
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail.map((d: { msg: string }) => d.msg).join('; ')
  return fallback
}

function body(d: Draft): PrikazBody {
  return { company: d.company, employee: d.employee, employment: d.employment }
}

function Field(props: {
  label: string; value: string | number | null | undefined
  onChange: (v: string) => void; type?: string; placeholder?: string
}) {
  return (
    <div className="form-group">
      <label>{props.label}</label>
      <input type={props.type || 'text'} value={props.value ?? ''} placeholder={props.placeholder}
        onChange={(e) => props.onChange(e.target.value)} />
    </div>
  )
}

export default function HrPage() {
  const [draft, setDraft] = useState<Draft>(loadDraft)
  const [companies, setCompanies] = useState<PersonnelCompany[]>([])
  const [iin, setIin] = useState<IinCheck | null>(null)
  const [preview, setPreview] = useState<PrikazPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const importRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...draft, savedAt: Date.now() }))
  }, [draft])
  useEffect(() => { personnelApi.listCompanies().then(setCompanies).catch(() => {}) }, [])

  const setCompany = (patch: Partial<PersonnelCompany>) => setDraft((d) => ({ ...d, company: { ...d.company, ...patch } }))
  const setEmployee = (patch: Partial<PersonnelEmployee>) => setDraft((d) => ({ ...d, employee: { ...d.employee, ...patch } }))
  const setEmployment = (patch: Partial<PersonnelEmployment>) => setDraft((d) => ({ ...d, employment: { ...d.employment, ...patch } }))

  const flash = (m: string) => { setNotice(m); setError(''); setTimeout(() => setNotice(''), 3000) }
  const fail = (e: unknown, fb: string) => setError(errText(e, fb))

  async function checkIin(value: string) {
    if (!value) { setIin(null); return }
    try {
      const res = await personnelApi.validateIin(value, draft.employee.birth_date, draft.employee.gender)
      setIin(res)
      if (res.valid) {
        const patch: Partial<PersonnelEmployee> = {}
        if (res.birth_date && !draft.employee.birth_date) patch.birth_date = res.birth_date
        if (res.gender && !draft.employee.gender) patch.gender = res.gender
        if (Object.keys(patch).length) setEmployee(patch)
      }
    } catch (e) { fail(e, 'Не удалось проверить ИИН') }
  }

  // Company is the one stored entity (open-registry requisites) — optional convenience.
  async function saveCompanyToDirectory() {
    setBusy(true); setError('')
    try {
      const saved = draft.companyId
        ? await personnelApi.updateCompany(draft.companyId, draft.company)
        : await personnelApi.createCompany(draft.company)
      setDraft((d) => ({ ...d, companyId: saved.id, company: saved }))
      setCompanies(await personnelApi.listCompanies())
      flash('Компания сохранена в справочник')
    } catch (e) { fail(e, 'Не удалось сохранить компанию') } finally { setBusy(false) }
  }
  function pickCompany(id: number) {
    const c = companies.find((x) => x.id === id)
    if (c) setDraft((d) => ({ ...d, companyId: c.id, company: c }))
  }

  async function loadPreview() {
    setBusy(true); setError('')
    try { setPreview(await personnelApi.prikazPreview(body(draft))) }
    catch (e) { fail(e, 'Не удалось получить предпросмотр') } finally { setBusy(false) }
  }

  // Editing an auto-value updates the client draft, then re-previews. Nothing is stored.
  async function applyEmployeeEdit(field: string, value: string) {
    const next = { ...draft, employee: { ...draft.employee, [field]: value } }
    setDraft(next)
    setBusy(true); setError('')
    try { setPreview(await personnelApi.prikazPreview(body(next))); flash('Правка учтена') }
    catch (e) { fail(e, 'Ошибка') } finally { setBusy(false) }
  }
  async function applyEmploymentEdit(field: string, value: string) {
    const next = { ...draft, employment: { ...draft.employment, [field]: value } }
    setDraft(next)
    setBusy(true); setError('')
    try { setPreview(await personnelApi.prikazPreview(body(next))); flash('Правка учтена') }
    catch (e) { fail(e, 'Ошибка') } finally { setBusy(false) }
  }

  async function download() {
    setBusy(true); setError('')
    try { await personnelApi.generatePrikaz(body(draft)) }
    catch (e) { fail(e, 'Не удалось сформировать приказ') } finally { setBusy(false) }
  }

  // --- document package (заход 1: matotvet + akt) ---
  const [importPreview, setImportPreview] = useState<InventoryItem[] | null>(null)
  const [mapping, setMapping] = useState<
    { columns: InventoryColumn[]; header_row: number; file: File; assign: Record<number, string> } | null
  >(null)
  const invRef = useRef<HTMLInputElement>(null)

  const toggleDoc = (key: string) =>
    setDraft((d) => ({ ...d, documents: { ...d.documents, [key]: !d.documents[key] } }))
  const setLiability = (patch: Partial<Draft['liability']>) =>
    setDraft((d) => ({ ...d, liability: { ...d.liability, ...patch } }))
  const setAct = (patch: Partial<ActDraft>) =>
    setDraft((d) => ({ ...d, act: { ...d.act, ...patch } }))
  const toggleDeduction = (key: string) =>
    setDraft((d) => ({
      ...d,
      deductions: d.deductions.includes(key) ? d.deductions.filter((k) => k !== key) : [...d.deductions, key],
    }))
  const setPolicy = (patch: Partial<PolicyInput>) =>
    setDraft((d) => ({ ...d, policy: { ...d.policy, ...patch } }))
  const addAcquainted = () =>
    setPolicy({ acquainted: [...draft.policy.acquainted, { position: '', fio_short: '' }] })
  const updateAcquainted = (i: number, patch: Partial<CommissionMember>) =>
    setPolicy({ acquainted: draft.policy.acquainted.map((r, j) => (j === i ? { ...r, ...patch } : r)) })
  const deleteAcquainted = (i: number) =>
    setPolicy({ acquainted: draft.policy.acquainted.filter((_, j) => j !== i) })
  const setContract = (patch: Partial<ContractInput>) =>
    setDraft((d) => ({ ...d, contract: { ...d.contract, ...patch } }))

  const addRow = () =>
    setDraft((d) => ({ ...d, inventory: [...d.inventory, { name: '', code: '', unit: '', qty: '', price: '' }] }))
  const updateRow = (i: number, patch: Partial<InventoryItem>) =>
    setDraft((d) => ({ ...d, inventory: d.inventory.map((r, j) => (j === i ? { ...r, ...patch } : r)) }))
  const deleteRow = (i: number) =>
    setDraft((d) => ({ ...d, inventory: d.inventory.filter((_, j) => j !== i) }))

  const addCommission = () =>
    setAct({ commission: [...draft.act.commission, { position: '', fio_short: '' }] })
  const updateCommission = (i: number, patch: Partial<CommissionMember>) =>
    setAct({ commission: draft.act.commission.map((r, j) => (j === i ? { ...r, ...patch } : r)) })
  const deleteCommission = (i: number) =>
    setAct({ commission: draft.act.commission.filter((_, j) => j !== i) })

  async function onInventoryFile(file: File) {
    setError('')
    try {
      const res = await personnelApi.parseInventory(file)
      if (res.status === 'needs_mapping') {
        setMapping({ columns: res.columns, header_row: res.header_row ?? 0, file, assign: {} })
      } else if (!res.items.length) {
        setError('В файле не найдено ни одной позиции')
      } else {
        setImportPreview(res.items)   // show recognized rows BEFORE adding — confirm/cancel
      }
    } catch (e) { fail(e, 'Не удалось разобрать файл') }
    finally { if (invRef.current) invRef.current.value = '' }
  }
  function confirmImport() {
    if (importPreview) setDraft((d) => ({ ...d, inventory: [...d.inventory, ...importPreview] }))
    setImportPreview(null); flash('Опись добавлена')
  }

  const setAssign = (ci: number, cat: string) =>
    setMapping((m) => (m ? { ...m, assign: { ...m.assign, [ci]: cat } } : m))

  async function confirmMapping() {
    if (!mapping) return
    const picked: Record<string, number> = { name: -1, qty: -1, price: -1, code: -1, unit: -1 }
    Object.entries(mapping.assign).forEach(([ci, cat]) => {
      if (cat && cat !== 'ignore') picked[cat] = Number(ci)
    })
    if (picked.name < 0 || picked.qty < 0 || picked.price < 0) {
      setError('Укажите колонки: наименование, количество и цена'); return
    }
    setBusy(true); setError('')
    try {
      const res = await personnelApi.parseInventory(mapping.file, {
        header_row: mapping.header_row,
        col_name: picked.name, col_qty: picked.qty, col_price: picked.price,
        col_code: picked.code >= 0 ? picked.code : undefined,
        col_unit: picked.unit >= 0 ? picked.unit : undefined,
      })
      setMapping(null)
      if (res.items.length) setImportPreview(res.items)
      else setError('С этим сопоставлением позиций не найдено')
    } catch (e) { fail(e, 'Не удалось импортировать') } finally { setBusy(false) }
  }

  const invTotal = draft.inventory.reduce((sum, r) => sum + num(r.qty) * num(r.price), 0)

  async function generatePackage() {
    const documents = Object.keys(draft.documents).filter((k) => draft.documents[k])
    if (!documents.length) { setError('Отметьте хотя бы один документ'); return }
    if (draft.documents.akt && draft.inventory.length === 0) {
      setError('Для акта приёма-передачи добавьте хотя бы одну позицию описи (или снимите галочку «Акт»)')
      return
    }
    if (draft.documents.zayavlenie && draft.deductions.length === 0) {
      setError('Для заявления на вычеты отметьте хотя бы один вид вычета (или снимите галочку «Заявление»)')
      return
    }
    if (draft.documents.td && draft.contract.kind === 'fixed' && !draft.contract.term_count && !draft.contract.end_date) {
      setError('Для срочного договора укажите срок (число + единица) или дату окончания')
      return
    }
    const b: PackageBody = {
      company: draft.company, employee: draft.employee, employment: draft.employment, documents,
    }
    if (draft.documents.matotvet || draft.documents.akt) b.liability = draft.liability
    if (draft.documents.akt) { b.act = draft.act; b.inventory = draft.inventory }
    if (draft.documents.zayavlenie) {
      b.deductions = draft.deductions
      // пусто → сервер берёт месяц приёма (employment.start_date); иначе первый день выбранного месяца
      b.apply_from = draft.applyFromMonth ? `${draft.applyFromMonth}-01` : null
    }
    if (draft.documents.polozhenie_pd || draft.documents.prikaz_pd) b.policy = draft.policy
    if (draft.documents.td) b.contract = draft.contract
    setBusy(true); setError('')
    try { await personnelApi.generatePackage(b) }
    catch (e) { fail(e, 'Не удалось сформировать пакет') } finally { setBusy(false) }
  }

  function exportDraft() {
    const blob = new Blob([JSON.stringify(draft, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `черновик_приём_${draft.employee.last_name || 'без_имени'}.json`
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url)
  }
  function importDraft(file: File) {
    const reader = new FileReader()
    reader.onload = () => {
      try { setDraft({ ...EMPTY_DRAFT, ...JSON.parse(String(reader.result)) }); setPreview(null); flash('Черновик загружен') }
      catch { setError('Не удалось прочитать файл черновика') }
    }
    reader.readAsText(file)
  }
  function resetDraft() {
    if (!confirm('Очистить все введённые данные?')) return
    localStorage.removeItem(DRAFT_KEY)
    setDraft(EMPTY_DRAFT); setPreview(null); setIin(null); setError(''); setNotice('')
  }

  const c = draft.company, e = draft.employee, m = draft.employment

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', paddingBottom: 60 }}>
      <h2 style={{ margin: '16px 0' }}>Приём на работу</h2>

      <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', color: '#9a3412', padding: '12px 16px', borderRadius: 8, marginBottom: 16 }}>
        <strong>Данные не сохраняются на сервере.</strong> Сервис не хранит персональные данные ваших
        сотрудников — заполненная форма живёт только в этом браузере. Скачайте документы до закрытия
        страницы. Черновик можно сохранить файлом (кнопка ниже) и загрузить позже.
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
        <button className="btn btn-secondary" onClick={exportDraft}>Скачать черновик (JSON)</button>
        <button className="btn btn-secondary" onClick={() => importRef.current?.click()}>Загрузить черновик</button>
        <input ref={importRef} type="file" accept="application/json" style={{ display: 'none' }}
          onChange={(ev) => ev.target.files?.[0] && importDraft(ev.target.files[0])} />
        <button className="btn btn-secondary" onClick={resetDraft}>Очистить данные</button>
      </div>

      {error && <div className="error-message">{error}</div>}
      {notice && <div style={{ background: '#ecfdf5', color: '#065f46', padding: '10px 14px', borderRadius: 8, marginBottom: 12 }}>{notice}</div>}

      {/* 1. Company */}
      <section style={{ marginBottom: 28 }}>
        <h3>1. Работодатель</h3>
        {companies.length > 0 && (
          <div className="form-group">
            <label>Выбрать из справочника</label>
            <select value={draft.companyId ?? ''} onChange={(ev) => pickCompany(Number(ev.target.value))}>
              <option value="">— заполнить вручную —</option>
              {companies.map((x) => <option key={x.id} value={x.id}>{x.name_ru} (БИН {x.bin})</option>)}
            </select>
          </div>
        )}
        <Field label="Наименование (рус)" value={c.name_ru} onChange={(v) => setCompany({ name_ru: v })} />
        <Field label="БИН" value={c.bin} onChange={(v) => setCompany({ bin: v })} placeholder="12 цифр" />
        <Field label="Город" value={c.city} onChange={(v) => setCompany({ city: v })} />
        <Field label="Юридический адрес" value={c.legal_address} onChange={(v) => setCompany({ legal_address: v })} />
        <Field label="ФИО директора (им.п.)" value={c.director_fio_ru} onChange={(v) => setCompany({ director_fio_ru: v })} placeholder="Иванов Иван Иванович" />
        <div className="form-group">
          <label>Пол подписанта</label>
          <select value={c.director_gender ?? 'male'} onChange={(ev) => setCompany({ director_gender: ev.target.value })}>
            <option value="male">муж.</option><option value="female">жен.</option>
          </select>
        </div>
        <Field label="Должность подписанта" value={c.signatory_position} onChange={(v) => setCompany({ signatory_position: v })} />
        <Field label="Действует на основании" value={c.acts_on_basis} onChange={(v) => setCompany({ acts_on_basis: v })} />
        <button className="btn btn-secondary" onClick={saveCompanyToDirectory} disabled={busy}>
          {draft.companyId ? 'Обновить в справочнике' : 'Сохранить в справочник (реквизиты юрлица)'}
        </button>
      </section>

      {/* 2. Employee */}
      <section style={{ marginBottom: 28 }}>
        <h3>2. Работник</h3>
        <Field label="Фамилия" value={e.last_name} onChange={(v) => setEmployee({ last_name: v })} />
        <Field label="Имя" value={e.first_name} onChange={(v) => setEmployee({ first_name: v })} />
        <Field label="Отчество" value={e.middle_name} onChange={(v) => setEmployee({ middle_name: v })} />
        <div className="form-group">
          <label>ИИН</label>
          <input value={e.iin ?? ''} placeholder="12 цифр"
            onChange={(ev) => setEmployee({ iin: ev.target.value })}
            onBlur={(ev) => checkIin(ev.target.value)} />
          {iin && !iin.valid && (
            <div style={{ color: '#b91c1c', fontSize: 13, marginTop: 4 }}>
              ИИН не прошёл проверку: нужно 12 цифр с верной контрольной суммой и корректной датой рождения.
            </div>
          )}
          {iin && iin.valid && (
            <div style={{ color: '#065f46', fontSize: 13, marginTop: 4 }}>
              ИИН корректен{iin.birth_date ? `, дата рождения ${iin.birth_date}` : ''}{iin.gender ? `, пол ${iin.gender === 'male' ? 'муж.' : 'жен.'}` : ''}.
              {iin.warnings.length > 0 && <div style={{ color: '#b45309' }}>{iin.warnings.join('; ')}</div>}
            </div>
          )}
        </div>
        <div className="form-group">
          <label>Документ</label>
          <select value={e.document_type ?? 'id_card'} onChange={(ev) => setEmployee({ document_type: ev.target.value })}>
            <option value="id_card">удостоверение личности</option>
            <option value="passport">паспорт</option>
          </select>
        </div>
        <Field label="Номер документа" value={e.document_number} onChange={(v) => setEmployee({ document_number: v })} />
        <Field label="Кем выдан" value={e.document_issued_by} onChange={(v) => setEmployee({ document_issued_by: v })} />
        <Field label="Дата выдачи" type="date" value={e.document_issue_date} onChange={(v) => setEmployee({ document_issue_date: v })} />
        <Field label="Дата рождения" type="date" value={e.birth_date} onChange={(v) => setEmployee({ birth_date: v })} />
        <div className="form-group">
          <label>Пол</label>
          <select value={e.gender ?? 'male'} onChange={(ev) => setEmployee({ gender: ev.target.value })}>
            <option value="male">муж.</option><option value="female">жен.</option>
          </select>
        </div>
        <Field label="Адрес (факт.)" value={e.actual_address} onChange={(v) => setEmployee({ actual_address: v })} />
        <Field label="Телефон" value={e.phone} onChange={(v) => setEmployee({ phone: v })} />
      </section>

      {/* 3. Conditions */}
      <section style={{ marginBottom: 28 }}>
        <h3>3. Условия приёма</h3>
        <Field label="Должность" value={m.position_ru} onChange={(v) => setEmployment({ position_ru: v })} />
        <Field label="Подразделение" value={m.department} onChange={(v) => setEmployment({ department: v })} />
        <Field label="Дата начала работы" type="date" value={m.start_date} onChange={(v) => setEmployment({ start_date: v })} />
        <Field label="Оклад, ₸ (целые тенге)" type="text" value={m.salary as string}
          onChange={(v) => setEmployment({ salary: v.replace(/[^\d]/g, '') })} />
        <div className="form-group">
          <label>Ставка</label>
          <select value={String(m.rate ?? '1')} onChange={(ev) => setEmployment({ rate: ev.target.value })}>
            <option value="1">1,0 (полная)</option><option value="0.75">0,75</option>
            <option value="0.5">0,5</option><option value="0.25">0,25</option>
          </select>
        </div>
        <Field label="Испытательный срок, мес (0–3)" type="number" value={m.probation_months} onChange={(v) => setEmployment({ probation_months: Number(v) })} />
        <Field label="№ трудового договора (вручную)" value={m.contract_number} onChange={(v) => setEmployment({ contract_number: v })} />
        <Field label="Дата ТД" type="date" value={m.contract_date} onChange={(v) => setEmployment({ contract_date: v })} />
        <Field label="№ приказа (вручную)" value={m.order_number} onChange={(v) => setEmployment({ order_number: v })} />
        <Field label="Дата приказа" type="date" value={m.order_date} onChange={(v) => setEmployment({ order_date: v })} />
        <Field label="Дата заявления" type="date" value={m.application_date} onChange={(v) => setEmployment({ application_date: v })} />
        <Field label="Часов в неделю" type="number" value={m.hours_per_week} onChange={(v) => setEmployment({ hours_per_week: Number(v) })} />
        <Field label="Выходные" value={m.days_off} onChange={(v) => setEmployment({ days_off: v })} />
      </section>

      {/* 4. Preview & generate */}
      <section>
        <h3>4. Предпросмотр и формирование</h3>
        <button className="btn btn-secondary" onClick={loadPreview} disabled={busy}>Обновить предпросмотр</button>
        {preview && (
          <div style={{ marginTop: 16 }}>
            {preview.warnings.length > 0 && (
              <div style={{ background: '#fffbeb', color: '#92400e', padding: '10px 14px', borderRadius: 8, marginBottom: 12 }}>
                {preview.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
              </div>
            )}
            <p style={{ fontSize: 13, color: '#6b7280' }}>
              Автогенерируемые значения можно поправить — правки хранятся в черновике на этом компьютере
              и попадают в документ. Ничего на сервере не сохраняется.
            </p>
            <EditableRow label="ФИО (родительный)" initial={preview.editable.employee.fio_genitive}
              onSave={(v) => applyEmployeeEdit('fio_genitive_override', v)} />
            <EditableRow label="ФИО (дательный)" initial={preview.editable.employee.fio_dative}
              onSave={(v) => applyEmployeeEdit('fio_dative_override', v)} />
            <EditableRow label="ФИО (винительный)" initial={preview.editable.employee.fio_accusative}
              onSave={(v) => applyEmployeeEdit('fio_accusative_override', v)} />
            <EditableRow label="Должность" initial={preview.editable.employment.position_ru}
              onSave={(v) => applyEmploymentEdit('position_ru', v)} />
            <EditableRow label="Оклад прописью" initial={preview.editable.employment.salary_words_ru}
              onSave={(v) => applyEmploymentEdit('salary_words_override', v)} />
            <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={download} disabled={busy}>
              Сформировать приказ (.docx)
            </button>
          </div>
        )}
      </section>

      {/* 5. Package (заход 1: приказ + матответственность + акт) */}
      <section style={{ marginTop: 32, borderTop: '1px solid #e5e7eb', paddingTop: 20 }}>
        <h3>5. Пакет документов (ZIP)</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
          {PACKAGE_DOCS.map(([key, label]) => (
            <label key={key} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input type="checkbox" checked={!!draft.documents[key]} onChange={() => toggleDoc(key)} />
              {label}
            </label>
          ))}
        </div>

        {draft.documents.zayavlenie && (
          <div style={{ background: '#f8fafc', borderRadius: 8, padding: 14, marginBottom: 12 }}>
            <h4 style={{ marginBottom: 8 }}>Заявление на налоговые вычеты (ИПН)</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
              {DEDUCTION_OPTIONS.map(([key, label]) => (
                <label key={key} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input type="checkbox" checked={draft.deductions.includes(key)} onChange={() => toggleDeduction(key)} />
                  {label}
                </label>
              ))}
            </div>
            <div className="form-group">
              <label>Применять с месяца</label>
              <input type="month" value={draft.applyFromMonth || monthOf(m.start_date)}
                onChange={(ev) => setDraft((d) => ({ ...d, applyFromMonth: ev.target.value }))} />
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
                По умолчанию — месяц приёма. В документе: «начиная с {'{месяца}'} {'{года}'} года».
              </div>
            </div>
          </div>
        )}

        {draft.documents.td && (
          <div style={{ background: '#f8fafc', borderRadius: 8, padding: 14, marginBottom: 12 }}>
            <h4 style={{ marginBottom: 8 }}>Трудовой договор</h4>
            <div className="form-group">
              <label>Вид договора</label>
              <select value={draft.contract.kind} onChange={(ev) => setContract({ kind: ev.target.value })}>
                {CONTRACT_KINDS.map(([val, label]) => <option key={val} value={val}>{label}</option>)}
              </select>
            </div>
            <Field label="№ договора" value={draft.contract.number} onChange={(v) => setContract({ number: v })} />
            <Field label="Дата договора" type="date" value={draft.contract.doc_date} onChange={(v) => setContract({ doc_date: v })} />

            {draft.contract.kind === 'fixed' && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <div className="form-group" style={{ flex: '1 1 120px' }}>
                  <label>Срок</label>
                  <input type="number" min={1} value={draft.contract.term_count ?? ''}
                    onChange={(ev) => setContract({ term_count: ev.target.value ? Number(ev.target.value) : null })} />
                </div>
                <div className="form-group" style={{ flex: '1 1 120px' }}>
                  <label>Единица</label>
                  <select value={draft.contract.term_unit} onChange={(ev) => setContract({ term_unit: ev.target.value })}>
                    <option value="year">лет</option><option value="month">месяцев</option>
                  </select>
                </div>
                <div className="form-group" style={{ flex: '1 1 160px' }}>
                  <label>Дата окончания</label>
                  <input type="date" value={draft.contract.end_date ?? ''}
                    onChange={(ev) => setContract({ end_date: ev.target.value || null })} />
                </div>
              </div>
            )}
            {draft.contract.kind === 'task' && (
              <>
                <Field label="Описание работы (рус)" value={draft.contract.task} onChange={(v) => setContract({ task: v })} />
                <Field label="Описание работы (каз)" value={draft.contract.task_kz} onChange={(v) => setContract({ task_kz: v })} />
              </>
            )}
            <Field label="Срок конфиденциальности (лет)" value={draft.contract.confidential_years}
              onChange={(v) => setContract({ confidential_years: v })} />

            <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px dashed #cbd5e1' }}>
              <strong style={{ fontSize: 14 }}>Казахские соответствия и режим (для двуязычного ТД)</strong>
              <p style={{ fontSize: 12, color: '#b45309', margin: '4px 0 10px' }}>
                Казахский текст не вычитан юристом — проверьте перевод перед подписанием.
                Числа, даты и срок на казахском формируются автоматически.
              </p>
              <Field label="Наименование компании (каз)" value={c.name_kk} onChange={(v) => setCompany({ name_kk: v })} />
              <Field label="Юр. адрес компании (каз)" value={c.address_kz} onChange={(v) => setCompany({ address_kz: v })} />
              <Field label="ФИО директора (каз)" value={c.director_fio_kk} onChange={(v) => setCompany({ director_fio_kk: v })} />
              <Field label="Должность подписанта (каз)" value={c.signer_position_kz} onChange={(v) => setCompany({ signer_position_kz: v })} />
              <Field label="ФИО работника (каз)" value={e.fio_full_kz} onChange={(v) => setEmployee({ fio_full_kz: v })} />
              <Field label="Документ работника (каз)" value={e.id_document_kz} onChange={(v) => setEmployee({ id_document_kz: v })}
                placeholder="жеке куәлік № … ІІМ … берген" />
              <Field label="Должность (каз)" value={m.position_kk} onChange={(v) => setEmployment({ position_kk: v })} />
              <Field label="Место работы (рус)" value={m.workplace} onChange={(v) => setEmployment({ workplace: v })} placeholder="г. Астана, офис Работодателя" />
              <Field label="Место работы (каз)" value={m.workplace_kz} onChange={(v) => setEmployment({ workplace_kz: v })} />
              <Field label="Условия труда (рус)" value={m.conditions} onChange={(v) => setEmployment({ conditions: v })} placeholder="нормальными" />
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <div className="form-group" style={{ flex: '1 1 120px' }}>
                  <label>Часов в день</label>
                  <input type="number" value={m.hours_per_day ?? ''} onChange={(ev) => setEmployment({ hours_per_day: ev.target.value })} />
                </div>
                <div className="form-group" style={{ flex: '1 1 120px' }}>
                  <label>Дней отпуска</label>
                  <input type="number" value={m.vacation_days ?? ''} onChange={(ev) => setEmployment({ vacation_days: Number(ev.target.value) })} />
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Field label="Начало рабочего дня" value={m.work_time_from} onChange={(v) => setEmployment({ work_time_from: v })} />
                <Field label="Конец рабочего дня" value={m.work_time_to} onChange={(v) => setEmployment({ work_time_to: v })} />
                <Field label="Обед с" value={m.lunch_from} onChange={(v) => setEmployment({ lunch_from: v })} />
                <Field label="Обед до" value={m.lunch_to} onChange={(v) => setEmployment({ lunch_to: v })} />
              </div>
            </div>
          </div>
        )}

        {(draft.documents.matotvet || draft.documents.akt) && (
          <div style={{ background: '#f8fafc', borderRadius: 8, padding: 14, marginBottom: 12 }}>
            <h4 style={{ marginBottom: 8 }}>Реквизиты договора о матответственности</h4>
            <Field label="№ договора" value={draft.liability.number} onChange={(v) => setLiability({ number: v })} />
            <Field label="Дата договора" type="date" value={draft.liability.doc_date} onChange={(v) => setLiability({ doc_date: v })} />
          </div>
        )}

        {draft.documents.akt && (
          <div style={{ background: '#f8fafc', borderRadius: 8, padding: 14, marginBottom: 12 }}>
            <h4 style={{ marginBottom: 8 }}>Акт приёма-передачи</h4>
            <Field label="№ акта" value={draft.act.number} onChange={(v) => setAct({ number: v })} />
            <Field label="Дата акта" type="date" value={draft.act.doc_date} onChange={(v) => setAct({ doc_date: v })} />
            <Field label="Основание (напр. «приказ № 14 от 17.08.2026»; пусто — не выводится)"
              value={draft.act.basis} onChange={(v) => setAct({ basis: v })} />
            <Field label="Особые отметки" value={draft.act.notes} onChange={(v) => setAct({ notes: v })} />

            <div style={{ marginTop: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                <strong>Опись ценностей</strong>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button className="btn btn-secondary" onClick={addRow}>+ строка</button>
                  <button className="btn btn-secondary" onClick={() => invRef.current?.click()}>Загрузить из Excel</button>
                  <input ref={invRef} type="file" accept=".xlsx" style={{ display: 'none' }}
                    onChange={(ev) => ev.target.files?.[0] && onInventoryFile(ev.target.files[0])} />
                </div>
              </div>
              {draft.inventory.length === 0 ? (
                <p style={{ color: '#6b7280', fontSize: 13, marginTop: 6 }}>
                  Опись пуста. Добавьте строки вручную или загрузите из Excel
                  (колонки: Наименование, Количество, Цена; по желанию — Код, Ед. изм.).
                </p>
              ) : (
                <div style={{ overflowX: 'auto', marginTop: 6 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <thead>
                      <tr>{['№', 'Наименование', 'Код', 'Ед.', 'Кол-во', 'Цена', 'Сумма', ''].map((h, i) =>
                        <th key={i} style={{ textAlign: 'left', padding: '4px 6px', borderBottom: '1px solid #e5e7eb' }}>{h}</th>)}</tr>
                    </thead>
                    <tbody>
                      {draft.inventory.map((r, i) => (
                        <tr key={i}>
                          <td style={cellS}>{i + 1}</td>
                          <td style={cellS}><input value={r.name} onChange={(e) => updateRow(i, { name: e.target.value })} style={inS} /></td>
                          <td style={cellS}><input value={r.code} onChange={(e) => updateRow(i, { code: e.target.value })} style={{ ...inS, width: 80 }} /></td>
                          <td style={cellS}><input value={r.unit} onChange={(e) => updateRow(i, { unit: e.target.value })} style={{ ...inS, width: 60 }} /></td>
                          <td style={cellS}><input value={String(r.qty)} onChange={(e) => updateRow(i, { qty: e.target.value })} style={{ ...inS, width: 70 }} /></td>
                          <td style={cellS}><input value={String(r.price)} onChange={(e) => updateRow(i, { price: e.target.value })} style={{ ...inS, width: 100 }} /></td>
                          <td style={{ ...cellS, whiteSpace: 'nowrap' }}>{fmt(num(r.qty) * num(r.price))}</td>
                          <td style={cellS}><button className="btn btn-secondary" onClick={() => deleteRow(i)} title="Удалить строку">×</button></td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr>
                        <td colSpan={6} style={{ ...cellS, textAlign: 'right', fontWeight: 600 }}>Итого:</td>
                        <td style={{ ...cellS, fontWeight: 600, whiteSpace: 'nowrap' }}>{fmt(invTotal)} ₸</td>
                        <td />
                      </tr>
                    </tfoot>
                  </table>
                </div>
              )}
            </div>

            <div style={{ marginTop: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong>Комиссия</strong>
                <button className="btn btn-secondary" onClick={addCommission}>+ член комиссии</button>
              </div>
              {draft.act.commission.map((mrow, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                  <input placeholder="Должность" value={mrow.position} onChange={(e) => updateCommission(i, { position: e.target.value })} style={{ ...inS, flex: 1 }} />
                  <input placeholder="Фамилия И.О." value={mrow.fio_short} onChange={(e) => updateCommission(i, { fio_short: e.target.value })} style={{ ...inS, flex: 1 }} />
                  <button className="btn btn-secondary" onClick={() => deleteCommission(i)} title="Удалить">×</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {(draft.documents.polozhenie_pd || draft.documents.prikaz_pd) && (
          <div style={{ background: '#f8fafc', borderRadius: 8, padding: 14, marginBottom: 12 }}>
            <h4 style={{ marginBottom: 8 }}>Персональные данные — приказ и Положение</h4>
            <Field label="№ приказа" value={draft.policy.order_number} onChange={(v) => setPolicy({ order_number: v })} />
            <Field label="Дата приказа" type="date" value={draft.policy.doc_date} onChange={(v) => setPolicy({ doc_date: v })} />
            <Field label="Ответственный, ФИО (им.п.)" value={draft.policy.responsible_fio}
              onChange={(v) => setPolicy({ responsible_fio: v })} placeholder="Иванов Иван Иванович" />
            <Field label="Должность ответственного (им.п.)" value={draft.policy.responsible_position}
              onChange={(v) => setPolicy({ responsible_position: v })} placeholder="директор" />
            <Field label="Срок ознакомления" type="date" value={draft.policy.deadline}
              onChange={(v) => setPolicy({ deadline: v })} />
            <Field label="Контроль (за кем)" value={draft.policy.control} onChange={(v) => setPolicy({ control: v })} />
            <div style={{ marginTop: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong>Ознакомить (лист ознакомления)</strong>
                <button className="btn btn-secondary" onClick={addAcquainted}>+ сотрудник</button>
              </div>
              {draft.policy.acquainted.map((row, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginTop: 6 }}>
                  <input placeholder="Должность" value={row.position} onChange={(e) => updateAcquainted(i, { position: e.target.value })} style={{ ...inS, flex: 1 }} />
                  <input placeholder="Фамилия И.О." value={row.fio_short} onChange={(e) => updateAcquainted(i, { fio_short: e.target.value })} style={{ ...inS, flex: 1 }} />
                  <button className="btn btn-secondary" onClick={() => deleteAcquainted(i)} title="Удалить">×</button>
                </div>
              ))}
            </div>
          </div>
        )}

        <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={generatePackage} disabled={busy}>
          Сформировать пакет (ZIP)
        </button>
      </section>

      {importPreview && (
        <div className="modal-overlay" onClick={() => setImportPreview(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 660 }}>
            <div className="modal-body">
              <h3 style={{ marginBottom: 8 }}>Распознано позиций: {importPreview.length}</h3>
              <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 10 }}>Проверьте, прежде чем добавить в опись.</p>
              <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead><tr>{['Наименование', 'Код', 'Ед.', 'Кол-во', 'Цена'].map((h, i) =>
                    <th key={i} style={{ textAlign: 'left', padding: '4px 6px', borderBottom: '1px solid #e5e7eb' }}>{h}</th>)}</tr></thead>
                  <tbody>
                    {importPreview.map((r, i) => (
                      <tr key={i}>
                        <td style={cellS}>{r.name}</td><td style={cellS}>{r.code}</td><td style={cellS}>{r.unit}</td>
                        <td style={cellS}>{String(r.qty)}</td><td style={cellS}>{String(r.price)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 16 }}>
                <button className="btn btn-secondary" onClick={() => setImportPreview(null)}>Отмена</button>
                <button className="btn btn-primary" onClick={confirmImport}>Добавить в опись</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {mapping && (
        <div className="modal-overlay" onClick={() => setMapping(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 680 }}>
            <div className="modal-body">
              <h3 style={{ marginBottom: 6 }}>Сопоставьте колонки файла</h3>
              <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 12 }}>
                Автоматически распознать колонки не удалось. Укажите, что есть что — это нужно сделать один раз.
              </p>
              <div style={{ maxHeight: 340, overflowY: 'auto' }}>
                {mapping.columns.map((col) => (
                  <div key={col.index} style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 8 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontWeight: 600 }}>{col.title}</div>
                      {col.samples.length > 0 && (
                        <div style={{ fontSize: 12, color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          напр.: {col.samples.join(', ')}
                        </div>
                      )}
                    </div>
                    <select value={mapping.assign[col.index] ?? 'ignore'} onChange={(e) => setAssign(col.index, e.target.value)}>
                      {CATEGORY_OPTIONS.map(([val, label]) => <option key={val} value={val}>{label}</option>)}
                    </select>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 16 }}>
                <button className="btn btn-secondary" onClick={() => setMapping(null)}>Отмена</button>
                <button className="btn btn-primary" onClick={confirmMapping} disabled={busy}>Импортировать</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function EditableRow(props: { label: string; initial: string; onSave: (v: string) => void }) {
  const [value, setValue] = useState(props.initial)
  useEffect(() => { setValue(props.initial) }, [props.initial])
  const dirty = value !== props.initial
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 10 }}>
      <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
        <label>{props.label}</label>
        <input value={value} onChange={(e) => setValue(e.target.value)} />
      </div>
      <button className="btn btn-secondary" disabled={!dirty} onClick={() => props.onSave(value)}>Применить</button>
    </div>
  )
}
