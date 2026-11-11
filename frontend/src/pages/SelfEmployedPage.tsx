import { useEffect, useState } from 'react'
import {
  selfEmployedApi,
  type IinCheck,
  type SelfEmployedBody,
  type SelfEmployedOked,
} from '../api/client'

// Модуль STATELESS: сервер не хранит ни ИИН, ни ФИО исполнителя. Черновик живёт
// только в этом браузере и сам сбрасывается через сутки — как в кадровом модуле.
const DRAFT_KEY = 'selfemployed_draft_v1'
const DRAFT_TTL_MS = 24 * 60 * 60 * 1000

// Локальная дата 'YYYY-MM-DD' (не UTC — чтобы у полуночи не съезжало на день).
const todayISO = (): string => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const endOfYearISO = (): string => `${new Date().getFullYear()}-12-31`

type Draft = SelfEmployedBody & { subjectTouched: boolean; savedAt?: number }

const EMPTY_DRAFT: Draft = {
  oked: '',
  number: '',
  city: 'г. Алматы',
  contract_date: todayISO(),
  valid_from: '',
  valid_to: endOfYearISO(),
  amount: 0,
  payment_days: 20,
  payment_method: 'cashless',
  rent_period: 'month',
  subject: '',
  customer: {
    org_form: 'ТОО', name: '', bin: '', position: 'Директор', head_name: '',
    basis_gen: 'Устава', address: '', iik: '', bank: '', bik: '', phone: '', email: '',
  },
  executor: {
    full_name: '', iin: '', status: 'citizen', address: '', iik: '', bank: '', bik: '', phone: '',
  },
  subjectTouched: false,
}

function loadDraft(): Draft {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return EMPTY_DRAFT
    const saved = JSON.parse(raw) as Draft
    if (!saved.savedAt || Date.now() - saved.savedAt > DRAFT_TTL_MS) return EMPTY_DRAFT
    return {
      ...EMPTY_DRAFT, ...saved,
      customer: { ...EMPTY_DRAFT.customer, ...(saved.customer || {}) },
      executor: { ...EMPTY_DRAFT.executor, ...(saved.executor || {}) },
    }
  } catch {
    return EMPTY_DRAFT
  }
}

function errText(e: unknown, fallback: string): string {
  // @ts-expect-error narrow axios shape
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail.map((d: { msg: string }) => d.msg).join('; ')
  return fallback
}

const fmtTenge = (n: number) => n.toLocaleString('ru-RU')

function Field(props: {
  label: string; value: string | number | null | undefined
  onChange: (v: string) => void
  type?: string; placeholder?: string; hint?: string; onBlur?: (v: string) => void
}) {
  return (
    <div className="form-group">
      <label>{props.label}</label>
      <input type={props.type || 'text'} value={props.value ?? ''} placeholder={props.placeholder}
        onChange={(e) => props.onChange(e.target.value)}
        onBlur={(e) => props.onBlur?.(e.target.value)} />
      {props.hint && <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>{props.hint}</div>}
    </div>
  )
}

