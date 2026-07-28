import { useState } from 'react'
import FileUpload from '../components/FileUpload'
import { reconciliationApi, CurrencyResult } from '../api/client'

type Step = 'upload' | 'processing' | 'result'

const fmt = (n: number | null | undefined, d = 2) =>
  n == null ? '—' : n.toLocaleString('ru-RU', { minimumFractionDigits: d, maximumFractionDigits: d })

const STATUS: Record<string, { label: string; color: string; bg: string }> = {
  ok: { label: 'OK', color: '#16a34a', bg: '#dcfce7' },
  off: { label: 'Расхождение', color: '#dc2626', bg: '#fee2e2' },
  no_nb: { label: 'Нет курса НБ', color: '#b45309', bg: '#fef3c7' },
  no_rate: { label: 'Курс не определён', color: '#dc2626', bg: '#fee2e2' }, // ошибка — красный, как off
  no_val: { label: 'Нет валютной суммы', color: '#6b7280', bg: '#f1f5f9' }, // информационно — серый
}

const th: React.CSSProperties = { textAlign: 'left', padding: '8px 10px', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap', fontSize: 13 }
const td: React.CSSProperties = { padding: '6px 10px', borderBottom: '1px solid #f1f5f9', fontSize: 13 }
const num: React.CSSProperties = { ...td, textAlign: 'right', whiteSpace: 'nowrap' }

export default function CurrencyPage() {
  const [step, setStep] = useState<Step>('upload')
  const [cardFile, setCardFile] = useState<File | null>(null)
  const [nbFile, setNbFile] = useState<File | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [result, setResult] = useState<CurrencyResult | null>(null)
  const [error, setError] = useState('')

  const handleReconcile = async () => {
    if (!cardFile || !nbFile) return
    setError('')
    setStep('processing')
    try {
      const up = await reconciliationApi.uploadCurrency(cardFile, nbFile)
      setSessionId(up.session_id)
      const res = await reconciliationApi.processCurrency(up.session_id)
      setResult(res)
      setStep('result')
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Ошибка обработки файлов')
      setStep('upload')
    }
  }

  const handleDownload = () => {
    if (!sessionId) return
    const token = localStorage.getItem('token')
    fetch(reconciliationApi.downloadCurrency(sessionId), {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.blob())
      .then(blob => {
        const u = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = u
        a.download = `Сверка курсов ${sessionId.slice(0, 8)}.xlsx`
        a.click()
        window.URL.revokeObjectURL(u)
      })
  }

  const handleReset = () => {
    setStep('upload'); setCardFile(null); setNbFile(null)
    setSessionId(null); setResult(null); setError('')
  }

  const bc = result?.balance_check

  return (
    <div>
      <h1 style={{ marginBottom: 8 }}>Сверка курсов валют (USD 1С ↔ Нацбанк)</h1>
      <p style={{ color: '#6b7280', marginBottom: 24 }}>
        Карточка валютного счёта из 1С сверяется с курсами Нацбанка. Колонки определяются автоматически.
        Файл курсов НБ — по одной валюте (USD).
      </p>

      {error && <div className="error-message" style={{ marginBottom: 16 }}>{error}</div>}

      {step !== 'result' && (
        <div className="card">
          <div className="dashboard-cards" style={{ gap: 16 }}>
            <FileUpload label="Карточка счёта 1С (валютная)" onFileSelect={setCardFile} selectedFile={cardFile} />
            <FileUpload label="Курсы Нацбанка (USD)" onFileSelect={setNbFile} selectedFile={nbFile} />
          </div>
          <button
            className="btn btn-primary"
            style={{ marginTop: 20 }}
            disabled={!cardFile || !nbFile || step === 'processing'}
            onClick={handleReconcile}
          >
            {step === 'processing' ? 'Обработка…' : 'Сверить'}
          </button>
        </div>
      )}

      {step === 'result' && result && (
        <>
          <div className="dashboard-cards" style={{ marginBottom: 20 }}>
            <div className="card"><h3>Сопоставлено</h3><p style={{ fontSize: 28, fontWeight: 700 }}>{result.matched}</p></div>
            <div className="card"><h3>Расхождений</h3><p style={{ fontSize: 28, fontWeight: 700, color: result.off_rate ? '#dc2626' : '#16a34a' }}>{result.off_rate}</p></div>
            <div className="card"><h3>Курс не определён</h3><p style={{ fontSize: 28, fontWeight: 700, color: result.no_rate ? '#dc2626' : '#16a34a' }}>{result.no_rate}</p></div>
            <div className="card"><h3>Нет курса НБ</h3><p style={{ fontSize: 28, fontWeight: 700, color: result.no_nb ? '#b45309' : '#111827' }}>{result.no_nb}</p></div>
            <div className="card"><h3>Без валютной суммы</h3><p style={{ fontSize: 28, fontWeight: 700, color: '#6b7280' }}>{result.no_val}</p></div>
            <div className="card"><h3>Итого</h3><p style={{ fontSize: 15 }}>{fmt(result.total_usd)} USD<br />{fmt(result.total_kzt)} ₸</p></div>
          </div>

          <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
            <button className="btn btn-primary" onClick={handleDownload}>Скачать Excel</button>
            <button className="btn btn-secondary" onClick={handleReset}>Новая сверка</button>
          </div>

          {bc && (
            <div
              className="card"
              style={{ marginBottom: 20, borderLeft: `4px solid ${bc.mismatch ? '#dc2626' : '#16a34a'}` }}
            >
              <h3 style={{ marginBottom: 12 }}>
                Контроль сальдо на конец периода
                {bc.mismatch
                  ? <span style={{ color: '#dc2626', fontWeight: 700 }}> — расхождение</span>
                  : <span style={{ color: '#16a34a', fontWeight: 700 }}> — сходится</span>}
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '8px 24px', fontSize: 14 }}>
                <div><span style={{ color: '#6b7280' }}>Сальдо в валюте: </span>{fmt(bc.saldo_val)}</div>
                <div><span style={{ color: '#6b7280' }}>Сальдо в тенге: </span>{fmt(bc.saldo_kzt)} ₸</div>
                <div><span style={{ color: '#6b7280' }}>Курс НБ: </span>{fmt(bc.rate_nb, 4)}</div>
                <div><span style={{ color: '#6b7280' }}>Подразумеваемый курс: </span>{fmt(bc.implied_rate, 4)}</div>
                <div><span style={{ color: '#6b7280' }}>Ожидаемое сальдо ₸: </span>{fmt(bc.expected_kzt)} ₸</div>
                <div style={{ color: bc.mismatch ? '#dc2626' : undefined, fontWeight: bc.mismatch ? 600 : undefined }}>
                  <span style={{ color: '#6b7280', fontWeight: 400 }}>Разница: </span>{fmt(bc.diff)} ₸
                </div>
              </div>
            </div>
          )}

          <div className="card" style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead>
                <tr>
                  <th style={th}>Дата</th><th style={th}>Документ</th>
                  <th style={{ ...th, textAlign: 'right' }}>USD</th><th style={{ ...th, textAlign: 'right' }}>KZT</th>
                  <th style={{ ...th, textAlign: 'right' }}>Курс 1С</th><th style={{ ...th, textAlign: 'right' }}>Курс НБ</th>
                  <th style={{ ...th, textAlign: 'right' }}>Откл.</th>
                  <th style={{ ...th, textAlign: 'right' }}>Должно быть KZT</th>
                  <th style={{ ...th, textAlign: 'right' }}>Разница KZT</th>
                  <th style={th}>Статус</th>
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r, i) => {
                  const s = STATUS[r.status] || STATUS.ok
                  const isErr = r.status === 'no_rate'
                  return (
                    <tr key={i} style={isErr ? { background: '#fef2f2' } : undefined}>
                      <td style={td}>{r.date}</td>
                      <td style={td}>{r.description}</td>
                      <td style={num}>{fmt(r.usd)}</td>
                      <td style={num}>{fmt(r.kzt)}</td>
                      <td style={num}>{fmt(r.rate1c, 4)}</td>
                      <td style={num}>{fmt(r.rate_nb, 4)}</td>
                      <td style={num}>{fmt(r.diff, 4)}</td>
                      <td style={{ ...num, color: isErr ? '#dc2626' : undefined, fontWeight: isErr ? 600 : undefined }}>
                        {isErr ? fmt(r.expected_kzt) : '—'}
                      </td>
                      <td style={{ ...num, color: isErr ? '#dc2626' : undefined, fontWeight: isErr ? 600 : undefined }}>
                        {isErr ? fmt(r.delta_kzt) : '—'}
                      </td>
                      <td style={td}>
                        <span style={{ color: s.color, background: s.bg, padding: '2px 8px', borderRadius: 6, fontSize: 12, fontWeight: 600 }}>{s.label}</span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
