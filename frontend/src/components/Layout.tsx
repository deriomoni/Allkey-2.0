import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { usersApi } from '../api/client'
import AuthModal from './AuthModal'
import PurchaseModal from './PurchaseModal'

export default function Layout() {
  const { user, isAuthenticated, logout, refreshUser } = useAuth()
  const [showAuth, setShowAuth] = useState(false)
  const [showPurchase, setShowPurchase] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [showUserPopup, setShowUserPopup] = useState(false)
  const [showEditProfile, setShowEditProfile] = useState(false)
  const [editName, setEditName] = useState('')
  const [editPassword, setEditPassword] = useState('')
  const [editLoading, setEditLoading] = useState(false)
  const [editError, setEditError] = useState('')

  const showUpgrade = isAuthenticated && (
    user?.license_status === 'trial' ||
    user?.license_status === 'expired' ||
    (user?.license_expires_at && new Date(user.license_expires_at).getTime() - Date.now() < 7 * 24 * 60 * 60 * 1000)
  )

  const handleProtectedNavClick = (e: React.MouseEvent) => {
    if (!isAuthenticated) {
      e.preventDefault()
      setShowAuth(true)
    }
    setMobileMenuOpen(false)
  }

  const handleOpenEditProfile = () => {
    setEditName(user?.full_name || '')
    setEditPassword('')
    setEditError('')
    setShowUserPopup(false)
    setShowEditProfile(true)
  }

  const handleSaveProfile = async () => {
    setEditLoading(true)
    setEditError('')
    try {
      const data: { full_name?: string; password?: string } = {}
      if (editName && editName !== user?.full_name) data.full_name = editName
      if (editPassword) data.password = editPassword
      if (Object.keys(data).length === 0) {
        setShowEditProfile(false)
        return
      }
      await usersApi.updateMe(data)
      await refreshUser()
      setShowEditProfile(false)
    } catch {
      setEditError('Ошибка при сохранении')
    } finally {
      setEditLoading(false)
    }
  }

  return (
    <>
      <nav className="nav">
        <div className="nav-container">
          <button
            className="nav-hamburger"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              {mobileMenuOpen ? (
                <><path d="M6 6l12 12"/><path d="M18 6L6 18"/></>
              ) : (
                <><path d="M3 12h18"/><path d="M3 6h18"/><path d="M3 18h18"/></>
              )}
            </svg>
          </button>

          <NavLink to="/" className="nav-brand">
            allkey.kz
          </NavLink>

          <div className={`nav-links ${mobileMenuOpen ? 'open' : ''}`}>
            <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''} onClick={() => setMobileMenuOpen(false)}>
              Главная
            </NavLink>
            <NavLink to="/case1" className={({ isActive }) => isActive ? 'active' : ''} onClick={handleProtectedNavClick}>
              Кейс 1
            </NavLink>
            <NavLink to="/case2" className={({ isActive }) => isActive ? 'active' : ''} onClick={handleProtectedNavClick}>
              Кейс 2
            </NavLink>
            <NavLink to="/case3" className={({ isActive }) => isActive ? 'active' : ''} onClick={handleProtectedNavClick}>
              Кейс 3
            </NavLink>
            {isAuthenticated && user?.role === 'admin' && (
              <>
                <NavLink to="/users" className={({ isActive }) => isActive ? 'active' : ''} onClick={() => setMobileMenuOpen(false)}>
                  Пользователи
                </NavLink>
                <NavLink to="/settings" className={({ isActive }) => isActive ? 'active' : ''} onClick={() => setMobileMenuOpen(false)}>
                  Настройки
                </NavLink>
              </>
            )}
            {showUpgrade && (
              <button className="btn btn-upgrade" onClick={() => setShowPurchase(true)}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M7 11V3M3 7l4-4 4 4"/>
                </svg>
                Тарифы
              </button>
            )}
          </div>

          <div className="nav-user">
            {isAuthenticated ? (
              <>
                <div className="nav-user-info">
                  <div className="nav-user-name">{user?.full_name}</div>
                  <div className="nav-user-role">
                    {user?.license_plan_name && user?.license_badge_color ? (
                      <span
                        style={{
                          background: user.license_badge_color,
                          color: 'white',
                          padding: '2px 10px',
                          borderRadius: 50,
                          fontSize: 10,
                          fontWeight: 600,
                        }}
                      >
                        {user.license_plan_name}
                      </span>
                    ) : (
                      user?.role === 'admin' ? 'Администратор' : 'Пользователь'
                    )}
                  </div>
                </div>
                <div className="nav-avatar-wrapper">
                  <div className="nav-avatar" onClick={() => setShowUserPopup(!showUserPopup)}>
                    {user?.full_name?.charAt(0)?.toUpperCase()}
                  </div>
                  {showUserPopup && (
                    <>
                      <div className="nav-popup-overlay" onClick={() => setShowUserPopup(false)} />
                      <div className="nav-user-popup">
                        <div className="nav-popup-name">{user?.full_name}</div>
                        <div className="nav-popup-email">{user?.email}</div>
                        {user?.license_plan_name && user?.license_badge_color && (
                          <span
                            style={{
                              background: user.license_badge_color,
                              color: 'white',
                              padding: '3px 14px',
                              borderRadius: 50,
                              fontSize: 11,
                              fontWeight: 600,
                              display: 'inline-block',
                              marginTop: 8,
                            }}
                          >
                            {user.license_plan_name}
                          </span>
                        )}
                        <button className="nav-popup-edit" onClick={handleOpenEditProfile}>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                          </svg>
                          Редактировать
                        </button>
                        <button className="nav-popup-logout" onClick={() => { setShowUserPopup(false); logout() }}>
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                            <polyline points="16 17 21 12 16 7"/>
                            <line x1="21" y1="12" x2="9" y2="12"/>
                          </svg>
                          Выйти
                        </button>
                      </div>
                    </>
                  )}
                </div>
                <button className="nav-logout" onClick={logout} title="Выйти">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                    <polyline points="16 17 21 12 16 7"/>
                    <line x1="21" y1="12" x2="9" y2="12"/>
                  </svg>
                </button>
              </>
            ) : (
              <button className="btn btn-primary" onClick={() => setShowAuth(true)}>
                Войти
              </button>
            )}
          </div>
        </div>
      </nav>

      {isAuthenticated && user?.license_status === 'trial' && user?.license_expires_at && (() => {
        const expires = new Date(user.license_expires_at!)
        const now = new Date()
        const daysLeft = Math.max(0, Math.ceil((expires.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)))
        const months = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
        const dateStr = `${expires.getDate()} ${months[expires.getMonth()]}`
        const badgeColor = user.license_badge_color || '#ef4444'
        return (
          <div className="trial-banner" style={{ backgroundColor: badgeColor }}>
            <div className="container trial-banner-content">
              <span>Пробный период (осталось {daysLeft} {daysLeft === 1 ? 'день' : daysLeft < 5 ? 'дня' : 'дней'}) до {dateStr}.</span>
              <button className="trial-banner-btn" onClick={() => setShowPurchase(true)}>Узнать тарифы</button>
            </div>
          </div>
        )
      })()}

      <Outlet />

      <AuthModal isOpen={showAuth} onClose={() => setShowAuth(false)} />
      <PurchaseModal isOpen={showPurchase} onClose={() => setShowPurchase(false)} />

      {showEditProfile && (
        <div className="modal-overlay" onClick={() => setShowEditProfile(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setShowEditProfile(false)}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M18 6L6 18"/><path d="M6 6l12 12"/>
              </svg>
            </button>
            <div className="modal-body">
              <h3 style={{ marginBottom: 20, fontSize: 18, fontWeight: 600 }}>Редактировать профиль</h3>
              {editError && <div className="error-message">{editError}</div>}
              <div className="form-group">
                <label>Имя</label>
                <input
                  type="text"
                  value={editName}
                  onChange={e => setEditName(e.target.value)}
                  placeholder="Введите имя"
                />
              </div>
              <div className="form-group">
                <label>Новый пароль</label>
                <input
                  type="password"
                  value={editPassword}
                  onChange={e => setEditPassword(e.target.value)}
                  placeholder="Оставьте пустым, чтобы не менять"
                />
              </div>
              <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 24 }}>
                <button className="btn btn-secondary" onClick={() => setShowEditProfile(false)}>
                  Отмена
                </button>
                <button className="btn btn-primary" onClick={handleSaveProfile} disabled={editLoading}>
                  {editLoading ? 'Сохранение...' : 'Сохранить'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
