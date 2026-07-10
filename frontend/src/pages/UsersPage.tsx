import { useState, useEffect } from 'react'
import { useAuth } from '../auth/AuthContext'
import { usersApi, licensesApi, User, LicensePlan } from '../api/client'
import { Navigate } from 'react-router-dom'

export default function UsersPage() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)

  // Create form state
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState('user')
  const [formLoading, setFormLoading] = useState(false)

  // Edit form state
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [editFullName, setEditFullName] = useState('')
  const [editPassword, setEditPassword] = useState('')
  const [editLoading, setEditLoading] = useState(false)

  // License assignment state
  const [assigningUser, setAssigningUser] = useState<User | null>(null)
  const [plans, setPlans] = useState<LicensePlan[]>([])
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null)
  const [assignLoading, setAssignLoading] = useState(false)

  // Redirect if not admin
  if (currentUser?.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  const loadUsers = async () => {
    try {
      const data = await usersApi.getAll()
      setUsers(data)
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Ошибка загрузки пользователей')
    } finally {
      setLoading(false)
    }
  }

  const loadPlans = async () => {
    try {
      const data = await licensesApi.getAllPlans()
      setPlans(data)
    } catch { /* ignore */ }
  }

  useEffect(() => {
    loadUsers()
    loadPlans()
  }, [])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormLoading(true)
    setError('')

    try {
      await usersApi.create({ email, password, full_name: fullName, role })
      setShowForm(false)
      setEmail('')
      setPassword('')
      setFullName('')
      setRole('user')
      await loadUsers()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Ошибка создания пользователя')
    } finally {
      setFormLoading(false)
    }
  }

  const handleEditOpen = (user: User) => {
    setEditingUser(user)
    setEditFullName(user.full_name)
    setEditPassword('')
    setError('')
  }

  const handleEditSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingUser) return
    setEditLoading(true)
    setError('')

    try {
      const data: { full_name?: string; password?: string } = {}
      if (editFullName !== editingUser.full_name) data.full_name = editFullName
      if (editPassword) data.password = editPassword

      if (Object.keys(data).length === 0) {
        setEditingUser(null)
        return
      }

      await usersApi.update(editingUser.id, data)
      setEditingUser(null)
      await loadUsers()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Ошибка обновления пользователя')
    } finally {
      setEditLoading(false)
    }
  }

  const handleDelete = async (userId: number) => {
    if (!confirm('Вы уверены, что хотите удалить этого пользователя?')) {
      return
    }

    try {
      await usersApi.delete(userId)
      await loadUsers()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Ошибка удаления пользователя')
    }
  }

  const handleAssignLicense = async () => {
    if (!assigningUser || !selectedPlanId) return
    setAssignLoading(true)
    setError('')

    try {
      await licensesApi.assign(assigningUser.id, selectedPlanId)
      setAssigningUser(null)
      setSelectedPlanId(null)
      await loadUsers()
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } }
      setError(error.response?.data?.detail || 'Ошибка назначения лицензии')
    } finally {
      setAssignLoading(false)
    }
  }

  const getLicenseBadge = (user: User) => {
    const status = user.license_status || 'none'

    if (status === 'none') {
      return <span className="license-badge none">Нет</span>
    }

    const statusLabel: Record<string, string> = {
      active: 'Активна',
      trial: 'Trial',
      expired: 'Истекла',
    }

    // Use badge_color from the plan if available
    if (user.license_badge_color && user.license_plan_name) {
      return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              background: user.license_badge_color,
              color: 'white',
              padding: '3px 12px',
              borderRadius: 50,
              fontSize: 12,
              fontWeight: 600,
              whiteSpace: 'nowrap',
            }}
          >
            {user.license_plan_name}
          </span>
          {status === 'expired' && (
            <span style={{ fontSize: 11, color: '#ef4444' }}>(истекла)</span>
          )}
        </span>
      )
    }

    return (
      <span className={`license-badge ${status}`}>
        {statusLabel[status] || status}
      </span>
    )
  }

  if (loading) {
    return <div className="loading">Загрузка...</div>
  }

  return (
    <div className="container">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <h1>Управление пользователями</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Отмена' : 'Добавить пользователя'}
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      {showForm && (
        <div className="card" style={{ marginBottom: 24 }}>
          <h3 style={{ marginBottom: 16 }}>Новый пользователь</h3>
          <form onSubmit={handleCreate}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="form-group">
                <label>ФИО</label>
                <input type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
              </div>
              <div className="form-group">
                <label>Email</label>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <div className="form-group">
                <label>Пароль</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </div>
              <div className="form-group">
                <label>Роль</label>
                <select value={role} onChange={(e) => setRole(e.target.value)}>
                  <option value="user">Пользователь</option>
                  <option value="admin">Администратор</option>
                </select>
              </div>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn-primary" disabled={formLoading}>
                {formLoading ? 'Создание...' : 'Создать'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Edit user modal */}
      {editingUser && (
        <div className="modal-overlay" onClick={() => setEditingUser(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setEditingUser(null)}>
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>
            <div className="modal-body">
              <h3 style={{ marginBottom: 16 }}>Редактирование: {editingUser.email}</h3>
              <form onSubmit={handleEditSave}>
                <div className="form-group">
                  <label>ФИО</label>
                  <input type="text" value={editFullName} onChange={(e) => setEditFullName(e.target.value)} required />
                </div>
                <div className="form-group">
                  <label>Новый пароль (оставьте пустым, если не меняется)</label>
                  <input type="password" value={editPassword} onChange={(e) => setEditPassword(e.target.value)} placeholder="Введите новый пароль" />
                </div>
                <div className="actions">
                  <button type="button" className="btn btn-secondary" onClick={() => setEditingUser(null)}>Отмена</button>
                  <button type="submit" className="btn btn-primary" disabled={editLoading}>
                    {editLoading ? 'Сохранение...' : 'Сохранить'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Assign license modal */}
      {assigningUser && (
        <div className="modal-overlay" onClick={() => setAssigningUser(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setAssigningUser(null)}>
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 5l10 10M15 5L5 15" />
              </svg>
            </button>
            <div className="modal-body">
              <h3 style={{ marginBottom: 4 }}>Назначить лицензию</h3>
              <p style={{ color: '#64748b', marginBottom: 20, fontSize: 14 }}>{assigningUser.full_name} ({assigningUser.email})</p>

              <div className="form-group">
                <label>Тарифный план</label>
                <select
                  value={selectedPlanId || ''}
                  onChange={e => setSelectedPlanId(Number(e.target.value) || null)}
                >
                  <option value="">Выберите план...</option>
                  {plans.map(plan => (
                    <option key={plan.id} value={plan.id}>
                      {plan.name} — {plan.duration_days} дн. — {new Intl.NumberFormat('ru-RU').format(plan.price)} ₸
                    </option>
                  ))}
                </select>
              </div>

              <div className="actions">
                <button type="button" className="btn btn-secondary" onClick={() => setAssigningUser(null)}>Отмена</button>
                <button
                  className="btn btn-primary"
                  disabled={!selectedPlanId || assignLoading}
                  onClick={handleAssignLicense}
                >
                  {assignLoading ? 'Назначение...' : 'Назначить'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>ФИО</th>
              <th>Email</th>
              <th>Роль</th>
              <th>Лицензия</th>
              <th>Срок</th>
              <th>Дата создания</th>
              <th>Действия</th>
            </tr>
          </thead>
          <tbody>
            {users.map(user => (
              <tr key={user.id}>
                <td>{user.id}</td>
                <td>{user.full_name}</td>
                <td>{user.email}</td>
                <td>{user.role === 'admin' ? 'Администратор' : 'Пользователь'}</td>
                <td>
                  {getLicenseBadge(user)}
                </td>
                <td style={{ fontSize: 13, color: '#64748b' }}>
                  {user.license_expires_at
                    ? new Date(user.license_expires_at).toLocaleDateString('ru-RU')
                    : '—'
                  }
                </td>
                <td>{new Date(user.created_at).toLocaleDateString('ru-RU')}</td>
                <td>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '6px 10px', fontSize: 12 }}
                      onClick={() => handleEditOpen(user)}
                    >
                      Изменить
                    </button>
                    <button
                      className="btn btn-primary"
                      style={{ padding: '6px 10px', fontSize: 12 }}
                      onClick={() => { setAssigningUser(user); setSelectedPlanId(null) }}
                    >
                      Лицензия
                    </button>
                    {user.id !== currentUser?.id && (
                      <button
                        className="btn btn-danger"
                        style={{ padding: '6px 10px', fontSize: 12 }}
                        onClick={() => handleDelete(user.id)}
                      >
                        Удалить
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
