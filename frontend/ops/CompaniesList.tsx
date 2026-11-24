import { useEffect, useMemo, useState } from 'react'
import { Api, CompanyRow, REGIME, Status } from './api'
import { ColumnFilter, Facet, FacetSelection, matchesFacets, readSelection, writeSelection } from './ColumnFilter'

// Поиск — только на клиенте: названия не уходят в URL и в access-логи сервера.
function norm(s: string) {
  return s.toLowerCase().replace(/ё/g, 'е').replace(/[«»"'“”]/g, '').replace(/\s+/g, ' ').trim()
}

// Ключевые формы — первыми в фильтре «Формы» (и отдельными колонками в экспорте).
const KEY_FORMS = ['300.00', '200.00', '101.04', '220.00', '100.00', '910.00', '700.00']

// Фильтры по столбцам. «Статус КГД» — добавить сюда записью, когда появится столбец.
function makeFacets(items: CompanyRow[]): Facet<CompanyRow>[] {
  const all = new Set<string>()
  for (const c of items) for (const f of c.forms || []) all.add(f)
  const forms = [...KEY_FORMS.filter((f) => all.has(f)), ...[...all].filter((f) => !KEY_FORMS.includes(f)).sort()]
  return [
    {
      key: 'regime', label: 'Режим',
      value: (c) => c.tax_regime || 'none',
      labels: { general: REGIME.general, simplified: REGIME.simplified, retail: REGIME.retail, none: 'не установлен' },
    },
    {
      key: 'vat', label: 'НДС',
      value: (c) => (c.vat_payer === true ? 'yes' : c.vat_payer === false ? 'no' : 'none'),
      labels: { yes: 'да', no: 'нет', none: 'не установлен' },
    },
    {
      key: 'forms', label: 'Формы',
      value: (c) => [...(c.forms?.length ? c.forms : ['none']), ...(c.plan_missing ? ['noplan'] : [])],
      labels: { ...Object.fromEntries(forms.map((f) => [f, f])), none: 'нет форм', noplan: 'план не рассчитан' },
    },
  ]
}
const FACET_KEYS = makeFacets([])

function fmtDate(iso: string | null) {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-')
  return d && m && y ? `${d}.${m}.${y}` : iso
}

// Синхронизация карточек и импорт — в разделе «Служебное» (/x/ops-service, только admin).
// Сотрудник (staff) видит список, фильтры, ссылку на Диск, экспорт и карточку; без «скрытой» и подозрений в списке.
export default function CompaniesList({ api, onOpen }: { api: Api; onOpen: (id: number) => void }) {
  const [items, setItems] = useState<CompanyRow[] | null>(null)
  const [status, setStatus] = useState<Status | null>(null)
  const [role, setRole] = useState<'admin' | 'staff' | null>(null)
  const isAdmin = role === 'admin'
  const [q, setQ] = useState('')
  // Живые и архив — отдельными вкладками; вкладка в URL (?tab=archive), без названий компаний.
  const [tab, setTabState] = useState<'active' | 'archive'>(
    () => (new URLSearchParams(window.location.search).get('tab') === 'archive' ? 'archive' : 'active'))
  const setTab = (t: 'active' | 'archive') => {
    const u = new URL(window.location.href)
    if (t === 'archive') u.searchParams.set('tab', 'archive')
    else u.searchParams.delete('tab')
    window.history.replaceState(null, '', u.pathname + u.search.replace(/%2C/gi, ','))
    setTabState(t)
  }
  const [onlySuspected, setOnlySuspected] = useState(false)
  // ТЗ 1.1 п. 9: скрытые компании видит только admin; в списке — по фильтру, по умолчанию выключен.
  const [showHidden, setShowHidden] = useState(false)
  const [facetSel, setFacetSel] = useState<FacetSelection>(() => readSelection(FACET_KEYS))
  const [busyId, setBusyId] = useState<number | null>(null)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState('')

  const load = () => {
    setError('')
    Promise.all([api.companies(), api.status(), api.me()])
      .then(([c, s, m]) => { setItems(c); setStatus(s); setRole(m.role) })
      .catch((e) => setError(e.message))
  }
  useEffect(load, [])

  const facets = useMemo(() => makeFacets(items || []), [items])
  const setFacet = (key: string, next: Set<string>) => {
    const sel = { ...facetSel, [key]: next }
    writeSelection(facets, sel)
    setFacetSel(sel)
  }
  const anyFacet = facets.some((f) => facetSel[f.key]?.size)

  const toggleHidden = async (c: CompanyRow) => {
    setBusyId(c.id)
    setError('')
    try {
      const r = await api.setHidden(c.id, !c.hidden)
      setItems((xs) => xs && xs.map((x) => (x.id === c.id ? { ...x, hidden: r.hidden } : x)))
      api.status().then(setStatus).catch(() => {})
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusyId(null)
    }
  }

  const base = useMemo(() => (items || []).filter((c) => showHidden || !c.hidden), [items, showHidden])
  const hiddenCount = useMemo(() => (items || []).filter((c) => c.hidden).length, [items])

  // Все фильтры, кроме фильтров по столбцам: вкладка, подозрения, поиск.
  const prefiltered = useMemo(() => {
    const nq = norm(q)
    return base.filter((c) => {
      if (tab === 'active' ? !c.active : c.active) return false
      if (onlySuspected && !c.suspected_count) return false
      if (!nq) return true
      // name — основной ключ; legal_name, прежние имена папок (aliases) и БИН — чтобы находилось и по ним.
      const hay = [c.name, c.legal_name || '', c.bin || '', ...c.aliases].map(norm)
      return hay.some((h) => h.includes(nq))
    })
  }, [base, q, tab, onlySuspected])

  const filtered = useMemo(() => prefiltered.filter((c) => matchesFacets(c, facets, facetSel)), [prefiltered, facets, facetSel])

  const counts = useMemo(() => ({
    active: base.filter((c) => c.active).length,
    archive: base.filter((c) => !c.active).length,
  }), [base])

  // Экспорт — ровно текущий отфильтрованный список, в порядке экрана (id — в теле запроса, не в адресе).
  const doExport = async () => {
    setExporting(true)
    setError('')
    try {
      await api.exportCompanies(filtered.map((c) => c.id))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setExporting(false)
    }
  }

  const cols = isAdmin ? 7 : 6
  return (
    <div>
      <div className="opsx-head">
        <div>
          <h1>Компании</h1>
          {status && (
            <div className="opsx-muted">
              Активных <b>{status.active}</b> · архивных <b>{status.inactive}</b> · всего {status.total}
              {status.hidden !== undefined && <> · из них скрытых {status.hidden}</>}
              {status.last_synced_at && <> · синхронизировано {new Date(status.last_synced_at).toLocaleString('ru-RU')}</>}
            </div>
          )}
        </div>
        <div className="opsx-actions">
          <button className="opsx-btn" onClick={doExport} disabled={!items || exporting || filtered.length === 0}
            title="Выгрузить текущий отфильтрованный список">
            {exporting ? 'Готовим…' : `Скачать xlsx${items ? ` (${filtered.length})` : ''}`}
          </button>
        </div>
      </div>

      {error && <div className="opsx-alert opsx-alert-err">{error}</div>}

      <div className="opsx-tabs">
        <button className={`opsx-tab ${tab === 'active' ? 'opsx-tab-on' : ''}`} onClick={() => setTab('active')}>
          Живые{items && <> ({counts.active})</>}
        </button>
        <button className={`opsx-tab ${tab === 'archive' ? 'opsx-tab-on' : ''}`} onClick={() => setTab('archive')}>
          Архив{items && <> ({counts.archive})</>}
        </button>
      </div>

      <div className="opsx-filters">
        <input
          className="opsx-input"
          placeholder="Поиск по названию, прежнему имени папки, БИН"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        {isAdmin && (
          <>
            <label className="opsx-check">
              <input type="checkbox" checked={onlySuspected} onChange={(e) => setOnlySuspected(e.target.checked)} />
              есть подозрения{items && <> ({base.filter((c) => c.suspected_count).length})</>}
            </label>
            <label className="opsx-check" title="Скрытые компании видит только администратор">
              <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} />
              показать скрытые{items && <> ({hiddenCount})</>}
            </label>
          </>
        )}
        {items && <span className="opsx-muted">Показано {filtered.length}</span>}
      </div>

      <div className="opsx-filters opsx-facets">
        {facets.map((f) => (
          <ColumnFilter
            key={f.key}
            facet={f}
            // счётчики — по строкам, прошедшим все остальные фильтры, кроме этого столбца
            rows={prefiltered.filter((c) => matchesFacets(c, facets, facetSel, f.key))}
            selected={facetSel[f.key] || new Set()}
            onChange={(next) => setFacet(f.key, next)}
          />
        ))}
        {anyFacet && (
          <button type="button" className="opsx-link opsx-link-inline" onClick={() => {
            const sel = Object.fromEntries(facets.map((f) => [f.key, new Set<string>()]))
            writeSelection(facets, sel)
            setFacetSel(sel)
          }}>Сбросить фильтры</button>
        )}
      </div>

      {!items && !error && <div className="opsx-muted">Загрузка…</div>}
      {items && items.length === 0 && (
        <div className="opsx-alert">Реестр пуст.{isAdmin && <> Загрузите карточки в разделе «Служебное» → «Синхронизировать».</>}</div>
      )}
      {items && items.length > 0 && (
        <div className="opsx-table-wrap">
          <table className="opsx-table">
            <thead>
              <tr>
                <th>Название</th>
                <th>БИН</th>
                <th>Режим{facetSel.regime?.size ? ' •' : ''}</th>
                <th>НДС{facetSel.vat?.size ? ' •' : ''}</th>
                <th>Формы{facetSel.forms?.size ? ' •' : ''}</th>
                <th>Папка на Диске</th>
                {isAdmin && <th>Скрытая</th>}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr className="opsx-row-static"><td colSpan={cols} className="opsx-muted">Нет компаний под выбранные фильтры.</td></tr>
              )}
              {filtered.map((c) => (
                <tr key={c.id} onClick={() => onOpen(c.id)}
                  className={[c.active ? '' : 'opsx-row-off', c.hidden ? 'opsx-row-hidden' : ''].join(' ')}>
                  <td>
                    <div className="opsx-name">
                      {c.name}
                      {c.hidden && <span className="opsx-pill opsx-pill-hidden">скрытая</span>}
                      {!!c.suspected_count && (
                        <span className="opsx-pill opsx-pill-susp" title="Подозрения на обязательство по сдаче формы">
                          {c.suspected_count} подозр.
                        </span>
                      )}
                    </div>
                    {!c.name_official && <div className="opsx-sub">официальное название не заполнено · {c.slug}</div>}
                    {c.aliases.length > 0 && <div className="opsx-sub">{c.aliases.join(' · ')}</div>}
                  </td>
                  <td className="opsx-mono">{c.bin || '—'}</td>
                  <td>{c.tax_regime ? REGIME[c.tax_regime] || c.tax_regime : '—'}</td>
                  <td>
                    {c.vat_payer === true ? 'да' : c.vat_payer === false ? 'нет' : '—'}
                    {c.vat_payer === true && c.vat_date && <div className="opsx-sub">с {fmtDate(c.vat_date)}</div>}
                  </td>
                  <td className="opsx-forms">
                    {c.forms?.length ? c.forms.join(', ') : (c.plan_missing ? null : <span className="opsx-muted">—</span>)}
                    {c.plan_missing && <div className="opsx-sub">план не рассчитан</div>}
                  </td>
                  <td>
                    {c.drive_url ? (
                      <a
                        className="opsx-drive-link"
                        href={c.drive_url}
                        target="_blank"
                        rel="noreferrer"
                        title={c.folder_name ? `Папка «${c.folder_name}» на Google Диске` : 'Папка на Google Диске'}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                        </svg>
                        Открыть ↗
                      </a>
                    ) : (
                      <span className="opsx-pill opsx-pill-warn">не привязана</span>
                    )}
                    {c.missing_in_repo && <span className="opsx-pill opsx-pill-warn">нет в репо</span>}
                  </td>
                  {isAdmin && (
                    <td onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={!!c.hidden}
                        aria-label={c.hidden ? 'Скрытая — открыть для сотрудников' : 'Сделать скрытой'}
                        title={c.hidden
                          ? 'Скрытая: видит только администратор. Нажмите, чтобы открыть (правка карточки коммитом)'
                          : 'Сделать скрытой: сотрудники не увидят компанию нигде (правка карточки коммитом)'}
                        className={`opsx-switch ${c.hidden ? 'opsx-switch-on' : ''}`}
                        disabled={busyId !== null}
                        onClick={() => toggleHidden(c)}
                      >
                        <span className="opsx-switch-knob" />
                      </button>
                      {busyId === c.id && <span className="opsx-muted opsx-switch-note">сохраняем…</span>}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
