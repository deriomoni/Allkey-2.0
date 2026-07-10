import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import AuthModal from '../components/AuthModal'
import PurchaseModal from '../components/PurchaseModal'

export default function LandingPage() {
  const { user, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const [showAuth, setShowAuth] = useState(false)
  const [showPurchase, setShowPurchase] = useState(false)

  const isLicenseExpired = user?.license_status === 'expired'

  const handleCaseClick = (path: string) => {
    if (!isAuthenticated) {
      setShowAuth(true)
      return
    }
    if (isLicenseExpired) {
      setShowPurchase(true)
      return
    }
    navigate(path)
  }

  return (
    <>
      <div className="container">
        {/* License expired banner */}
        {isAuthenticated && isLicenseExpired && (
          <div className="license-banner">
            <span className="license-banner-text">
              Ваш срок подписки истёк. Продлите доступ для продолжения работы.
            </span>
            <button className="btn" onClick={() => setShowPurchase(true)}>
              Продлить
            </button>
          </div>
        )}

        {/* Hero */}
        <div className="landing-hero">
          <h1>
            {isAuthenticated
              ? `Добро пожаловать, ${user?.full_name}!`
              : 'Автоматизация финансовой сверки'
            }
          </h1>
          <p>Выберите тип сверки для начала работы</p>
        </div>

        {/* Case cards */}
        <div className="dashboard-cards">
          <div
            className={`dashboard-card ${isLicenseExpired ? 'disabled' : ''}`}
            onClick={() => handleCaseClick('/case1')}
          >
            <div className="dashboard-card-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M16 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8Z"/>
                <path d="M15 3v4a1 1 0 0 0 1 1h4"/>
                <path d="m9 15 2 2 4-4"/>
              </svg>
            </div>
            <h3>Кейс 1: Карточка 6010 vs ЭСФ</h3>
            <p>Сверка выручки и выставленных счетов для контроля корректности данных.</p>
            <button className="dashboard-card-btn">
              Начать сверку
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M3 8h10M9 4l4 4-4 4"/>
              </svg>
            </button>
          </div>

          <div
            className={`dashboard-card ${isLicenseExpired ? 'disabled' : ''}`}
            onClick={() => handleCaseClick('/case2')}
          >
            <div className="dashboard-card-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
              </svg>
            </div>
            <h3>Кейс 2: Акты взаимных расчётов</h3>
            <p>Проверка задолженности и детальных взаиморасчетов с контрагентами.</p>
            <button className="dashboard-card-btn">
              Начать сверку
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M3 8h10M9 4l4 4-4 4"/>
              </svg>
            </button>
          </div>

          <div
            className={`dashboard-card ${isLicenseExpired ? 'disabled' : ''}`}
            onClick={() => handleCaseClick('/case3')}
          >
            <div className="dashboard-card-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="3" width="20" height="18" rx="2"/>
                <path d="M8 7v10M12 7v10M16 7v10"/>
              </svg>
            </div>
            <h3>Кейс 3: Карточка 3310 vs ЭСФ</h3>
            <p>Сверка поступлений и входящих электронных счетов-фактур за период.</p>
            <button className="dashboard-card-btn">
              Начать сверку
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M3 8h10M9 4l4 4-4 4"/>
              </svg>
            </button>
          </div>
        </div>

        {/* How it works */}
        <div className="landing-steps">
          <h2>Как это работает</h2>
          <div className="landing-steps-grid">
            <div className="landing-step">
              <div className="landing-step-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
              </div>
              <div className="landing-step-label">Шаг 1</div>
              <div className="landing-step-title">Загрузка данных</div>
            </div>
            <div className="landing-step">
              <div className="landing-step-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <circle cx="12" cy="12" r="3"/>
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                </svg>
              </div>
              <div className="landing-step-label">Шаг 2</div>
              <div className="landing-step-title">Обработка</div>
            </div>
            <div className="landing-step">
              <div className="landing-step-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M9 11l3 3L22 4"/>
                  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                </svg>
              </div>
              <div className="landing-step-label">Шаг 3</div>
              <div className="landing-step-title">Валидация</div>
            </div>
            <div className="landing-step">
              <div className="landing-step-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <circle cx="18" cy="18" r="3"/>
                  <circle cx="6" cy="6" r="3"/>
                  <path d="M13 6h3a2 2 0 0 1 2 2v7"/>
                  <path d="M11 18H8a2 2 0 0 1-2-2V9"/>
                </svg>
              </div>
              <div className="landing-step-label">Шаг 4</div>
              <div className="landing-step-title">Сопоставление</div>
            </div>
            <div className="landing-step">
              <div className="landing-step-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                  <polyline points="7.5 4.21 12 6.81 16.5 4.21"/>
                  <polyline points="7.5 19.79 7.5 14.6 3 12"/>
                  <polyline points="21 12 16.5 14.6 16.5 19.79"/>
                  <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                  <line x1="12" y1="22.08" x2="12" y2="12"/>
                </svg>
              </div>
              <div className="landing-step-label">Шаг 5</div>
              <div className="landing-step-title">Анализ</div>
            </div>
            <div className="landing-step">
              <div className="landing-step-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                </svg>
              </div>
              <div className="landing-step-label">Шаг 6</div>
              <div className="landing-step-title">Готовый отчет</div>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="footer">
        <div className="footer-container">
          <div className="footer-left">
            <span className="footer-copy">
              &copy; {new Date().getFullYear()} allkey.kz &mdash; Автоматизация финансовой сверки
            </span>
            <a href="https://redev.online" target="_blank" rel="noopener noreferrer" className="footer-redev">Разработано Redev</a>
          </div>
          <div className="footer-links">
            <a href="/offer">Публичная оферта</a>
          </div>
        </div>
      </footer>

      <AuthModal isOpen={showAuth} onClose={() => setShowAuth(false)} />
      <PurchaseModal isOpen={showPurchase} onClose={() => setShowPurchase(false)} />
    </>
  )
}
