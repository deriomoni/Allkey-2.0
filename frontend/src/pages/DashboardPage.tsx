import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function DashboardPage() {
  const { user } = useAuth()
  const navigate = useNavigate()

  return (
    <div>
      <h1 style={{ marginBottom: 8 }}>Добро пожаловать, {user?.full_name}!</h1>
      <p style={{ color: '#6b7280', marginBottom: 32 }}>
        Выберите тип сверки для начала работы
      </p>

      <div className="dashboard-cards">
        <div className="dashboard-card" onClick={() => navigate('/case1')}>
          <h3>Кейс 1: Карточка 6010 vs ЭСФ</h3>
          <p>
            Сверка карточки счёта 6010 из 1С с отчётом по электронным счетам-фактурам.
            Сравнение сумм и выявление расхождений.
          </p>
        </div>

        <div className="dashboard-card" onClick={() => navigate('/case2')}>
          <h3>Кейс 2: Акты взаимных расчётов</h3>
          <p>
            Сверка актов сверки взаимных расчётов между контрагентами.
            Построчное сравнение дебета и кредита.
          </p>
        </div>

        <div className="dashboard-card" onClick={() => navigate('/case3')}>
          <h3>Кейс 3: Карточка 3310 vs ЭСФ</h3>
          <p>
            Сверка карточки счёта 3310 (Поступление) с реестром входящих ЭСФ.
            Показывает ТРУ, отправителя и получателя.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginTop: 32 }}>
        <h3 style={{ marginBottom: 16 }}>Как это работает</h3>
        <ol style={{ paddingLeft: 20, color: '#4b5563' }}>
          <li style={{ marginBottom: 8 }}>Выберите тип сверки</li>
          <li style={{ marginBottom: 8 }}>Загрузите Excel файлы для сравнения</li>
          <li style={{ marginBottom: 8 }}>Настройте парсинг: укажите строку заголовка и сопоставьте колонки</li>
          <li style={{ marginBottom: 8 }}>Просмотрите предварительный результат</li>
          <li style={{ marginBottom: 8 }}>Выполните сверку</li>
          <li>Скачайте результат в формате Excel</li>
        </ol>
      </div>
    </div>
  )
}
