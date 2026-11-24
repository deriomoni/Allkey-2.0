import { useEffect, useState } from 'react'
import { Api, Status, SyncResult } from './api'
import ReportsImport from './ReportsImport'
import FormsImport from './FormsImport'

// Раздел «Служебное» (/x/ops-service, только admin модуля): синхронизация карточек из allkey-ops
// и импорт файла отчётов. С экрана «Компании» эти кнопки убраны.
export default function ServiceScreen({ api, basePath }: { api: Api; basePath: string }) {
  const [view, setView] = useState<'main' | 'import'>(
    () => (new URLSearchParams(window.location.search).get('view') === 'import' ? 'import' : 'main'))
  const [status, setStatus] = useState<Status | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [sync, setSync] = useState<SyncResult | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const onPop = () => setView(new URLSearchParams(window.location.search).get('view') === 'import' ? 'import' : 'main')
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
  const go = (v: 'main' | 'import') => {
    window.history.pushState(null, '', basePath + (v === 'import' ? '?view=import' : ''))
    setView(v)
    window.scrollTo(0, 0)
  }

  const loadStatus = () => api.status().then(setStatus).catch((e) => setError(e.message))
  useEffect(() => { loadStatus() }, [])

  const runSync = async () => {
    setSyncing(true)
    setSync(null)
    setError('')
    try {
      const r = await api.sync()
      setSync(r)
      if (r.ok) loadStatus()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSyncing(false)
    }
  }

  if (view === 'import') return <ReportsImport api={api} onBack={() => go('main')} />

  return (
    <div>
      <div className="opsx-head">
        <div>
          <h1>Служебное</h1>
          <div className="opsx-muted">Загрузка данных реестра компаний. Только для администратора.</div>
        </div>
      </div>
      {error && <div className="opsx-alert opsx-alert-err">{error}</div>}

      <div className="opsx-card">
        <div className="opsx-block-head">
          <h2>Синхронизация карточек</h2>
          <button className="opsx-btn opsx-btn-primary" onClick={runSync} disabled={syncing}>
            {syncing ? 'Проверка и синхронизация…' : 'Синхронизировать'}
          </button>
        </div>
        <div className="opsx-muted opsx-service-text">
          Читает карточки <span className="opsx-mono">clients/*/client.yaml</span> из клона allkey-ops: сначала валидатор, затем обновление реестра.
          {status && (
            <div>
              Сейчас: активных {status.active}, архивных {status.inactive}, всего {status.total}
              {status.hidden !== undefined && <>, скрытых {status.hidden}</>}
              {status.last_synced_at && <> · синхронизировано {new Date(status.last_synced_at).toLocaleString('ru-RU')}</>}
              {!status.repo_configured && <> · <b>путь к allkey-ops (ARTY_OPS_PATH) не задан</b></>}
            </div>
          )}
        </div>
        {sync && !sync.ok && (
          <div className="opsx-alert opsx-alert-err opsx-service-gap">
            <b>Синхронизация не выполнена.</b>
            {sync.error && <div>{sync.error}</div>}
            {!sync.validator_ok && (
              <>
                <div>Валидатор карточек нашёл ошибки — исправьте их в репозитории allkey-ops и повторите:</div>
                <ul>{sync.validator_errors.map((e, i) => <li key={i}><code>{e}</code></li>)}</ul>
              </>
            )}
          </div>
        )}
        {sync && sync.ok && (
          <div className="opsx-alert opsx-alert-ok opsx-service-gap">
            Валидатор: ошибок нет. Синхронизировано {sync.total} карточек (активных {sync.active}, архивных {sync.inactive}):
            новых {sync.created}, изменено {sync.updated}, без изменений {sync.unchanged}
            {sync.missing_in_repo > 0 && <>, пропали из репозитория {sync.missing_in_repo}</>}.
          </div>
        )}
      </div>

      <div className="opsx-card">
        <div className="opsx-block-head">
          <h2>Импорт отчётов</h2>
          <button className="opsx-btn" onClick={() => go('import')}>Импорт отчётов</button>
        </div>
        <div className="opsx-muted opsx-service-text">
          Загрузка xlsx-реестра статусов форм (лист на форму): предпросмотр сопоставления с компаниями → подтверждение.
        </div>
      </div>
      <FormsImport api={api} />
    </div>
  )
}
