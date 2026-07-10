import { ReconciliationResult, Case1DataRow, ReconciliationSummary, Case2Summary, Case3Summary } from '../api/client'

interface ResultTableProps {
  result: ReconciliationResult
  caseType: 'case1' | 'case2' | 'case3'
}

export default function ResultTable({ result, caseType }: ResultTableProps) {
  const getStatusClass = (status: string) => {
    if (status === 'Совпадает') return 'status-matched'
    if (status === 'Расхождение') return 'status-mismatched'
    return 'status-not-found'
  }

  const case1Columns = [
    { key: 'date', label: 'Дата' },
    { key: 'document', label: 'Документ' },
    { key: 'counterparty_6010', label: 'Контрагент 1С' },
    { key: 'recipient_esf', label: 'Получатель ЭСФ' },
    { key: 'amount_6010', label: 'Сумма 1С' },
    { key: 'amount_esf', label: 'Сумма ЭСФ' },
    { key: 'difference', label: 'Разница' },
    { key: 'status', label: 'Статус' },
  ]

  const case3Columns = [
    { key: 'date', label: 'Дата' },
    { key: 'document', label: 'Документ' },
    { key: 'tru', label: 'ТРУ' },
    { key: 'sender_esf', label: 'Отправитель ЭСФ' },
    { key: 'amount_3310', label: 'Сумма 3310' },
    { key: 'amount_esf', label: 'Сумма ЭСФ' },
    { key: 'difference', label: 'Разница' },
    { key: 'status', label: 'Статус' },
  ]

  const case2Columns = [
    { key: 'date', label: 'Дата' },
    { key: 'document', label: 'Наш документ' },
    { key: 'our_doc_number', label: '№ нашего' },
    { key: 'cp_document', label: 'Документ контрагента' },
    { key: 'cp_doc_number', label: '№ контраг.' },
    { key: 'our_debit', label: 'Наш дебет' },
    { key: 'our_credit', label: 'Наш кредит' },
    { key: 'cp_debit', label: 'Дебет контрагента' },
    { key: 'cp_credit', label: 'Кредит контрагента' },
    { key: 'match_phase', label: 'Метод' },
    { key: 'status', label: 'Статус' },
  ]

  const columns = caseType === 'case1' ? case1Columns : caseType === 'case3' ? case3Columns : case2Columns

  const formatNumber = (value: unknown): string => {
    if (value === null || value === undefined) return '-'
    if (typeof value === 'number') {
      return value.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    }
    return String(value)
  }

  const formatAmount = (value: unknown): string => {
    if (value === null || value === undefined) return '-'
    if (typeof value === 'number') {
      return value.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₸'
    }
    return String(value)
  }

  const summary = result.summary as ReconciliationSummary | undefined
  const case2Summary = result.summary as Case2Summary | undefined
  const case3Summary = result.summary as Case3Summary | undefined

  return (
    <div>
      {/* Summary section for Case 2 */}
      {caseType === 'case2' && case2Summary && (
        <div style={{
          background: case2Summary.has_discrepancies ? '#fef2f2' : '#f0fdf4',
          border: `1px solid ${case2Summary.has_discrepancies ? '#fecaca' : '#bbf7d0'}`,
          borderRadius: 8,
          padding: 16,
          marginBottom: 24
        }}>
          <div className="case-summary-header">
            <h4 style={{ margin: 0, color: case2Summary.has_discrepancies ? '#dc2626' : '#16a34a' }}>
              {case2Summary.has_discrepancies ? 'Обнаружены расхождения' : 'Все записи совпадают'}
            </h4>
            <span style={{
              fontSize: 14,
              padding: '4px 12px',
              borderRadius: 4,
              background: case2Summary.has_discrepancies ? '#fee2e2' : '#dcfce7',
              color: case2Summary.has_discrepancies ? '#b91c1c' : '#15803d',
              fontWeight: 600
            }}>
              {case2Summary.match_rate}% совпадение
            </span>
          </div>

          <div className="case-summary-grid">
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Записей в нашем акте</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{case2Summary.total_entries_act1}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Записей у контрагента</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{case2Summary.total_entries_act2}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Совпало</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: '#16a34a' }}>{case2Summary.matched_count}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Расхождений</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: case2Summary.has_discrepancies ? '#dc2626' : '#16a34a' }}>
                {(result.not_found_in_source1 || 0) + (result.not_found_in_source2 || 0)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Match phases legend for Case 2 */}
      {caseType === 'case2' && (
        <div style={{
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: 8,
          padding: '12px 16px',
          marginBottom: 16,
          fontSize: 13,
          color: '#475569'
        }}>
          <div style={{ fontWeight: 600, marginBottom: 6, color: '#334155' }}>Фазы сопоставления:</div>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <span><strong style={{ color: '#16a34a' }}>Фаза 1</strong> — номер документа + сумма (самое точное)</span>
            <span><strong style={{ color: '#2563eb' }}>Фаза 2</strong> — тип операции + сумма</span>
            <span><strong style={{ color: '#d97706' }}>Фаза 3</strong> — только сумма (наименее точное)</span>
          </div>
        </div>
      )}

      {/* Summary section for Case 3 */}
      {caseType === 'case3' && case3Summary && (
        <div style={{
          background: case3Summary.has_discrepancies ? '#fef2f2' : '#f0fdf4',
          border: `1px solid ${case3Summary.has_discrepancies ? '#fecaca' : '#bbf7d0'}`,
          borderRadius: 8,
          padding: 16,
          marginBottom: 24
        }}>
          <div className="case-summary-header">
            <h4 style={{ margin: 0, color: case3Summary.has_discrepancies ? '#dc2626' : '#16a34a' }}>
              {case3Summary.has_discrepancies ? 'Обнаружены расхождения' : 'Все записи совпадают'}
            </h4>
            <span style={{
              fontSize: 14,
              padding: '4px 12px',
              borderRadius: 4,
              background: case3Summary.has_discrepancies ? '#fee2e2' : '#dcfce7',
              color: case3Summary.has_discrepancies ? '#b91c1c' : '#15803d',
              fontWeight: 600
            }}>
              {case3Summary.match_rate ?? 0}% совпадение
            </span>
          </div>

          <div className="case-summary-grid">
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Записей в 3310</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{case3Summary.total_3310_entries}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>ЭСФ в реестре</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{case3Summary.total_esf_invoices}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Совпало</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: '#16a34a' }}>{case3Summary.matched_count}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Разница сумм</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: case3Summary.has_discrepancies ? '#dc2626' : '#16a34a' }}>
                {formatAmount(case3Summary.total_difference)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Summary section for Case 1 */}
      {caseType === 'case1' && summary && (
        <div style={{
          background: summary.has_discrepancies ? '#fef2f2' : '#f0fdf4',
          border: `1px solid ${summary.has_discrepancies ? '#fecaca' : '#bbf7d0'}`,
          borderRadius: 8,
          padding: 16,
          marginBottom: 24
        }}>
          <div className="case-summary-header">
            <h4 style={{ margin: 0, color: summary.has_discrepancies ? '#dc2626' : '#16a34a' }}>
              {summary.has_discrepancies ? 'Обнаружены расхождения' : 'Все записи совпадают'}
            </h4>
            <span style={{
              fontSize: 14,
              padding: '4px 12px',
              borderRadius: 4,
              background: summary.has_discrepancies ? '#fee2e2' : '#dcfce7',
              color: summary.has_discrepancies ? '#b91c1c' : '#15803d',
              fontWeight: 600
            }}>
              {summary.match_rate ?? 0}% совпадение
            </span>
          </div>

          <div className="case-summary-grid">
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Записей в 1С</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{summary.total_1c_entries}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>ЭСФ в реестре</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{summary.total_esf_invoices}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Совпало</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: '#16a34a' }}>{summary.matched_count}</div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>Разница сумм</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: summary.has_discrepancies ? '#dc2626' : '#16a34a' }}>
                {formatAmount(summary.total_difference)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stats cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="value">{result.total_records}</div>
          <div className="label">Всего записей</div>
        </div>
        <div className="stat-card">
          <div className="value" style={{ color: '#10b981' }}>{result.matched}</div>
          <div className="label">Совпадает</div>
        </div>
        <div className="stat-card">
          <div className="value" style={{ color: '#ef4444' }}>{result.mismatched}</div>
          <div className="label">Расхождения сумм</div>
        </div>
        <div className="stat-card">
          <div className="value" style={{ color: '#f59e0b' }}>{result.not_found_in_source1}</div>
          <div className="label">{caseType === 'case1' || caseType === 'case3' ? 'Нет в ЭСФ' : 'Нет у контрагента'}</div>
        </div>
        <div className="stat-card">
          <div className="value" style={{ color: '#f59e0b' }}>{result.not_found_in_source2}</div>
          <div className="label">{caseType === 'case1' || caseType === 'case3' ? 'Нет в 1С' : 'Нет у нас'}</div>
        </div>
      </div>

      {/* Data table */}
      <div style={{ overflowX: 'auto', marginTop: 24 }}>
        <table>
          <thead>
            <tr>
              {columns.map(col => (
                <th key={col.key}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.data.map((row, idx) => {
              const r = row as Case1DataRow
              const rowData = row as unknown as Record<string, unknown>
              return (
                <tr key={idx} className={getStatusClass(r.status)}>
                  {columns.map(col => {
                    const value = rowData[col.key]

                    // Format amounts
                    if (col.key.includes('amount') || col.key === 'difference') {
                      return (
                        <td key={col.key} style={{ textAlign: 'right', fontFamily: 'monospace' }}>
                          {formatNumber(value)}
                        </td>
                      )
                    }

                    // Status with badge
                    if (col.key === 'status') {
                      return (
                        <td key={col.key}>
                          <span style={{
                            padding: '2px 8px',
                            borderRadius: 4,
                            fontSize: 12,
                            fontWeight: 500,
                            background: r.status === 'Совпадает' ? '#dcfce7' :
                              r.status === 'Расхождение' ? '#fee2e2' : '#fef3c7',
                            color: r.status === 'Совпадает' ? '#166534' :
                              r.status === 'Расхождение' ? '#991b1b' : '#92400e'
                          }}>
                            {r.status}
                          </span>
                        </td>
                      )
                    }

                    // Counterparty/TRU/sender - truncate if too long
                    if (col.key === 'counterparty_6010' || col.key === 'recipient_esf' || col.key === 'tru' || col.key === 'sender_esf') {
                      const text = value ? String(value) : '-'
                      return (
                        <td key={col.key} title={text} style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {text.length > 25 ? text.slice(0, 25) + '...' : text}
                        </td>
                      )
                    }

                    // Case 2: Document columns - show full text with wrap
                    if (col.key === 'document' || col.key === 'cp_document') {
                      const text = value ? String(value) : '-'
                      return (
                        <td key={col.key} title={text} style={{ minWidth: 200, maxWidth: 350, fontSize: 13, whiteSpace: 'normal', wordBreak: 'break-word' }}>
                          {text}
                        </td>
                      )
                    }

                    // Case 2: Match phase with color coding
                    if (col.key === 'match_phase') {
                      const phase = value ? String(value) : '-'
                      const phaseColor = phase.includes('1') ? '#16a34a' : phase.includes('2') ? '#2563eb' : phase.includes('3') ? '#d97706' : '#6b7280'
                      return (
                        <td key={col.key} style={{ fontSize: 11, color: phaseColor, fontWeight: 600, whiteSpace: 'nowrap' }}>
                          {phase}
                        </td>
                      )
                    }

                    // Case 2: Debit/Credit amounts
                    if (col.key === 'our_debit' || col.key === 'our_credit' || col.key === 'cp_debit' || col.key === 'cp_credit') {
                      return (
                        <td key={col.key} style={{ textAlign: 'right', fontFamily: 'monospace' }}>
                          {formatNumber(value)}
                        </td>
                      )
                    }

                    // Default
                    return <td key={col.key}>{value !== undefined && value !== null ? String(value) : '-'}</td>
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* ESF details expandable section for Case 1 and Case 3 */}
      {(caseType === 'case1' || caseType === 'case3') && (
        <details style={{ marginTop: 24 }}>
          <summary style={{ cursor: 'pointer', fontWeight: 500, color: '#3b82f6' }}>
            Показать детали ЭСФ (регистрационные номера)
          </summary>
          <div style={{ marginTop: 12, overflowX: 'auto' }}>
            <table style={{ fontSize: 13 }}>
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Получатель</th>
                  <th>№ ЭСФ</th>
                  <th>Рег. номер ЭСФ</th>
                  <th>Сумма</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {result.data.map((row, idx) => {
                  const r = row as Case1DataRow
                  if (!r.esf_reg_number) return null
                  return (
                    <tr key={idx}>
                      <td>{r.date}</td>
                      <td>{r.recipient_esf ?? '-'}</td>
                      <td>{r.esf_number}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{r.esf_reg_number}</td>
                      <td style={{ textAlign: 'right' }}>{formatNumber(r.amount_esf)}</td>
                      <td>{r.status}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  )
}
