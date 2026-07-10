import { useState, useEffect, useCallback } from 'react'
import FileUpload from '../components/FileUpload'
import ResultTable from '../components/ResultTable'
import ColumnMapper from '../components/ColumnMapper'
import { reconciliationApi, ReconciliationResult, PreviewResponse } from '../api/client'

type Step = 'upload' | 'configure' | 'processing' | 'result'

const ACCOUNT_3310_FIELDS = [
  { key: 'date', label: 'Дата' },
  { key: 'tru', label: 'ТРУ' },
  { key: 'amount', label: 'Сумма' },
]

const DEFAULT_3310_MAPPINGS: Record<string, number> = {
  date: 0,
  tru: 3,
  amount: 9,
}

const ESF_FIELDS = [
  { key: 'operation_date', label: 'Дата операции' },
  { key: 'sender_name', label: 'Отправитель' },
  { key: 'amount_without_vat', label: 'Сумма' },
  { key: 'invoice_number', label: 'Номер СФ' },
  { key: 'esf_reg_number', label: 'Рег. номер ЭСФ' },
]

const DEFAULT_ESF_MAPPINGS: Record<string, number> = {
  operation_date: 8,
  sender_name: 1,
  amount_without_vat: 11,
  invoice_number: 5,
  esf_reg_number: 6,
}

const SESSION_KEY = 'case3_session'

