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
  const [onlyActive, setOnlyActive] = useState(true)
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
      if (onlyActive && !c.active) return false
      if (!nq) return true
      const hay = [c.name, c.folder_name || '', c.bin || '', ...c.aliases].map(norm)
      return hay.some((h) => h.includes(nq))
    })
  }, [items, q, onlyActive])

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

      <div className="opsx-filters">
        <input
          className="opsx-input"
          placeholder="Поиск по названию, алиасам, папке, БИН"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <label className="opsx-check">
          <input type="checkbox" checked={onlyActive} onChange={(e) => setOnlyActive(e.target.checked)} />
          только активные
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
                <th>Активна</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr key={c.id} onClick={() => onOpen(c.id)} className={c.active ? '' : 'opsx-row-off'}>
                  <td>
                    <div className="opsx-name">{c.name}</div>
                    {!c.name_official && <div className="opsx-sub">официальное название не заполнено · {c.slug}</div>}
                    {c.aliases.length > 0 && <div className="opsx-sub">{c.aliases.join(' · ')}</div>}
                  </td>
                  <td className="opsx-mono">{c.bin || '—'}</td>
                  <td>{c.tax_regime ? REGIME[c.tax_regime] || c.tax_regime : '—'}</td>
                  <td>{c.vat_payer === true ? 'да' : c.vat_payer === false ? 'нет' : '—'}</td>
                  <td>{c.responsible || <span className="opsx-muted">—</span>}</td>
                  <td>
                    {c.active ? <span className="opsx-pill opsx-pill-on">активна</span> : <span className="opsx-pill">архив</span>}
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
