import { useEffect, useState } from 'react'
import {
  personnelApi,
  type PersonnelCompany,
  type PersonnelEmployee,
  type PersonnelEmployment,
  type IinCheck,
  type PrikazPreview,
} from '../api/client'

// Draft persistence (ТЗ §8): the form survives a page reload — data from a
// client often arrives piecemeal.
const DRAFT_KEY = 'hr_priem_draft_v1'

type Draft = {
  company: Partial<PersonnelCompany>
  employee: Partial<PersonnelEmployee>
  employment: Partial<PersonnelEmployment>
  companyId?: number
  employeeId?: number
  employmentId?: number
}

const EMPTY_DRAFT: Draft = {
  company: { director_gender: 'male', signatory_position: 'Директор', acts_on_basis: 'Устава' },
  employee: { document_type: 'id_card', gender: 'male', citizenship: 'Республики Казахстан' },
  employment: {
    contract_type: 'indefinite', rate: '1', probation_months: 0, currency: 'KZT',
    work_time_from: '09:00', work_time_to: '18:00', lunch_from: '13:00', lunch_to: '14:00',
    days_off: 'суббота, воскресенье', vacation_days: 24, ipn_deduction: 'base_30_mrp',
  },
}

function loadDraft(): Draft {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (raw) return { ...EMPTY_DRAFT, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return EMPTY_DRAFT
}

// Turn an axios error into a message that explains what is wrong, not "validation error".
function errText(e: unknown, fallback: string): string {
  // @ts-expect-error narrow axios shape
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail.map((d: { msg: string }) => d.msg).join('; ')
  return fallback
}

function Field(props: {
  label: string
  value: string | number | null | undefined
  onChange: (v: string) => void
  type?: string
  placeholder?: string
  hint?: string
}) {
  return (
    <div className="form-group">
      <label>{props.label}</label>
      <input
        type={props.type || 'text'}
        value={props.value ?? ''}
        placeholder={props.placeholder}
        onChange={(e) => props.onChange(e.target.value)}
      />
      {props.hint && <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>{props.hint}</div>}
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

  // Persist every change to survive reloads.
  useEffect(() => { localStorage.setItem(DRAFT_KEY, JSON.stringify(draft)) }, [draft])
  useEffect(() => { personnelApi.listCompanies().then(setCompanies).catch(() => {}) }, [])

  const setCompany = (patch: Partial<PersonnelCompany>) =>
    setDraft((d) => ({ ...d, company: { ...d.company, ...patch } }))
  const setEmployee = (patch: Partial<PersonnelEmployee>) =>
    setDraft((d) => ({ ...d, employee: { ...d.employee, ...patch } }))
  const setEmployment = (patch: Partial<PersonnelEmployment>) =>
    setDraft((d) => ({ ...d, employment: { ...d.employment, ...patch } }))

  const flash = (m: string) => { setNotice(m); setError(''); setTimeout(() => setNotice(''), 3000) }
  const fail = (e: unknown, fb: string) => setError(errText(e, fb))

  async function checkIin(value: string) {
    if (!value) { setIin(null); return }
    try {
      const res = await personnelApi.validateIin(value, draft.employee.birth_date, draft.employee.gender)
      setIin(res)
      // autofill birth date / gender from the ИИН when empty
      if (res.valid) {
        const patch: Partial<PersonnelEmployee> = {}
        if (res.birth_date && !draft.employee.birth_date) patch.birth_date = res.birth_date
        if (res.gender && !draft.employee.gender) patch.gender = res.gender
        if (Object.keys(patch).length) setEmployee(patch)
      }
    } catch (e) { fail(e, 'Не удалось проверить ИИН') }
  }

  async function saveCompany() {
    setBusy(true); setError('')
    try {
      const saved = draft.companyId
        ? await personnelApi.updateCompany(draft.companyId, draft.company)
        : await personnelApi.createCompany(draft.company)
      setDraft((d) => ({ ...d, companyId: saved.id, company: saved }))
      setCompanies(await personnelApi.listCompanies())
      flash('Компания сохранена')
    } catch (e) { fail(e, 'Не удалось сохранить компанию') } finally { setBusy(false) }
  }

  function pickCompany(id: number) {
    const c = companies.find((x) => x.id === id)
    if (c) setDraft((d) => ({ ...d, companyId: c.id, company: c }))
  }

  async function saveEmployee() {
    setBusy(true); setError('')
    try {
      const saved = draft.employeeId
        ? await personnelApi.updateEmployee(draft.employeeId, draft.employee)
        : await personnelApi.createEmployee(draft.employee)
      setDraft((d) => ({ ...d, employeeId: saved.id, employee: saved }))
      flash(saved.warnings?.length ? saved.warnings.join('; ') : 'Работник сохранён')
    } catch (e) { fail(e, 'Не удалось сохранить работника') } finally { setBusy(false) }
  }

  async function saveEmployment() {
    if (!draft.companyId || !draft.employeeId) { setError('Сначала сохраните компанию и работника'); return }
    setBusy(true); setError('')
    try {
      const payload = { ...draft.employment, company_id: draft.companyId, employee_id: draft.employeeId }
      const saved = draft.employmentId
        ? await personnelApi.updateEmployment(draft.employmentId, payload)
        : await personnelApi.createEmployment(payload)
      setDraft((d) => ({ ...d, employmentId: saved.id, employment: saved }))
      flash(saved.warnings?.length ? saved.warnings.join('; ') : 'Условия приёма сохранены')
    } catch (e) { fail(e, 'Не удалось сохранить условия приёма') } finally { setBusy(false) }
  }

  async function loadPreview() {
    if (!draft.employmentId) { setError('Сначала сохраните условия приёма'); return }
    setBusy(true); setError('')
    try { setPreview(await personnelApi.prikazPreview(draft.employmentId)) }
    catch (e) { fail(e, 'Не удалось получить предпросмотр') } finally { setBusy(false) }
  }

  // Save an edited auto-field back to where it persists, then refresh the preview.
  async function saveEmployeeOverride(field: string, value: string) {
    if (!draft.employeeId) return
    setBusy(true); setError('')
    try {
      await personnelApi.updateEmployee(draft.employeeId, { [field]: value })
      await loadPreview()
      flash('Правка сохранена в карточку работника')
    } catch (e) { fail(e, 'Не удалось сохранить правку') } finally { setBusy(false) }
  }
  async function saveEmploymentOverride(field: string, value: string) {
    if (!draft.employmentId) return
    setBusy(true); setError('')
    try {
      await personnelApi.updateEmployment(draft.employmentId, { [field]: value })
      await loadPreview()
      flash('Правка сохранена')
    } catch (e) { fail(e, 'Не удалось сохранить правку') } finally { setBusy(false) }
  }

  async function download() {
    if (!draft.employmentId) return
    setBusy(true); setError('')
    try { await personnelApi.downloadPrikaz(draft.employmentId) }
    catch (e) { fail(e, 'Не удалось сформировать приказ') } finally { setBusy(false) }
  }

  function resetDraft() {
    if (!confirm('Очистить форму и начать заново?')) return
    localStorage.removeItem(DRAFT_KEY)
    setDraft(EMPTY_DRAFT); setPreview(null); setIin(null); setError(''); setNotice('')
  }

  const c = draft.company, e = draft.employee, m = draft.employment

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', paddingBottom: 60 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '16px 0' }}>
        <h2>Приём на работу</h2>
        <button className="btn btn-secondary" onClick={resetDraft}>Очистить черновик</button>
      </div>
      {error && <div className="error-message">{error}</div>}
      {notice && <div style={{ background: '#ecfdf5', color: '#065f46', padding: '10px 14px', borderRadius: 8, marginBottom: 12 }}>{notice}</div>}

      {/* 1. Company */}
      <section style={{ marginBottom: 28 }}>
        <h3>1. Работодатель</h3>
        {companies.length > 0 && (
          <div className="form-group">
            <label>Выбрать существующую</label>
            <select value={draft.companyId ?? ''} onChange={(ev) => pickCompany(Number(ev.target.value))}>
              <option value="">— создать новую —</option>
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
        <button className="btn btn-primary" onClick={saveCompany} disabled={busy}>
          {draft.companyId ? 'Обновить компанию' : 'Сохранить компанию'}
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
          <input
            value={e.iin ?? ''}
            placeholder="12 цифр"
            onChange={(ev) => setEmployee({ iin: ev.target.value })}
            onBlur={(ev) => checkIin(ev.target.value)}
          />
          {iin && !iin.valid && (
            <div style={{ color: '#b91c1c', fontSize: 13, marginTop: 4 }}>
              ИИН не прошёл проверку: должно быть 12 цифр с верной контрольной суммой и корректной датой рождения.
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
        <button className="btn btn-primary" onClick={saveEmployee} disabled={busy}>
          {draft.employeeId ? 'Обновить работника' : 'Сохранить работника'}
        </button>
      </section>

      {/* 3. Conditions */}
      <section style={{ marginBottom: 28 }}>
        <h3>3. Условия приёма</h3>
        <Field label="Должность" value={m.position_ru} onChange={(v) => setEmployment({ position_ru: v })} />
        <Field label="Подразделение" value={m.department} onChange={(v) => setEmployment({ department: v })} />
        <Field label="Дата начала работы" type="date" value={m.start_date} onChange={(v) => setEmployment({ start_date: v })} />
        <Field label="Оклад, ₸" type="number" value={m.salary as string} onChange={(v) => setEmployment({ salary: v })} />
        <div className="form-group">
          <label>Ставка</label>
          <select value={String(m.rate ?? '1')} onChange={(ev) => setEmployment({ rate: ev.target.value })}>
            <option value="1">1,0 (полная)</option><option value="0.75">0,75</option>
            <option value="0.5">0,5</option><option value="0.25">0,25</option>
          </select>
        </div>
        <Field label="Испытательный срок, мес (0–3)" type="number" value={m.probation_months} onChange={(v) => setEmployment({ probation_months: Number(v) })} />
        <Field label="№ трудового договора" value={m.contract_number} onChange={(v) => setEmployment({ contract_number: v })} />
        <Field label="Дата ТД" type="date" value={m.contract_date} onChange={(v) => setEmployment({ contract_date: v })} />
        <Field label="№ приказа" value={m.order_number} onChange={(v) => setEmployment({ order_number: v })} />
        <Field label="Дата приказа" type="date" value={m.order_date} onChange={(v) => setEmployment({ order_date: v })} />
        <Field label="Дата заявления" type="date" value={m.application_date} onChange={(v) => setEmployment({ application_date: v })} />
        <Field label="Часов в неделю" type="number" value={m.hours_per_week} onChange={(v) => setEmployment({ hours_per_week: Number(v) })} />
        <Field label="Выходные" value={m.days_off} onChange={(v) => setEmployment({ days_off: v })} />
        <button className="btn btn-primary" onClick={saveEmployment} disabled={busy}>
          {draft.employmentId ? 'Обновить условия' : 'Сохранить условия'}
        </button>
        {(m.warnings?.length ?? 0) > 0 && (
          <div style={{ background: '#fffbeb', color: '#92400e', padding: '10px 14px', borderRadius: 8, marginTop: 10 }}>
            {m.warnings!.map((w, i) => <div key={i}>⚠ {w}</div>)}
          </div>
        )}
      </section>

      {/* 4. Preview & generate */}
      <section>
        <h3>4. Предпросмотр и формирование</h3>
        <button className="btn btn-secondary" onClick={loadPreview} disabled={busy || !draft.employmentId}>
          Обновить предпросмотр
        </button>
        {preview && (
          <div style={{ marginTop: 16 }}>
            <p style={{ fontSize: 13, color: '#6b7280' }}>
              Автогенерируемые значения можно поправить — правка ФИО пишется в карточку работника
              и применяется во всех его документах; должность и сумма прописью — к этому приёму.
            </p>
            <EditableRow label="ФИО (родительный)" initial={preview.editable.employee.fio_genitive}
              onSave={(v) => saveEmployeeOverride('fio_genitive_override', v)} />
            <EditableRow label="ФИО (дательный)" initial={preview.editable.employee.fio_dative}
              onSave={(v) => saveEmployeeOverride('fio_dative_override', v)} />
            <EditableRow label="ФИО (винительный)" initial={preview.editable.employee.fio_accusative}
              onSave={(v) => saveEmployeeOverride('fio_accusative_override', v)} />
            <EditableRow label="Должность" initial={preview.editable.employment.position_ru}
              onSave={(v) => saveEmploymentOverride('position_ru', v)} />
            <EditableRow label="Оклад прописью" initial={preview.editable.employment.salary_words_ru}
              onSave={(v) => saveEmploymentOverride('salary_words_override', v)} />
            <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={download} disabled={busy}>
              Сформировать приказ (.docx)
            </button>
          </div>
        )}
      </section>
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
      <button className="btn btn-secondary" disabled={!dirty} onClick={() => props.onSave(value)}>Сохранить</button>
    </div>
  )
}
