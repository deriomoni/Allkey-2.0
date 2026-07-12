import { useState, useEffect, useCallback } from 'react'
import FileUpload from '../components/FileUpload'
import ResultTable from '../components/ResultTable'
import ColumnMapper from '../components/ColumnMapper'
import type { DateExtractConfig } from '../components/ColumnMapper'
import { reconciliationApi, ReconciliationResult, PreviewResponse } from '../api/client'

type Step = 'upload' | 'configure' | 'processing' | 'result'

const ACT_FIELDS = [
  { key: 'date', label: 'Дата' },
  { key: 'document', label: 'Документ' },
  { key: 'debit', label: 'Дебет' },
  { key: 'credit', label: 'Кредит' },
]

const DEFAULT_MAPPINGS = {
  date: 1,
  document: 2,
  debit: 4,
  credit: 5,
}

const SESSION_KEY = 'case2_session'

export default function Case2Page() {
  const [step, setStep] = useState<Step>(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      if (parsed.step === 'configure') return 'configure'
    }
    return 'upload'
  })
  const [sessionId, setSessionId] = useState<string | null>(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).sessionId ?? null : null
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Files
  const [ourActFile, setOurActFile] = useState<File | null>(null)
  const [counterpartyActFile, setCounterpartyActFile] = useState<File | null>(null)

  // Preview data
  const [ourPreview, setOurPreview] = useState<PreviewResponse | null>(null)
  const [cpPreview, setCpPreview] = useState<PreviewResponse | null>(null)

  // Column mappings
  const [ourHeaderRow, setOurHeaderRow] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).ourHeaderRow ?? 0 : 0
  })
  const [cpHeaderRow, setCpHeaderRow] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).cpHeaderRow ?? 0 : 0
  })
  const [ourMappings, setOurMappings] = useState<Record<string, number>>(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).ourMappings ?? { ...DEFAULT_MAPPINGS } : { ...DEFAULT_MAPPINGS }
  })
  const [cpMappings, setCpMappings] = useState<Record<string, number>>(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).cpMappings ?? { ...DEFAULT_MAPPINGS } : { ...DEFAULT_MAPPINGS }
  })

  // Date extraction config
  const DEFAULT_DATE_EXTRACT: DateExtractConfig = { hasDateColumn: true, dateFormat: 'DD.MM.YYYY', dateSourceColumn: 2 }
  const [ourDateExtract, setOurDateExtract] = useState<DateExtractConfig>(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).ourDateExtract ?? { ...DEFAULT_DATE_EXTRACT } : { ...DEFAULT_DATE_EXTRACT }
  })
  const [cpDateExtract, setCpDateExtract] = useState<DateExtractConfig>(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).cpDateExtract ?? { ...DEFAULT_DATE_EXTRACT } : { ...DEFAULT_DATE_EXTRACT }
  })

  // Result
  const [result, setResult] = useState<ReconciliationResult | null>(null)

  // Persist session state to sessionStorage
  useEffect(() => {
    if (sessionId) {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({
        sessionId, step, ourHeaderRow, cpHeaderRow, ourMappings, cpMappings,
        ourDateExtract, cpDateExtract,
      }))
    }
  }, [sessionId, step, ourHeaderRow, cpHeaderRow, ourMappings, cpMappings, ourDateExtract, cpDateExtract])

  // Restore previews on page reload if session exists
  const restorePreviews = useCallback(async (sid: string, hOur: number, hCp: number) => {
    try {
      setLoading(true)
      const [ourPrev, cpPrev] = await Promise.all([
        reconciliationApi.previewCase2(sid, 'our_act', hOur),
        reconciliationApi.previewCase2(sid, 'counterparty_act', hCp),
      ])
      setOurPreview(ourPrev)
      setCpPreview(cpPrev)
    } catch {
      sessionStorage.removeItem(SESSION_KEY)
      setSessionId(null)
      setStep('upload')
      setError('Сессия истекла. Пожалуйста, загрузите файлы заново.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (sessionId && step === 'configure' && !ourPreview) {
      restorePreviews(sessionId, ourHeaderRow, cpHeaderRow)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Step 1 -> Step 2: Upload files and load previews
  const handleUploadAndConfigure = async () => {
    if (!ourActFile || !counterpartyActFile) {
      setError('Пожалуйста, загрузите оба файла')
      return
    }

    setLoading(true)
    setError('')

    try {
      // Upload files
      const uploadResponse = await reconciliationApi.uploadCase2(ourActFile, counterpartyActFile)
      setSessionId(uploadResponse.session_id)

      // Load previews for both files
      const [ourPreviewData, cpPreviewData] = await Promise.all([
        reconciliationApi.previewCase2(uploadResponse.session_id, 'our_act', ourHeaderRow),
        reconciliationApi.previewCase2(uploadResponse.session_id, 'counterparty_act', cpHeaderRow),
      ])

      setOurPreview(ourPreviewData)
      setCpPreview(cpPreviewData)
      setStep('configure')
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Ошибка загрузки файлов')
    } finally {
      setLoading(false)
    }
  }

  // Reload preview when header row changes
  const handleOurHeaderRowChange = async (value: number) => {
    setOurHeaderRow(value)
    if (sessionId) {
      try {
        const preview = await reconciliationApi.previewCase2(sessionId, 'our_act', value)
        setOurPreview(preview)
      } catch {
        // Ignore preview errors
      }
    }
  }

  const handleCpHeaderRowChange = async (value: number) => {
    setCpHeaderRow(value)
    if (sessionId) {
      try {
        const preview = await reconciliationApi.previewCase2(sessionId, 'counterparty_act', value)
        setCpPreview(preview)
      } catch {
        // Ignore preview errors
      }
    }
  }

  // Step 2 -> Step 3: Process with selected mappings
  const handleProcess = async () => {
    if (!sessionId) return

    setLoading(true)
    setError('')
    setStep('processing')

    try {
      const processResponse = await reconciliationApi.processCase2(
        sessionId,
        {
          header_row: ourHeaderRow,
          column_mappings: ourMappings,
          ...(!ourDateExtract.hasDateColumn ? {
            date_extract_from_text: true,
            date_format: ourDateExtract.dateFormat,
            date_source_column: ourDateExtract.dateSourceColumn,
          } : {}),
        },
        {
          header_row: cpHeaderRow,
          column_mappings: cpMappings,
          ...(!cpDateExtract.hasDateColumn ? {
            date_extract_from_text: true,
            date_format: cpDateExtract.dateFormat,
            date_source_column: cpDateExtract.dateSourceColumn,
          } : {}),
        }
      )

      setResult(processResponse)
      setStep('result')
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Ошибка обработки файлов')
      setStep('configure')
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (!sessionId) return
    const token = localStorage.getItem('token')
    const url = reconciliationApi.downloadCase2(sessionId)

    fetch(url, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.blob())
      .then(blob => {
        const downloadUrl = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = downloadUrl
        a.download = `reconciliation_case2_${sessionId.slice(0, 8)}.xlsx`
        a.click()
        window.URL.revokeObjectURL(downloadUrl)
      })
  }

  const handleReset = () => {
    sessionStorage.removeItem(SESSION_KEY)
    setStep('upload')
    setSessionId(null)
    setOurActFile(null)
    setCounterpartyActFile(null)
    setOurPreview(null)
    setCpPreview(null)
    setOurHeaderRow(0)
    setCpHeaderRow(0)
    setOurMappings({ ...DEFAULT_MAPPINGS })
    setCpMappings({ ...DEFAULT_MAPPINGS })
    setOurDateExtract({ ...DEFAULT_DATE_EXTRACT })
    setCpDateExtract({ ...DEFAULT_DATE_EXTRACT })
    setResult(null)
    setError('')
  }

  // Preview table component — shows column numbers + header row + data rows
  const PreviewTable = ({ columns, data }: { columns: string[], data: (string | number | null)[][] }) => (
    <div style={{ overflowX: 'auto', marginTop: 12 }}>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
        <thead>
          {/* Column index numbers */}
          <tr>
            {columns.map((_, idx) => (
              <th
                key={idx}
                style={{
                  padding: '4px 8px',
                  border: '1px solid #e5e7eb',
                  backgroundColor: '#e0e7ff',
                  color: '#4338ca',
                  fontSize: 10,
                  fontWeight: 600,
                  textAlign: 'center',
                }}
              >
                [{idx}]
              </th>
            ))}
          </tr>
          {/* Header row */}
          <tr>
            {columns.map((col, idx) => (
              <th
                key={idx}
                style={{
                  padding: '6px 8px',
                  border: '1px solid #e5e7eb',
                  backgroundColor: '#f3f4f6',
                  fontWeight: 600,
                  whiteSpace: 'nowrap',
                  maxWidth: 150,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
                title={col}
              >
                {col === 'nan' ? '' : col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.slice(0, 15).map((row, rowIdx) => (
            <tr key={rowIdx}>
              {row.map((cell, cellIdx) => (
                <td
                  key={cellIdx}
                  style={{
                    padding: '6px 8px',
                    border: '1px solid #e5e7eb',
                    whiteSpace: 'nowrap',
                    maxWidth: 150,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                  title={String(cell ?? '')}
                >
                  {cell ?? ''}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )

  return (
    <div>
      <h1 style={{ marginBottom: 24 }}>Кейс 2: Акты взаимных расчётов</h1>

      {/* Steps indicator */}
      <div className="steps">
        <div className={`step ${step === 'upload' ? 'active' : 'completed'}`}>
          <div className="step-number">1</div>
          <div className="step-label">Загрузка</div>
        </div>
        <div className={`step ${step === 'configure' ? 'active' : step === 'processing' || step === 'result' ? 'completed' : ''}`}>
          <div className="step-number">2</div>
          <div className="step-label">Настройка</div>
        </div>
        <div className={`step ${step === 'processing' ? 'active' : step === 'result' ? 'completed' : ''}`}>
          <div className="step-number">3</div>
          <div className="step-label">Обработка</div>
        </div>
        <div className={`step ${step === 'result' ? 'active' : ''}`}>
          <div className="step-number">4</div>
          <div className="step-label">Результат</div>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {/* Step 1: Upload */}
      {step === 'upload' && (
        <div className="card">
          <h3 style={{ marginBottom: 16 }}>Загрузите файлы</h3>

          <div className="info-box" style={{ marginBottom: 20, padding: '12px 16px', backgroundColor: '#f0f9ff', borderRadius: 8, borderLeft: '4px solid #3b82f6' }}>
            <p style={{ margin: 0, fontSize: 14, color: '#1e40af' }}>
              <strong>Автоматическая сверка:</strong> структура акта (заголовок, колонки, период, сальдо) определяется автоматически. Просто загрузите оба акта — сверка идёт по номеру реализации, ЭСФ, дате и сумме. Ручная настройка колонок нужна только для нестандартных файлов.
            </p>
          </div>

          <div className="case-upload-grid">
            <FileUpload
              label="Наш акт сверки"
              selectedFile={ourActFile}
              onFileSelect={setOurActFile}
            />
            <FileUpload
              label="Акт контрагента"
              selectedFile={counterpartyActFile}
              onFileSelect={setCounterpartyActFile}
            />
          </div>

          <div style={{ marginTop: 16, fontSize: 13, color: '#6b7280' }}>
            <p><strong>Формат:</strong> стандартный акт сверки из 1С, формат .xls/.xlsx</p>
            <p><strong>Сопоставление:</strong> по дате + сумме + типу операции (товар, оплата, корректировка)</p>
          </div>

          <div className="actions">
            <button
              className="btn btn-primary"
              onClick={handleUploadAndConfigure}
              disabled={!ourActFile || !counterpartyActFile || loading}
            >
              {loading ? 'Загрузка...' : 'Далее'}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Configure */}
      {step === 'configure' && (
        <div className="card">
          <h3 style={{ marginBottom: 16 }}>Проверка файлов</h3>

          <div className="info-box" style={{ marginBottom: 20, padding: '12px 16px', backgroundColor: '#ecfdf5', borderRadius: 8, borderLeft: '4px solid #10b981' }}>
            <p style={{ margin: 0, fontSize: 14, color: '#065f46' }}>
              <strong>Структура определяется автоматически.</strong> Ниже — превью загруженных актов. Обычно ничего настраивать не нужно — сразу нажмите «Выполнить сверку». Ручная настройка колонок ниже — только для нестандартных файлов.
            </p>
          </div>

          <div className="case-configure-grid">
            {/* Our Act Settings */}
            <div className="case-configure-panel">
              <h4 style={{ margin: '0 0 16px 0', color: '#374151' }}>Наш акт сверки</h4>
              {ourPreview && (
                <>
                  <details style={{ marginBottom: 12 }}>
                    <summary style={{ cursor: 'pointer', fontSize: 13, color: '#6b7280', userSelect: 'none' }}>
                      Расширенные настройки (для нестандартных файлов)
                    </summary>
                    <div style={{ marginTop: 12 }}>
                      <ColumnMapper
                        columns={ourPreview.columns}
                        mappings={ourMappings}
                        fields={ACT_FIELDS}
                        headerRow={ourHeaderRow}
                        onHeaderRowChange={handleOurHeaderRowChange}
                        onMappingChange={(key, value) => setOurMappings({ ...ourMappings, [key]: value })}
                        previewData={ourPreview.data}
                        dateExtract={ourDateExtract}
                        onDateExtractChange={setOurDateExtract}
                      />
                    </div>
                  </details>
                  <div style={{ marginTop: 16 }}>
                    <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                      Превью данных ({ourPreview.total_rows} строк всего):
                    </div>
                    <PreviewTable columns={ourPreview.columns} data={ourPreview.data} />
                  </div>
                </>
              )}
            </div>

            {/* Counterparty Act Settings */}
            <div className="case-configure-panel">
              <h4 style={{ margin: '0 0 16px 0', color: '#374151' }}>Акт контрагента</h4>
              {cpPreview && (
                <>
                  <details style={{ marginBottom: 12 }}>
                    <summary style={{ cursor: 'pointer', fontSize: 13, color: '#6b7280', userSelect: 'none' }}>
                      Расширенные настройки (для нестандартных файлов)
                    </summary>
                    <div style={{ marginTop: 12 }}>
                      <ColumnMapper
                        columns={cpPreview.columns}
                        mappings={cpMappings}
                        fields={ACT_FIELDS}
                        headerRow={cpHeaderRow}
                        onHeaderRowChange={handleCpHeaderRowChange}
                        onMappingChange={(key, value) => setCpMappings({ ...cpMappings, [key]: value })}
                        previewData={cpPreview.data}
                        dateExtract={cpDateExtract}
                        onDateExtractChange={setCpDateExtract}
                      />
                    </div>
                  </details>
                  <div style={{ marginTop: 16 }}>
                    <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                      Превью данных ({cpPreview.total_rows} строк всего):
                    </div>
                    <PreviewTable columns={cpPreview.columns} data={cpPreview.data} />
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="actions">
            <button
              className="btn btn-secondary"
              onClick={() => setStep('upload')}
            >
              Назад
            </button>
            <button
              className="btn btn-primary"
              onClick={handleProcess}
              disabled={loading}
            >
              {loading ? 'Обработка...' : 'Выполнить сверку'}
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Processing */}
      {step === 'processing' && (
        <div className="card" style={{ textAlign: 'center', padding: 48 }}>
          <div className="spinner" style={{
            width: 48,
            height: 48,
            border: '4px solid #e5e7eb',
            borderTop: '4px solid #3b82f6',
            borderRadius: '50%',
            animation: 'spin 1s linear infinite',
            margin: '0 auto 24px'
          }} />
          <h3>Обработка файлов...</h3>
          <p style={{ color: '#6b7280' }}>
            Парсинг актов сверки, сопоставление по дате, сумме и типу операции
          </p>
          <style>{`
            @keyframes spin {
              0% { transform: rotate(0deg); }
              100% { transform: rotate(360deg); }
            }
          `}</style>
        </div>
      )}

      {/* Step 4: Result */}
      {step === 'result' && result && (
        <div className="card">
          <div className="case-result-header">
            <h3 style={{ margin: 0 }}>Результаты сверки</h3>
            <div className="actions" style={{ margin: 0 }}>
              <button className="btn btn-secondary" onClick={handleReset}>
                Новая сверка
              </button>
              <button className="btn btn-success" onClick={handleDownload}>
                Скачать Excel
              </button>
            </div>
          </div>
          <ResultTable result={result} caseType="case2" />
        </div>
      )}
    </div>
  )
}
