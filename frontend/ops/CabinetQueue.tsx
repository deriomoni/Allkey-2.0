import { useEffect, useState } from 'react'
import { Api, CabinetQueueEntry } from './api'
import { fmtDateTime } from './CardParts'

// «Служебное»: очередь на вход в кабинет налогоплательщика (ops_cabinet_queue). Ставят из карточки
// («Поставить в очередь на вход») или CLI; knp-watch после прогона по компании снимает запись сам.
export default function CabinetQueue({ api }: { api: Api }) {
  const [items, setItems] = useState<CabinetQueueEntry[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<number | null>(null)

  const load = () => api.cabinetQueue().then(setItems).catch((e) => setError(e.message))
  useEffect(() => { load() }, [])

  const done = async (e: CabinetQueueEntry) => {
    setBusy(e.id); setError('')
    try {
      await api.cabinetQueueDone(e.id, 'снято вручную')
      await load()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="opsx-card">
      <div className="opsx-block-head">
        <h2>Очередь: кабинет налогоплательщика</h2>
        {items && <span className="opsx-muted">в очереди {items.length}</span>}
      </div>
      <div className="opsx-muted opsx-service-text">
        Компании, по которым нужно войти в кабинет (knp-watch). Поставить — кнопкой в карточке компании; после прогона knp-watch снимает запись сам.
      </div>
      {error && <div className="opsx-alert opsx-alert-err opsx-service-gap">{error}</div>}
      {items && items.length > 0 && (
        <div className="opsx-table-wrap opsx-service-gap">
          <table className="opsx-table opsx-table-compact">
            <thead><tr><th>Компания</th><th>БИН</th><th>Почему</th><th>Поставлена</th><th>Последняя проверка</th><th></th></tr></thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id}>
                  <td>{e.name}{e.note && <div className="opsx-muted">{e.note}</div>}</td>
                  <td className="opsx-mono">{e.bin || '—'}</td>
                  <td>{e.reason_label}</td>
                  <td>{fmtDateTime(e.requested_at)}{e.requested_by && <div className="opsx-muted">{e.requested_by}</div>}</td>
                  <td>
                    {e.checked_at ? fmtDateTime(e.checked_at) : <span className="opsx-muted">не было</span>}
                    {e.taken_at && <div className="opsx-sub">в работе с {fmtDateTime(e.taken_at)}</div>}
                  </td>
                  <td><button className="opsx-link opsx-link-inline" disabled={busy === e.id} onClick={() => done(e)}>снять</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
