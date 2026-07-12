import { ReconciliationResult, Case2DataRow, Case2Summary, Case2HeaderSummary } from '../api/client'

// Rich result view for the upgraded Case 2 (act-of-mutual-settlements
// reconciliation): header/saldo comparison, period-mismatch banner, the
// reconciled rows and a separate «вне периода» section.

const fmtAmount = (v: number | null | undefined): string => {
  if (v === null || v === undefined) return '—'
  return v.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const statusStyle = (status: string): { bg: string; fg: string } => {
  if (status === 'Совпадает') return { bg: '#dcfce7', fg: '#166534' }
  if (status === 'Расхождение') return { bg: '#fee2e2', fg: '#991b1b' }
  return { bg: '#fef3c7', fg: '#92400e' } // Нет у…, Вне периода
}

const ACT_COLUMNS: { key: keyof Case2DataRow; label: string; align?: 'right' }[] = [
  { key: 'category', label: 'Категория' },
  { key: 'num1', label: '№ акт 1' },
  { key: 'num2', label: '№ акт 2' },
  { key: 'date', label: 'Дата' },
  { key: 'amount1', label: 'Сумма акт 1', align: 'right' },
  { key: 'amount2', label: 'Сумма акт 2', align: 'right' },
  { key: 'esf1', label: 'ЭСФ 1' },
  { key: 'esf2', label: 'ЭСФ 2' },
  { key: 'match_method', label: 'Метод' },
  { key: 'status_detail', label: 'Статус' },
  { key: 'note', label: 'Комментарий' },
]

function ActTable({ rows }: { rows: Case2DataRow[] }) {
  return (
    <div style={{ overflowX: 'auto', marginTop: 12 }}>
      <table style={{ fontSize: 13 }}>
        <thead>
          <tr>
            {ACT_COLUMNS.map(c => (
              <th key={c.key as string} style={{ textAlign: c.align === 'right' ? 'right' : 'left' }}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => {
            const st = statusStyle(row.status)
            return (
              <tr key={idx}>
                {ACT_COLUMNS.map(c => {
                  const value = row[c.key]
                  if (c.key === 'amount1' || c.key === 'amount2') {
                    return (
                      <td key={c.key as string} style={{ textAlign: 'right', fontFamily: 'monospace' }}>
                        {fmtAmount(value as number | null)}
                      </td>
                    )
                  }
                  if (c.key === 'status_detail') {
                    return (
                      <td key={c.key as string}>
                        <span style={{ padding: '2px 8px', borderRadius: 4, fontSize: 12, fontWeight: 500, background: st.bg, color: st.fg, whiteSpace: 'nowrap' }}>
                          {value ? String(value) : row.status}
                        </span>
                      </td>
                    )
                  }
                  if (c.key === 'match_method') {
                    const m = value ? String(value) : ''
                    const color = m === 'Номер' ? '#16a34a' : m === 'ЭСФ' ? '#2563eb' : m === 'Дата+сумма' ? '#d97706' : '#9ca3af'
                    return <td key={c.key as string} style={{ fontSize: 11, color, fontWeight: 600, whiteSpace: 'nowrap' }}>{m || '—'}</td>
                  }
                  if (c.key === 'note') {
                    const text = value ? String(value) : ''
                    return <td key={c.key as string} style={{ fontSize: 12, color: '#6b7280', minWidth: 160, maxWidth: 320, whiteSpace: 'normal' }}>{text}</td>
                  }
                  return <td key={c.key as string} style={{ whiteSpace: 'nowrap' }}>{value !== undefined && value !== null && value !== '' ? String(value) : '—'}</td>
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function SaldoRow({ label, a, b, comment }: { label: string; a: number | null; b: number | null; comment?: string }) {
  return (
    <tr>
      <td style={{ fontWeight: 500 }}>{label}</td>
      <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>{fmtAmount(a)}</td>
      <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>{fmtAmount(b)}</td>
      <td style={{ fontSize: 12, color: '#6b7280' }}>{comment}</td>
    </tr>
  )
}

export default function Case2ResultView({ result }: { result: ReconciliationResult }) {
  const summary = result.summary as Case2Summary | undefined
  const hs = result.header_summary as Case2HeaderSummary | undefined
  const rows = (result.data as Case2DataRow[]) || []
  const outRows = (result.out_of_period as Case2DataRow[]) || []
  const hasDiscrepancies = summary?.has_discrepancies ?? (result.mismatched > 0)

  const diffComment = (diff: number | null | undefined, note: string): string => {
    if (diff === null || diff === undefined || Math.abs(diff) < 0.005) return 'совпадает'
    return `разница ${fmtAmount(diff)} ₸${note ? ` — ${note}` : ''}`
  }

  return (
    <div>
      {/* Owners / period */}
      {hs && (
        <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: 16, marginBottom: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Акт 1</div>
              <div style={{ fontWeight: 600 }}>{hs.owner_act1 || '—'}</div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>период {hs.period_act1 || '?'}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Акт 2</div>
              <div style={{ fontWeight: 600 }}>{hs.owner_act2 || '—'}</div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>период {hs.period_act2 || '?'}</div>
            </div>
          </div>
          {summary?.auto_detected === false && (
            <div style={{ marginTop: 10, fontSize: 12, color: '#92400e' }}>
              Структура определена вручную (автоопределение не сработало на этом файле).
            </div>
          )}
        </div>
      )}

      {/* Period mismatch banner */}
      {hs?.period_mismatch && (
        <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8, padding: '12px 16px', marginBottom: 16, fontSize: 13, color: '#92400e' }}>
          <strong>Периоды актов не совпадают</strong> ({hs.period_act1} vs {hs.period_act2}). Сопоставимы только за общий период {hs.common_period || '—'}. Операции вне общего периода вынесены в раздел «Вне периода» ниже — это не расхождение.
        </div>
      )}

      {/* Summary status */}
      <div style={{
        background: hasDiscrepancies ? '#fef2f2' : '#f0fdf4',
        border: `1px solid ${hasDiscrepancies ? '#fecaca' : '#bbf7d0'}`,
        borderRadius: 8, padding: 16, marginBottom: 16,
      }}>
        <div className="case-summary-header">
          <h4 style={{ margin: 0, color: hasDiscrepancies ? '#dc2626' : '#16a34a' }}>
            {hasDiscrepancies ? 'Обнаружены расхождения' : 'Все операции сходятся'}
          </h4>
          {summary && (
            <span style={{ fontSize: 14, padding: '4px 12px', borderRadius: 4, background: hasDiscrepancies ? '#fee2e2' : '#dcfce7', color: hasDiscrepancies ? '#b91c1c' : '#15803d', fontWeight: 600 }}>
              {summary.match_rate}% совпадение
            </span>
          )}
        </div>
        <div className="case-summary-grid">
          <div><div style={{ fontSize: 12, color: '#6b7280' }}>Записей в акте 1</div><div style={{ fontSize: 18, fontWeight: 600 }}>{summary?.total_entries_act1 ?? '—'}</div></div>
          <div><div style={{ fontSize: 12, color: '#6b7280' }}>Записей в акте 2</div><div style={{ fontSize: 18, fontWeight: 600 }}>{summary?.total_entries_act2 ?? '—'}</div></div>
          <div><div style={{ fontSize: 12, color: '#6b7280' }}>Совпало</div><div style={{ fontSize: 18, fontWeight: 600, color: '#16a34a' }}>{result.matched}</div></div>
          <div><div style={{ fontSize: 12, color: '#6b7280' }}>Расхождений</div><div style={{ fontSize: 18, fontWeight: 600, color: hasDiscrepancies ? '#dc2626' : '#16a34a' }}>{result.mismatched + result.not_found_in_source1 + result.not_found_in_source2}</div></div>
        </div>
      </div>

      {/* Saldo / turnovers */}
      {hs && (
        <div style={{ overflowX: 'auto', marginBottom: 20 }}>
          <table style={{ fontSize: 13 }}>
            <thead>
              <tr><th>Показатель</th><th style={{ textAlign: 'right' }}>Акт 1</th><th style={{ textAlign: 'right' }}>Акт 2</th><th>Разница / комментарий</th></tr>
            </thead>
            <tbody>
              <SaldoRow label="Сальдо на начало" a={hs.opening_act1} b={hs.opening_act2} comment={diffComment(hs.opening_diff, 'возникла до периода')} />
              <SaldoRow label="Обороты Дебет" a={hs.turnover_debit_act1} b={hs.turnover_debit_act2} comment={hs.period_mismatch ? 'разные периоды' : ''} />
              <SaldoRow label="Обороты Кредит" a={hs.turnover_credit_act1} b={hs.turnover_credit_act2} comment={hs.period_mismatch ? 'разные периоды' : ''} />
              <SaldoRow label="Сальдо на конец" a={hs.closing_act1} b={hs.closing_act2} comment={diffComment(hs.closing_diff, '')} />
            </tbody>
          </table>
        </div>
      )}

      {/* Stat cards */}
      <div className="stats-grid">
        <div className="stat-card"><div className="value">{result.total_records}</div><div className="label">Операций сверено</div></div>
        <div className="stat-card"><div className="value" style={{ color: '#10b981' }}>{result.matched}</div><div className="label">Совпадает</div></div>
        <div className="stat-card"><div className="value" style={{ color: '#ef4444' }}>{result.mismatched}</div><div className="label">Расхождения</div></div>
        <div className="stat-card"><div className="value" style={{ color: '#f59e0b' }}>{result.not_found_in_source1}</div><div className="label">Нет у контрагента</div></div>
        <div className="stat-card"><div className="value" style={{ color: '#f59e0b' }}>{result.not_found_in_source2}</div><div className="label">Нет у нас</div></div>
      </div>

      {/* Matching method legend */}
      <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '12px 16px', margin: '16px 0', fontSize: 13, color: '#475569' }}>
        <div style={{ fontWeight: 600, marginBottom: 6, color: '#334155' }}>Как сопоставлено:</div>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <span><strong style={{ color: '#16a34a' }}>Номер</strong> — реализация №N = вх. №N</span>
          <span><strong style={{ color: '#2563eb' }}>ЭСФ</strong> — по номеру электронной счёт-фактуры</span>
          <span><strong style={{ color: '#d97706' }}>Дата+сумма</strong> — платежи, возвраты, встречные поставки</span>
        </div>
      </div>

      {/* Reconciled rows */}
      <h4 style={{ margin: '8px 0' }}>Сверка{hs?.common_period ? ` (общий период ${hs.common_period})` : ''}</h4>
      <ActTable rows={rows} />

      {/* Out of period */}
      {outRows.length > 0 && (
        <details style={{ marginTop: 20 }} open>
          <summary style={{ cursor: 'pointer', fontWeight: 600, color: '#b45309' }}>
            Вне общего периода — {outRows.length} строк (информационно, не расхождение)
          </summary>
          <ActTable rows={outRows} />
        </details>
      )}
    </div>
  )
}
