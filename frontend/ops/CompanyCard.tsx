import { ReactNode, useEffect, useMemo, useState } from 'react'
import { Api, CompanyDetail, REGIME, REPORT_STATUS } from './api'
import ObligationsBlock from './ObligationsBlock'
import { FormNotes, NoteForm, NotesSection, OnecSection, ProfileSection } from './CardParts'

const FEATURES: Record<string, string> = {
  has_employees: 'есть сотрудники',
  has_import: 'импорт (таможенные КБК)',
  has_transport: 'транспорт',
  has_property: 'имущество',
  has_land: 'земля',
  has_emissions: 'эмиссии',
  has_nonresident_payments: 'выплаты нерезидентам (101.04)',
  has_cash_register: 'касса ОФД',
  is_forwarder: 'экспедитор',
}

function yn(v: unknown) {
  return v === true ? 'да' : v === false ? 'нет' : '—'
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="opsx-kv">
      <div className="opsx-k">{k}</div>
      <div className="opsx-v">{children === null || children === undefined || children === '' ? <span className="opsx-muted">—</span> : children}</div>
    </div>
  )
}

export default function CompanyCard({ api, id, onBack }: { api: Api; id: number; onBack: () => void }) {
  const [c, setC] = useState<CompanyDetail | null>(null)
  const [error, setError] = useState('')
  const [role, setRole] = useState<'admin' | 'staff' | null>(null)
  const isAdmin = role === 'admin'
  const [noteForm, setNoteForm] = useState<string | null>(null)  // форма, к которой открыта заметка

  const load = () => api.company(id).then(setC).catch((e) => setError(e.status === 404 ? 'Компания не найдена' : e.message))
  useEffect(() => { load(); api.me().then((m) => setRole(m.role)).catch(() => {}) }, [id])

  const periods = useMemo(() => {
    if (!c) return [] as string[]
    // хронологически: 2024-Q1 < 2024-H1 < 2024-Q3 < 2024 (год целиком — после кварталов)
    const key = (p: string) => {
      const m = p.match(/(\d{4})(?:-(Q|H)(\d))?/)
      if (!m) return [9999, 99, p] as const
      const sub = m[2] === 'Q' ? Number(m[3]) * 2 : m[2] === 'H' ? Number(m[3]) * 4 : 10
      return [Number(m[1]), sub, p] as const
    }
    return Array.from(new Set(c.reports.map((r) => r.period))).sort((a, b) => {
      const x = key(a), y = key(b)
      return x[0] - y[0] || x[1] - y[1] || String(x[2]).localeCompare(String(y[2]))
    })
  }, [c])
  const forms = useMemo(() => {
    if (!c) return [] as string[]
    const confirmedForms = c.obligations.filter((f) => f.status === 'confirmed').map((f) => f.form)
    return Array.from(new Set([...c.reports.map((r) => r.form), ...confirmedForms])).sort()
  }, [c])
  // Подтверждённые обязательства: форма → основания (basis), показываются рядом с формой.
  const basis = useMemo(() => {
    const m: Record<string, string[]> = {}
    for (const f of c?.obligations || []) {
      if (f.status === 'confirmed') m[f.form] = [...(m[f.form] || []), ...f.trigger.map((t) => (f.period ? `${f.period}: ${t}` : t))]
    }
    return m
  }, [c])

  if (error) return <div><button className="opsx-link" onClick={onBack}>← К списку</button><div className="opsx-alert opsx-alert-err">{error}</div></div>
  if (!c) return <div className="opsx-muted">Загрузка…</div>

  const card = c.card || {}
  const tax = card.tax || {}
  const features = tax.features || {}
  const resp = card.responsible || {}
  const banks: any[] = Array.isArray(card.banks) ? card.banks : []
  const portals = card.systems?.portals || {}

  return (
    <div>
      <button className="opsx-link" onClick={onBack}>← К списку компаний</button>
      <div className="opsx-head">
        <div>
          <h1>{c.name}</h1>
          {c.legal_name && <div className="opsx-legal">{c.legal_name}</div>}
          <div className="opsx-muted">
            <span className="opsx-mono">{c.bin || 'БИН не указан'}</span> · {c.slug}
            {' '}{c.active ? <span className="opsx-pill opsx-pill-on">активна</span> : <span className="opsx-pill">архив</span>}
          </div>
        </div>
        <div className="opsx-actions">
          {c.drive.root_url && <a className="opsx-btn opsx-btn-primary" href={c.drive.root_url} target="_blank" rel="noreferrer">Папка на Диске ↗</a>}
          {c.drive.agent_url && <a className="opsx-btn" href={c.drive.agent_url} target="_blank" rel="noreferrer">_agent ↗</a>}
        </div>
      </div>

      {!c.active && (
        <div className="opsx-alert opsx-alert-warn">
          <b>Архивная карточка.</b> Причина: {c.inactive_reason || 'не указана'}
          {c.inactive_since && <> · с {new Date(c.inactive_since).toLocaleDateString('ru-RU')}</>}
        </div>
      )}

      <ObligationsBlock api={api} c={c} isAdmin={isAdmin} onChanged={async () => { await load() }} />

      <div className="opsx-grid">
        <section className="opsx-card">
          <h2>Реквизиты</h2>
          <Row k="Наименование">{c.legal_name}</Row>
          <Row k="Название">{c.name_official ? c.name : <span className="opsx-muted">не заполнено в карточке (показана папка на Диске)</span>}</Row>
          <Row k="БИН"><span className="opsx-mono">{c.bin}</span></Row>
          <Row k="Режим">{tax.regime ? REGIME[tax.regime] || tax.regime : null}</Row>
          <Row k="Плательщик НДС">{yn(tax.vat_payer)}</Row>
          <Row k="Astana Hub">{yn(tax.astana_hub)}</Row>
          <Row k="СЭЗ">{tax.sez}</Row>
          <Row k="Бухгалтер">{card.accountant}</Row>
          <Row k="Ответственный">
            {[resp.name, resp.email, resp.whatsapp, resp.telegram].filter(Boolean).join(' · ')}
          </Row>
          <Row k="Ведём с">{card.since}</Row>
          <Row k="Алиасы">
            {c.aliases.length ? <div className="opsx-chips">{c.aliases.map((a) => <span key={a} className="opsx-chip">{a}</span>)}</div> : null}
          </Row>
        </section>

        <section className="opsx-card">
          <OnecSection key={JSON.stringify(c.onec)} api={api} c={c} onChanged={async () => { await load() }} />
          <h2 className="opsx-h2-gap">Google Диск</h2>
          <Row k="Папка">{c.drive.folder_name}</Row>
          <Row k="Папка на Диске">{c.drive.root_url ? <a href={c.drive.root_url} target="_blank" rel="noreferrer">открыть ↗</a> : <span className="opsx-muted">id папки не заполнен</span>}</Row>
          {isAdmin && <Row k="_agent">{c.drive.agent_url ? <a href={c.drive.agent_url} target="_blank" rel="noreferrer">открыть ↗</a> : <span className="opsx-muted">id папки не заполнен</span>}</Row>}
        </section>
      </div>

      <section className="opsx-card">
        <h2>Признаки</h2>
        <div className="opsx-chips">
          {Object.keys({ ...FEATURES, ...features }).map((k) => (
            <span key={k} className={'opsx-chip ' + (features[k] ? 'opsx-chip-on' : 'opsx-chip-off')}>
              {features[k] ? '✓ ' : ''}{FEATURES[k] || k}
            </span>
          ))}
        </div>
        <div className="opsx-sub-grid">
          <Row k="Банки">
            {banks.length ? banks.map((b, i) => <div key={i}>{[b.bank, b.currency, b.iban].filter(Boolean).join(' · ')}</div>) : null}
          </Row>
          <Row k="Кассы ОФД">{Array.isArray(card.cash_registers) && card.cash_registers.length ? card.cash_registers.length : null}</Row>
          <Row k="Порталы">
            {['knp', 'esf', 'stat'].filter((p) => portals[p]).map((p) => p.toUpperCase()).join(', ')}
          </Row>
        </div>
      </section>

      <section className="opsx-card">
        <h2>Формы</h2>
        {forms.length === 0 ? (
          <div className="opsx-muted">Статусов форм пока нет. Их загружает «Импорт отчётов».</div>
        ) : (
          <div className="opsx-table-wrap">
            <table className="opsx-table opsx-table-compact">
              <thead>
                <tr><th>Форма</th>{periods.map((p) => <th key={p}>{p}</th>)}</tr>
              </thead>
              <tbody>
                {forms.map((f) => (
                  <tr key={f}>
                    <td className="opsx-form-cell">
                      <span className="opsx-mono">{f}</span>
                      {basis[f] && basis[f].map((b, i) => <div key={i} className="opsx-basis">основание: {b}</div>)}
                      <FormNotes notes={(c.staff_notes || []).filter((n) => n.form === f)} />
                      {noteForm === f ? (
                        <NoteForm api={api} c={c} form={f} periods={periods.filter((p) => c.reports.some((x) => x.form === f && x.period === p))}
                          onChanged={async () => { await load() }} onDone={() => setNoteForm(null)} />
                      ) : (
                        <button className="opsx-link opsx-link-inline opsx-note-add" onClick={() => setNoteForm(f)}>+ замечание</button>
                      )}
                    </td>
                    {periods.map((p) => {
                      const r = c.reports.find((x) => x.form === f && x.period === p)
                      if (!r) return <td key={p} className="opsx-muted">·</td>
                      return (
                        <td key={p} title={r.raw_value || ''}>
                          <span className={`opsx-st opsx-st-${r.status}`}>{REPORT_STATUS[r.status] || r.status}</span>
                          {r.evidence_url && <> <a href={r.evidence_url} target="_blank" rel="noreferrer">файл</a></>}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <NotesSection api={api} c={c} onChanged={async () => { await load() }} />

      <ProfileSection c={c} />

      <details className="opsx-card">
        <summary>Карточка целиком (client.yaml)</summary>
        <pre className="opsx-pre">{JSON.stringify(card, null, 2)}</pre>
      </details>
    </div>
  )
}
