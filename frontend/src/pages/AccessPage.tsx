import { useState, useEffect } from 'react'
import { useAuth } from '../auth/AuthContext'
import { servicesApi, ServiceAdmin } from '../api/client'
import { Navigate } from 'react-router-dom'

export default function AccessPage() {
  const { user, refreshUser } = useAuth()
  const [services, setServices] = useState<ServiceAdmin[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [savingCode, setSavingCode] = useState<string | null>(null)

  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  const loadServices = async () => {
    try {
      const data = await servicesApi.getAll()
      setServices(data)
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || 'Ошибка загрузки сервисов')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadServices()
  }, [])

  const applyUpdate = async (code: string, fn: () => Promise<ServiceAdmin>) => {
    setSavingCode(code)
    setError('')
    try {
      const updated = await fn()
      setServices((prev) => prev.map((s) => (s.code === code ? updated : s)))
      // A change here can alter what the admin themselves sees in the menu.
      await refreshUser()
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || 'Ошибка сохранения')
      await loadServices()
    } finally {
      setSavingCode(null)
    }
  }

  const toggleRole = (svc: ServiceAdmin, role: 'employee' | 'client') => {
    const has = svc.roles.includes(role)
    const roles = has ? svc.roles.filter((r) => r !== role) : [...svc.roles, role]
    applyUpdate(svc.code, () => servicesApi.setAccess(svc.code, roles))
  }

  const toggleEnabled = (svc: ServiceAdmin) => {
    applyUpdate(svc.code, () => servicesApi.update(svc.code, { is_enabled: !svc.is_enabled }))
  }

  const changeStatus = (svc: ServiceAdmin, status: 'beta' | 'production') => {
    applyUpdate(svc.code, () => servicesApi.update(svc.code, { status }))
  }

  if (loading) {
    return <div className="loading">Загрузка...</div>
  }

  return (
    <div className="container">
      <h1 style={{ marginBottom: 24 }}>Доступы к сервисам</h1>

      {error && <div className="error-message">{error}</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Сервис</th>
              <th>Статус</th>
              <th style={{ textAlign: 'center' }}>Вкл.</th>
              <th style={{ textAlign: 'center' }}>Сотрудники</th>
              <th style={{ textAlign: 'center' }}>Клиенты</th>
            </tr>
          </thead>
          <tbody>
            {services.map((svc) => (
              <tr key={svc.code} style={{ opacity: savingCode === svc.code ? 0.6 : 1 }}>
                <td>
                  <div style={{ fontWeight: 600 }}>{svc.title}</div>
                  <div style={{ fontSize: 12, color: '#94a3b8' }}>{svc.code}</div>
                </td>
                <td>
                  <select
                    value={svc.status}
                    onChange={(e) => changeStatus(svc, e.target.value as 'beta' | 'production')}
                    disabled={savingCode === svc.code}
                  >
                    <option value="production">production</option>
                    <option value="beta">beta</option>
                  </select>
                </td>
                <td style={{ textAlign: 'center' }}>
                  <input
                    className="access-checkbox"
                    type="checkbox"
                    checked={svc.is_enabled}
                    onChange={() => toggleEnabled(svc)}
                    disabled={savingCode === svc.code}
                  />
                </td>
                <td style={{ textAlign: 'center' }}>
                  <input
                    className="access-checkbox"
                    type="checkbox"
                    checked={svc.roles.includes('employee')}
                    onChange={() => toggleRole(svc, 'employee')}
                    disabled={savingCode === svc.code}
                  />
                </td>
                <td style={{ textAlign: 'center' }}>
                  <input
                    className="access-checkbox"
                    type="checkbox"
                    checked={svc.roles.includes('client')}
                    onChange={() => toggleRole(svc, 'client')}
                    disabled={savingCode === svc.code}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <p className="access-note">
          Владелец (администратор) всегда видит все сервисы — включая beta и отключённые, — поэтому
          отдельной колонки для него нет. Галочки управляют доступом сотрудников и клиентов;
          выключатель «Вкл.» полностью скрывает сервис у всех, кроме владельца.
        </p>
      </div>
    </div>
  )
}
