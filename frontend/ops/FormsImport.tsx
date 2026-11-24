import { useState } from 'react'
import { Api, FormsPreview } from './api'

// Импорт форм из xlsx в формате экспорта «Компании» (только admin, раздел «Служебное»).
// Шаг 1 — предпросмотр (ничего не пишет), шаг 2 — «Применить» (коммит в prod-decisions + журнал).
export default function FormsImport({ api }: { api: Api }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<FormsPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState<string>('')

  const runPreview = async () => {
    if (!file) return
    setBusy(true); setError(''); setDone(''); setPreview(null)
    try {
      setPreview(await api.formsImportPreview(file))
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const apply = async () => {
    if (!preview) return
    setBusy(true); setError('')
    try {
      const r = await api.formsImportApply(preview)
      setDone(r.companies_changed
        ? `Применено: карточек ${r.companies_changed}, форм добавлено ${r.forms_added}, убрано ${r.forms_removed}. Коммит ${r.commit} в prod-decisions.`
        : 'Изменений нет — карточки уже в таком состоянии.')
      setPreview(null)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const t = preview?.totals
  return (
    <div className="opsx-card">
      <div className="opsx-block-head">
        <h2>Импорт форм из xlsx</h2>
      </div>
      <div className="opsx-muted opsx-service-text">
        Файл в формате «Скачать xlsx» с экрана «Компании». Сопоставление по БИН. Меняются только колонки форм:
        «да» — форма добавляется в карточку, «нет» — убирается, пустая ячейка ничего не меняет.
        Режим и НДС из файла не записываются — расхождения показываются отдельно (спор решает КГД).
      </div>
      <div className="opsx-actions opsx-service-gap">
        <input type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files?.[0] || null); setPreview(null); setDone('') }} />
        <button className="opsx-btn" disabled={!file || busy} onClick={runPreview}>
          {busy && !preview ? 'Читаем…' : 'Предпросмотр'}
        </button>
      </div>
      {error && <div className="opsx-alert opsx-alert-err opsx-service-gap">{error}</div>}
      {done && <div className="opsx-alert opsx-alert-ok opsx-service-gap">{done}</div>}

      {preview && t && (
        <div className="opsx-service-gap">
          <div className="opsx-alert">
            Файл «{preview.file_name}»: строк {preview.companies_in_file}, найдено по БИН {preview.matched}.
            Изменится карточек <b>{t.companies_changed}</b>: форм добавится <b>{t.forms_added}</b>, уберётся <b>{t.forms_removed}</b>.
            {preview.unmatched.length > 0 && <> Без совпадения: {preview.unmatched.length}.</>}
            {preview.discrepancies.length > 0 && <> Расхождений режима/НДС: {preview.discrepancies.length}.</>}
          </div>

          {preview.changes.length > 0 && (
            <>
              <div className="opsx-h3">Что изменится</div>
              <div className="opsx-table-wrap">
                <table className="opsx-table opsx-table-compact">
                  <thead><tr><th>Компания</th><th>БИН</th><th>Добавится</th><th>Уберётся</th></tr></thead>
                  <tbody>
                    {preview.changes.map((c) => (
                      <tr key={c.company_id} className="opsx-row-static">
                        <td>{c.name}</td><td className="opsx-mono">{c.bin}</td>
                        <td>{c.add.join(', ') || '—'}</td><td>{c.remove.join(', ') || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {preview.discrepancies.length > 0 && (
            <>
              <div className="opsx-h3">Расхождения с карточкой (не записываются)</div>
              <div className="opsx-table-wrap">
                <table className="opsx-table opsx-table-compact">
                  <thead><tr><th>Компания</th><th>БИН</th><th>Поле</th><th>В файле</th><th>В карточке</th></tr></thead>
                  <tbody>
                    {preview.discrepancies.map((d, i) => (
                      <tr key={i} className="opsx-row-static">
                        <td>{d.company}</td><td className="opsx-mono">{d.bin}</td><td>{d.field}</td><td>{d.file}</td><td>{d.card}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {(preview.unmatched.length > 0 || preview.blocked.length > 0 || preview.warnings.length > 0) && (
            <div className="opsx-alert opsx-alert-warn opsx-service-gap">
              {preview.unmatched.length > 0 && (
                <div>
                  <b>Не найдены по БИН (не создаются):</b>
                  <ul>{preview.unmatched.map((u, i) => <li key={i}>строка {u.row}: {u.name || '—'} · {u.bin || 'без БИН'} — {u.reason}</li>)}</ul>
                </div>
              )}
              {preview.blocked.length > 0 && (
                <div>
                  <b>Не убираются (форма по подтверждённому обязательству):</b>
                  <ul>{preview.blocked.map((b, i) => <li key={i}>{b.company} — {b.form}</li>)}</ul>
                </div>
              )}
              {preview.warnings.length > 0 && (
                <div><b>Пропущенные ячейки:</b><ul>{preview.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></div>
              )}
            </div>
          )}

          <div className="opsx-actions opsx-service-gap">
            <button className="opsx-btn opsx-btn-primary" disabled={busy || t.companies_changed === 0} onClick={apply}>
              {busy ? 'Применяем…' : `Применить (${t.companies_changed})`}
            </button>
            <button className="opsx-btn" disabled={busy} onClick={() => setPreview(null)}>Отмена</button>
          </div>
        </div>
      )}
    </div>
  )
}
