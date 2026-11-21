import { useMemo, useState } from 'react'
import { Api, MATCH_BY, Preview, PreviewRow, REPORT_STATUS } from './api'

// Шаги: загрузка xlsx → предпросмотр «строка → карточка» → ручная привязка
// несопоставленных → подтверждение → запись (source=import_xlsx).
export default function ReportsImport({ api, onBack }: { api: Api; onBack: () => void }) {
  const [preview, setPreview] = useState<Preview | null>(null)
  const [binding, setBinding] = useState<Record<string, number>>({})
  const [skip, setSkip] = useState<Record<string, boolean>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState<{ created: number; updated: number; skipped: number } | null>(null)

  const onFile = async (f: File | undefined) => {
    if (!f) return
    setBusy(true); setError(''); setPreview(null); setDone(null); setBinding({}); setSkip({})
    try {
      setPreview(await api.importPreview(f))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const target = (r: PreviewRow) => binding[r.row_id] ?? r.match?.company_id
  const matched = useMemo(() => preview?.rows.filter((r) => r.match) || [], [preview])
  const unmatched = useMemo(() => preview?.rows.filter((r) => !r.match) || [], [preview])
  const toWrite = useMemo(
    () => (preview?.rows || []).filter((r) => !skip[r.row_id] && target(r) && r.cells.length > 0),
    [preview, binding, skip],
  )
  const cellsCount = toWrite.reduce((n, r) => n + r.cells.length, 0)

  const commit = async () => {
    setBusy(true); setError('')
    try {
      const res = await api.importCommit(toWrite.map((r) => ({ company_id: target(r)!, form: r.form, cells: r.cells })))
      setDone(res)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const companySelect = (r: PreviewRow) => (
    <select
      className="opsx-input opsx-select"
      value={binding[r.row_id] ?? ''}
      onChange={(e) => setBinding({ ...binding, [r.row_id]: Number(e.target.value) || (undefined as any) })}
    >
      <option value="">— не привязано —</option>
      {r.candidates.length > 0 && (
        <optgroup label="Похожие">
          {r.candidates.map((c) => <option key={c.company_id} value={c.company_id}>{c.name}</option>)}
        </optgroup>
      )}
      <optgroup label="Все компании">
        {preview!.companies.map((c) => <option key={c.id} value={c.id}>{c.name}{c.active ? '' : ' (архив)'}</option>)}
      </optgroup>
    </select>
  )

  const cellsView = (r: PreviewRow) => (
    <div className="opsx-cells">
      {r.cells.length === 0 && <span className="opsx-muted">пустая строка</span>}
      {r.cells.map((c) => (
        <span key={c.period} className={`opsx-st opsx-st-${c.status}`} title={c.raw}>
          {c.period}: {REPORT_STATUS[c.status]}
        </span>
      ))}
    </div>
  )

  return (
    <div>
      <button className="opsx-link" onClick={onBack}>← К списку компаний</button>
      <h1>Импорт статусов отчётности</h1>
      <div className="opsx-muted opsx-mb">
        Файл xlsx: каждый лист — форма (имя листа, напр. «300.00»), колонка «Наименование компании», остальные колонки — периоды.
        Файл на сервере не сохраняется.
      </div>

      <div className="opsx-card">
        <input type="file" accept=".xlsx" disabled={busy} onChange={(e) => onFile(e.target.files?.[0])} />
        {busy && !preview && <span className="opsx-muted"> Разбор файла…</span>}
      </div>

      {error && <div className="opsx-alert opsx-alert-err">{error}</div>}
      {done && (
        <div className="opsx-alert opsx-alert-ok">
          Записано: новых {done.created}, обновлено {done.updated}{done.skipped ? `, пропущено ${done.skipped}` : ''}.
        </div>
      )}

      {preview && !done && (
        <>
          <div className="opsx-card">
            <h2>Листы</h2>
            {preview.sheets.map((s) => (
              <div key={s.form}><b className="opsx-mono">{s.form}</b> — строк {s.rows}, периоды: {s.periods.join(', ')}</div>
            ))}
            {preview.warnings.map((w, i) => <div key={i} className="opsx-warn-text">{w}</div>)}
          </div>

          {unmatched.length > 0 && (
            <div className="opsx-card">
              <h2>Не сопоставлены — привяжите вручную ({unmatched.length})</h2>
              <table className="opsx-table opsx-table-compact">
                <thead><tr><th>Лист</th><th>Строка в файле</th><th>Компания</th><th>Статусы</th></tr></thead>
                <tbody>
                  {unmatched.map((r) => (
                    <tr key={r.row_id} className="opsx-row-static">
                      <td className="opsx-mono">{r.form}</td>
                      <td>{r.company_text} <span className="opsx-muted">#{r.row_number}</span></td>
                      <td>{companySelect(r)}</td>
                      <td>{cellsView(r)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="opsx-card">
            <h2>Сопоставлены ({matched.length})</h2>
            <table className="opsx-table opsx-table-compact">
              <thead><tr><th></th><th>Лист</th><th>Строка в файле</th><th>→ Карточка</th><th>Статусы</th></tr></thead>
              <tbody>
                {matched.map((r) => (
                  <tr key={r.row_id} className="opsx-row-static">
                    <td><input type="checkbox" checked={!skip[r.row_id]} onChange={(e) => setSkip({ ...skip, [r.row_id]: !e.target.checked })} /></td>
                    <td className="opsx-mono">{r.form}</td>
                    <td>{r.company_text}</td>
                    <td>{r.match!.name} <span className="opsx-muted">({MATCH_BY[r.match!.by] || r.match!.by})</span></td>
                    <td>{cellsView(r)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="opsx-actions opsx-sticky">
            <span className="opsx-muted">К записи: строк {toWrite.length}, ячеек {cellsCount}</span>
            <button className="opsx-btn opsx-btn-primary" disabled={busy || toWrite.length === 0} onClick={commit}>
              Подтвердить и записать
            </button>
          </div>
        </>
      )}
    </div>
  )
}
