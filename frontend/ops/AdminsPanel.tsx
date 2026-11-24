import { useEffect, useState } from 'react'
import { AdminsInfo, Api } from './api'

const SOURCE: Record<string, string> = {
  env: 'из .env (OPS_ADMIN_USER_ID)',
  cli: 'выдана явно (grant-admin)',
}

// Блок для страницы «Настройки»: кто сейчас имеет доступ к реестру компаний.
// Только чтение — выдача и снятие роли делаются на сервере (CLI), не из браузера.
export default function AdminsPanel({ api }: { api: Api }) {
  const [info, setInfo] = useState<AdminsInfo | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.admins().then(setInfo).catch((e) => setError(e.message))
  }, [])

  return (
    <section className="opsx-card">
      <h2>Доступ к реестру компаний — роль admin модуля «Операции»</h2>
      {error && <div className="opsx-alert opsx-alert-err">{error}</div>}
      {!info && !error && <div className="opsx-muted">Загрузка…</div>}
      {info && (
        <>
          <table className="opsx-table opsx-table-compact">
            <thead>
              <tr><th>id</th><th>Пользователь</th><th>Email</th><th>Источник роли</th><th>С</th></tr>
            </thead>
            <tbody>
              {info.items.map((a) => (
                <tr key={a.user_id} className="opsx-row-static">
                  <td className="opsx-mono">{a.user_id}</td>
                  <td>
                    {a.full_name || '—'}
                    {!a.is_active && <span className="opsx-pill opsx-pill-warn">деактивирован</span>}
                  </td>
                  <td>{a.email || '—'}</td>
                  <td>
                    {SOURCE[a.granted_by || ''] || a.granted_by || '—'}
                    {a.is_env_admin && a.granted_by !== 'env' && <span className="opsx-muted"> · он же OPS_ADMIN_USER_ID</span>}
                  </td>
                  <td>{a.granted_at ? new Date(a.granted_at).toLocaleString('ru-RU') : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h2 className="opsx-h2-gap">Роль «сотрудник» — экран «Компании» без служебных функций</h2>
          {info.staff.length === 0 ? (
            <div className="opsx-muted">Никому не выдана.</div>
          ) : (
            <table className="opsx-table opsx-table-compact">
              <thead><tr><th>id</th><th>Пользователь</th><th>Email</th><th>С</th></tr></thead>
              <tbody>
                {info.staff.map((a) => (
                  <tr key={a.user_id} className="opsx-row-static">
                    <td className="opsx-mono">{a.user_id}</td>
                    <td>{a.full_name || '—'}{!a.is_active && <span className="opsx-pill opsx-pill-warn">деактивирован</span>}</td>
                    <td>{a.email || '—'}</td>
                    <td>{a.granted_at ? new Date(a.granted_at).toLocaleString('ru-RU') : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="opsx-muted" style={{ marginTop: 10 }}>
            Доступ даёт только роль: глобального флага видимости нет. Сотрудник:{' '}
            <code>python -m app.operations.cli grant-staff --email …</code> / <code>revoke-staff --email …</code>.
            Роль admin из .env снимается автоматически при смене OPS_ADMIN_USER_ID; явную снимает только{' '}
            <code>python -m app.operations.cli revoke-admin --user-id N</code>.
          </div>
        </>
      )}
    </section>
  )
}
