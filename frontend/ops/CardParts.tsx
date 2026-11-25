import { ReactNode, useState } from 'react'
import { Api, Cabinet, CompanyDetail, Profile, REPORT_STATUS, StaffNote } from './api'

// Блоки карточки итерации 4: правка адреса 1С, заметки сотрудников, «Профиль».
// Все правки — на сервере коммитом в prod-decisions с email автора; здесь только формы.

const ONEC_KIND: Record<string, string> = { cloud: 'облачная', local: 'локальная', none: 'нет базы' }

export function fmtDateTime(v?: string | null) {
  if (!v) return ''
  const d = new Date(v)
  return isNaN(+d) ? String(v) : d.toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: v.length > 10 ? 'short' : undefined })
}

export function Row({ k, children }: { k: string; children: ReactNode }) {
  const empty = children === null || children === undefined || children === ''
  return (
    <div className="opsx-kv">
      <div className="opsx-k">{k}</div>
      <div className="opsx-v">{empty ? <span className="opsx-muted">—</span> : children}</div>
    </div>
  )
}

function useRun(onChanged: () => Promise<void>) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError('')
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
  return { busy, error, run }
}

// --- 1С -----------------------------------------------------------------------------------

export function OnecSection({ api, c, onChanged }: { api: Api; c: CompanyDetail; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState(false)
  const [kind, setKind] = useState(c.onec.kind || 'cloud')
  const [url, setUrl] = useState(c.onec.url || '')
  const [note, setNote] = useState(c.onec.note || '')
  const [reason, setReason] = useState('')
  const { busy, error, run } = useRun(onChanged)
  const edited = (c.card?.systems?.onec || {}).edited as { by?: string; at?: string; reason?: string } | undefined

  const start = () => {
    setKind(c.onec.kind || 'cloud'); setUrl(c.onec.url || ''); setNote(c.onec.note || ''); setReason(''); setEditing(true)
  }
  const changed = kind !== (c.onec.kind || 'cloud') || url.trim() !== (c.onec.url || '') || note.trim() !== (c.onec.note || '')
  const save = async () => {
    const body: { url?: string; kind?: string; note?: string; reason: string } = { reason: reason.trim() }
    if (kind !== (c.onec.kind || 'cloud')) body.kind = kind
    if (url.trim() !== (c.onec.url || '')) body.url = url.trim()
    if (note.trim() !== (c.onec.note || '')) body.note = note.trim()
    if (await run(() => api.updateOnec(c.id, body))) setEditing(false)
  }

  return (
    <>
      <div className="opsx-block-head">
        <h2>1С</h2>
        {!editing && <button className="opsx-btn opsx-btn-sm" onClick={start}>Изменить адрес базы</button>}
      </div>
      {error && <div className="opsx-alert opsx-alert-err">{error}</div>}
      {editing ? (
        <div className="opsx-obl-form">
          <div className="opsx-obl-row">
            <label>Тип базы
              <select className="opsx-input opsx-input-sm" value={kind} onChange={(e) => setKind(e.target.value)}>
                {Object.entries(ONEC_KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
          </div>
          <label>Адрес базы<input className="opsx-input opsx-textarea" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} /></label>
          <label>Заметка<input className="opsx-input opsx-textarea" value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <label>Причина изменения (обязательно)
            <input className="opsx-input opsx-textarea" placeholder="например: база переехала на host1c.kz" value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <div className="opsx-sub">Правка уходит в карточку коммитом в prod-decisions с вашим email.</div>
          <div className="opsx-actions">
            <button className="opsx-btn opsx-btn-primary" disabled={busy || !changed || reason.trim().length < 3} onClick={save}>
              {busy ? 'Сохраняем…' : 'Сохранить'}
            </button>
            <button className="opsx-btn" disabled={busy} onClick={() => setEditing(false)}>Отмена</button>
          </div>
        </div>
      ) : (
        <>
          <Row k="База">{c.onec.kind ? ONEC_KIND[c.onec.kind] || c.onec.kind : null}</Row>
          <Row k="Адрес">{c.onec.url ? <a href={c.onec.url} target="_blank" rel="noreferrer" className="opsx-break">{c.onec.url}</a> : null}</Row>
          <Row k="Заметка">{c.onec.note}</Row>
          {edited?.by && (
            <Row k="Изменено">{edited.by}{edited.at && <>, {fmtDateTime(edited.at)}</>}{edited.reason && <> — {edited.reason}</>}</Row>
          )}
        </>
      )}
      <Row k="Логин агента">{c.onec.login}</Row>
      <Row k="Запуск">{c.onec.run_on === 'server' ? 'на сервере' : c.onec.run_on === 'manual' ? 'вручную' : c.onec.run_on}</Row>
      <Row k="Период закрыт по">{c.onec.closed_through}</Row>
    </>
  )
}

// --- заметки ------------------------------------------------------------------------------

function NoteItem({ n }: { n: StaffNote }) {
  return (
    <div className="opsx-note">
      <div className="opsx-note-text">{n.text}</div>
      <div className="opsx-sub">{n.author}{n.at && <>, {fmtDateTime(n.at)}</>}{n.form && <> · к {n.form}{n.period && <> {n.period}</>}</>}</div>
    </div>
  )
}

export function NoteForm({ api, c, onChanged, form, periods, onDone }: {
  api: Api; c: CompanyDetail; onChanged: () => Promise<void>; form?: string; periods?: string[]; onDone: () => void
}) {
  const [text, setText] = useState('')
  const [period, setPeriod] = useState(periods && periods.length ? periods[periods.length - 1] : '')
  const { busy, error, run } = useRun(onChanged)
  const save = async () => {
    if (await run(() => api.addNote(c.id, { text: text.trim(), form, period: form ? period : undefined }))) {
      setText(''); onDone()
    }
  }
  return (
    <div className="opsx-obl-form">
      {error && <div className="opsx-alert opsx-alert-err">{error}</div>}
      {form && periods && periods.length > 0 && (
        <label>Период
          <select className="opsx-input opsx-input-sm" value={period} onChange={(e) => setPeriod(e.target.value)}>
            {periods.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
      )}
      <textarea className="opsx-input opsx-textarea" rows={2} autoFocus placeholder={form ? `Замечание по ${form}` : 'Заметка по компании'}
        value={text} onChange={(e) => setText(e.target.value)} />
      <div className="opsx-actions">
        <button className="opsx-btn opsx-btn-primary" disabled={busy || text.trim().length < 2} onClick={save}>{busy ? 'Сохраняем…' : 'Добавить'}</button>
        <button className="opsx-btn" disabled={busy} onClick={onDone}>Отмена</button>
      </div>
    </div>
  )
}

export function FormNotes({ notes }: { notes: StaffNote[] }) {
  if (!notes.length) return null
  return <div className="opsx-form-notes">{notes.map((n, i) => <NoteItem key={i} n={n} />)}</div>
}

export function NotesSection({ api, c, onChanged }: { api: Api; c: CompanyDetail; onChanged: () => Promise<void> }) {
  const [adding, setAdding] = useState(false)
  const general = (c.staff_notes || []).filter((n) => !n.form)
  return (
    <section className="opsx-card">
      <div className="opsx-block-head">
        <h2>Заметки по компании</h2>
        {!adding && <button className="opsx-btn opsx-btn-sm" onClick={() => setAdding(true)}>Добавить заметку</button>}
      </div>
      {adding && <NoteForm api={api} c={c} onChanged={onChanged} onDone={() => setAdding(false)} />}
      {general.length === 0 && !adding && <div className="opsx-muted">Заметок нет.</div>}
      {[...general].reverse().map((n, i) => <NoteItem key={i} n={n} />)}
    </section>
  )
}

// --- Профиль ------------------------------------------------------------------------------

const EMPTY = <span className="opsx-muted">нет данных, профиль не загружен</span>

function list<T>(xs: T[] | undefined, fmt: (x: T) => string) {
  return xs && xs.length ? xs.map((x, i) => <div key={i}>{fmt(x)}</div>) : null
}

export function ProfileSection({ c }: { c: CompanyDetail }) {
  const p: Profile | null = c.profile
  const v = (x: ReactNode) => (p ? (x ?? <span className="opsx-muted">в профиле нет</span>) : EMPTY)
  const fmtD = (d?: string) => (d ? ` (с ${fmtDateTime(d)})` : '')
  return (
    <section className="opsx-card">
      <div className="opsx-block-head">
        <h2>Профиль</h2>
        {c.profile_url && <a className="opsx-btn opsx-btn-sm" href={c.profile_url} target="_blank" rel="noreferrer">Папка «Профиль» ↗</a>}
      </div>
      <div className="opsx-sub opsx-mb">{p ? <>Источник: {p.source || '—'}{p.date && <> · профиль от {fmtDateTime(p.date)}</>}</> : 'Профиль из кабинета КГД ещё не загружен.'}</div>
      <Row k="Расчётные счета">{v(list(p?.bank_accounts, (b) => [b.bank, b.bic, b.iban, b.currency].filter(Boolean).join(' · ')))}</Row>
      <Row k="ККМ">{v(list(p?.cash_registers, (k) => [k.reg_number && `рег. № ${k.reg_number}`, k.model, k.serial && `зав. № ${k.serial}`, k.ofd, k.registered && `с ${fmtDateTime(k.registered)}`].filter(Boolean).join(' · ')))}</Row>
      <Row k="УГД">{v(list(p?.ugd, (u) => [u.code, u.name, u.type].filter(Boolean).join(' · ') + fmtD(u.from)))}</Row>
      <Row k="Руководитель">{v(p?.head || null)}</Row>
      <Row k="Адрес">{v(p?.address || null)}</Row>
      <Row k="ОКЭД">{v(list(p?.oked, (o) => [o.code, o.name, o.type].filter(Boolean).join(' · ') + fmtD(o.from)))}</Row>
    </section>
  )
}

// --- Кабинет налогоплательщика (блок cabinet: карточки; пишет knp-watch) ---------------------

const money = (n?: number) => (typeof n === 'number' ? n.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) : '—')
const RED: Record<string, string> = { unread: 'не прочитано', overdue: 'срок прошёл', due_soon: 'срок скоро' }
const CAB_REPORT: Record<string, string> = { accepted: 'принят', submitted: 'сдан', rejected: 'отклонён', not_found: 'не найден в кабинете' }

export function CabinetSection({ api, c, isAdmin, onChanged }: { api: Api; c: CompanyDetail; isAdmin: boolean; onChanged: () => Promise<void> }) {
  const k: Cabinet | null = c.cabinet || null
  const q = c.cabinet_queue
  const { busy, error, run } = useRun(onChanged)
  const saldoRows = (k?.saldo?.rows || []).filter((r) => (r.tax || 0) + (r.penalty || 0) + (r.fine || 0) !== 0)
  const notices = k?.notices?.items || []
  const reports = k?.reports || []
  return (
    <section className="opsx-card">
      <div className="opsx-block-head">
        <h2>Кабинет налогоплательщика</h2>
        <div className="opsx-actions">
        {isAdmin && <a className="opsx-btn opsx-btn-sm opsx-btn-primary" href="https://knp.kgd.gov.kz/signin" target="_blank"
          rel="noreferrer noopener">Проверить кабинет ↗</a>}
        {isAdmin && (q
          ? <span className="opsx-muted">в очереди на вход с {fmtDateTime(q.requested_at)} ({q.reason_label}){' '}
              <button className="opsx-link opsx-link-inline" disabled={busy}
                onClick={() => run(() => api.cabinetQueueDone(q.id, 'снято вручную'))}>снять</button></span>
          : c.active && <button className="opsx-btn opsx-btn-sm" disabled={busy}
              onClick={() => run(() => api.cabinetQueueAdd(c.id))}>Поставить в очередь на вход</button>)}
        </div>
      </div>
      {error && <div className="opsx-alert opsx-alert-err">{error}</div>}
      {!k ? (
        <div className="opsx-muted">В кабинет ещё не заходили — данные появятся после проверки knp-watch.</div>
      ) : (
        <>
          <div className="opsx-sub opsx-mb">
            Проверено {fmtDateTime(k.checked_at) || '—'}{k.status && <> · {k.status}</>}
          </div>
          <Row k="Сальдо">
            {k.saldo ? (
              <div>
                <div>
                  {(k.saldo.debt_total || 0) > 0
                    ? <span className="opsx-st opsx-st-rejected">недоимка {money(k.saldo.debt_total)} ₸</span>
                    : <span className="opsx-st opsx-st-accepted">недоимки нет</span>}
                  {(k.saldo.overpaid_total || 0) > 0 && <> · переплата {money(k.saldo.overpaid_total)} ₸</>}
                  <span className="opsx-muted"> · на {fmtDateTime(k.saldo.date) || '—'}{k.saldo.fresh === false && ' (не на дату проверки)'}{k.saldo.pages && ` · страниц ${k.saldo.pages}`}</span>
                </div>
                {saldoRows.length > 0 && (
                  <table className="opsx-table opsx-table-compact opsx-cab-table">
                    <thead><tr><th>КБК</th><th>ОГД</th><th>Налог</th><th>Пеня</th><th>Штраф</th></tr></thead>
                    <tbody>{saldoRows.map((r, i) => (
                      <tr key={i}><td className="opsx-mono">{r.kbk}</td><td className="opsx-mono">{r.ogd}</td>
                        <td>{money(r.tax)}</td><td>{money(r.penalty)}</td><td>{money(r.fine)}</td></tr>
                    ))}</tbody>
                  </table>
                )}
              </div>
            ) : null}
          </Row>
          <Row k="Выписка по л/с">
            {k.statement ? <>заказана {fmtDateTime(k.statement.ordered_at) || '—'}{k.statement.from && <> · с {fmtDateTime(k.statement.from)}</>}
              {' · '}{k.statement.ready ? 'сформирована (лежит в кабинете)' : 'ещё формируется'}</> : null}
          </Row>
          <Row k="Уведомления">
            {k.notices ? (notices.length === 0
              ? <span className="opsx-muted">нет{k.notices.from && ` с ${fmtDateTime(k.notices.from)}`}</span>
              : <div>{notices.map((n, i) => (
                  <div key={i} className="opsx-cab-line">
                    {n.red && <><span className="opsx-st opsx-st-rejected">{RED[n.red] || n.red}</span>{' '}</>}
                    {fmtDateTime(n.date)} · {[n.type, n.number && `№ ${n.number}`].filter(Boolean).join(' ')}
                    {n.due && <> · срок {fmtDateTime(n.due)}</>}
                    {n.summary && <div className="opsx-muted">{n.summary}</div>}
                  </div>
                ))}</div>) : null}
          </Row>
          <Row k="Сданные формы">
            {reports.length === 0
              ? (k.reports_checked_through ? <span className="opsx-muted">сроков не было · проверено по {fmtDateTime(k.reports_checked_through)}</span> : null)
              : <div>
                  {reports.map((r, i) => (
                    <div key={i} className="opsx-cab-line">
                      <span className="opsx-mono">{r.form}</span> {r.period}{r.due && <> · срок {fmtDateTime(r.due)}</>} ·{' '}
                      <span className={`opsx-st opsx-st-${r.cabinet === 'not_found' ? 'rejected' : r.cabinet}`}>{CAB_REPORT[r.cabinet || ''] || REPORT_STATUS[r.cabinet || ''] || r.cabinet}</span>
                      {r.accepted_at && <> {fmtDateTime(r.accepted_at)}</>}
                      {r.drive && <span className="opsx-muted"> · на Диске: форма {r.drive.form_file ? '✓' : '—'}, уведомление {r.drive.notice_file ? '✓' : '—'}{(r.drive.added || []).length > 0 && `, добавлено ${(r.drive.added || []).length}`}</span>}
                    </div>
                  ))}
                  {k.reports_checked_through && <div className="opsx-muted">проверено по {fmtDateTime(k.reports_checked_through)}</div>}
                </div>}
          </Row>
        </>
      )}
    </section>
  )
}
