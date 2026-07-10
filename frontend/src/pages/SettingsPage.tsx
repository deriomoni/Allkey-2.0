import { useState, useEffect } from 'react'
import { useAuth } from '../auth/AuthContext'
import { licensesApi, settingsApi, LicensePlan } from '../api/client'
import { Navigate } from 'react-router-dom'

export default function SettingsPage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<'plans' | 'contacts'>('plans')

  // Plans state
  const [plans, setPlans] = useState<LicensePlan[]>([])
  const [plansLoading, setPlansLoading] = useState(true)
  const [showPlanForm, setShowPlanForm] = useState(false)
  const [editingPlan, setEditingPlan] = useState<LicensePlan | null>(null)
  const [planName, setPlanName] = useState('')
  const [planDescription, setPlanDescription] = useState('')
  const [planPrice, setPlanPrice] = useState('')
  const [planDuration, setPlanDuration] = useState('')
  const [planActive, setPlanActive] = useState(true)
  const [planDefault, setPlanDefault] = useState(false)
  const [planBadgeColor, setPlanBadgeColor] = useState('#ef4444')
  const [planFormLoading, setPlanFormLoading] = useState(false)

  // Settings state
  const [whatsapp, setWhatsapp] = useState('')
  const [telegram, setTelegram] = useState('')
  const [kaspiUrl, setKaspiUrl] = useState('')
  const [settingsLoading, setSettingsLoading] = useState(true)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [settingsSuccess, setSettingsSuccess] = useState('')

  const [error, setError] = useState('')

  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  const loadPlans = async () => {
    try {
      const data = await licensesApi.getAllPlans()
      setPlans(data)
    } catch { setError('Ошибка загрузки тарифов') }
    finally { setPlansLoading(false) }
  }

  const loadSettings = async () => {
    try {
      const data = await settingsApi.getAll()
      setWhatsapp(data.whatsapp_number || '')
      setTelegram(data.telegram_link || '')
      setKaspiUrl(data.kaspi_payment_url || '')
    } catch { setError('Ошибка загрузки настроек') }
    finally { setSettingsLoading(false) }
  }

  useEffect(() => {
    loadPlans()
    loadSettings()
  }, [])

  const resetPlanForm = () => {
    setPlanName('')
    setPlanDescription('')
    setPlanPrice('')
    setPlanDuration('')
    setPlanActive(true)
    setPlanDefault(false)
    setPlanBadgeColor('#ef4444')
    setEditingPlan(null)
    setShowPlanForm(false)
  }

  const handleEditPlan = (plan: LicensePlan) => {
    setEditingPlan(plan)
    setPlanName(plan.name)
    setPlanDescription(plan.description)
    setPlanPrice(String(plan.price))
    setPlanDuration(String(plan.duration_days))
    setPlanActive(plan.is_active)
    setPlanDefault(plan.is_default)
    setPlanBadgeColor(plan.badge_color || '#ef4444')
    setShowPlanForm(true)
  }

  const handleSavePlan = async (e: React.FormEvent) => {
    e.preventDefault()
    setPlanFormLoading(true)
    setError('')

    try {
      const data = {
        name: planName,
        description: planDescription,
        price: parseFloat(planPrice) || 0,
        duration_days: parseInt(planDuration) || 30,
        is_active: planActive,
        is_default: planDefault,
        badge_color: planBadgeColor,
      }

      if (editingPlan) {
        await licensesApi.updatePlan(editingPlan.id, data)
      } else {
        await licensesApi.createPlan(data)
      }
      resetPlanForm()
      await loadPlans()
    } catch { setError('Ошибка сохранения тарифа') }
    finally { setPlanFormLoading(false) }
  }

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault()
    setSettingsSaving(true)
    setError('')
    setSettingsSuccess('')

    try {
      await settingsApi.update({
        whatsapp_number: whatsapp,
        telegram_link: telegram,
        kaspi_payment_url: kaspiUrl,
      })
      setSettingsSuccess('Настройки сохранены')
      setTimeout(() => setSettingsSuccess(''), 3000)
    } catch { setError('Ошибка сохранения настроек') }
    finally { setSettingsSaving(false) }
  }

  const formatDuration = (days: number) => {
    if (days <= 7) return `${days} дн.`
    if (days <= 30) return `${days} дн.`
    if (days <= 180) return `${Math.round(days / 30)} мес.`
    return `${Math.round(days / 365)} г.`
  }

  return (
    <div>
      <h1 style={{ marginBottom: 24 }}>Настройки</h1>

      {error && <div className="error-message">{error}</div>}

      <div className="settings-tabs">
        <button
          className={`settings-tab ${activeTab === 'plans' ? 'active' : ''}`}
          onClick={() => setActiveTab('plans')}
        >
          Тарифные планы
        </button>
        <button
          className={`settings-tab ${activeTab === 'contacts' ? 'active' : ''}`}
          onClick={() => setActiveTab('contacts')}
        >
          Контакты для оплаты
        </button>
      </div>

      {activeTab === 'plans' && (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
            <button className="btn btn-primary" onClick={() => { resetPlanForm(); setShowPlanForm(true) }}>
              Добавить тариф
            </button>
          </div>

          {showPlanForm && (
            <div className="card" style={{ marginBottom: 24 }}>
              <h3 style={{ marginBottom: 16 }}>{editingPlan ? 'Редактировать тариф' : 'Новый тариф'}</h3>
              <form onSubmit={handleSavePlan}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <div className="form-group">
                    <label>Название</label>
                    <input type="text" value={planName} onChange={e => setPlanName(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label>Цена (тенге)</label>
                    <input type="number" value={planPrice} onChange={e => setPlanPrice(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label>Срок (дней)</label>
                    <input type="number" value={planDuration} onChange={e => setPlanDuration(e.target.value)} required />
                  </div>
                  <div className="form-group">
                    <label>Статус</label>
                    <select value={planActive ? 'true' : 'false'} onChange={e => setPlanActive(e.target.value === 'true')}>
                      <option value="true">Активный</option>
                      <option value="false">Неактивный</option>
                    </select>
                  </div>
                </div>
                <div className="form-group">
                  <label>Описание</label>
                  <input type="text" value={planDescription} onChange={e => setPlanDescription(e.target.value)} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <div className="form-group">
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                      <input
                        type="checkbox"
                        checked={planDefault}
                        onChange={e => setPlanDefault(e.target.checked)}
                        style={{ width: 18, height: 18, accentColor: '#0d9488' }}
                      />
                      Назначать при регистрации
                    </label>
                    <span style={{ fontSize: 12, color: '#94a3b8', marginTop: 4, display: 'block' }}>
                      Только один тариф может быть назначен по умолчанию
                    </span>
                  </div>
                  <div className="form-group">
                    <label>Цвет бейджа</label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <input
                        type="color"
                        value={planBadgeColor}
                        onChange={e => setPlanBadgeColor(e.target.value)}
                        style={{ width: 40, height: 36, padding: 2, border: '1px solid #e2e8f0', borderRadius: 6, cursor: 'pointer' }}
                      />
                      <span
                        style={{
                          background: planBadgeColor,
                          color: 'white',
                          padding: '4px 14px',
                          borderRadius: 50,
                          fontSize: 12,
                          fontWeight: 600,
                        }}
                      >
                        {planName || 'Превью'}
                      </span>
                      <input
                        type="text"
                        value={planBadgeColor}
                        onChange={e => setPlanBadgeColor(e.target.value)}
                        style={{ width: 90, fontSize: 13 }}
                        placeholder="#ef4444"
                      />
                    </div>
                  </div>
                </div>
                <div className="actions">
                  <button type="button" className="btn btn-secondary" onClick={resetPlanForm}>Отмена</button>
                  <button type="submit" className="btn btn-primary" disabled={planFormLoading}>
                    {planFormLoading ? 'Сохранение...' : 'Сохранить'}
                  </button>
                </div>
              </form>
            </div>
          )}

          <div className="card">
            {plansLoading ? (
              <div className="loading">Загрузка...</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Название</th>
                    <th>Цена</th>
                    <th>Срок</th>
                    <th>Описание</th>
                    <th>Статус</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {plans.map(plan => (
                    <tr key={plan.id}>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span
                            style={{
                              background: plan.badge_color || '#ef4444',
                              color: 'white',
                              padding: '3px 12px',
                              borderRadius: 50,
                              fontSize: 12,
                              fontWeight: 600,
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {plan.name}
                          </span>
                          {plan.is_default && (
                            <span style={{ fontSize: 11, color: '#0d9488', fontWeight: 500 }}>
                              (при регистрации)
                            </span>
                          )}
                        </div>
                      </td>
                      <td>{new Intl.NumberFormat('ru-RU').format(plan.price)} ₸</td>
                      <td>{formatDuration(plan.duration_days)}</td>
                      <td style={{ color: '#64748b', fontSize: 13 }}>{plan.description}</td>
                      <td>
                        <span className={`license-badge ${plan.is_active ? 'active' : 'expired'}`}>
                          {plan.is_active ? 'Активный' : 'Неактивный'}
                        </span>
                      </td>
                      <td>
                        <button
                          className="btn btn-secondary"
                          style={{ padding: '6px 12px', fontSize: 12 }}
                          onClick={() => handleEditPlan(plan)}
                        >
                          Изменить
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {activeTab === 'contacts' && (
        <div className="card">
          {settingsLoading ? (
            <div className="loading">Загрузка...</div>
          ) : (
            <form onSubmit={handleSaveSettings}>
              {settingsSuccess && <div className="success-message">{settingsSuccess}</div>}
              <div className="form-group">
                <label>WhatsApp номер</label>
                <input
                  type="text"
                  value={whatsapp}
                  onChange={e => setWhatsapp(e.target.value)}
                  placeholder="+7 777 123 4567"
                />
              </div>
              <div className="form-group">
                <label>Telegram ссылка</label>
                <input
                  type="text"
                  value={telegram}
                  onChange={e => setTelegram(e.target.value)}
                  placeholder="https://t.me/username"
                />
              </div>
              <div className="form-group">
                <label>Kaspi ссылка для оплаты</label>
                <input
                  type="text"
                  value={kaspiUrl}
                  onChange={e => setKaspiUrl(e.target.value)}
                  placeholder="https://pay.kaspi.kz/pay/..."
                />
              </div>
              <div className="actions">
                <button type="submit" className="btn btn-primary" disabled={settingsSaving}>
                  {settingsSaving ? 'Сохранение...' : 'Сохранить'}
                </button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  )
}
