import { useEffect, useMemo, useState } from 'react'
import { Api, CompanyRow, REGIME, Status, SyncResult } from './api'

// Поиск — только на клиенте: названия не уходят в URL и в access-логи сервера.
function norm(s: string) {
  return s.toLowerCase().replace(/ё/g, 'е').replace(/[«»"'“”]/g, '').replace(/\s+/g, ' ').trim()
}

export default function CompaniesList({ api, onOpen, onImport }: { api: Api; onOpen: (id: number) => void; onImport: () => void }) {
  const [items, setItems] = useState<CompanyRow[] | null>(null)
  const [status, setStatus] = useState<Status | null>(null)
  const [q, setQ] = useState('')
  // Живые и архив — отдельными вкладками; вкладка в URL (?tab=archive), без названий компаний.
  const [tab, setTabState] = useState<'active' | 'archive'>(
    () => (new URLSearchParams(window.location.search).get('tab') === 'archive' ? 'archive' : 'active'))
  const setTab = (t: 'active' | 'archive') => {
    const u = new URL(window.location.href)
    if (t === 'archive') u.searchParams.set('tab', 'archive')
    else u.searchParams.delete('tab')
    window.history.replaceState(null, '', u.pathname + u.search)
    setTabState(t)
  }
  const [onlySuspected, setOnlySuspected] = useState(false)
  const [error, setError] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [sync, setSync] = useState<SyncResult | null>(null)

  const load = () => {
    setError('')
    Promise.all([api.companies(), api.status()])
      .then(([c, s]) => { setItems(c); setStatus(s) })
      .catch((e) => setError(e.message))
  }
  useEffect(load, [])

  const runSync = async () => {
    setSyncing(true)
    setSync(null)
    try {
      const r = await api.sync()
      setSync(r)
      if (r.ok) load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSyncing(false)
    }
  }

  const filtered = useMemo(() => {
    if (!items) return []
    const nq = norm(q)
    return items.filter((c) => {
      if (tab === 'active' ? !c.active : c.active) return false
      if (onlySuspected && !c.suspected_count) return false
      if (!nq) return true
      // name — основной ключ; legal_name, прежние имена папок (aliases) и БИН — чтобы находилось и по ним.
      const hay = [c.name, c.legal_name || '', c.bin || '', ...c.aliases].map(norm)
      return hay.some((h) => h.includes(nq))
    })
  }, [items, q, tab, onlySuspected])

  const counts = useMemo(() => ({
    active: (items || []).filter((c) => c.active).length,
    archive: (items || []).filter((c) => !c.active).length,
  }), [items])

  return (
    <div>
      <div className="opsx-head">
        <div>
          <h1>Компании</h1>
          {status && (
            <div className="opsx-muted">
              Активных <b>{status.active}</b> · архивных <b>{status.inactive}</b> · всего {status.total}
              {status.last_synced_at && <> · синхронизировано {new Date(status.last_synced_at).toLocaleString('ru-RU')}</>}
            </div>
          )}
        </div>
        <div className="opsx-actions">
          <button className="opsx-btn" onClick={onImport}>Импорт отчётов</button>
          <button className="opsx-btn opsx-btn-primary" onClick={runSync} disabled={syncing}>
            {syncing ? 'Проверка и синхронизация…' : 'Синхронизировать'}
          </button>
        </div>
      </div>

      {sync && !sync.ok && (
        <div className="opsx-alert opsx-alert-err">
          <b>Синхронизация не выполнена.</b>
          {sync.error && <div>{sync.error}</div>}
          {!sync.validator_ok && (
            <>
              <div>Валидатор карточек нашёл ошибки — исправьте их в репозитории arty-ops и повторите:</div>
              <ul>{sync.validator_errors.map((e, i) => <li key={i}><code>{e}</code></li>)}</ul>
            </>
          )}
        </div>
      )}
      {sync && sync.ok && (
        <div className="opsx-alert opsx-alert-ok">
          Валидатор: ошибок нет. Синхронизировано {sync.total} карточек (активных {sync.active}, архивных {sync.inactive}):
          новых {sync.created}, изменено {sync.updated}, без изменений {sync.unchanged}
          {sync.missing_in_repo > 0 && <>, пропали из репозитория {sync.missing_in_repo}</>}.
        </div>
      )}
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
        <label className="opsx-check">
          <input type="checkbox" checked={onlySuspected} onChange={(e) => setOnlySuspected(e.target.checked)} />
          есть подозрения{items && <> ({items.filter((c) => c.suspected_count).length})</>}
        </label>
        {items && <span className="opsx-muted">Показано {filtered.length}</span>}
      </div>

      {!items && !error && <div className="opsx-muted">Загрузка…</div>}
      {items && items.length === 0 && (
        <div className="opsx-alert">Реестр пуст. Нажмите «Синхронизировать», чтобы загрузить карточки из arty-ops.</div>
      )}
      {items && items.length > 0 && (
        <div className="opsx-table-wrap">
          <table className="opsx-table">
            <thead>
              <tr>
                <th>Название</th>
                <th>БИН</th>
                <th>Режим</th>
                <th>НДС</th>
                <th>Ответственный</th>
                <th>Папка на Диске</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr key={c.id} onClick={() => onOpen(c.id)} className={c.active ? '' : 'opsx-row-off'}>
                  <td>
                    <div className="opsx-name">
                      {c.name}
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
                  <td>{c.vat_payer === true ? 'да' : c.vat_payer === false ? 'нет' : '—'}</td>
                  <td>{c.responsible || <span className="opsx-muted">—</span>}</td>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
