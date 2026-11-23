import { useEffect, useMemo, useState } from 'react'
import { Api, Discrepancy, PlanCounters, PlanFilter, PlanLoadResult, PlanRow, REPORT_STATUS } from './api'

// Экран «Отчёты»: план форм из allkey-ops (reports/plan-2026.csv, source=plan) и вкладка «Расхождения».
// Фильтры и поиск — на клиенте; в URL уходят только вкладка и, для экспорта, значения фильтров
// (период/форма/статус/режим — без названий компаний).

type Tab = 'plan' | 'disc'

const STATUS_OPTIONS: [string, string][] = [
  ['due', 'ожидается'],
  ['clarify', 'уточнить'],
  ['not_required', 'не требуется'],
]
const PLAN_STATUS_LABEL: Record<string, string> = { ...REPORT_STATUS, due: 'ожидается' }

function readTab(): Tab {
  return new URLSearchParams(window.location.search).get('tab') === 'disc' ? 'disc' : 'plan'
}

function uniq(values: (string | null)[]) {
  return Array.from(new Set(values.filter((v): v is string => !!v))).sort((a, b) => a.localeCompare(b, 'ru'))
}

function companyHref(basePath: string, id: number) {
  return basePath.replace(/ops-reports$/, 'ops') + `?c=${id}`
}

