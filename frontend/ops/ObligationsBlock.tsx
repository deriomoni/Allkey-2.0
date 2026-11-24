import { useState } from 'react'
import { Api, CompanyDetail, ObligationFlag, OBLIGATION_SOURCE } from './api'

// Блок «Обязательства»: подозрения на обязанность сдать форму (knowledge/obligation-triggers.md).
// Решения пишутся в client.yaml репозитория arty-ops коммитом от системы, затем карточка перечитывается.
const TEMPLATE = 'контрагент/объект → за что → сумма → документ, дата'

function fmtDate(d: string | null) {
  if (!d) return ''
  const t = new Date(d)
  return isNaN(t.getTime()) ? d : t.toLocaleDateString('ru-RU')
}

function Trigger({ lines }: { lines: string[] }) {
  if (lines.length === 1) return <div className="opsx-trigger">{lines[0]}</div>
  return (
    <ul className="opsx-trigger-list">
      {lines.map((t, i) => <li key={i} className="opsx-trigger">{t}</li>)}
    </ul>
  )
}

function Meta({ f }: { f: ObligationFlag }) {
  return (
    <div className="opsx-sub">
      поднял: {OBLIGATION_SOURCE[f.source || ''] || f.source || '—'}{f.raised_by && <> ({f.raised_by})</>}{f.raised_at && <>, {fmtDate(f.raised_at)}</>}
      {f.decided_by && <> · решение: {f.decided_by}{f.decided_at && <>, {fmtDate(f.decided_at)}</>}</>}
    </div>
  )
}

// Формы, по которым сотрудник может поставить флаг «подозрение» (сервер проверяет то же самое).
export const STAFF_FLAG_FORMS = ['101.04', '328.00', '700.00', 'отчёт участника Астана Хаб']

