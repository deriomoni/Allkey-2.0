interface DateExtractConfig {
  hasDateColumn: boolean
  dateFormat: string // 'DD.MM.YYYY' | 'DD.MM.YY'
  dateSourceColumn: number
}

interface ColumnMapperProps {
  columns: string[]
  mappings: Record<string, number>
  fields: { key: string; label: string }[]
  onMappingChange: (key: string, value: number) => void
  headerRow: number
  onHeaderRowChange: (value: number) => void
  previewData?: (string | number | null)[][]
  dateExtract?: DateExtractConfig
  onDateExtractChange?: (config: DateExtractConfig) => void
}

export type { DateExtractConfig }

// Forward-fill "nan" for merged cells: if col is "nan", use previous column's name
function fillMergedHeaders(columns: string[]): string[] {
  const result: string[] = []
  let last = ''
  for (const col of columns) {
    if (col && col !== 'nan') {
      last = col
      result.push(col)
    } else {
      result.push(last || `Колонка ${result.length}`)
    }
  }
  return result
}

const DATE_FORMATS = [
  { value: 'DD.MM.YYYY', label: 'DD.MM.YYYY (01.01.2026)' },
  { value: 'DD.MM.YY', label: 'DD.MM.YY (01.01.26)' },
]

export default function ColumnMapper({
  columns,
  mappings,
  fields,
  onMappingChange,
  headerRow,
  onHeaderRowChange,
  previewData,
  dateExtract,
  onDateExtractChange,
}: ColumnMapperProps) {
  const filledColumns = fillMergedHeaders(columns)

  // Sample from 3rd data row (header+3): skips sub-headers and saldo rows
  const sampleData = previewData && previewData.length > 2 ? previewData[2]
    : previewData && previewData.length > 0 ? previewData[previewData.length - 1]
    : undefined

  const formatSample = (value: string | number | null): string => {
    if (value === null || value === undefined || value === '') return ''
    const s = String(value)
    if (s.toLowerCase() === 'nan') return ''
    return s.length > 20 ? s.slice(0, 20) + '…' : s
  }

  const getOptionLabel = (col: string, idx: number): string => {
    if (!sampleData || idx >= sampleData.length) return `${idx}: ${col}`
    const sample = formatSample(sampleData[idx])
    if (!sample) return `${idx}: ${col}`
    return `${idx}: ${col}  ⟶  ${sample}`
  }

  const showDateExtract = dateExtract && onDateExtractChange
  const visibleFields = showDateExtract && !dateExtract.hasDateColumn
    ? fields.filter(f => f.key !== 'date')
    : fields

  return (
    <div>
      <div className="form-group">
        <label>Строка заголовка (начиная с 0)</label>
        <input
          type="number"
          min="0"
          value={headerRow}
          onChange={(e) => onHeaderRowChange(parseInt(e.target.value) || 0)}
        />
      </div>

      {showDateExtract && (
        <div style={{ marginBottom: 12, padding: '10px 12px', backgroundColor: '#f0f9ff', borderRadius: 6, border: '1px solid #bfdbfe' }}>
          <div className="form-group" style={{ marginBottom: dateExtract.hasDateColumn ? 0 : 8 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={!dateExtract.hasDateColumn}
                onChange={(e) => onDateExtractChange({
                  ...dateExtract,
                  hasDateColumn: !e.target.checked,
                })}
                style={{ width: 16, height: 16 }}
              />
              <span style={{ fontSize: 13 }}>Нет отдельной колонки с датой (извлечь из текста)</span>
            </label>
          </div>

          {!dateExtract.hasDateColumn && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <div className="form-group" style={{ margin: 0 }}>
                <label style={{ fontSize: 12 }}>Формат даты</label>
                <select
                  value={dateExtract.dateFormat}
                  onChange={(e) => onDateExtractChange({ ...dateExtract, dateFormat: e.target.value })}
                >
                  {DATE_FORMATS.map(f => (
                    <option key={f.value} value={f.value}>{f.label}</option>
                  ))}
                </select>
              </div>
              <div className="form-group" style={{ margin: 0 }}>
                <label style={{ fontSize: 12 }}>Извлечь дату из колонки</label>
                <select
                  value={dateExtract.dateSourceColumn}
                  onChange={(e) => onDateExtractChange({ ...dateExtract, dateSourceColumn: parseInt(e.target.value) })}
                >
                  {filledColumns.map((col, idx) => (
                    <option key={idx} value={idx}>
                      {getOptionLabel(col, idx)}
                    </option>
                  ))}
                </select>
                {sampleData && dateExtract.dateSourceColumn >= 0 && dateExtract.dateSourceColumn < sampleData.length && (
                  <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                    Пример: <span style={{ fontFamily: 'monospace', color: '#1d4ed8' }}>
                      {formatSample(sampleData[dateExtract.dateSourceColumn])}
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="column-mapper">
        {visibleFields.map(field => {
          const selectedIdx = mappings[field.key] ?? -1
          const sample = sampleData && selectedIdx >= 0 && selectedIdx < sampleData.length
            ? formatSample(sampleData[selectedIdx])
            : null

          return (
            <div key={field.key} className="form-group">
              <label>{field.label}</label>
              <select
                value={selectedIdx}
                onChange={(e) => onMappingChange(field.key, parseInt(e.target.value))}
              >
                <option value={-1}>Не выбрано</option>
                {filledColumns.map((col, idx) => (
                  <option key={idx} value={idx}>
                    {getOptionLabel(col, idx)}
                  </option>
                ))}
              </select>
              {sample && (
                <div style={{ fontSize: 11, color: '#6b7280', marginTop: 2 }}>
                  Пример: <span style={{ fontFamily: 'monospace', color: '#1d4ed8' }}>{sample}</span>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