export default function ReportsScreen({ api, basePath }: { api: Api; basePath: string }) {
  const [tab, setTab] = useState<Tab>(readTab)
  useEffect(() => {
    const onPop = () => setTab(readTab())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
  const go = (t: Tab) => {
    window.history.pushState(null, '', basePath + (t === 'disc' ? '?tab=disc' : ''))
    setTab(t)
  }

  return (
    <div>
      <div className="opsx-head">
        <div>
          <h1>Отчёты</h1>
          <div className="opsx-muted">План налоговых форм за 4 кв. 2026, 2 п/г 2026 и 2026 год — из allkey-ops</div>
        </div>
      </div>
      <div className="opsx-tabs">
        <button className={`opsx-tab ${tab === 'plan' ? 'opsx-tab-on' : ''}`} onClick={() => go('plan')}>План форм</button>
        <button className={`opsx-tab ${tab === 'disc' ? 'opsx-tab-on' : ''}`} onClick={() => go('disc')}>Расхождения</button>
      </div>
      {tab === 'plan' ? <PlanTab api={api} basePath={basePath} /> : <DiscrepanciesTab api={api} basePath={basePath} />}
    </div>
  )
}

function PlanTab({ api, basePath }: { api: Api; basePath: string }) {
  const [items, setItems] = useState<PlanRow[] | null>(null)
  const [counters, setCounters] = useState<PlanCounters | null>(null)
  const [error, setError] = useState('')
  const [f, setF] = useState<PlanFilter>({})
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadRes, setLoadRes] = useState<PlanLoadResult | null>(null)
  const [exporting, setExporting] = useState('')

  const load = () => {
    setError('')
    return api.plan().then((d) => { setItems(d.items); setCounters(d.counters) }).catch((e) => setError(e.message))
  }
  useEffect(() => { load() }, [])

  const runLoad = async () => {
    setLoading(true)
    setLoadRes(null)
    try {
      setLoadRes(await api.loadPlan())
      await load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const options = useMemo(() => ({
    period: uniq((items || []).map((i) => i.period)),
    form: uniq((items || []).map((i) => i.form)),
    regime: uniq((items || []).map((i) => i.regime)),
  }), [items])

  const withoutForms = useMemo(() => new Set(counters?.companies_without_forms_ids || []), [counters])

  const filtered = useMemo(() => {
    if (!items) return []
    const nq = q.trim().toLowerCase()
    return items.filter((i) =>
      (!f.without_forms || withoutForms.has(i.company_id)) &&
      (!f.period || i.period === f.period) &&
      (!f.form || i.form === f.form) &&
      (!f.status || i.status === f.status) &&
      (!f.regime || i.regime === f.regime) &&
      (!nq || i.company.toLowerCase().includes(nq) || (i.bin || '').includes(nq)))
  }, [items, f, q, withoutForms])

  const set = (k: keyof PlanFilter, v: any) => setF((p) => ({ ...p, [k]: v || undefined }))
  const anyFilter = Object.values(f).some(Boolean) || !!q

  const doExport = async (kind: 'registry' | 'flat') => {
    setExporting(kind)
    try {
      await api.exportPlan(kind, f)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setExporting('')
    }
  }

  const onDecided = (id: number, status: string, decision: 'confirmed' | 'not_required', basis: string) => {
    // локально обновляем строку и пересчитываем счётчики с сервера
    setItems((xs) => xs && xs.map((x) => x.id === id ? { ...x, status, decision, decision_basis: basis } : x))
    api.plan().then((d) => setCounters(d.counters)).catch(() => {})
  }

  return (
    <div>
      {error && <div className="opsx-alert opsx-alert-err">{error}</div>}
      {loadRes && (
        <div className="opsx-alert opsx-alert-ok">
          План загружен: новых {loadRes.created}, обновлено {loadRes.updated}
          {loadRes.conflicts_with_history > 0 && <>, совпало с историей реестра и пропущено {loadRes.conflicts_with_history}</>}
          {loadRes.unknown_company > 0 && <>, компания не найдена {loadRes.unknown_company}</>}
          {loadRes.invalid > 0 && <>, некорректных строк {loadRes.invalid}</>}.
        </div>
      )}

      {counters && (
        <div className="opsx-counters">
          <button className={`opsx-counter ${!f.status && !f.without_forms ? 'opsx-counter-on' : ''}`}
            onClick={() => setF((p) => ({ ...p, status: undefined, without_forms: undefined }))}>
            <span className="opsx-counter-n">{counters.total}</span><span>всего строк</span>
          </button>
          <button className={`opsx-counter ${f.status === 'due' ? 'opsx-counter-on' : ''}`} onClick={() => set('status', f.status === 'due' ? '' : 'due')}>
            <span className="opsx-counter-n">{counters.due}</span><span>ожидается</span>
          </button>
          <button className={`opsx-counter opsx-counter-warn ${f.status === 'clarify' ? 'opsx-counter-on' : ''}`} onClick={() => set('status', f.status === 'clarify' ? '' : 'clarify')}>
            <span className="opsx-counter-n">{counters.clarify}</span><span>уточнить</span>
          </button>
          <button className={`opsx-counter ${f.without_forms ? 'opsx-counter-on' : ''}`} onClick={() => set('without_forms', !f.without_forms)}>
            <span className="opsx-counter-n">{counters.companies_without_forms}</span><span>компаний без форм</span>
          </button>
          {counters.not_required > 0 && (
            <button className={`opsx-counter ${f.status === 'not_required' ? 'opsx-counter-on' : ''}`} onClick={() => set('status', f.status === 'not_required' ? '' : 'not_required')}>
              <span className="opsx-counter-n">{counters.not_required}</span><span>не требуется</span>
            </button>
          )}
        </div>
      )}

      <div className="opsx-filters">
        <input className="opsx-input opsx-input-sm" placeholder="Компания или БИН" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="opsx-input opsx-filter" value={f.period || ''} onChange={(e) => set('period', e.target.value)}>
          <option value="">Все периоды</option>
          {options.period.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="opsx-input opsx-filter" value={f.form || ''} onChange={(e) => set('form', e.target.value)}>
          <option value="">Все формы</option>
          {options.form.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="opsx-input opsx-filter" value={f.status || ''} onChange={(e) => set('status', e.target.value)}>
          <option value="">Все статусы</option>
          {STATUS_OPTIONS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="opsx-input opsx-filter" value={f.regime || ''} onChange={(e) => set('regime', e.target.value)}>
          <option value="">Все режимы</option>
          {options.regime.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        {anyFilter && <button className="opsx-link opsx-link-inline" onClick={() => { setF({}); setQ('') }}>Сбросить</button>}
      </div>

      <div className="opsx-actions opsx-mb">
        <button className="opsx-btn opsx-btn-primary" disabled={!!exporting || !filtered.length} onClick={() => doExport('registry')}>
          {exporting === 'registry' ? 'Готовим…' : 'Экспорт: формат реестра (лист на форму)'}
        </button>
        <button className="opsx-btn" disabled={!!exporting || !filtered.length} onClick={() => doExport('flat')}>
          {exporting === 'flat' ? 'Готовим…' : 'Экспорт: плоский лист'}
        </button>
        <button className="opsx-btn" disabled={loading} onClick={runLoad} title="Загрузить reports/plan-2026.csv из клона allkey-ops. История реестра не затирается.">
          {loading ? 'Загружаем…' : 'Загрузить план из allkey-ops'}
        </button>
        <span className="opsx-muted">
          {items && `Показано ${filtered.length} из ${items.length}`}
          {q && ' · поиск в экспорт не попадает'}
        </span>
      </div>

      {!items ? (
        !error && <div className="opsx-muted">Загрузка…</div>
      ) : items.length === 0 ? (
        <div className="opsx-card">План ещё не загружен. Нажмите «Загрузить план из allkey-ops».</div>
      ) : (
        <div className="opsx-table-wrap">
          <table className="opsx-table opsx-table-compact opsx-plan">
            <thead>
              <tr>
                <th>Компания</th><th>БИН</th><th>Режим</th><th>НДС</th><th>Форма</th><th>Период</th><th>Срок</th>
                <th>Статус</th><th>Причина уточнения</th><th>Основание</th><th>Источник</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((i) => (
                <PlanTr key={i.id} i={i} api={api} basePath={basePath} onDecided={onDecided} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function PlanTr({ i, api, basePath, onDecided }: {
  i: PlanRow; api: Api; basePath: string
  onDecided: (id: number, status: string, d: 'confirmed' | 'not_required', basis: string) => void
}) {
  const [mode, setMode] = useState<'confirmed' | 'not_required' | null>(null)
  const [basis, setBasis] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const save = async () => {
    if (!mode) return
    setBusy(true)
    setErr('')
    try {
      const r = await api.decide(i.id, mode, basis.trim())
      onDecided(i.id, r.status, mode, basis.trim())
      setMode(null)
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <tr className="opsx-row-static">
      <td><a className="opsx-cell-link" href={companyHref(basePath, i.company_id)}>{i.company}</a></td>
      <td className="opsx-mono">{i.bin}</td>
      <td>{i.regime}</td>
      <td>{i.vat}</td>
      <td className="opsx-nowrap"><b>{i.form}</b></td>
      <td className="opsx-nowrap">{i.period}</td>
      <td className="opsx-nowrap">{i.due_date}</td>
      <td>
        <span className={`opsx-st opsx-st-${i.status}`}>{PLAN_STATUS_LABEL[i.status] || i.status}</span>
        {i.decision && (
          <div className="opsx-sub" title={i.decision_basis || ''}>
            решено: {i.decision === 'confirmed' ? 'ожидается' : 'не требуется'} — {i.decision_basis}
            <div>предложение для карточки создано</div>
          </div>
        )}
      </td>
      <td className="opsx-wide">
        {i.clarify_reason}
        {i.status === 'clarify' && !i.decision && (
          mode ? (
            <div className="opsx-decide">
              <div className="opsx-sub">{mode === 'confirmed' ? 'Подтвердить: ожидается' : 'Не требуется'} — основание:</div>
              <textarea className="opsx-input opsx-textarea" rows={2} autoFocus value={basis}
                placeholder="Например: КГД 20.11.2026 — плательщик НДС" onChange={(e) => setBasis(e.target.value)} />
              {err && <div className="opsx-warn-text">{err}</div>}
              <div className="opsx-actions">
                <button className="opsx-btn opsx-btn-primary opsx-btn-sm" disabled={busy || basis.trim().length < 3} onClick={save}>
                  {busy ? 'Сохраняем…' : 'Сохранить'}
                </button>
                <button className="opsx-btn opsx-btn-sm" disabled={busy} onClick={() => { setMode(null); setErr('') }}>Отмена</button>
              </div>
            </div>
          ) : (
            <div className="opsx-actions opsx-decide-btns">
              <button className="opsx-btn opsx-btn-sm" onClick={() => setMode('confirmed')}>Подтвердить: ожидается</button>
              <button className="opsx-btn opsx-btn-sm" onClick={() => setMode('not_required')}>Не требуется</button>
            </div>
          )
        )}
      </td>
      <td className="opsx-wide">{i.basis}</td>
      <td>{i.info_source}</td>
    </tr>
  )
}

function DiscrepanciesTab({ api, basePath }: { api: Api; basePath: string }) {
  const [data, setData] = useState<{ file: string | null; items: Discrepancy[] } | null>(null)
  const [ids, setIds] = useState<Record<string, number>>({})
  const [error, setError] = useState('')
  useEffect(() => {
    api.discrepancies().then(setData).catch((e) => setError(e.message))
    api.companies().then((cs) => setIds(Object.fromEntries(cs.map((c) => [c.slug, c.id])))).catch(() => {})
  }, [])
  if (error) return <div className="opsx-alert opsx-alert-err">{error}</div>
  if (!data) return <div className="opsx-muted">Загрузка…</div>
  return (
    <div>
      <div className="opsx-muted opsx-mb">
        {data.file ? <>Расхождения реестра владельца с карточками и календарём — <span className="opsx-mono">{data.file}</span>, {data.items.length} строк.</> : 'Файл расхождений в allkey-ops не найден.'}
      </div>
      {data.items.length > 0 && (
        <div className="opsx-table-wrap">
          <table className="opsx-table opsx-table-compact">
            <thead><tr><th>#</th><th>Компания</th><th>Расхождение</th><th>Источник</th></tr></thead>
            <tbody>
              {data.items.map((d, n) => (
                <tr key={n} className="opsx-row-static">
                  <td className="opsx-muted">{n + 1}</td>
                  <td>{ids[d.company_slug] ? <a className="opsx-cell-link" href={companyHref(basePath, ids[d.company_slug])}>{d.company}</a> : d.company}</td>
                  <td>{d.discrepancy}</td>
                  <td className="opsx-muted">{d.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