export default function ObligationsBlock({ api, c, onChanged, isAdmin }: {
  api: Api; c: CompanyDetail; onChanged: () => Promise<void>; isAdmin: boolean
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState('')
  const [period, setPeriod] = useState('')
  const [trigger, setTrigger] = useState('')
  const [dismissing, setDismissing] = useState<number | null>(null)
  const [reason, setReason] = useState('')

  const suspected = c.obligations.filter((f) => f.status === 'suspected')
  const confirmed = c.obligations.filter((f) => f.status === 'confirmed')
  const dismissed = c.obligations.filter((f) => f.status === 'dismissed')
  const lines = trigger.split('\n').map((s) => s.trim()).filter(Boolean)
  const offTemplate = lines.filter((l) => (l.match(/→/g) || []).length < 3)

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await fn()
      await onChanged()
      return true
    } catch (e: any) {
      setError(e.message)
      return false
    } finally {
      setBusy(false)
    }
  }

  const submitNew = async () => {
    const ok = await run(() => api.raiseObligation(c.id, { form: form.trim(), period: period.trim(), trigger: lines }))
    if (ok) {
      setAdding(false); setForm(''); setPeriod(''); setTrigger('')
    }
  }

  const submitDismiss = async (f: ObligationFlag) => {
    const ok = await run(() => api.decideObligation(c.id, f, 'dismiss', reason.trim()))
    if (ok) {
      setDismissing(null); setReason('')
    }
  }

  return (
    <section className="opsx-card">
      <div className="opsx-block-head">
        <h2>Обязательства</h2>
        {c.active && !adding && (
          <button className="opsx-btn" disabled={busy} onClick={() => { setAdding(true); if (!isAdmin) setForm(STAFF_FLAG_FORMS[0]) }}>
            {isAdmin ? 'Есть обязательство' : 'Подозрение на обязательство'}
          </button>
        )}
      </div>
      {error && <div className="opsx-alert opsx-alert-err">{error}</div>}

      {adding && (
        <div className="opsx-obl-form">
          <div className="opsx-obl-row">
            <label>Форма
              {isAdmin ? (
                <input className="opsx-input opsx-input-sm" placeholder="101.04" value={form} onChange={(e) => setForm(e.target.value)} />
              ) : (
                <select className="opsx-input opsx-input-sm" value={form} onChange={(e) => setForm(e.target.value)}>
                  {STAFF_FLAG_FORMS.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              )}
            </label>
            <label>Период<input className="opsx-input opsx-input-sm" placeholder="2026-Q4" value={period} onChange={(e) => setPeriod(e.target.value)} /></label>
          </div>
          <label>Основание — одна строка на основание
            <textarea className="opsx-input opsx-textarea" rows={3} placeholder={TEMPLATE} value={trigger} onChange={(e) => setTrigger(e.target.value)} />
          </label>
          <div className="opsx-sub">
            Шаблон: «{TEMPLATE}». Основание обязательно. Если по этой форме за период уже есть открытый флаг, основание добавится в него.
            {!isAdmin && <> Подтверждает или снимает флаг администратор.</>}
          </div>
          {offTemplate.length > 0 && <div className="opsx-warn-text">Не по шаблону: {offTemplate.join('; ')}</div>}
          <div className="opsx-actions">
            <button className="opsx-btn opsx-btn-primary" disabled={busy || !form.trim() || !period.trim() || lines.length === 0} onClick={submitNew}>
              Поднять флаг
            </button>
            <button className="opsx-btn" disabled={busy} onClick={() => setAdding(false)}>Отмена</button>
          </div>
        </div>
      )}

      <h3 className="opsx-h3">Подозрения {suspected.length > 0 && <span className="opsx-pill opsx-pill-susp">{suspected.length}</span>}</h3>
      {suspected.length === 0 ? <div className="opsx-muted">Подозрений нет.</div> : suspected.map((f) => (
        <div key={f.idx} className="opsx-flag opsx-flag-susp">
          <div className="opsx-flag-main">
            <div><b className="opsx-mono">{f.form}</b> · {f.period}</div>
            <Trigger lines={f.trigger} />
            <Meta f={f} />
          </div>
          {isAdmin && <div className="opsx-flag-actions">
            {dismissing === f.idx ? (
              <div className="opsx-dismiss">
                <input className="opsx-input opsx-input-sm" placeholder="Причина снятия (обязательно)" value={reason} onChange={(e) => setReason(e.target.value)} />
                <button className="opsx-btn" disabled={busy || !reason.trim()} onClick={() => submitDismiss(f)}>Снять</button>
                <button className="opsx-link" onClick={() => { setDismissing(null); setReason('') }}>отмена</button>
              </div>
            ) : (
              <>
                <button className="opsx-btn opsx-btn-primary" disabled={busy} onClick={() => run(() => api.decideObligation(c.id, f, 'confirm'))}>Подтвердить</button>
                <button className="opsx-btn" disabled={busy} onClick={() => { setDismissing(f.idx); setReason('') }}>Снять</button>
              </>
            )}
          </div>}
        </div>
      ))}

      <h3 className="opsx-h3">Подтверждённые</h3>
      {confirmed.length === 0 ? <div className="opsx-muted">Нет.</div> : confirmed.map((f) => (
        <div key={f.idx} className="opsx-flag opsx-flag-conf">
          <div className="opsx-flag-main">
            <div><b className="opsx-mono">{f.form}</b> · {f.period} <span className="opsx-pill opsx-pill-on">в tax.forms</span></div>
            <Trigger lines={f.trigger} />
            <Meta f={f} />
          </div>
        </div>
      ))}

      {dismissed.length > 0 && (
        <details className="opsx-history">
          <summary>Снятые ({dismissed.length}) — история</summary>
          {dismissed.map((f) => (
            <div key={f.idx} className="opsx-flag opsx-flag-off">
              <div className="opsx-flag-main">
                <div><b className="opsx-mono">{f.form}</b> · {f.period}</div>
                <Trigger lines={f.trigger} />
                <div className="opsx-sub">причина: {f.reason}</div>
                <Meta f={f} />
              </div>
            </div>
          ))}
        </details>
      )}
    </section>
  )
}
