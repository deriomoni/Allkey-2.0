import { useEffect, useRef, useState } from 'react'

// Фильтр по столбцу: выпадающий список значений со счётчиками, можно выбрать несколько.
// Описание столбца — одна запись Facet; новый столбец (например, «Статус КГД») = ещё одна запись.

export interface Facet<T> {
  key: string                       // имя параметра в адресе (?regime=general,none)
  label: string                     // подпись кнопки = название столбца
  value: (row: T) => string         // код значения строки ('none' — не установлен)
  labels: Record<string, string>    // код → подпись; порядок ключей = порядок в списке
}

export type FacetSelection = Record<string, Set<string>>

// Выбор держим в адресе страницы (коды значений, без названий компаний — они в URL не попадают).
export function readSelection(facets: Facet<any>[]): FacetSelection {
  const q = new URLSearchParams(window.location.search)
  const sel: FacetSelection = {}
  for (const f of facets) {
    sel[f.key] = new Set((q.get(f.key) || '').split(',').map((s) => s.trim()).filter(Boolean))
  }
  return sel
}

export function writeSelection(facets: Facet<any>[], sel: FacetSelection) {
  const u = new URL(window.location.href)
  for (const f of facets) {
    const v = [...(sel[f.key] || [])]
    if (v.length) u.searchParams.set(f.key, v.join(','))
    else u.searchParams.delete(f.key)
  }
  // запятые в адресе оставляем читаемыми
  window.history.replaceState(null, '', u.pathname + u.search.replace(/%2C/gi, ','))
}

export function matchesFacets<T>(row: T, facets: Facet<T>[], sel: FacetSelection, skip?: string) {
  return facets.every((f) => f.key === skip || !sel[f.key]?.size || sel[f.key].has(f.value(row)))
}

export function ColumnFilter<T>({ facet, rows, selected, onChange }: {
  facet: Facet<T>
  rows: T[]                         // строки, прошедшие все остальные фильтры (кроме этого столбца)
  selected: Set<string>
  onChange: (next: Set<string>) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', esc) }
  }, [open])

  const counts: Record<string, number> = {}
  for (const r of rows) {
    const v = facet.value(r)
    counts[v] = (counts[v] || 0) + 1
  }
  // известные значения — в заданном порядке; незнакомые (если появятся) — в конце
  const values = [...Object.keys(facet.labels), ...Object.keys(counts).filter((v) => !(v in facet.labels))]
    .filter((v) => counts[v] || selected.has(v))

  const toggle = (v: string) => {
    const next = new Set(selected)
    if (next.has(v)) next.delete(v)
    else next.add(v)
    onChange(next)
  }

  const summary = selected.size
    ? [...selected].map((v) => facet.labels[v] || v).join(', ')
    : 'все'

  return (
    <div className="opsx-facet" ref={ref}>
      <button
        type="button"
        className={`opsx-facet-btn ${selected.size ? 'opsx-facet-on' : ''}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {facet.label}: <span className="opsx-facet-sum">{summary}</span> ▾
      </button>
      {open && (
        <div className="opsx-facet-pop" role="listbox" aria-multiselectable="true">
          {values.length === 0 && <div className="opsx-muted opsx-facet-empty">нет значений</div>}
          {values.map((v) => (
            <label key={v} className="opsx-facet-item">
              <input type="checkbox" checked={selected.has(v)} onChange={() => toggle(v)} />
              <span className="opsx-facet-label">{facet.labels[v] || v}</span>
              <span className="opsx-facet-count">{counts[v] || 0}</span>
            </label>
          ))}
          {selected.size > 0 && (
            <button type="button" className="opsx-link opsx-facet-clear" onClick={() => onChange(new Set())}>
              Сбросить
            </button>
          )}
        </div>
      )}
    </div>
  )
}
