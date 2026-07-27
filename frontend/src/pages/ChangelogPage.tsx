import { useState, useEffect } from 'react'
import { useAuth } from '../auth/AuthContext'
import { changelogApi, ChangelogEntry, ChangelogInput } from '../api/client'

type Category = 'fix' | 'feature' | 'improvement'

const CATEGORY_META: Record<Category, { label: string; bg: string; color: string }> = {
  fix: { label: 'Исправление', bg: '#fee2e2', color: '#b91c1c' },
  feature: { label: 'Новое', bg: '#dcfce7', color: '#15803d' },
  improvement: { label: 'Улучшение', bg: '#dbeafe', color: '#1d4ed8' },
}

const CATEGORY_ORDER: Category[] = ['fix', 'feature', 'improvement']

function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso
}

function today(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

const emptyForm: ChangelogInput = { date: today(), category: 'fix', service_code: '', title: '', body: '' }

export default function ChangelogPage() {
  const { user, services } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [entries, setEntries] = useState<ChangelogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<ChangelogInput>(emptyForm)
  const [saving, setSaving] = useState(false)

  const [editing, setEditing] = useState<ChangelogEntry | null>(null)
  const [editForm, setEditForm] = useState<ChangelogInput>(emptyForm)
  const [editSaving, setEditSaving] = useState(false)

  // Название сверки по коду — из доступных пользователю сервисов, иначе сам код.
  const serviceLabel = (code: string | null | undefined): string => {
    if (!code) return ''
    return services.find((s) => s.code === code)?.title || code
  }

  const load = async () => {
    try {
      setEntries(await changelogApi.getAll())
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || 'Ошибка загрузки обновлений')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await changelogApi.create({ ...form, service_code: form.service_code || null })
      setForm({ ...emptyForm, date: today() })
      setShowForm(false)
      await load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || 'Ошибка сохранения')
    } finally {
      setSaving(false)
    }
  }

  const openEdit = (entry: ChangelogEntry) => {
    setEditing(entry)
    setEditForm({
      date: entry.date.slice(0, 10),
      category: entry.category,
      service_code: entry.service_code || '',
      title: entry.title,
      body: entry.body || '',
    })
    setError('')
  }

  const handleEditSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editing) return
    setEditSaving(true)
    setError('')
    try {
      await changelogApi.update(editing.id, { ...editForm, service_code: editForm.service_code || null })
      setEditing(null)
      await load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || 'Ошибка сохранения')
    } finally {
      setEditSaving(false)
    }
  }

  const handleDelete = async (entry: ChangelogEntry) => {
    if (!confirm('Удалить эту запись?')) return
    setError('')
    try {
      await changelogApi.delete(entry.id)
      await load()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || 'Ошибка удаления')
    }
  }

  const categoryFields = (value: ChangelogInput, set: (v: ChangelogInput) => void) => (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div className="form-group">
          <label>Дата</label>
          <input type="date" value={value.date} onChange={(e) => set({ ...value, date: e.target.value })} required />
        </div>
        <div className="form-group">
          <label>Категория</label>
          <select value={value.category} onChange={(e) => set({ ...value, category: e.target.value as Category })}>
            {CATEGORY_ORDER.map((c) => (
              <option key={c} value={c}>{CATEGORY_META[c].label}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="form-group">
        <label>Сверка (необязательно)</label>
        <select
          value={value.service_code || ''}
          onChange={(e) => set({ ...value, service_code: e.target.value })}
        >
          <option value="">— не привязано —</option>
          {services.map((s) => (
            <option key={s.code} value={s.code}>{s.title}</option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <label>Заголовок</label>
        <input type="text" value={value.title} onChange={(e) => set({ ...value, title: e.target.value })} required />
      </div>
      <div className="form-group">
        <label>Описание</label>
        <textarea
          value={value.body || ''}
          onChange={(e) => set({ ...value, body: e.target.value })}
          rows={5}
          style={{ resize: 'vertical' }}
        />
      </div>
    </>
  )

  if (loading) {
    return <div className="loading">Загрузка...</div>
  }

  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1>Обновления</h1>
        {isAdmin && (
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Отмена' : 'Добавить запись'}
          </button>
        )}
      </div>

      {error && <div className="error-message">{error}</div>}

      {isAdmin && showForm && (
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 style={{ marginBottom: 16 }}>Новая запись</h3>
          <form onSubmit={handleCreate}>
            {categoryFields(form, setForm)}
            <div className="actions">
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Сохранение...' : 'Опубликовать'}
              </button>
            </div>
          </form>
        </div>
      )}

      {entries.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', color: '#64748b', padding: 40 }}>
          Пока нет записей об обновлениях.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {entries.map((entry) => {
            const meta = CATEGORY_META[entry.category] || { label: entry.category, bg: '#e2e8f0', color: '#475569' }
            const svc = serviceLabel(entry.service_code)
            return (
              <div key={entry.id} className="card">
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 10 }}>
                  <span
                    style={{
                      background: meta.bg, color: meta.color,
                      padding: '3px 12px', borderRadius: 50, fontSize: 12, fontWeight: 600,
                    }}
                  >
                    {meta.label}
                  </span>
                  <span style={{ fontSize: 13, color: '#64748b' }}>{formatDate(entry.date)}</span>
                  {svc && (
                    <span
                      style={{
                        background: '#f1f5f9', color: '#475569',
                        padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 500,
                      }}
                    >
                      {svc}
                    </span>
                  )}
                  {isAdmin && (
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '6px 10px', fontSize: 12 }}
                        onClick={() => openEdit(entry)}
                      >
                        Изменить
                      </button>
                      <button
                        className="btn btn-danger"
                        style={{ padding: '6px 10px', fontSize: 12 }}
                        onClick={() => handleDelete(entry)}
                      >
                        Удалить
                      </button>
                    </div>
                  )}
                </div>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: entry.body ? 8 : 0 }}>{entry.title}</div>
                {entry.body && (
                  <div style={{ color: '#334155', fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                    {entry.body}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {editing && (
        <div className="modal-overlay" onClick={() => setEditing(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setEditing(null)}>
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>
            <div className="modal-body">
              <h3 style={{ marginBottom: 16 }}>Редактирование записи</h3>
              <form onSubmit={handleEditSave}>
                {categoryFields(editForm, setEditForm)}
                <div className="actions">
                  <button type="button" className="btn btn-secondary" onClick={() => setEditing(null)}>Отмена</button>
                  <button type="submit" className="btn btn-primary" disabled={editSaving}>
                    {editSaving ? 'Сохранение...' : 'Сохранить'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