export default function Case3Page() {
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
  const [account3310File, setAccount3310File] = useState<File | null>(null)
  const [esfFile, setEsfFile] = useState<File | null>(null)

  // Preview data
  const [account3310Preview, setAccount3310Preview] = useState<PreviewResponse | null>(null)
  const [esfPreview, setEsfPreview] = useState<PreviewResponse | null>(null)

  // Column mappings
  const [account3310HeaderRow, setAccount3310HeaderRow] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).account3310HeaderRow ?? 0 : 0
  })
  const [esfHeaderRow, setEsfHeaderRow] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).esfHeaderRow ?? 0 : 0
  })
  const [account3310Mappings, setAccount3310Mappings] = useState<Record<string, number>>(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).account3310Mappings ?? { ...DEFAULT_3310_MAPPINGS } : { ...DEFAULT_3310_MAPPINGS }
  })
  const [esfMappings, setEsfMappings] = useState<Record<string, number>>(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).esfMappings ?? { ...DEFAULT_ESF_MAPPINGS } : { ...DEFAULT_ESF_MAPPINGS }
  })

  // Document filter
  const [docFilter, setDocFilter] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).docFilter ?? 'Поступление' : 'Поступление'
  })
  const [customDocFilter, setCustomDocFilter] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_KEY)
    return saved ? JSON.parse(saved).customDocFilter ?? '' : ''
  })

  // Result
  const [result, setResult] = useState<ReconciliationResult | null>(null)

  // Persist session state to sessionStorage
  useEffect(() => {
    if (sessionId) {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({
        sessionId, step, account3310HeaderRow, esfHeaderRow,
        account3310Mappings, esfMappings, docFilter, customDocFilter,
      }))
    }
  }, [sessionId, step, account3310HeaderRow, esfHeaderRow, account3310Mappings, esfMappings, docFilter, customDocFilter])

  // Restore previews on page reload if session exists
  const restorePreviews = useCallback(async (sid: string, headerRow3310: number, headerRowEsf: number) => {
    try {
      setLoading(true)
      const [a3310Preview, esfPrev] = await Promise.all([
        reconciliationApi.previewCase3(sid, 'account_3310', headerRow3310),
        reconciliationApi.previewCase3(sid, 'esf_report', headerRowEsf),
      ])
      setAccount3310Preview(a3310Preview)
      setEsfPreview(esfPrev)
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
    if (sessionId && step === 'configure' && !account3310Preview) {
      restorePreviews(sessionId, account3310HeaderRow, esfHeaderRow)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Step 1 -> Step 2: Upload files and load previews
  const handleUploadAndConfigure = async () => {
    if (!account3310File || !esfFile) {
      setError('Пожалуйста, загрузите оба файла')
      return
    }

    setLoading(true)
    setError('')

    try {
      const uploadResponse = await reconciliationApi.uploadCase3(account3310File, esfFile)
      setSessionId(uploadResponse.session_id)

      const [account3310PreviewData, esfPreviewData] = await Promise.all([
        reconciliationApi.previewCase3(uploadResponse.session_id, 'account_3310', account3310HeaderRow),
        reconciliationApi.previewCase3(uploadResponse.session_id, 'esf_report', esfHeaderRow),
      ])

      setAccount3310Preview(account3310PreviewData)
      setEsfPreview(esfPreviewData)
      setStep('configure')
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Ошибка загрузки файлов')
    } finally {
      setLoading(false)
    }
  }

  const handleAccount3310HeaderRowChange = async (value: number) => {
    setAccount3310HeaderRow(value)
    if (sessionId) {
      try {
        const preview = await reconciliationApi.previewCase3(sessionId, 'account_3310', value)
        setAccount3310Preview(preview)
      } catch {
        // Ignore preview errors
      }
    }
  }

  const handleEsfHeaderRowChange = async (value: number) => {
    setEsfHeaderRow(value)
    if (sessionId) {
      try {
        const preview = await reconciliationApi.previewCase3(sessionId, 'esf_report', value)
        setEsfPreview(preview)
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
      const processResponse = await reconciliationApi.processCase3(
        sessionId,
        {
          header_row: account3310HeaderRow,
          column_mappings: account3310Mappings,
          doc_filter: docFilter === '__custom__' ? customDocFilter : docFilter,
        },
        {
          header_row: esfHeaderRow,
          column_mappings: esfMappings,
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
    const url = reconciliationApi.downloadCase3(sessionId)

    fetch(url, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.blob())
      .then(blob => {
        const downloadUrl = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = downloadUrl
        a.download = `reconciliation_case3_${sessionId.slice(0, 8)}.xlsx`
        a.click()
        window.URL.revokeObjectURL(downloadUrl)
      })
  }

  const handleReset = () => {
    sessionStorage.removeItem(SESSION_KEY)
    setStep('upload')
    setSessionId(null)
    setAccount3310File(null)
    setEsfFile(null)
    setAccount3310Preview(null)
    setEsfPreview(null)
    setAccount3310HeaderRow(0)
    setEsfHeaderRow(0)
    setAccount3310Mappings({ ...DEFAULT_3310_MAPPINGS })
    setEsfMappings({ ...DEFAULT_ESF_MAPPINGS })
    setDocFilter('Поступление')
    setCustomDocFilter('')
    setResult(null)
    setError('')
  }

  const PreviewTable = ({ columns, data }: { columns: string[], data: (string | number | null)[][] }) => (
    <div style={{ overflowX: 'auto', marginTop: 12 }}>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
        <thead>
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
      <h1 style={{ marginBottom: 24 }}>Кейс 3: Карточка 3310 vs ЭСФ</h1>

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
              <strong>Входящие счета-фактуры:</strong> сверка карточки счёта 3310 (Поступление) с реестром входящих ЭСФ.
            </p>
          </div>

          <div className="case-upload-grid">
            <FileUpload
              label="Карточка счёта 3310 (1С)"
              selectedFile={account3310File}
              onFileSelect={setAccount3310File}
            />
            <FileUpload
              label="Реестр ЭСФ (входящие)"
              selectedFile={esfFile}
              onFileSelect={setEsfFile}
            />
          </div>

          <div style={{ marginTop: 16, fontSize: 13, color: '#6b7280' }}>
            <p><strong>Карточка 3310:</strong> экспорт из 1С, формат .xls/.xlsx</p>
            <p><strong>Реестр ЭСФ:</strong> выгрузка входящих из cabinet.esf.gov.kz, формат .xlsx</p>
          </div>

          <div className="actions">
            <button
              className="btn btn-primary"
              onClick={handleUploadAndConfigure}
              disabled={!account3310File || !esfFile || loading}
            >
              {loading ? 'Загрузка...' : 'Далее'}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Configure */}
      {step === 'configure' && (
        <div className="card">
          <h3 style={{ marginBottom: 16 }}>Настройка колонок</h3>

          <div className="info-box" style={{ marginBottom: 20, padding: '12px 16px', backgroundColor: '#fef3c7', borderRadius: 8, borderLeft: '4px solid #f59e0b' }}>
            <p style={{ margin: 0, fontSize: 14, color: '#92400e' }}>
              Выберите, какие колонки содержат нужные данные. Ниже показано превью первых строк файлов.
            </p>
          </div>

          {/* Document filter selection */}
          <div style={{ marginBottom: 20, padding: '12px 16px', backgroundColor: '#f9fafb', borderRadius: 8, border: '1px solid #e5e7eb' }}>
            <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, fontSize: 14, color: '#374151' }}>
              Фильтр документа
            </label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              {['Поступление', 'Реализация'].map((filter) => (
                <button
                  key={filter}
                  onClick={() => setDocFilter(filter)}
                  style={{
                    padding: '6px 16px',
                    borderRadius: 20,
                    border: docFilter === filter ? '2px solid #3b82f6' : '1px solid #d1d5db',
                    backgroundColor: docFilter === filter ? '#eff6ff' : '#fff',
                    color: docFilter === filter ? '#1d4ed8' : '#374151',
                    fontWeight: docFilter === filter ? 600 : 400,
                    fontSize: 13,
                    cursor: 'pointer',
                  }}
                >
                  {filter}
                </button>
              ))}
              <button
                onClick={() => setDocFilter('__custom__')}
                style={{
                  padding: '6px 16px',
                  borderRadius: 20,
                  border: docFilter === '__custom__' ? '2px solid #3b82f6' : '1px solid #d1d5db',
                  backgroundColor: docFilter === '__custom__' ? '#eff6ff' : '#fff',
                  color: docFilter === '__custom__' ? '#1d4ed8' : '#374151',
                  fontWeight: docFilter === '__custom__' ? 600 : 400,
                  fontSize: 13,
                  cursor: 'pointer',
                }}
              >
                Другое
              </button>
              {docFilter === '__custom__' && (
                <input
                  type="text"
                  value={customDocFilter}
                  onChange={(e) => setCustomDocFilter(e.target.value)}
                  placeholder="Введите слово-фильтр..."
                  style={{
                    padding: '6px 12px',
                    borderRadius: 6,
                    border: '1px solid #d1d5db',
                    fontSize: 13,
                    width: 200,
                  }}
                />
              )}
            </div>
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>
              Будут обработаны только строки, содержащие выбранное слово в колонке документа
            </div>
          </div>

          <div className="case-configure-grid">
            {/* Account 3310 Settings */}
            <div className="case-configure-panel">
              <h4 style={{ margin: '0 0 16px 0', color: '#374151' }}>Карточка счёта 3310</h4>
              {account3310Preview && (
                <>
                  <ColumnMapper
                    columns={account3310Preview.columns}
                    mappings={account3310Mappings}
                    fields={ACCOUNT_3310_FIELDS}
                    headerRow={account3310HeaderRow}
                    onHeaderRowChange={handleAccount3310HeaderRowChange}
                    onMappingChange={(key, value) => setAccount3310Mappings({ ...account3310Mappings, [key]: value })}
                    previewData={account3310Preview.data}
                  />
                  <div style={{ marginTop: 16 }}>
                    <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                      Превью данных ({account3310Preview.total_rows} строк всего):
                    </div>
                    <PreviewTable columns={account3310Preview.columns} data={account3310Preview.data} />
                  </div>
                </>
              )}
            </div>

            {/* ESF Report Settings */}
            <div className="case-configure-panel">
              <h4 style={{ margin: '0 0 16px 0', color: '#374151' }}>Реестр ЭСФ</h4>
              {esfPreview && (
                <>
                  <ColumnMapper
                    columns={esfPreview.columns}
                    mappings={esfMappings}
                    fields={ESF_FIELDS}
                    headerRow={esfHeaderRow}
                    onHeaderRowChange={handleEsfHeaderRowChange}
                    onMappingChange={(key, value) => setEsfMappings({ ...esfMappings, [key]: value })}
                    previewData={esfPreview.data}
                  />
                  <div style={{ marginTop: 16 }}>
                    <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>
                      Превью данных ({esfPreview.total_rows} строк всего):
                    </div>
                    <PreviewTable columns={esfPreview.columns} data={esfPreview.data} />
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
            Парсинг карточки 3310, группировка документов, сопоставление с ЭСФ
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
          <ResultTable result={result} caseType="case3" />
        </div>
      )}
    </div>
  )
}