export default function SelfEmployedPage() {
  const [okeds, setOkeds] = useState<SelfEmployedOked[]>([])
  const [draft, setDraft] = useState<Draft>(loadDraft)
  const [iin, setIin] = useState<IinCheck | null>(null)
  const [binValid, setBinValid] = useState<boolean | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    selfEmployedApi.getOkeds()
      .then(setOkeds)
      .catch((e) => setError(errText(e, 'Не удалось загрузить справочник видов деятельности')))
  }, [])

  useEffect(() => {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...draft, savedAt: Date.now() }))
  }, [draft])

  const profile = okeds.find((o) => o.code === draft.oked) || null
  const isRent = profile?.kind === 'rent'
  const isIP = draft.customer.org_form === 'ИП'

  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }))
  const setCustomer = (patch: Partial<Draft['customer']>) =>
    setDraft((d) => ({ ...d, customer: { ...d.customer, ...patch } }))
  const setExecutor = (patch: Partial<Draft['executor']>) =>
    setDraft((d) => ({ ...d, executor: { ...d.executor, ...patch } }))

  // Смена вида деятельности подставляет предмет по умолчанию. Если предмет уже
  // правили руками — сначала спрашиваем, иначе правка потерялась бы молча.
  function pickOked(code: string) {
    const next = okeds.find((o) => o.code === code)
    const current = (draft.subject ?? '').trim()
    if (!next) { set({ oked: code }); return }
    if (draft.subjectTouched && current && current !== next.default_subject) {
      const replace = confirm(
        'Предмет договора вы правили вручную. Заменить его текстом по умолчанию ' +
        `для вида деятельности ${next.code}?`
      )
      set(replace
        ? { oked: code, subject: next.default_subject, subjectTouched: false }
        : { oked: code })
      return
    }
    set({ oked: code, subject: next.default_subject, subjectTouched: false })
  }

  async function checkIin(value: string) {
    if (!value) { setIin(null); return }
    try { setIin(await selfEmployedApi.validateIin(value)) } catch { setIin(null) }
  }

  async function checkBin(value: string) {
    if (!value) { setBinValid(null); return }
    try { setBinValid((await selfEmployedApi.validateBin(value)).valid) } catch { setBinValid(null) }
  }

  // Обязательные поля (ТЗ): форма, наименование, БИН, ФИО руководителя;
  // ФИО и ИИН исполнителя; вид деятельности, сумма и дата «по».
  function missing(): string[] {
    const out: string[] = []
    if (!draft.oked) out.push('вид деятельности')
    if (!draft.customer.name.trim()) out.push('наименование заказчика')
    if (!draft.customer.bin.trim()) out.push(isIP ? 'ИИН заказчика' : 'БИН заказчика')
    if (!draft.customer.head_name.trim()) out.push('ФИО руководителя')
    if (!draft.executor.full_name.trim()) out.push('ФИО исполнителя')
    if (!draft.executor.iin.trim()) out.push('ИИН исполнителя')
    if (!draft.amount || draft.amount < 1) out.push(isRent ? 'арендная плата' : 'сумма договора')
    if (!draft.valid_to) out.push('срок действия «по»')
    return out
  }

  function body(): SelfEmployedBody {
    const { subjectTouched: _t, savedAt: _s, ...rest } = draft
    return {
      ...rest,
      amount: Number(draft.amount) || 0,
      payment_days: Number(draft.payment_days) || 20,
      valid_from: draft.valid_from ? draft.valid_from : null,
      subject: (draft.subject ?? '').trim() || null,
      customer: {
        ...draft.customer,
        position_gen: null,   // падеж считает бэкенд (хелпер personnel на pymorphy3)
        head_name_gen: null,
      },
    }
  }

  // Перед скачиванием дёргаем /check: предупреждения показываем, но генерацию
  // не останавливаем — решение за бухгалтером.
  async function handleGenerate() {
    const gaps = missing()
    if (gaps.length) {
      setError(`Заполните: ${gaps.join(', ')}.`)
      return
    }
    setError(''); setBusy(true)
    const payload = body()
    try {
      const res = await selfEmployedApi.check(payload)
      setWarnings(res.warnings)
    } catch (e) {
      setWarnings([])
      setError(errText(e, 'Не удалось выполнить проверку — договор всё равно формируется'))
    }
    try {
      await selfEmployedApi.generate(payload)
    } catch (e) {
      setError(errText(e, 'Не удалось сформировать договор'))
    } finally {
      setBusy(false)
    }
  }

  function resetDraft() {
    if (!confirm('Очистить все введённые данные?')) return
    localStorage.removeItem(DRAFT_KEY)
    setDraft(EMPTY_DRAFT); setIin(null); setBinValid(null); setWarnings([]); setError('')
  }

  const amountLabel = isRent ? 'Арендная плата, ₸ (целыми тенге)' : 'Сумма договора, ₸ (целыми тенге)'

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', paddingBottom: 60 }}>
      <h2 style={{ margin: '16px 0' }}>Договор с самозанятым</h2>

      <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', color: '#9a3412', padding: '12px 16px', borderRadius: 8, marginBottom: 16 }}>
        <strong>Данные не сохраняются на сервере.</strong> ИИН и ФИО исполнителя нужны только
        для формирования документа — заполненная форма живёт в этом браузере. Скачайте договор
        до закрытия страницы.
      </div>

      <div style={{ background: '#f8fafc', border: '1px solid #e5e7eb', color: '#374151', padding: '12px 16px', borderRadius: 8, marginBottom: 16, fontSize: 14 }}>
        Договор формируется по типовому шаблону под вид деятельности из перечня самозанятых
        и подлежит проверке сторонами. Предел дохода самозанятого — 300 МРП в месяц.
      </div>

      {error && <div className="error-message">{error}</div>}

      {/* 1. Вид деятельности */}
      <section style={{ marginBottom: 28 }}>
        <h3>1. Вид деятельности</h3>
        <div className="form-group">
          <label>ОКЭД из перечня самозанятых</label>
          <select value={draft.oked} onChange={(e) => pickOked(e.target.value)}>
            <option value="">— выберите вид деятельности —</option>
            {okeds.map((o) => <option key={o.code} value={o.code}>{o.code} — {o.name}</option>)}
          </select>
          {profile && (
            <div style={{ fontSize: 13, color: '#374151', marginTop: 6 }}>
              Будет сформирован: <strong>{profile.title}</strong>. Срок уведомления о расторжении —
              {' '}{profile.notice_days} календарных дней.
            </div>
          )}
        </div>
        <div className="form-group">
          <label>Предмет договора</label>
          <textarea rows={3} value={draft.subject ?? ''} placeholder="подставится по выбранному ОКЭД, можно поправить"
            onChange={(e) => set({ subject: e.target.value, subjectTouched: true })} />
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
            Формулировка в винительном падеже — продолжение фразы «обязуется выполнить…».
          </div>
        </div>
      </section>

      {/* 2. Договор */}
      <section style={{ marginBottom: 28 }}>
        <h3>2. Договор</h3>
        <Field label="Номер" value={draft.number} onChange={(v) => set({ number: v })} placeholder="СЗ-001" />
        <Field label="Дата договора" type="date" value={draft.contract_date} onChange={(v) => set({ contract_date: v })} />
        <Field label="Город" value={draft.city} onChange={(v) => set({ city: v })} />
      </section>

      {/* 3. Заказчик */}
      <section style={{ marginBottom: 28 }}>
        <h3>3. {isRent ? 'Арендатор' : 'Заказчик'}</h3>
        <div className="form-group">
          <label>Форма</label>
          <select value={draft.customer.org_form}
            onChange={(e) => setCustomer({ org_form: e.target.value as Draft['customer']['org_form'] })}>
            <option value="ТОО">ТОО</option>
            <option value="АО">АО</option>
            <option value="ИП">ИП</option>
          </select>
        </div>
        <Field label="Наименование (без формы)" value={draft.customer.name}
          onChange={(v) => setCustomer({ name: v })} placeholder="Ромашка Трейд" />
        <div className="form-group">
          <label>{isIP ? 'ИИН' : 'БИН'}</label>
          <input value={draft.customer.bin} placeholder="12 цифр" inputMode="numeric" maxLength={12}
            onChange={(e) => setCustomer({ bin: e.target.value.replace(/\D/g, '') })}
            onBlur={(e) => checkBin(e.target.value.replace(/\D/g, ''))} />
          {binValid === false && (
            <div style={{ color: '#b91c1c', fontSize: 13, marginTop: 4 }}>
              Не прошёл проверку: нужно 12 цифр с верной контрольной суммой.
            </div>
          )}
          {binValid === true && (
            <div style={{ color: '#065f46', fontSize: 13, marginTop: 4 }}>Проверка пройдена.</div>
          )}
        </div>
        {!isIP && (
          <>
            <Field label="Должность руководителя" value={draft.customer.position}
              onChange={(v) => setCustomer({ position: v })} placeholder="Директор"
              hint="В преамбуле подставится в родительном падеже («в лице директора …»)." />
            <Field label="Действует на основании" value={draft.customer.basis_gen}
              onChange={(v) => setCustomer({ basis_gen: v })} placeholder="Устава" />
          </>
        )}
        <Field label="ФИО руководителя (им. п.)" value={draft.customer.head_name}
          onChange={(v) => setCustomer({ head_name: v })} placeholder="Сейткалиева Айгерим Маратовна"
          hint="Падеж и форму «действующего / действующей» подставим сами." />
        <Field label="Адрес" value={draft.customer.address} onChange={(v) => setCustomer({ address: v })} />
        <Field label="ИИК" value={draft.customer.iik} onChange={(v) => setCustomer({ iik: v })} />
        <Field label="Банк" value={draft.customer.bank} onChange={(v) => setCustomer({ bank: v })} />
        <Field label="БИК" value={draft.customer.bik} onChange={(v) => setCustomer({ bik: v })} />
        <Field label="Телефон" value={draft.customer.phone} onChange={(v) => setCustomer({ phone: v })} />
        <Field label="E-mail" value={draft.customer.email} onChange={(v) => setCustomer({ email: v })} />
      </section>

      {/* 4. Исполнитель */}
      <section style={{ marginBottom: 28 }}>
        <h3>4. {isRent ? 'Арендодатель' : 'Исполнитель'} (самозанятый)</h3>
        <Field label="ФИО (им. п.)" value={draft.executor.full_name}
          onChange={(v) => setExecutor({ full_name: v })} placeholder="Нурланов Ерлан Бакытович" />
        <div className="form-group">
          <label>ИИН</label>
          <input value={draft.executor.iin} placeholder="12 цифр" inputMode="numeric" maxLength={12}
            onChange={(e) => setExecutor({ iin: e.target.value.replace(/\D/g, '') })}
            onBlur={(e) => checkIin(e.target.value.replace(/\D/g, ''))} />
          {iin && !iin.valid && (
            <div style={{ color: '#b91c1c', fontSize: 13, marginTop: 4 }}>
              ИИН не прошёл проверку: нужно 12 цифр с верной контрольной суммой и корректной датой рождения.
            </div>
          )}
          {iin && iin.valid && (
            <div style={{ color: '#065f46', fontSize: 13, marginTop: 4 }}>
              ИИН корректен{iin.birth_date ? `, дата рождения ${iin.birth_date}` : ''}
              {iin.gender ? `, пол ${iin.gender === 'male' ? 'муж.' : 'жен.'}` : ''}.
            </div>
          )}
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
            Пол определяется по ИИН — в договоре сами поставим «гражданин / гражданка»
            и «именуемый / именуемая».
          </div>
        </div>
        <div className="form-group">
          <label>Статус</label>
          <select value={draft.executor.status}
            onChange={(e) => setExecutor({ status: e.target.value as Draft['executor']['status'] })}>
            <option value="citizen">гражданин(ка) РК</option>
            <option value="kandas">кандас</option>
          </select>
        </div>
        <Field label="Адрес" value={draft.executor.address} onChange={(v) => setExecutor({ address: v })} />
        <Field label="ИИК" value={draft.executor.iik} onChange={(v) => setExecutor({ iik: v })} />
        <Field label="Банк" value={draft.executor.bank} onChange={(v) => setExecutor({ bank: v })} />
        <Field label="БИК" value={draft.executor.bik} onChange={(v) => setExecutor({ bik: v })} />
        <Field label="Телефон" value={draft.executor.phone} onChange={(v) => setExecutor({ phone: v })} />
      </section>

      {/* 5. Условия оплаты и срок */}
      <section style={{ marginBottom: 28 }}>
        <h3>5. Оплата и срок</h3>
        <div className="form-group">
          <label>{amountLabel}</label>
          <input type="number" min={1} step={1} value={draft.amount || ''}
            onChange={(e) => set({ amount: Math.max(0, Math.trunc(Number(e.target.value) || 0)) })} />
          {draft.amount > 0 && (
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>{fmtTenge(draft.amount)} ₸</div>
          )}
        </div>
        {isRent && (
          <div className="form-group">
            <label>Арендная плата указана</label>
            <select value={draft.rent_period}
              onChange={(e) => set({ rent_period: e.target.value as Draft['rent_period'] })}>
              <option value="month">в месяц</option>
              <option value="term">за весь срок</option>
            </select>
          </div>
        )}
        <div className="form-group">
          <label>Срок оплаты, рабочих дней (п. 5.2)</label>
          <input type="number" min={1} step={1} value={draft.payment_days}
            onChange={(e) => set({ payment_days: Math.max(1, Math.trunc(Number(e.target.value) || 1)) })} />
        </div>
        <div className="form-group">
          <label>Способ оплаты</label>
          <select value={draft.payment_method}
            onChange={(e) => set({ payment_method: e.target.value as Draft['payment_method'] })}>
            <option value="cashless">безналично на счёт исполнителя</option>
            <option value="any">наличными или безналично</option>
          </select>
        </div>
        <Field label="Срок действия: с" type="date" value={draft.valid_from ?? ''}
          onChange={(v) => set({ valid_from: v })} hint="Пусто — договор действует с даты подписания." />
        <Field label="Срок действия: по" type="date" value={draft.valid_to}
          onChange={(v) => set({ valid_to: v })} />
      </section>

      {/* 6. Формирование */}
      <section style={{ marginBottom: 28 }}>
        <h3>6. Формирование</h3>
        {warnings.length > 0 && (
          <div style={{ background: '#fef3c7', border: '1px solid #fde68a', color: '#b45309', padding: '12px 16px', borderRadius: 8, marginBottom: 12, fontSize: 14 }}>
            <strong>Проверьте перед подписанием:</strong>
            <ul style={{ margin: '8px 0 0', paddingLeft: 22 }}>
              {warnings.map((w, i) => <li key={i} style={{ marginTop: 4 }}>{w}</li>)}
            </ul>
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-primary" onClick={handleGenerate} disabled={busy}>
            {busy ? 'Формирование…' : 'Сформировать договор (.docx)'}
          </button>
          <button className="btn btn-secondary" onClick={resetDraft} disabled={busy}>Очистить данные</button>
        </div>
      </section>
    </div>
  )
}
