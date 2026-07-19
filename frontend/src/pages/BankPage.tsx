import { useState } from 'react'
import FileUpload from '../components/FileUpload'
import { reconciliationApi, BankResult } from '../api/client'

type Step = 'upload' | 'processing' | 'result'

const fmt = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const STATUS: Record<string, { label: string; color: string; bg: string }> = {
  date_diff: { label: 'Разная дата', color: '#b45309', bg: '#fef3c7' },
  only_bank: { label: 'Нет в 1С', color: '#dc2626', bg: '#fee2e2' },
  only_1c: { label: 'Нет в банке', color: '#dc2626', bg: '#fee2e2' },
}

const th: React.CSSProperties = { textAlign: 'left', padding: '8px 10px', borderBottom: '2px solid #e5e7eb', whiteSpace: 'nowrap', fontSize: 13 }
const td: React.CSSProperties = { padding: '6px 10px', borderBottom: '1px solid #f1f5f9', fontSize: 13 }
const num: React.CSSProperties = { ...td, textAlign: 'right', whiteSpace: 'nowrap' }

export default function BankPage() {
  const [step, setStep] = useState<Step>('upload')
  const [cardFile, setCardFile] = useState<File | null>(null)
  const [bankFile, setBankFile] = useState<File | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [result, setResult] = useState<BankResult | null>(null)
  const [error, setError] = useState('')

  const handleReconcile = async () => {
    if (!cardFile || !bankFile) return
    setError('')
    setStep('processing')
    try {
      const up = await reconciliationApi.uploadBank(cardFile, bankFile)
      setSessionId(up.session_id)
      const res = await reconciliationApi.processBank(up.session_id)
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
    fetch(reconciliationApi.downloadBank(sessionId), {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => r.blob())
      .then(blob => {
        const u = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = u
        a.download = `Сверка выписки ${sessionId.slice(0, 8)}.xlsx`
        a.click()
        window.URL.revokeObjectURL(u)
      })
  }

  const handleReset = () => {
    setStep('upload'); setCardFile(null); setBankFile(null)
    setSessionId(null); setResult(null); setError('')
  }

  const diff = result?.balance_diff
  const hasDiff = diff != null && Math.abs(diff) > 0.005
  const discrepancies = result?.rows.filter(r => r.status !== 'ok') || []

  const ctrlRow = (label: string, bank: number | null, c1: number | null) => (
    <tr>
      <td style={td}>{label}</td>
      <td style={num}>{fmt(bank)}</td>
      <td style={num}>{fmt(c1)}</td>
      <td style={{ ...num, color: bank != null && c1 != null && Math.abs(bank - c1) > 0.005 ? '#dc2626' : '#111827' }}>
        {bank != null && c1 != null ? fmt(bank - c1) : '—'}
      </td>
    </tr>
  )

  return (
    <div>
      <h1 style={{ marginBottom: 8 }}>Сверка выписок (1С ↔ банк)</h1>
      <p style={{ color: '#6b7280', marginBottom: 24 }}>
        Карточка счёта из 1С сверяется с банковской выпиской: обороты, остатки, неучтённые поступления.
        Колонки определяются автоматически.
      </p>

      {error && <div className="error-message" style={{ marginBottom: 16 }}>{error}</div>}

      {step !== 'result' && (
        <div className="card">
          <div className="dashboard-cards" style={{ gap: 16 }}>
            <FileUpload label="Карточка счёта 1С (напр. 1030)" onFileSelect={setCardFile} selectedFile={cardFile} />
            <FileUpload label="Банковская выписка" onFileSelect={setBankFile} selectedFile={bankFile} />
          </div>
          <button
            className="btn btn-primary"
            style={{ marginTop: 20 }}
            disabled={!cardFile || !bankFile || step === 'processing'}
            onClick={handleReconcile}
          >
            {step === 'processing' ? 'Обработка…' : 'Сверить'}
          </button>
        </div>
      )}

      {step === 'result' && result && (
        <>
          {result.currency && (
            <div className="card" style={{ marginBottom: 16, background: '#eff6ff', borderColor: '#bfdbfe' }}>
              Валютный счёт: сверка по сумме в валюте (строка «Вал.»), тенговый эквивалент не участвует.
            </div>
          )}

          {hasDiff ? (
            <div className="card" style={{ marginBottom: 16, background: '#fef2f2', borderColor: '#fecaca' }}>
              <strong style={{ color: '#dc2626' }}>⚠ Расхождение по остатку: {fmt(diff)} ₸</strong>
              {result.gaps.length > 0 ? (
                <ul style={{ margin: '8px 0 0', paddingLeft: 20, color: '#4b5563', fontSize: 14 }}>
                  {result.gaps.map((g, i) => (
                    <li key={i}>
                      Остаток в выписке изменился с {g.from_date} по {g.to_date} на {fmt(g.amount)} ₸ без операции —
                      вероятно, неучтённое поступление. Найти первичный документ и провести в 1С.
                    </li>
                  ))}
                </ul>
              ) : (
                <p style={{ margin: '8px 0 0', color: '#4b5563', fontSize: 14 }}>
                  Обороты и/или остатки расходятся. Проверьте операции «Нет в 1С» и «Нет в банке» ниже.
                </p>
              )}
            </div>
          ) : (
            <div className="card" style={{ marginBottom: 16, background: '#f0fdf4', borderColor: '#bbf7d0' }}>
              <strong style={{ color: '#16a34a' }}>Расхождений по остатку не найдено — обороты и остатки совпадают.</strong>
            </div>
          )}

          {result.split_docs.length > 0 && (
            <div className="card" style={{ marginBottom: 16, background: '#fffbeb', borderColor: '#fde68a', fontSize: 14 }}>
              В 1С разбиты на 2 строки (часть «Оплата», часть «Оплата (аванс)») ПП: №{result.split_docs.join(', №')}.
              Это не ошибка — сверка выполнена на уровне документа.
            </div>
          )}

          {/* Контрольная сверка */}
          <div className="card" style={{ marginBottom: 20, overflowX: 'auto' }}>
            <h3 style={{ marginBottom: 12 }}>Контрольная сверка</h3>
            <table style={{ borderCollapse: 'collapse', width: '100%' }}>
              <thead>
                <tr>
                  <th style={th}></th>
                  <th style={{ ...th, textAlign: 'right' }}>Банк</th>
                  <th style={{ ...th, textAlign: 'right' }}>1С</th>
                  <th style={{ ...th, textAlign: 'right' }}>Разница</th>
                </tr>
              </thead>
              <tbody>
                {ctrlRow('Входящий остаток', result.open_bank, result.open_c1)}
                {ctrlRow('Обороты: приход', result.bank_in, result.c1_in)}
                {ctrlRow('Обороты: списание', result.bank_out, result.c1_out)}
                {ctrlRow('Исходящий остаток', result.close_bank, result.close_c1)}
              </tbody>
            </table>
            <p style={{ marginTop: 12, color: '#6b7280', fontSize: 13 }}>
              Сопоставлено: {result.matched} · Нет в 1С: {result.only_bank} · Нет в банке: {result.only_1c}
            </p>
          </div>

          <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
            <button className="btn btn-primary" onClick={handleDownload}>Скачать Excel</button>
            <button className="btn btn-secondary" onClick={handleReset}>Новая сверка</button>
          </div>

          {/* Расхождения */}
          <div className="card" style={{ overflowX: 'auto' }}>
            <h3 style={{ marginBottom: 12 }}>Расхождения ({discrepancies.length})</h3>
            {discrepancies.length === 0 ? (
              <p style={{ color: '#16a34a' }}>Все операции сопоставлены.</p>
            ) : (
              <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                <thead>
                  <tr>
                    <th style={th}>Дата</th><th style={th}>Направление</th>
                    <th style={{ ...th, textAlign: 'right' }}>Сумма, ₸</th>
                    <th style={th}>Тип</th><th style={th}>№ (банк/1С)</th><th style={th}>Назначение</th>
                  </tr>
                </thead>
                <tbody>
                  {discrepancies.map((r, i) => {
                    const s = STATUS[r.status] || STATUS.only_bank
                    return (
                      <tr key={i}>
                        <td style={td}>{r.date}</td>
                        <td style={td}>{r.dir === 'in' ? 'приход' : 'списание'}</td>
                        <td style={num}>{fmt(r.amount)}</td>
                        <td style={td}>
                          <span style={{ color: s.color, background: s.bg, padding: '2px 8px', borderRadius: 6, fontSize: 12, fontWeight: 600 }}>{s.label}</span>
                        </td>
                        <td style={td}>{r.status === 'only_bank' ? `банк №${r.bank_no}` : `1С №${r.c1_no}`}</td>
                        <td style={{ ...td, maxWidth: 360, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {r.bank_purpose || r.c1_purpose || ''}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
