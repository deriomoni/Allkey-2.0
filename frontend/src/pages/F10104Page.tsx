import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import {
  f10104Api, ratesApi,
  type F10104Country, type F10104Flag, type F10104Refbooks,
  type F10104ServiceKind, type NbrkRateRow,
} from '../api/client'

// Помогайка по форме 101.04 — визард по одной операции.
//
// Порядок шагов взят из ТЗ §4 и НЕ переставляется: S1 → S2 → S5 → S3 → S6 →
// S7 → S8 → S4 → S9 → результат. Он подобран так, чтобы условные шаги не
// перескакивали при смене ответа: тип дохода спрашивается раньше скрининга ПУ,
// потому что от него зависит, нужен ли скрининг вообще.
//
// Налоговой логики здесь нет. Признаки страны (офшор, конвенция, ЕАЭС) и все
// тексты предупреждений приходят с бэкенда: ставок, кодов и норм в этом файле
// быть не должно.

const DRAFT_KEY = 'f10104_draft_v1'
const DRAFT_TTL_MS = 3 * 24 * 60 * 60 * 1000   // возврат к проверке через три дня — типовой сценарий

type Answers = Record<string, any>

type Draft = {
  answers: Answers
  stepIndex: number
  savedAt: number
}

const EMPTY_DRAFT: Draft = { answers: {}, stepIndex: 0, savedAt: 0 }

// ── Шаги. Порядок фиксирован, видимость условная (ТЗ §4). ──────────────────

type Step = {
  id: string
  title: string
  hint?: string
  visible?: (a: Answers, countries: Map<string, F10104Country>) => boolean
}

const STEPS: Step[] = [
  { id: 'S1', title: 'Контекст', hint: 'Период, компания, НДС, валюта' },
  { id: 'S2', title: 'Событие и контрагент' },
  { id: 'S5', title: 'Тип дохода' },
  {
    id: 'S3',
    title: 'Постоянное учреждение',
    visible: (a) => a['S2.2'] === 'branch_kz' || a['S5.1'] === 'services',
  },
  { id: 'S6', title: 'Место оказания', visible: (a) => a['S5.1'] === 'services' },
  {
    id: 'S7',
    title: 'Конвенция',
    visible: (a, countries) => {
      const c = countries.get(a['S2.3'])
      return !!c && !c.is_offshore && c.has_convention
    },
  },
  { id: 'S8', title: 'Сертификат резидентства', visible: (a) => a['S7.2'] === 'yes' },
  { id: 'S4', title: 'Даты и суммы' },
  { id: 'S9', title: 'НДС за нерезидента', visible: (a) => a['S1.4'] === 'yes' },
  { id: 'R', title: 'Заключение' },
]

// ── Варианты ответов. Формулировки — дословно из ТЗ §4. ────────────────────

const QUARTERS: [number, string][] = [
  [1, 'I квартал'], [2, 'II квартал'], [3, 'III квартал'], [4, 'IV квартал'],
]
const YEARS = [2026, 2027]

const COMPANY_SIZE: [string, string][] = [
  ['small', 'Малый бизнес'],
  ['medium', 'Средний бизнес'],
  ['large', 'Крупный бизнес'],
  ['nko', 'Некоммерческая организация'],
]

const RESIDENCY: [string, string][] = [
  ['yes', 'Да, резидент РК'],
  ['no', 'Нет'],
  ['branch', 'Филиал иностранной компании'],
]

const VAT_REGISTERED: [string, string][] = [
  ['yes', 'Да, состоим на учёте по НДС'],
  ['no', 'Нет'],
  ['unsure', 'Не уверен'],
]

const EVENTS: [string, string][] = [
  ['payment', 'Перечислили деньги нерезиденту'],
  ['act_no_payment', 'Подписан акт или получен инвойс, оплаты ещё нет'],
  ['offset', 'Провели взаимозачёт встречных требований'],
  ['debt_forgiven', 'Списали (простили) долг нерезидента'],
  ['property_transfer', 'Передали товар или имущество в счёт обязательства'],
  ['barter', 'Оказали встречную услугу (бартер)'],
  ['advance', 'Выплатили аванс (предоплату)'],
  ['accrued_deducted', 'Начислили доход, не выплатили, но отнесли на вычеты'],
]

const RECIPIENTS: [string, string][] = [
  ['legal_entity', 'Юридическое лицо-нерезидент'],
  ['individual', 'Физическое лицо-нерезидент'],
  ['branch_kz', 'Филиал или представительство иностранной компании в РК'],
  ['ip', 'ИП-нерезидент'],
]

const INCOME_TYPES: [string, string][] = [
  ['goods', 'Товары (поставка) — в том числе с работами или услугами в цене'],
  ['services', 'Работы или услуги'],
  ['royalty', 'Роялти / лицензия (право на ПО, товарный знак, ноу-хау)'],
  ['dividends', 'Дивиденды'],
  ['interest', 'Вознаграждение (проценты по займу, долговым ценным бумагам)'],
  ['rent', 'Аренда имущества'],
  ['transport_intl', 'Международная перевозка'],
  ['insurance', 'Страховая премия (страхование или перестрахование)'],
  ['capital_gain', 'Прирост стоимости (продажа акций, долей, имущества)'],
  ['penalty', 'Неустойка, штраф, пеня по договору'],
  ['other', 'Другое'],
]

const YES_NO: [string, string][] = [['yes', 'Да'], ['no', 'Нет']]

const INSURANCE_KINDS: [string, string][] = [
  ['insurance', 'Страхование рисков'],
  ['reinsurance', 'Перестрахование рисков'],
]

const PE_HAS_BIN: [string, string][] = [
  ['yes', 'Да'],
  ['no', 'Нет'],
  ['unknown', 'Не знаю'],
]

const PE_CONTRACT_WITH: [string, string][] = [
  ['branch', 'С филиалом (постоянным учреждением) в РК'],
  ['head_office', 'С головной компанией за рубежом'],
]

const PE_DURATION: [string, string][] = [
  ['under_183', 'До 183 дней'],
  ['over_183', 'Свыше 183 дней в любом 12-месячном периоде'],
  ['construction', 'Строительная площадка'],
  ['dependent_agent', 'Через зависимого агента'],
  ['na', 'Не применимо'],
]

const CERT_STATUS: [string, string][] = [
  ['yes', 'Да, сертификат получен'],
  ['pending', 'Ещё не получен, ожидаем'],
  ['no', 'Нет'],
]

// Семь пунктов чек-листа ст. 702 и 705. Пятый и шестой — РАЗНЫЕ даты и разные
// адресаты: их регулярно сливают в одну, и это прямая дорога к отказу
// в освобождении.
const CERT_CHECKLIST: [string, string, string][] = [
  ['S8.1', 'Форма документа',
   'Оригинал, заверенный компетентным органом; нотариально засвидетельствованная копия; либо бумажная копия электронного документа с интернет-ресурса компетентного органа. Скан обычного письма от контрагента сертификатом не является (ст. 702 п. 1).'],
  ['S8.2', 'Легализация',
   'Апостиль или консульская легализация — либо документ подпадает под исключение: размещён на интернет-ресурсе компетентного органа, иной порядок установлен международным договором или процедурой взаимного согласования (ст. 702 п. 2).'],
  ['S8.3', 'Перевод на казахский или русский язык',
   'Прямого требования нотариального перевода в ст. 702 нет, но аналогичное требование есть в ст. 708 — рекомендуется как страховка.'],
  ['S8.4', 'Период охватывает год выплаты дохода',
   'Если период не указан, документ действует за календарный год выдачи. Сертификат за 2025 год под выплату 2026 года не подойдёт (ст. 702 п. 3).'],
  ['S8.5', 'Сертификат получен вами от нерезидента в срок',
   'Не позднее более ранней из дат: 31 марта года, следующего за налоговым периодом, либо за 5 рабочих дней до завершения налоговой проверки (ст. 705 п. 3).'],
  ['S8.6', 'Копия сдана в налоговый орган',
   'Отдельная обязанность и другой срок: не позднее 5 календарных дней после срока сдачи формы 101.04 за IV квартал, то есть примерно 5 апреля (ст. 705 п. 7).'],
  ['S8.7', 'Для дивидендов, роялти и вознаграждений через посредника',
   'В контракте указаны наименование посредника, суммы выплат, данные окончательного получателя, его номер налоговой регистрации и данные госрегистрации (ст. 706 п. 2).'],
]

const PLACE_OF_SUPPLY: [string, string][] = [
  ['kz', 'Полностью на территории РК'],
  ['outside', 'Полностью за пределами РК'],
  ['partly', 'Частично там, частично здесь'],
]

const UNK_OPTIONS: [string, string][] = [
  ['yes', 'Да, есть'],
  ['no', 'Нет'],
  ['unknown', 'Не знаю'],
]

// ── Оформление. Инлайновые стили, как в остальных модулях. ─────────────────

const card: CSSProperties = {
  background: '#fff', border: '1px solid #e2e8f0', borderRadius: 10,
  padding: 20, marginBottom: 16,
}
const label: CSSProperties = { display: 'block', fontWeight: 600, marginBottom: 8, fontSize: 15 }
const hintS: CSSProperties = { color: '#64748b', fontSize: 13, marginTop: 4, lineHeight: 1.5 }
const inputS: CSSProperties = {
  width: '100%', padding: '8px 10px', border: '1px solid #cbd5e1',
  borderRadius: 6, fontSize: 14, background: '#fff',
}
const optionRow = (active: boolean): CSSProperties => ({
  display: 'flex', gap: 10, alignItems: 'flex-start', padding: '9px 12px',
  border: `1px solid ${active ? '#2563eb' : '#e2e8f0'}`,
  background: active ? '#eff6ff' : '#fff',
  borderRadius: 8, marginBottom: 6, cursor: 'pointer',
})

const cellL: CSSProperties = { padding: '6px 8px', borderBottom: '1px solid #f1f5f9', color: '#475569' }
const cellR: CSSProperties = { padding: '6px 8px', borderBottom: '1px solid #f1f5f9' }
const cellN: CSSProperties = { padding: '6px 8px', borderBottom: '1px solid #f1f5f9', color: '#94a3b8', fontSize: 12.5 }

// Печатная вёрстка. PDF в v1 не генерируем: браузер сам сохранит в PDF, а нам
// достаточно убрать интерфейсную обвязку и раскрыть свёрнутые блоки — в печать
// свёрнутое уходить не должно. Настоящая генерация PDF — задача после беты.
const PRINT_CSS = `
@media print {
  .nav, .footer, .f10104-noprint, .f10104-toggle { display: none !important; }
  .f10104-collapsible { display: block !important; }
  .f10104-result { max-width: none; }
  .f10104-disclaimer { break-inside: avoid; page-break-inside: avoid; }
  .f10104-print-footer { display: block !important; }
  @page { margin: 14mm; }
}
`

// Важность предупреждения задаётся справочником, не интерфейсом.
const FLAG_TONE: Record<string, { bg: string; border: string; color: string }> = {
  info: { bg: '#eff6ff', border: '#bfdbfe', color: '#1e40af' },
  medium: { bg: '#fff7ed', border: '#fed7aa', color: '#9a3412' },
  high: { bg: '#fef2f2', border: '#fecaca', color: '#991b1b' },
}

// Ключи, начинающиеся с подчёркивания, — состояние интерфейса, а не ответы
// визарда. На сервер они не уходят: набор ответов сохраняется вместе с
// вердиктом для воспроизводимости, и мусору из UI там не место.
export function toPayload(answers: Answers): Answers {
  return Object.fromEntries(Object.entries(answers).filter(([k]) => !k.startsWith('_')))
}

// Период загрузки курсов по умолчанию — квартал операции плюс месяц назад.
// Не с начала года: месяца достаточно, чтобы покрыть авансы предыдущего
// квартала, а запросов к Нацбанку вчетверо меньше (ZADANIE-kursy-valyut.md).
function defaultRatesPeriod(quarter: number, year: number): { from: string; to: string } {
  const quarterStart = new Date(Date.UTC(year, (quarter - 1) * 3, 1))
  const from = new Date(Date.UTC(year, (quarter - 1) * 3 - 1, 1))
  const to = new Date(Date.UTC(year, quarterStart.getUTCMonth() + 3, 0))
  const iso = (d: Date) => d.toISOString().slice(0, 10)
  return { from: iso(from), to: iso(to) }
}

function loadDraft(): Draft {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return EMPTY_DRAFT
    const parsed = JSON.parse(raw) as Draft
    if (!parsed.savedAt || Date.now() - parsed.savedAt > DRAFT_TTL_MS) {
      localStorage.removeItem(DRAFT_KEY)
      return EMPTY_DRAFT
    }
    return { ...EMPTY_DRAFT, ...parsed }
  } catch {
    return EMPTY_DRAFT
  }
}

// ── Мелкие блоки ──────────────────────────────────────────────────────────

function Radio(props: {
  question: string
  hint?: ReactNode
  options: [string, string][]
  value: unknown
  onChange: (v: string) => void
}) {
  return (
    <div style={{ marginBottom: 22 }}>
      <span style={label}>{props.question}</span>
      {props.options.map(([value, text]) => (
        <label key={value} style={optionRow(props.value === value)}>
          <input
            type="radio"
            checked={props.value === value}
            onChange={() => props.onChange(value)}
            style={{ marginTop: 3 }}
          />
          <span style={{ fontSize: 14 }}>{text}</span>
        </label>
      ))}
      {props.hint && <div style={hintS}>{props.hint}</div>}
    </div>
  )
}

function FlagCard({ flag }: { flag: F10104Flag }) {
  const tone = FLAG_TONE[flag.severity] || FLAG_TONE.info
  return (
    <div style={{
      background: tone.bg, border: `1px solid ${tone.border}`, color: tone.color,
      borderRadius: 8, padding: '12px 14px', marginBottom: 10, fontSize: 13.5, lineHeight: 1.55,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{flag.title}</div>
      <div>{flag.text}</div>
      {flag.basis && (
        <div style={{ marginTop: 6, opacity: 0.8, fontSize: 12.5 }}>Основание: {flag.basis}</div>
      )}
    </div>
  )
}

function StepNav({ steps, current, onGo }: {
  steps: Step[]; current: number; onGo: (i: number) => void
}) {
  return (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
      {steps.map((s, i) => {
        const done = i < current
        const active = i === current
        return (
          <button
            key={s.id}
            onClick={() => i <= current && onGo(i)}
            disabled={i > current}
            style={{
              padding: '5px 11px', borderRadius: 99, fontSize: 12.5, cursor: i <= current ? 'pointer' : 'default',
              border: `1px solid ${active ? '#2563eb' : '#e2e8f0'}`,
              background: active ? '#2563eb' : done ? '#f1f5f9' : '#fff',
              color: active ? '#fff' : done ? '#334155' : '#94a3b8',
            }}
          >
            {s.id} · {s.title}
          </button>
        )
      })}
    </div>
  )
}

function RateField(props: {
  label: string
  basis: string
  currency: string
  day?: string
  value?: number | null
  onChange: (v: number | null) => void
}) {
  const [status, setStatus] = useState<string>('')
  const [busy, setBusy] = useState(false)

  // Каждый курс тянется на СВОЮ дату отдельно. Переиспользовать один вызов
  // на всю операцию нельзя — это и есть ошибка, от которой поле защищает.
  async function pull() {
    if (!props.day) { setStatus('Сначала укажите дату.'); return }
    setBusy(true); setStatus('')
    try {
      const official = await ratesApi.getOfficial(props.currency, props.day)
      props.onChange(official.rate)
      setStatus(official.carriedForward
        ? `Курс на ${props.day} не публиковался, применён курс от ${official.actualDate} — ${official.rate}`
        : `Официальный курс НБ РК на ${props.day} — ${official.rate}`)
    } catch {
      setStatus('Курс получить не удалось. Введите вручную с обоснованием.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <span style={label}>{props.label}</span>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          style={{ ...inputS, maxWidth: 180 }} type="number" step="0.01" min="0"
          value={props.value ?? ''}
          onChange={(e) => props.onChange(e.target.value === '' ? null : Number(e.target.value))}
        />
        <button className="btn btn-secondary" onClick={pull} disabled={busy}>
          {busy ? 'Тяну…' : 'Подтянуть с НБ РК'}
        </button>
        <span style={{ ...hintS, marginTop: 0 }}>{props.basis}</span>
      </div>
      {status && <div style={{ ...hintS }}>{status}</div>}
    </div>
  )
}

function RatesPanel({ currency, quarter, year }: {
  currency: string; quarter: number; year: number
}) {
  const initial = defaultRatesPeriod(quarter, year)
  const [from, setFrom] = useState(initial.from)
  const [to, setTo] = useState(initial.to)
  const [rows, setRows] = useState<NbrkRateRow[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState('')

  // Доллар грузим вместе с валютой договора: он нужен для проверки порога
  // раскрытия 50 000 USD, когда договор заключён в другой валюте.
  const codes = currency === 'USD' ? ['USD'] : [currency, 'USD']

  async function load() {
    setBusy(true); setFailed('')
    try {
      setRows(await ratesApi.getRange(codes, from, to))
    } catch {
      setFailed('Не удалось загрузить курсы. Курс можно ввести вручную на шаге «Даты и суммы».')
    } finally {
      setBusy(false)
    }
  }

  const days = rows ? new Set(rows.map((r) => r.date)).size : 0
  const carried = rows ? rows.filter((r) => r.carriedForward).length : 0

  return (
    <div style={{
      border: '1px solid #e2e8f0', background: '#f8fafc',
      borderRadius: 8, padding: 14, marginTop: 10,
    }}>
      <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 4 }}>
        Курсы Национального Банка за период
      </div>
      <div style={{ ...hintS, marginTop: 0, marginBottom: 10 }}>
        Загрузите один раз — курсы подставятся во все операции квартала.
        По умолчанию берётся квартал операции плюс месяц назад: этого хватает,
        чтобы покрыть авансы предыдущего квартала.
      </div>

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div>
          <div style={{ ...hintS, marginTop: 0 }}>Дата с</div>
          <input type="date" style={{ ...inputS, width: 160 }} value={from}
            onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div>
          <div style={{ ...hintS, marginTop: 0 }}>Дата по</div>
          <input type="date" style={{ ...inputS, width: 160 }} value={to}
            onChange={(e) => setTo(e.target.value)} />
        </div>
        <button className="btn btn-primary" onClick={load} disabled={busy}>
          {busy ? 'Загружаю…' : 'Загрузить курсы'}
        </button>
        <button className="btn btn-secondary" onClick={() => setFrom(`${year}-01-01`)}>
          Расширить до начала года
        </button>
      </div>

      <div style={{ ...hintS, marginBottom: 0 }}>
        Валюты: {codes.join(', ')}
      </div>

      {failed && <div className="error-message" style={{ marginTop: 10 }}>{failed}</div>}

      {rows && !failed && (
        <div style={{
          marginTop: 12, padding: '10px 12px', background: '#fff',
          border: '1px solid #e2e8f0', borderRadius: 6, fontSize: 13.5,
        }}>
          Загружено <b>{rows.length}</b> строк за <b>{days}</b> дней ·
          период {from.split('-').reverse().join('.')} — {to.split('-').reverse().join('.')}
          {/* «Перенесено: 0» — постоянный шум: НБ РК публикует курс каждый
              календарный день, и перенос на живом фиде не случается. Показываем
              строку только тогда, когда перенос действительно был. */}
          {carried > 0 && (
            <div style={{ ...hintS, marginBottom: 0 }}>
              Перенесено с прошлых дат: <b>{carried}</b> — в эти дни фид НБ РК
              курса не отдал, подставлен последний доступный.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Экран результата ──────────────────────────────────────────────────────
//
// Железное правило экрана: где `confidence: manual_review` или
// `vat.applicable === null` — ЦИФРЫ НЕТ ВООБЩЕ. Ни серой, ни в скобках, ни
// «предварительно». Как только на экране появляется число, его переносят
// в отчёт, даже если рядом написано не переносить. Вместо числа — в чём
// вопрос, какие позиции и что проверить.

const money = (n: number): string => `${n.toLocaleString('ru-RU').replace(/,/g, ' ')} ₸`
const asDate = (iso?: string | null): string =>
  iso ? iso.split('-').reverse().join('.') : '—'

type Verdict = Record<string, any>

function SummaryRow({ mark, title, value, tone }: {
  mark: string; title: string; value: ReactNode; tone?: string
}) {
  return (
    <div style={{
      display: 'flex', gap: 10, alignItems: 'baseline', padding: '7px 0',
      borderBottom: '1px solid #f1f5f9', fontSize: 14.5,
    }}>
      <span style={{ width: 22 }}>{mark}</span>
      <span style={{ minWidth: 210, color: '#475569' }}>{title}</span>
      <b style={{ color: tone || '#0f172a' }}>{value}</b>
    </div>
  )
}

function ManualReview({ question, positions, whatToCheck }: {
  question: string; positions: string[]; whatToCheck: string
}) {
  return (
    <div style={{
      background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: 8,
      padding: '13px 15px', fontSize: 13.5, lineHeight: 1.55, color: '#7c2d12',
    }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>{question}</div>
      {positions.map((p, i) => (
        <div key={i} style={{ marginBottom: 4 }}>— {p}</div>
      ))}
      <div style={{ marginTop: 8 }}><b>Что проверить:</b> {whatToCheck}</div>
    </div>
  )
}

function Collapsible({ title, children }: { title: string; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={card}>
      {/* В печать блок уходит развёрнутым — см. печатные стили. */}
      <button
        onClick={() => setOpen(!open)}
        className="f10104-toggle"
        style={{
          background: 'none', border: 'none', padding: 0, cursor: 'pointer',
          fontSize: 16, fontWeight: 600, color: '#0f172a',
        }}
      >
        {open ? '▾' : '▸'} {title}
      </button>
      <div className="f10104-collapsible" style={{ display: open ? 'block' : 'none', marginTop: 12 }}>
        {children}
      </div>
    </div>
  )
}

/**
 * Спорная ставка по дивидендам (ст. 682 п. 1, пп. 5) против пп. 6)).
 *
 * ПОРЯДОК ЗДЕСЬ — ЧАСТЬ ЗАЩИТЫ, А НЕ ОФОРМЛЕНИЕ. Экран, начинающийся с двух
 * ставок «5 %» и «15 %», читается как предложение выбрать: бухгалтер возьмёт
 * меньшую и напишет обоснование формально. Получился бы механизм, узаконивающий
 * занижение налога, — ровно то, чего он должен не допускать.
 *
 * Поэтому сначала документ, потом ставка:
 *   1. констатация: вопрос спорен, вывода нет, нужно письменное основание;
 *      обе позиции с аргументами, но ставка внутри текста, а не заголовком;
 *   2. вопрос «есть ли письменное основание?»;
 *   3. «нет» — блок закрывается, варианты не показываются вовсе;
 *   4. «да» — открывается поле обоснования, и только заполненное открывает
 *      сами варианты.
 *
 * Механизм существует для того, у кого заключение уже на руках, и только
 * для него. Формулировки позиций — из справочника, своей редакции спорной
 * нормы у интерфейса нет.
 */
function DisputedPosition({ spec, value, hasBasis, onChange, onHasBasis }: {
  spec: any
  value: Record<string, any>
  hasBasis: string | undefined
  onChange: (patch: Record<string, any>) => void
  onHasBasis: (v: string) => void
}) {
  const basis = String(value.position_basis || '')
  const basisFilled = basis.trim().length > 0
  const chosen = value.position || ''

  // Стёртое обоснование не оставляет за собой принятый выбор: иначе ставка
  // «залипнет» — на экране выбранная позиция, а под ней уже нет основания.
  const setBasis = (text: string) => {
    onChange(text.trim() ? { position_basis: text }
                         : { position_basis: text, position: null })
  }

  const declineBasis = () => {
    onHasBasis('no')
    onChange({ position: null, position_basis: null })
  }

  return (
    <div style={{
      marginBottom: 22, padding: '14px 16px', borderRadius: 8,
      border: '1px solid #fbbf24', background: '#fffbeb',
    }}>
      {/* 1. Констатация. Ставок в заголовках нет. */}
      <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 8 }}>
        {spec.label}
      </div>
      <div style={{ fontSize: 13, color: '#78350f', lineHeight: 1.6, marginBottom: 10 }}>
        Помогайка по этому вопросу вывода не даёт: норма допускает два прочтения,
        и выбрать между ними — не её решение. Для расчёта нужно письменное
        основание — разъяснение КГД или заключение налогового консультанта.
      </div>

      {(spec.positions || []).map((position: any) => (
        <div key={position.id} style={{
          fontSize: 12.5, color: '#475569', lineHeight: 1.6, marginBottom: 8,
          paddingLeft: 10, borderLeft: '2px solid #fde68a',
        }}>
          {position.argument || position.basis}
          <div style={{ color: '#78350f', marginTop: 2 }}>{position.basis}</div>
        </div>
      ))}

      {spec.money_at_stake && (
        <div style={{ ...hintS, marginTop: 0, marginBottom: 12 }}>{spec.money_at_stake}</div>
      )}

      {/* 2. Вопрос про документ — раньше, чем любые варианты. */}
      <div style={{ borderTop: '1px solid #fde68a', paddingTop: 12 }}>
        <span style={label}>Есть ли у вас письменное основание по этому вопросу?</span>
        <div style={{ display: 'flex', gap: 10, marginTop: 6 }}>
          <button
            className={hasBasis === 'yes' ? 'btn btn-primary' : 'btn btn-secondary'}
            style={{ padding: '5px 14px', fontSize: 13 }}
            onClick={() => onHasBasis('yes')}
          >
            Да, есть
          </button>
          <button
            className={hasBasis === 'no' ? 'btn btn-primary' : 'btn btn-secondary'}
            style={{ padding: '5px 14px', fontSize: 13 }}
            onClick={declineBasis}
          >
            Нет
          </button>
        </div>
      </div>

      {/* 3. «Нет» — блок закрыт, вариантов не показываем. */}
      {hasBasis === 'no' && (
        <div style={{ ...hintS, marginTop: 10 }}>
          Помогайка идёт дальше без ставки по этой выплате. В результате будет
          вопрос и обе позиции, а не сумма. {spec.what_to_check || ''}
        </div>
      )}

      {/* 4. «Да» — сначала обоснование, и только заполненное открывает выбор. */}
      {hasBasis === 'yes' && (
        <div style={{ marginTop: 12 }}>
          <span style={label}>Реквизиты основания</span>
          <textarea
            style={{ ...inputS, minHeight: 58, resize: 'vertical' }}
            value={basis}
            placeholder="Номер и дата письма КГД, реквизиты заключения консультанта или ссылка на разъяснение"
            onChange={(e) => setBasis(e.target.value)}
          />

          {!basisFilled ? (
            <div style={hintS}>
              Заполните реквизиты — после этого можно будет указать, какая
              позиция в нём принята.
            </div>
          ) : (
            <div style={{ marginTop: 10 }}>
              <span style={label}>Какая позиция принята в этом основании?</span>
              {(spec.positions || []).map((position: any) => (
                <label
                  key={position.id}
                  style={{
                    display: 'block', marginTop: 6, padding: '8px 11px',
                    borderRadius: 6, cursor: 'pointer', background: '#fff',
                    border: `1px solid ${chosen === position.id ? '#b45309' : '#e5e7eb'}`,
                  }}
                >
                  <input
                    type="radio" name="s58-position" value={position.id}
                    checked={chosen === position.id}
                    onChange={() => onChange({ position: position.id })}
                    style={{ marginRight: 8 }}
                  />
                  {position.basis} — {Math.round(position.rate * 100)} %
                </label>
              ))}
              <div style={hintS}>
                Выбранная позиция, её основание и дата попадут в резюме
                результата и в печать отдельной строкой: решение принял
                пользователь, а не помогайка.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Подписи ЗНАЧЕНИЙ ответов для трассировки. Собираются из тех же списков
// вариантов, которыми визард рисует вопросы, — второй редакции подписей не
// заводим. Сервер подписывает только два значения, которые попадают внутрь
// текстов справочника ({event} и {recipient_type}); остальное здесь.
//
// ВОСЕМЬ СТРОК ДУБЛИРОВАНИЯ ЗДЕСЬ — ОСОЗНАННОЕ РЕШЕНИЕ, НЕ НЕДОСМОТР.
// Значения S2.1 и S2.2 подписаны и тут, и в explain.py (ANSWER_VALUE_LABELS):
// серверу они нужны для подстановки внутрь текстов справочника. Правильный
// конец — перенести все четырнадцать списков вариантов на сервер и читать их
// обеими сторонами. Работа не механическая, и делать её решено ПОСЛЕ проверки
// первой версии владельцем, отдельным заходом с прогоном: рефакторить
// проверенный насквозь визард перед самой выкаткой — способ сломать то, что
// работает, за день до первого живого использования. Решение владельца
// от 20.08.2026.
const VALUE_LABELS: Record<string, Record<string, string>> = {
  'S1.4': Object.fromEntries(VAT_REGISTERED),
  'S2.1': Object.fromEntries(EVENTS),
  'S2.2': Object.fromEntries(RECIPIENTS),
  'S3.1': Object.fromEntries(RESIDENCY),
  'S3.2': Object.fromEntries(PE_CONTRACT_WITH),
  'S3.3': Object.fromEntries(PE_HAS_BIN),
  'S3.4': Object.fromEntries(PE_DURATION),
  'S5.1': Object.fromEntries(INCOME_TYPES),
  'S5.4': Object.fromEntries(YES_NO),
  'S5.6': Object.fromEntries(YES_NO),
  'S5.7': Object.fromEntries(YES_NO),
  'S6.1': Object.fromEntries(PLACE_OF_SUPPLY),
  'S7.3': Object.fromEntries(CERT_STATUS),
  'S7.4': Object.fromEntries(YES_NO),
  'S7.5': Object.fromEntries(YES_NO),
  'S7.6': Object.fromEntries(YES_NO),
  'S7.7': Object.fromEntries(YES_NO),
  'S9.3': Object.fromEntries(PLACE_OF_SUPPLY),
}

/** Подпись значения ответа. Нет своего списка — берём то, что дал сервер. */
function valueLabel(input: { key: string; value: unknown; display: string }): string {
  const raw = input.value
  if (typeof raw === 'string') {
    const label = VALUE_LABELS[input.key]?.[raw]
    if (label) return label
  }
  return input.display
}

const ANSWER_LABELS: Record<string, string> = {
  'S1.1': 'отчётный период',
  'S1.4': 'плательщик НДС',
  'S1.5': 'валюта договора',
  'S2.1': 'событие выплаты',
  'S2.2': 'кто получатель',
  'S2.3': 'страна резидентства',
  'S2.5': 'учётный номер валютного договора',
  'S3.1': 'присутствие в РК',
  'S3.2': 'форма присутствия',
  'S3.3': 'регистрация ПУ',
  'S3.4': 'признаки ПУ',
  'S4.2': 'дата выплаты',
  'S5.1': 'вид дохода',
  'S5.4': 'стоимость услуг выделена',
  'S5.4a': 'сумма выделенных услуг',
  'S5.5': 'вид услуг',
  'S5.6': 'есть техподдержка',
  'S5.7': 'техподдержка выделена',
  'S5.8': 'доля участия',
  'S5.9': 'доход по авансу начислен',
  'S6.1': 'место оказания услуг',
  'S7.3': 'сертификат резидентства',
  'S7.4': 'доход связан с ПУ',
  'S7.5': 'окончательный получатель',
  'S7.6': 'транзитная структура',
  'S7.7': 'уплата за свой счёт',
  'S9.3': 'фактическое место выполнения',
  'S10': 'исключение по ст. 454 п. 3',
}

function NormLink({ norm }: { norm: string }) {
  const [text, setText] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  const toggle = async () => {
    if (open) { setOpen(false); return }
    setOpen(true)
    if (text !== null) return
    setBusy(true)
    try {
      const article = await f10104Api.getArticle(norm)
      setText(article.text || article.note || 'Текст нормы в справочнике отсутствует.')
    } catch {
      setText('Не удалось загрузить текст нормы.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button
        onClick={toggle}
        style={{
          border: 'none', background: 'none', padding: 0, cursor: 'pointer',
          color: '#2563eb', fontSize: 12.5, textDecoration: 'underline dotted',
          marginRight: 10,
        }}
      >
        {norm}
      </button>
      {open && (
        <div style={{
          margin: '6px 0 10px', padding: '9px 11px', borderRadius: 6,
          background: '#f8fafc', border: '1px solid #e2e8f0',
          fontSize: 12.5, lineHeight: 1.6, color: '#334155',
          whiteSpace: 'pre-wrap',
        }}>
          {busy ? 'Загрузка…' : text}
        </div>
      )}
    </>
  )
}

/** Одна развилка: что решено, из каких ответов и что было бы иначе. */
function DecisionRow({ decision, answerLabels }: {
  decision: any
  answerLabels: Record<string, string>
}) {
  const applied = decision.applied
  return (
    <div style={{
      padding: '10px 0', borderTop: '1px solid #f1f5f9', fontSize: 13.5,
    }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
        <span style={{ color: applied ? '#16a34a' : '#94a3b8' }}>
          {applied ? '✓' : '·'}
        </span>
        <div style={{ flex: 1 }}>
          <b>{decision.subject}</b>
          <div style={{ color: '#334155', marginTop: 3, lineHeight: 1.55 }}>
            {decision.text}
          </div>

          {(decision.inputs || []).length > 0 && (
            <div style={{ fontSize: 12.5, color: '#64748b', marginTop: 5 }}>
              из ответов:{' '}
              {decision.inputs.map((input: any, i: number) => (
                <span key={input.key}>
                  {i > 0 && '; '}
                  <span title={input.key}>
                    {answerLabels[input.key] || input.key}
                  </span>
                  {' — '}
                  <b style={{ color: '#334155' }}>{valueLabel(input)}</b>
                </span>
              ))}
            </div>
          )}

          {decision.counterfactual && (
            <div style={{
              marginTop: 7, padding: '7px 10px', borderRadius: 6,
              background: '#eff6ff', border: '1px solid #bfdbfe',
              fontSize: 12.5, color: '#1e40af',
            }}>
              {decision.counterfactual.condition} налог составил бы{' '}
              {decision.counterfactual.display}
            </div>
          )}

          {decision.note && (
            <div style={{ fontSize: 12.5, color: '#78350f', marginTop: 6 }}>
              {decision.note}
            </div>
          )}

          {(decision.norms || []).length > 0 && (
            <div style={{ marginTop: 6 }}>
              {decision.norms.map((norm: string) => (
                <NormLink key={norm} norm={norm} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/**
 * Блок 2 «Подробнее» (ТЗ §6): почему вывод именно такой.
 *
 * Всё содержимое приходит с сервера: тексты развилок — из справочника,
 * исходы — из журнала, который движок пишет в точках принятия решений.
 * Интерфейс их только раскладывает и умеет показать текст нормы по клику.
 */
function ExplanationBlock({ explanation, answerLabels }: {
  explanation: any
  answerLabels: Record<string, string>
}) {
  const [copied, setCopied] = useState(false)
  if (!explanation) return null

  const asText = () => {
    const line = (d: any) => {
      const inputs = (d.inputs || [])
        .map((i: any) => `${answerLabels[i.key] || i.key}: ${valueLabel(i)}`)
        .join('; ')
      const alt = d.counterfactual
        ? `\n    ${d.counterfactual.condition} налог составил бы ${d.counterfactual.display}`
        : ''
      return `  ${d.applied ? '+' : '-'} ${d.subject} — ${d.text}`
        + (inputs ? `\n    из ответов: ${inputs}` : '')
        + (d.norms?.length ? `\n    нормы: ${d.norms.join(', ')}` : '')
        + alt
    }
    return [
      'ЧТО ПРИМЕНИЛОСЬ',
      ...explanation.applied.map(line),
      '',
      'ЧТО НЕ ПРИМЕНИЛОСЬ',
      ...explanation.not_applied.map(line),
      '',
      'РАСЧЁТ',
      ...explanation.calc.map((c: any) =>
        `  ${c.label}${c.formula ? ` (${c.formula})` : ''}: ${c.value}`),
    ].join('\n')
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(asText())
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <Collapsible
      title={explanation.income_short
        ? `Подробнее: почему вывод именно такой (${explanation.income_short})`
        : 'Подробнее: почему вывод именно такой'}
    >
      <div className="f10104-noprint" style={{ marginBottom: 10 }}>
        <button
          className="btn btn-secondary"
          style={{ padding: '4px 10px', fontSize: 12.5 }}
          onClick={copy}
        >
          {copied ? 'Скопировано' : 'Скопировать блок'}
        </button>
      </div>

      <div style={{ fontWeight: 600, fontSize: 13, color: '#16a34a' }}>
        Что применилось
      </div>
      {explanation.applied.map((d: any) => (
        <DecisionRow key={d.rule_id} decision={d} answerLabels={answerLabels} />
      ))}

      <div style={{ fontWeight: 600, fontSize: 13, color: '#64748b', marginTop: 16 }}>
        Что не применилось и почему
      </div>
      {explanation.not_applied.length === 0 ? (
        <div style={{ fontSize: 13, color: '#94a3b8', padding: '10px 0' }}>
          Все пройденные развилки сработали.
        </div>
      ) : explanation.not_applied.map((d: any) => (
        <DecisionRow key={d.rule_id} decision={d} answerLabels={answerLabels} />
      ))}

      {explanation.calc?.length > 0 && (
        <>
          <div style={{ fontWeight: 600, fontSize: 13, marginTop: 16 }}>
            Откуда взялись числа
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5, marginTop: 6 }}>
            <tbody>
              {explanation.calc.map((c: any, i: number) => (
                <tr key={i}>
                  <td style={cellL}>{c.label}</td>
                  <td style={cellR}>{c.formula || '—'}</td>
                  <td style={cellN}>{c.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Collapsible>
  )
}

function ResultScreen({ answers, refbooks, onBack }: {
  answers: Answers; refbooks: F10104Refbooks; onBack: () => void
}) {
  const [verdict, setVerdict] = useState<Verdict | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function calculate() {
    setBusy(true); setError('')
    try {
      setVerdict(await f10104Api.evaluate(toPayload(answers)))
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Не удалось выполнить расчёт.')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => { calculate() }, [])

  if (busy && !verdict) return <div className="loading">Считаю…</div>
  if (error) {
    return (
      <div style={card}>
        <div className="error-message">{error}</div>
        <button className="btn btn-secondary" style={{ marginTop: 12 }} onClick={onBack}>
          Вернуться к ответам
        </button>
      </div>
    )
  }
  if (!verdict) return null

  const kpn = verdict.kpn
  const vat = verdict.vat
  const rep = verdict.reporting
  const dl = verdict.deadlines
  const per = verdict.periods
  const flags: F10104Flag[] = verdict.flags_detail || []
  // Цифру прячем там, где вывода действительно нет: `applicable === null` —
  // это про НДС конкретно. Общий `confidence: manual_review` может прийти и от
  // непроверенного порога раскрытия, когда НДС при этом посчитан, — тогда
  // прятать посчитанное число неправильно. Про уровень уверенности документа
  // говорит отдельная плашка вверху, её не пропустить.
  const vatUnknown = vat.applicable === null
  // Ставка по конвенции не определена: в справочной таблице запись
  // неоднозначна. Уровень обязательства — цифры нет ни в каком виде.
  const kpnUnknown = kpn.applicable === null || kpn.rate === null || kpn.rate_undetermined === true
  const needsReview = verdict.confidence === 'manual_review'

  // Чек-лист действий: каждый пункт с контрольной датой, посчитанной от ответов.
  const checklist: [string, string][] = []
  if (kpn.taxable && !kpnUnknown && kpn.amount_kzt > 0) {
    checklist.push([asDate(dl.kpn_payment), `Перечислить КПН у источника — ${money(kpn.amount_kzt)}`])
  }
  if (vat.applicable === true) {
    checklist.push([asDate(dl.vat_payment), `Перечислить НДС за нерезидента — ${money(vat.amount_kzt)}`])
    checklist.push([asDate(dl.vat_payment), 'Сдать форму 300.00, приложение 300.04'])
  }
  if (rep.form_101_04_required) {
    checklist.push([asDate(dl.form_101_04), `Сдать форму 101.04 за ${rep.period || 'отчётный квартал'}`])
  }
  if (kpn.convention_applied) {
    // Две РАЗНЫЕ даты и два разных адресата — в чек-листе тоже двумя пунктами.
    const nextYear = (per.kpn_year || new Date().getFullYear()) + 1
    checklist.push([`31.03.${nextYear}`,
      'Получить от нерезидента сертификат резидентства (ст. 705 п. 3)'])
    checklist.push([`05.04.${nextYear}`,
      'Сдать копию сертификата в налоговый орган (ст. 705 п. 7)'])
  }
  if (verdict.advance_control_date) {
    checklist.push([asDate(verdict.advance_control_date),
      'Контрольная дата по авансу: если нерезидент не отработал, сумма становится доходом из источников в РК'])
  }

  return (
    <div className="f10104-result">
      {needsReview && (
        <div style={{
          background: '#fff7ed', border: '1px solid #fed7aa', color: '#7c2d12',
          borderRadius: 8, padding: '13px 15px', marginBottom: 16,
          fontSize: 14, lineHeight: 1.55,
        }}>
          {refbooks.disclaimer.manual_review_banner}
        </div>
      )}

      {/* ── Блок 1. Резюме ── */}
      <div style={card}>
        <h3 style={{ marginTop: 0, fontSize: 17 }}>Что вы должны</h3>

        {kpn.taxable && kpnUnknown ? (
          <SummaryRow mark="⚠" title="КПН за нерезидента"
            value="требует решения — см. ниже" tone="#9a3412" />
        ) : kpn.taxable ? (
          <SummaryRow
            mark="✅" title="КПН за нерезидента"
            value={`${money(kpn.amount_kzt)} · срок до ${asDate(dl.kpn_payment)}`}
          />
        ) : (
          <SummaryRow mark="—" title="КПН за нерезидента" value="не возникает" tone="#475569" />
        )}

        {kpn.position_chosen && (
          <div style={{
            margin: '2px 0 10px 26px', fontSize: 12.5, color: '#78350f',
            lineHeight: 1.55,
          }}>
            Позицию по спорной норме выбрал пользователь
            ({Math.round((kpn.position_rate ?? 0) * 100)} %). Основание:{' '}
            {kpn.position_basis}. Дата: {new Date().toLocaleDateString('ru-RU')}.
          </div>
        )}

        {vatUnknown ? (
          // Ноль здесь был бы утверждением «налога нет», а это неверно.
          <SummaryRow mark="⚠" title="НДС за нерезидента"
            value="требует решения — см. ниже" tone="#9a3412" />
        ) : vat.applicable ? (
          <SummaryRow mark="✅" title="НДС за нерезидента"
            value={`${money(vat.amount_kzt)} · срок до ${asDate(dl.vat_payment)}`} />
        ) : (
          <SummaryRow mark="—" title="НДС за нерезидента" value="не возникает" tone="#475569" />
        )}

        <SummaryRow
          mark={rep.form_101_04_required ? '📄' : '—'}
          title="Форма 101.04"
          value={rep.form_101_04_required
            ? `${rep.period || ''} · срок до ${asDate(dl.form_101_04)}`
            : 'не требуется'}
          tone={rep.form_101_04_required ? undefined : '#475569'}
        />

        {verdict.route === 'individual_200_00' && (
          <SummaryRow mark="↗" title="Маршрут" value="Физлицо: ИПН и форма 200.00, приложение 200.02" />
        )}

        {per.vat_quarter && per.kpn_quarter && per.vat_quarter !== per.kpn_quarter && (
          <div style={{ ...hintS, marginTop: 10 }}>
            НДС попадает в {per.vat_quarter} квартал, КПН и форма 101.04 — в {per.kpn_quarter}.
            Это нормально и не является ошибкой.
          </div>
        )}
      </div>

      {/* ── manual_review: вопрос вместо числа ── */}
      {kpnUnknown && kpn.taxable && (
        <div style={{ marginBottom: 16 }}>
          <ManualReview
            question={kpn.positions?.length
              ? 'Ставка по этой выплате спорна: норма допускает два прочтения.'
              : 'Ставку по конвенции определить нельзя: в справочной таблице запись неоднозначна.'}
            positions={
              // Позиции по спорной норме приходят из справочника целиком:
              // формулировки не сочиняются в интерфейсе.
              (kpn.positions || []).length
                ? kpn.positions.map((p: any) =>
                    `${p.basis} — ${Math.round(p.rate * 100)} %. ${p.argument}`)
                : [kpn.treaty_note || 'Запись о ставке в справочной таблице неоднозначна.']
            }
            whatToCheck={kpn.what_to_check
              || 'Сверьте статью 10, 11 или 12 текста конвенции на adilet.zan.kz либо обратитесь к налоговому консультанту.'}
          />
        </div>
      )}

      {vatUnknown && (
        <div style={{ marginBottom: 16 }}>
          <ManualReview
            question={vat.reason || 'Определение места реализации требует ручной проверки.'}
            positions={[
              'По остаточному правилу место реализации определяется по исполнителю — тогда НДС не возникает.',
              'При иной квалификации договора место реализации может быть признано РК — тогда НДС начисляется.',
            ]}
            whatToCheck={`${vat.basis || 'ст. 459 п. 2'} — сверьте формулировку предмета договора с текстом на adilet.zan.kz либо обратитесь к налоговому консультанту.`}
          />
        </div>
      )}

      {/* ── Блок 2. Расчёт ── */}
      <Collapsible title="Расчёт">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
          <tbody>
            <tr><td style={cellL}>Сумма по акту</td><td style={cellR}>{answers['S4.4']} {answers['S1.5']}</td><td style={cellN}>—</td></tr>
            <tr><td style={cellL}>Курс для КПН</td><td style={cellR}>{verdict.fx_used?.kpn}</td><td style={cellN}>ст. 684 п. 1</td></tr>
            <tr><td style={cellL}>База КПН</td><td style={cellR}>{money(kpn.base_kzt)}</td><td style={cellN}>ст. 683</td></tr>
            {kpnUnknown ? (
              <tr><td style={cellL}>Ставка КПН</td>
                <td style={cellR}>не определена — см. выше</td>
                <td style={cellN}>ст. 706</td></tr>
            ) : (
              <>
                <tr><td style={cellL}>Ставка КПН</td><td style={cellR}>{Math.round((kpn.rate ?? 0) * 100)} %</td><td style={cellN}>{kpn.basis?.[0] || 'ст. 682'}</td></tr>
                <tr><td style={cellL}><b>КПН к уплате</b></td><td style={cellR}><b>{money(kpn.amount_kzt)}</b></td><td style={cellN}>—</td></tr>
              </>
            )}
            {vat.applicable === true && (
              <>
                <tr><td style={cellL}>Курс для НДС</td><td style={cellR}>{verdict.fx_used?.vat}</td><td style={cellN}>ст. 463 п. 2</td></tr>
                <tr><td style={cellL}>База НДС</td><td style={cellR}>{money(vat.base_kzt)}</td><td style={cellN}>ст. 463 п. 1</td></tr>
                <tr><td style={cellL}><b>НДС к уплате</b></td><td style={cellR}><b>{money(vat.amount_kzt)}</b></td><td style={cellN}>ст. 454</td></tr>
              </>
            )}
          </tbody>
        </table>
      </Collapsible>

      {/* ── Блок 3. Заготовка формы ── */}
      {rep.reported_in_form && (
        <div style={card}>
          <h3 style={{ marginTop: 0, fontSize: 17 }}>Заготовка приложения к форме 101.04</h3>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
            <tbody>
              {Object.entries(verdict.graphs || {})
                .filter(([, value]) => value !== null && value !== undefined && value !== '')
                .map(([graph, value]) => (
                  <tr key={graph}>
                    <td style={{ ...cellL, width: 60 }}><b>{graph}</b></td>
                    <td style={cellR}>
                      {String(value)}
                      {graph === 'F' && (
                        <span style={{ color: '#9a3412', marginLeft: 8 }}>
                          ⚠ кандидат — сверьте со справочником СОНО
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Блок 4. Чек-лист действий с датами ── */}
      {checklist.length > 0 && (
        <div style={card}>
          <h3 style={{ marginTop: 0, fontSize: 17 }}>Что и когда сделать</h3>
          {checklist.map(([when, what], i) => (
            <div key={i} style={{
              display: 'flex', gap: 12, padding: '8px 0',
              borderBottom: '1px solid #f1f5f9', fontSize: 14,
            }}>
              <b style={{ minWidth: 96 }}>{when}</b>
              <span>{what}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Блок 5. Красные флаги ── */}
      {flags.length > 0 && (
        <div>
          <h3 style={{ fontSize: 17, margin: '0 0 10px' }}>На что обратить внимание</h3>
          {flags.map((f) => <FlagCard key={f.code} flag={f} />)}
        </div>
      )}

      {/* ── Блок 6. Нормативное обоснование ── */}
      {kpn.position_chosen && (
        <div style={{
          marginBottom: 16, padding: '12px 14px', borderRadius: 8,
          border: '1px solid #cbd5e1', background: '#fff', fontSize: 13,
          lineHeight: 1.6, color: '#334155',
        }}>
          <b>Позицию по спорной норме выбрал пользователь.</b>{' '}
          Ставка {Math.round((kpn.position_rate ?? 0) * 100)} %.
          {' '}Основание: {kpn.position_basis}.
          {' '}Дата выбора: {new Date().toLocaleDateString('ru-RU')}.
          <div style={{ fontSize: 12.5, color: '#64748b', marginTop: 5 }}>
            Вопрос остаётся спорным: помогайка этот вывод себе не присваивает.
            Строка печатается и здесь, и в резюме выше.
          </div>
        </div>
      )}

      <ExplanationBlock
        explanation={verdict.explanation}
        answerLabels={ANSWER_LABELS}
      />

      <Collapsible title="Нормативное обоснование">
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13.5, lineHeight: 1.7 }}>
          {[...(kpn.basis || []), ...(verdict.basis || []), vat.basis]
            .filter(Boolean)
            .map((b: string, i: number) => <li key={i}>{b}</li>)}
        </ul>
      </Collapsible>

      {/* ── Блок 7. Дисклеймер — обязателен, не сворачивается ── */}
      <div className="f10104-disclaimer" style={{
        background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: 8,
        padding: '14px 16px', fontSize: 13, lineHeight: 1.6, color: '#334155',
        marginTop: 16,
      }}>
        {refbooks.disclaimer.text}
      </div>

      <div className="f10104-print-footer" style={{
        display: 'none', marginTop: 12, fontSize: 11, color: '#64748b',
      }}>
        {refbooks.disclaimer.print_footer}
      </div>

      <div className="f10104-noprint" style={{ display: 'flex', gap: 10, marginTop: 16 }}>
        <button className="btn btn-secondary" onClick={onBack}>Вернуться к ответам</button>
        <button className="btn btn-primary" onClick={() => window.print()}>
          Печать или сохранение в PDF
        </button>
      </div>
    </div>
  )
}

// ── Страница ──────────────────────────────────────────────────────────────

export default function F10104Page() {
  const [draft, setDraft] = useState<Draft>(loadDraft)
  const [refbooks, setRefbooks] = useState<F10104Refbooks | null>(null)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const savedTimer = useRef<number | undefined>(undefined)

  const answers = draft.answers

  useEffect(() => {
    f10104Api.getRefbooks()
      .then(setRefbooks)
      .catch(() => setError('Не удалось загрузить справочники. Модуль недоступен.'))
  }, [])

  useEffect(() => {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...draft, savedAt: Date.now() }))
    setSaved(true)
    window.clearTimeout(savedTimer.current)
    savedTimer.current = window.setTimeout(() => setSaved(false), 1500)
  }, [draft])

  const countryIndex = useMemo(() => {
    const map = new Map<string, F10104Country>()
    refbooks?.countries.forEach((c) => map.set(c.key, c))
    return map
  }, [refbooks])

  const kindIndex = useMemo(() => {
    const map = new Map<string, F10104ServiceKind>()
    refbooks?.service_kinds.forEach((k) => map.set(k.id, k))
    return map
  }, [refbooks])

  const visibleSteps = useMemo(
    () => STEPS.filter((s) => !s.visible || s.visible(answers, countryIndex)),
    [answers, countryIndex],
  )
  const stepIndex = Math.min(draft.stepIndex, visibleSteps.length - 1)
  const step = visibleSteps[stepIndex]

  const set = (key: string, value: unknown) =>
    setDraft((d) => ({ ...d, answers: { ...d.answers, [key]: value } }))

  const go = (i: number) => setDraft((d) => ({ ...d, stepIndex: Math.max(0, i) }))

  function resetDraft() {
    localStorage.removeItem(DRAFT_KEY)
    setDraft({ ...EMPTY_DRAFT, savedAt: Date.now() })
  }

  const flag = (code: string): F10104Flag | null => refbooks?.flags[code] || null

  // Предупреждения по ходу: показываются сразу, как только ответ включает
  // условие, а не в конце. Условие берётся из данных справочника (признак
  // страны), текст — тоже из справочника.
  // Предупреждения по ходу: показываются сразу, как только ответ включает
  // условие, а не в конце. Условия здесь ЗЕРКАЛЯТ движок — если разойдутся,
  // визард пообещает флаг, которого в вердикте не будет. Тексты берутся из
  // справочника, в этом файле их нет.
  function liveFlags(): F10104Flag[] {
    const codes: string[] = []
    const country = countryIndex.get(answers['S2.3'])
    const kind = kindIndex.get(answers['S5.5'])
    const id = step?.id

    if (id === 'S1' && answers['S1.4'] === 'no') codes.push('F-VAT-THRESHOLD')
    if (id === 'S2' && country?.is_offshore) codes.push('F-OFFSHORE')

    if (id === 'S5') {
      if (answers['S2.1'] === 'advance') codes.push('F-ADVANCE')
      if (answers['S5.1'] === 'goods' && answers['S5.4'] === 'no') codes.push('F-MIXED')
      if (answers['S5.1'] === 'royalty' && answers['S5.6'] === 'yes' && answers['S5.7'] === 'no') {
        codes.push('F-ROYALTY')
      }
      if (answers['S5.1'] === 'dividends' && Number(answers['S5.8']?.share_pct) >= 25) {
        codes.push('F-DIV-25')
      }
      // Движок ставит F-DESIGN-SCOPE именно на разработку ПО: там выше всего
      // риск переквалификации в дизайнерские услуги.
      if (answers['S5.1'] === 'services' && kind?.id === 'software_dev') {
        codes.push('F-DESIGN-SCOPE')
      }
    }

    if (id === 'S3' && ['over_183', 'construction', 'dependent_agent'].includes(answers['S3.4'])) {
      codes.push('F-PE-RISK')
    }

    if (id === 'S6' && answers['S6.1'] === 'partly' && answers['S6.2'] === 'no') {
      codes.push('F-MIXED')
    }

    return codes.map((c) => flag(c)).filter((f): f is F10104Flag => !!f)
  }

  // Зеркало движка: даты разные, курс на дату оборота не задан.
  function singleRateReused(): boolean {
    const currency = answers['S1.5']
    return !!currency && currency !== 'KZT'
      && !!answers['S4.1'] && !!answers['S4.2'] && answers['S4.1'] !== answers['S4.2']
      && !answers['S4.5b']
  }

  const period = answers['S1.1'] || {}

  const canAdvance = (): boolean => {
    if (step?.id === 'S1') {
      return !!period.quarter && !!period.year && !!answers['S1.3']
        && !!answers['S1.4'] && !!answers['S1.5']
    }
    if (step?.id === 'S2') {
      return !!answers['S2.1'] && !!answers['S2.2'] && !!answers['S2.3']
    }
    if (step?.id === 'S5') {
      if (!answers['S5.1']) return false
      if (answers['S5.1'] === 'services' && !answers['S5.5']) return false
      if (answers['S5.1'] === 'goods' && !answers['S5.2']) return false
      // Позиция по спорной норме без обоснования не принимается. Проверка
      // дублирует движок намеренно: пользователь должен узнать об этом на
      // шаге, а не увидеть на экране результата вопрос вместо суммы.
      const dividends = answers['S5.8'] || {}
      if (dividends.position && !String(dividends.position_basis || '').trim()) {
        return false
      }
      return true
    }
    if (step?.id === 'S3') return !!answers['S3.1'] && !!answers['S3.4']
    if (step?.id === 'S6') return !!answers['S6.1']
    if (step?.id === 'S7') return !!answers['S7.2']
    if (step?.id === 'S4') {
      const fxOk = answers['S1.5'] === 'KZT' || !!answers['S4.5']
      return !!answers['S4.2'] && !!answers['S4.4'] && fxOk
    }
    return true
  }

  if (error) {
    return (
      <div style={{ maxWidth: 900, margin: '0 auto', paddingBottom: 60 }}>
        <h2 style={{ margin: '16px 0' }}>Помогайка по форме 101.04</h2>
        <div className="error-message">{error}</div>
      </div>
    )
  }

  if (!refbooks) {
    return <div className="loading">Загрузка…</div>
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', paddingBottom: 60 }}>
      <style>{PRINT_CSS}</style>
      <h2 style={{ margin: '16px 0 6px' }}>Помогайка по форме 101.04</h2>
      <div style={{ color: '#64748b', fontSize: 13.5, marginBottom: 14 }}>
        КПН у источника выплаты и НДС за нерезидента · справочник правил {refbooks.rules_version}
      </div>

      <div style={{
        background: '#fff7ed', border: '1px solid #fed7aa', color: '#9a3412',
        padding: '12px 16px', borderRadius: 8, marginBottom: 16, fontSize: 13.5, lineHeight: 1.55,
      }}>
        <strong>Внутренняя бета.</strong> Результаты не являются налоговой консультацией
        и не должны передаваться клиентам без проверки. Ответы хранятся только в этом
        браузере и на сервере не сохраняются.
      </div>

      <StepNav steps={visibleSteps} current={stepIndex} onGo={go} />

      {step?.id === 'R' && (
        <ResultScreen
          answers={answers}
          refbooks={refbooks}
          onBack={() => go(stepIndex - 1)}
        />
      )}

      {step?.id !== 'R' && (
      <div style={card}>
        {step?.id === 'S1' && (
          <>
            <h3 style={{ marginTop: 0, fontSize: 17 }}>Контекст</h3>

            <div style={{ marginBottom: 22 }}>
              <span style={label}>Налоговый период операции</span>
              <div style={{ display: 'flex', gap: 10 }}>
                <select
                  style={inputS}
                  value={period.quarter || ''}
                  onChange={(e) => set('S1.1', { ...period, quarter: Number(e.target.value) })}
                >
                  <option value="">Квартал</option>
                  {QUARTERS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
                </select>
                <select
                  style={inputS}
                  value={period.year || ''}
                  onChange={(e) => set('S1.1', { ...period, year: Number(e.target.value) })}
                >
                  <option value="">Год</option>
                  {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>
              <div style={hintS}>
                Помогайка работает только с новым Налоговым кодексом — периоды с I квартала 2026 года.
              </div>
            </div>

            <Radio
              question="Категория вашей компании"
              options={COMPANY_SIZE}
              value={answers['S1.2']}
              onChange={(v) => set('S1.2', v)}
              hint="Влияет только на размер штрафа по КоАП, на сумму налога не влияет."
            />

            <Radio
              question="Ваша компания — резидент РК?"
              options={RESIDENCY}
              value={answers['S1.3']}
              onChange={(v) => set('S1.3', v)}
            />

            <Radio
              question="Вы состоите на регистрационном учёте по НДС?"
              options={VAT_REGISTERED}
              value={answers['S1.4']}
              onChange={(v) => set('S1.4', v)}
              // Второе предложение — про то, «как было до 2026 года» — убрано:
              // текста прежнего кодекса у нас нет, и практикующий бухгалтер
              // говорит, что так было всегда. Непроверенное не утверждаем.
              hint={'С 1 января 2026 года НДС за нерезидента платит только покупатель, состоящий '
                + 'на регистрационном учёте по НДС (ст. 454 п. 1 НК РК).'}
            />

            <div style={{ marginBottom: 4 }}>
              <span style={label}>Валюта расчётов по договору</span>
              <select
                style={{ ...inputS, maxWidth: 220 }}
                value={answers['S1.5'] || ''}
                onChange={(e) => set('S1.5', e.target.value)}
              >
                <option value="">Выберите валюту</option>
                {refbooks.currencies.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              {answers['S1.5'] && answers['S1.5'] !== 'KZT' && period.quarter && period.year && (
                <RatesPanel currency={answers['S1.5']} quarter={period.quarter} year={period.year} />
              )}
              {answers['S1.5'] && answers['S1.5'] !== 'KZT' && !(period.quarter && period.year) && (
                <div style={hintS}>Укажите налоговый период — и появится панель загрузки курсов.</div>
              )}
            </div>
          </>
        )}

        {step?.id === 'S2' && (
          <>
            <h3 style={{ marginTop: 0, fontSize: 17 }}>Событие и контрагент</h3>

            <Radio
              question="Что произошло?"
              options={EVENTS}
              value={answers['S2.1']}
              onChange={(v) => set('S2.1', v)}
              hint="Взаимозачёт, прощение долга, передача имущества и бартер — это тоже выплата дохода (ст. 679 п. 2)."
            />

            <Radio
              question="Кто получатель?"
              options={RECIPIENTS}
              value={answers['S2.2']}
              onChange={(v) => set('S2.2', v)}
            />

            <div style={{ marginBottom: 22 }}>
              <span style={label}>Страна резидентства контрагента</span>
              <select
                style={inputS}
                value={answers['S2.3'] || ''}
                onChange={(e) => set('S2.3', e.target.value)}
              >
                <option value="">Выберите страну</option>
                <optgroup label="Страны">
                  {refbooks.countries.filter((c) => !c.is_offshore).map((c) => (
                    <option key={c.key} value={c.key}>
                      {c.name}{c.has_convention ? ' · есть конвенция' : ''}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Государства с льготным налогообложением (перечень № 492)">
                  {refbooks.countries.filter((c) => c.is_offshore).map((c) => (
                    <option key={c.key} value={c.key}>№ {c.offshore_no} — {c.name}</option>
                  ))}
                </optgroup>
              </select>
            </div>

            <div style={{ marginBottom: 22 }}>
              <span style={label}>Наименование, налоговый номер, реквизиты контракта</span>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <input
                  style={inputS} placeholder="Наименование контрагента"
                  value={answers['S2.4']?.name || ''}
                  onChange={(e) => set('S2.4', { ...(answers['S2.4'] || {}), name: e.target.value })}
                />
                <input
                  style={inputS} placeholder="Налоговый номер в стране резидентства"
                  value={answers['S2.4']?.tin || ''}
                  onChange={(e) => set('S2.4', { ...(answers['S2.4'] || {}), tin: e.target.value })}
                />
                <input
                  style={inputS} placeholder="Номер контракта"
                  value={answers['S2.4']?.contract_no || ''}
                  onChange={(e) => set('S2.4', { ...(answers['S2.4'] || {}), contract_no: e.target.value })}
                />
                <input
                  style={inputS} type="date" placeholder="Дата контракта"
                  value={answers['S2.4']?.contract_date || ''}
                  onChange={(e) => set('S2.4', { ...(answers['S2.4'] || {}), contract_date: e.target.value })}
                />
              </div>
              <div style={hintS}>Попадает в графы C, E и G приложения к форме.</div>
            </div>

            <Radio
              question="Есть ли учётный номер валютного договора (УНК)?"
              options={UNK_OPTIONS}
              value={answers['S2.5'] ? 'yes' : answers['_unk'] || ''}
              onChange={(v) => {
                set('_unk', v)
                if (v !== 'yes') set('S2.5', null)
              }}
              hint="УНК присваивается банком при сумме договора свыше 50 000 USD — это валютный контроль, на налоги не влияет."
            />
            {answers['_unk'] === 'yes' && (
              <input
                style={{ ...inputS, maxWidth: 320, marginTop: -12, marginBottom: 20 }}
                placeholder="Номер УНК"
                value={answers['S2.5'] || ''}
                onChange={(e) => set('S2.5', e.target.value)}
              />
            )}
          </>
        )}

        {step?.id === 'S5' && (
          <>
            <h3 style={{ marginTop: 0, fontSize: 17 }}>Тип дохода</h3>

            <Radio
              question="Что вы приобрели или за что платите?"
              options={INCOME_TYPES}
              value={answers['S5.1']}
              onChange={(v) => set('S5.1', v)}
            />

            {answers['S5.1'] === 'goods' && (
              <>
                {/* Норма звучит сразу при выборе вида дохода, а не в заключении:
                    иначе бухгалтер проходит всю ветку, не понимая, зачем она. */}
                <div style={{
                  marginBottom: 18, padding: '11px 13px', borderRadius: 8,
                  border: '1px solid #bbf7d0', background: '#f0fdf4',
                  fontSize: 13, lineHeight: 1.6, color: '#166534',
                }}>
                  <b>Выплата за поставку товара доходом из источников в РК не признаётся</b>{' '}
                  (ст. 680 п. 1 пп. 4)) — КПН у источника с неё не удерживается.
                  <div style={{ marginTop: 5, color: '#3f6212' }}>
                    Эта ветка нужна из-за второй половины нормы: работы и услуги
                    на территории РК, связанные с поставкой. Если их стоимость
                    не выделена в цене — облагается вся стоимость контракта.
                  </div>
                </div>

                <Radio
                  question="Товар ввозится в РК по внешнеторговому контракту?"
                  options={YES_NO}
                  value={answers['S5.2']}
                  onChange={(v) => set('S5.2', v)}
                />
                <Radio
                  question="Включает ли контракт работы или услуги на территории РК — шефмонтаж, пусконаладку, обучение, гарантийное обслуживание?"
                  options={YES_NO}
                  value={answers['S5.3']}
                  onChange={(v) => set('S5.3', v)}
                />
                {answers['S5.3'] === 'yes' && (
                  <>
                    <Radio
                      question="Стоимость этих работ и услуг выделена отдельно в контракте или акте?"
                      options={YES_NO}
                      value={answers['S5.4']}
                      onChange={(v) => set('S5.4', v)}
                    />
                    {answers['S5.4'] === 'yes' && (
                      <div style={{ marginBottom: 22 }}>
                        <span style={label}>
                          Стоимость работ и услуг на территории РК, {answers['S1.5'] || 'валюта договора'}
                        </span>
                        <input
                          style={{ ...inputS, maxWidth: 260 }} type="number" min="0"
                          placeholder="Только услуги, без стоимости товара"
                          value={answers['S5.4a'] ?? ''}
                          onChange={(e) => set('S5.4a', e.target.value === '' ? null : Number(e.target.value))}
                        />
                        <div style={hintS}>
                          Это и есть база по КПН. Стоимость самого товара в неё не входит.
                        </div>
                      </div>
                    )}
                  </>
                )}
              </>
            )}

            {answers['S5.1'] === 'services' && (
              <div style={{ marginBottom: 22 }}>
                <span style={label}>Конкретный вид услуги</span>
                <select
                  style={inputS}
                  value={answers['S5.5'] || ''}
                  onChange={(e) => set('S5.5', e.target.value)}
                >
                  <option value="">Выберите вид услуги</option>
                  <optgroup label="Облагаются независимо от места оказания">
                    {refbooks.service_kinds.filter((k) => k.group === 'A').map((k) => (
                      <option key={k.id} value={k.id}>{k.label}</option>
                    ))}
                  </optgroup>
                  <optgroup label="Общие виды работ и услуг">
                    {refbooks.service_kinds.filter((k) => k.group !== 'A').map((k) => (
                      <option key={k.id} value={k.id}>{k.label}</option>
                    ))}
                  </optgroup>
                </select>
                {kindIndex.get(answers['S5.5'])?.group === 'A' && (
                  <div style={{
                    marginTop: 8, padding: '10px 12px', background: '#eff6ff',
                    border: '1px solid #bfdbfe', borderRadius: 8, fontSize: 13, color: '#1e40af',
                  }}>
                    Этот вид услуг облагается КПН у источника выплаты даже если услуги
                    полностью оказаны за пределами Казахстана — подпункт 3) пункта 1
                    статьи 679 НК РК. Освобождение по подпункту 5) пункта 1 статьи 681
                    к нему не применяется. С 2026 года в перечень добавлены обработка
                    информации, дизайнерские и рекламные услуги.
                  </div>
                )}
              </div>
            )}

            {answers['S5.1'] === 'royalty' && (
              <>
                <Radio
                  question="Включает ли платёж услуги по сопровождению или технической поддержке?"
                  options={YES_NO}
                  value={answers['S5.6']}
                  onChange={(v) => set('S5.6', v)}
                />
                {answers['S5.6'] === 'yes' && (
                  <Radio
                    question="Выделены ли они отдельной строкой в инвойсе или акте?"
                    options={YES_NO}
                    value={answers['S5.7']}
                    onChange={(v) => set('S5.7', v)}
                  />
                )}
              </>
            )}

            {answers['S5.1'] === 'dividends' && (
              <div style={{ marginBottom: 22 }}>
                <span style={label}>Доля участия нерезидента в капитале, %</span>
                <input
                  style={{ ...inputS, maxWidth: 160 }} type="number" min="0" max="100"
                  value={answers['S5.8']?.share_pct ?? ''}
                  onChange={(e) => set('S5.8', {
                    ...(answers['S5.8'] || {}),
                    share_pct: e.target.value === '' ? null : Number(e.target.value),
                  })}
                />
                <div style={hintS}>Влияет на выбор ставки и на предупреждение о спорной норме.</div>
              </div>
            )}

            {answers['S5.1'] === 'dividends'
              && Number(answers['S5.8']?.share_pct) >= 25
              && refbooks?.disputed_dividends && (
              <DisputedPosition
                spec={refbooks.disputed_dividends}
                value={answers['S5.8'] || {}}
                hasBasis={answers['_s58HasBasis'] as string | undefined}
                onHasBasis={(v) => set('_s58HasBasis', v)}
                onChange={(patch) => set('S5.8', { ...(answers['S5.8'] || {}), ...patch })}
              />
            )}

            {answers['S5.1'] === 'insurance' && (
              <Radio
                question="Страхование или перестрахование?"
                options={INSURANCE_KINDS}
                value={answers['S5.10']}
                onChange={(v) => set('S5.10', v)}
              />
            )}

            {answers['S2.1'] === 'advance' && (
              <>
                <Radio
                  question="Доход по этому авансу уже начислен?"
                  options={YES_NO}
                  value={answers['S5.9']?.accrued === true ? 'yes'
                    : answers['S5.9']?.accrued === false ? 'no' : ''}
                  onChange={(v) => set('S5.9', { ...(answers['S5.9'] || {}), accrued: v === 'yes' })}
                  hint="Аванс без начисления дохода в форму 101.04 не попадает вовсе."
                />
                {answers['S5.9']?.accrued === true && (
                  <div style={{ marginBottom: 22 }}>
                    <span style={label}>
                      Начисленная часть, {answers['S1.5'] || 'валюта договора'} — если начислен не весь аванс
                    </span>
                    <input
                      style={{ ...inputS, maxWidth: 260 }} type="number" min="0"
                      placeholder="Оставьте пустым, если начислен весь аванс"
                      value={answers['S5.9']?.accrued_amount ?? ''}
                      onChange={(e) => set('S5.9', {
                        ...(answers['S5.9'] || {}),
                        accrued_amount: e.target.value === '' ? null : Number(e.target.value),
                      })}
                    />
                    <div style={hintS}>Налог считается только с начисленной суммы.</div>
                  </div>
                )}
              </>
            )}
          </>
        )}

        {step?.id === 'S3' && (
          <>
            <h3 style={{ marginTop: 0, fontSize: 17 }}>Постоянное учреждение</h3>
            <div style={{ ...hintS, marginTop: 0, marginBottom: 16 }}>
              Проверяем, не ведёт ли контрагент деятельность в РК через постоянное
              учреждение: от этого зависит, удерживаете ли вы налог вообще.
            </div>

            <Radio
              question="Есть ли у контрагента БИН РК или регистрационное свидетельство налогового органа?"
              options={PE_HAS_BIN}
              value={answers['S3.1']}
              onChange={(v) => set('S3.1', v)}
            />

            {answers['S3.1'] === 'yes' && (
              <>
                <Radio
                  question="С кем заключён контракт?"
                  options={PE_CONTRACT_WITH}
                  value={answers['S3.2']}
                  onChange={(v) => set('S3.2', v)}
                />
                <Radio
                  question="Счёт-фактура выписана филиалом с казахстанским БИН?"
                  options={YES_NO}
                  value={answers['S3.3']}
                  onChange={(v) => set('S3.3', v)}
                />
              </>
            )}

            <Radio
              question="Длительность деятельности нерезидента в РК по этому и связанным проектам"
              options={PE_DURATION}
              value={answers['S3.4']}
              onChange={(v) => set('S3.4', v)}
            />
          </>
        )}

        {step?.id === 'S6' && (
          <>
            <h3 style={{ marginTop: 0, fontSize: 17 }}>Место оказания услуг</h3>
            <div style={{ ...hintS, marginTop: 0, marginBottom: 16 }}>
              Место оказания услуг для КПН и место реализации для НДС — разные
              понятия с разными правилами. Помогайка считает их отдельно.
            </div>

            <Radio
              question="Где фактически выполнялись работы или оказывались услуги?"
              options={PLACE_OF_SUPPLY}
              value={answers['S6.1']}
              onChange={(v) => set('S6.1', v)}
            />

            {answers['S6.1'] === 'partly' && (
              <Radio
                question="Есть ли документально подтверждённое распределение стоимости?"
                options={YES_NO}
                value={answers['S6.2']}
                onChange={(v) => set('S6.2', v)}
              />
            )}
          </>
        )}

        {step?.id === 'S7' && (
          <>
            <h3 style={{ marginTop: 0, fontSize: 17 }}>Конвенция об избежании двойного налогообложения</h3>
            <div style={{ ...hintS, marginTop: 0, marginBottom: 16 }}>
              С этой страной конвенция есть. Освобождение или пониженная ставка
              применяются не автоматически: условия проверяются ниже.
            </div>

            <Radio
              question="Хотите применить освобождение или пониженную ставку по конвенции?"
              options={YES_NO}
              value={answers['S7.2']}
              onChange={(v) => set('S7.2', v)}
              hint="Ответ «нет» — расчёт по ставкам Налогового кодекса."
            />

            {answers['S7.2'] === 'yes' && (
              <>
                <Radio
                  question="Получен ли документ, подтверждающий резидентство?"
                  options={CERT_STATUS}
                  value={answers['S7.3']}
                  onChange={(v) => set('S7.3', v)}
                  hint="Без сертификата на дату выплаты налог удерживается по ставке НК. Это не потеряно: нерезидент вправе подать заявление на возврат из бюджета (ст. 699–701)."
                />
                <Radio
                  question="Связан ли доход с деятельностью постоянного учреждения нерезидента в РК?"
                  options={YES_NO}
                  value={answers['S7.4']}
                  onChange={(v) => set('S7.4', v)}
                />
                {['dividends', 'royalty', 'interest'].includes(answers['S5.1']) && (
                  <Radio
                    question="Нерезидент — окончательный (фактический) получатель дохода, а не агент, номинальный держатель или посредник?"
                    options={YES_NO}
                    value={answers['S7.5']}
                    onChange={(v) => set('S7.5', v)}
                    hint="Для дивидендов, вознаграждений и роялти это отдельное условие ст. 706."
                  />
                )}
                <Radio
                  question="Использует ли контрагент положения конвенции в интересах третьего лица, не являющегося резидентом этой страны?"
                  options={YES_NO}
                  value={answers['S7.6']}
                  onChange={(v) => set('S7.6', v)}
                />
              </>
            )}

            <Radio
              question="Уплачиваете ли вы налог за счёт собственных средств, без удержания с дохода нерезидента?"
              options={YES_NO}
              value={answers['S7.7']}
              onChange={(v) => set('S7.7', v)}
            />
          </>
        )}

        {step?.id === 'S8' && (
          <>
            <h3 style={{ marginTop: 0, fontSize: 17 }}>Чек-лист сертификата резидентства</h3>
            <div style={{ ...hintS, marginTop: 0, marginBottom: 16 }}>
              Отметьте выполненные пункты. Непроставленный пункт попадёт
              в заключение как предупреждение — ответственность за неправомерное
              освобождение несёт налоговый агент, а не нерезидент.
            </div>

            {CERT_CHECKLIST.map(([key, title, note]) => (
              <label key={key} style={{
                display: 'flex', gap: 10, alignItems: 'flex-start', padding: '11px 12px',
                border: `1px solid ${answers[key] ? '#2563eb' : '#e2e8f0'}`,
                background: answers[key] ? '#eff6ff' : '#fff',
                borderRadius: 8, marginBottom: 8, cursor: 'pointer',
              }}>
                <input
                  type="checkbox" style={{ marginTop: 3 }}
                  checked={!!answers[key]}
                  onChange={(e) => set(key, e.target.checked)}
                />
                <span>
                  <span style={{ fontSize: 14, fontWeight: 600 }}>{title}</span>
                  <span style={{ ...hintS, display: 'block' }}>{note}</span>
                </span>
              </label>
            ))}

            <div style={{
              marginTop: 14, padding: '12px 14px', background: '#fff7ed',
              border: '1px solid #fed7aa', borderRadius: 8, fontSize: 13.5,
              color: '#9a3412', lineHeight: 1.55,
            }}>
              <b>Две разные даты, их часто путают.</b>
              <div style={{ marginTop: 6 }}>
                <b>До 31 марта года, следующего за годом выплаты</b> — нерезидент
                представляет сертификат вам, налоговому агенту (ст. 705 п. 3).
              </div>
              <div style={{ marginTop: 4 }}>
                <b>В течение 5 календарных дней после срока сдачи 101.04 за IV квартал,
                то есть примерно 5 апреля</b> — вы сдаёте копию сертификата в налоговый
                орган (ст. 705 п. 7).
              </div>
              <div style={{ marginTop: 6 }}>
                Разные сроки и разные адресаты: первый — вам от контрагента,
                второй — от вас в налоговую.
              </div>
            </div>
          </>
        )}

        {step?.id === 'S4' && (
          <>
            <h3 style={{ marginTop: 0, fontSize: 17 }}>Даты, суммы и курс</h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 18 }}>
              <div>
                <span style={label}>Дата подписания акта или инвойса обеими сторонами</span>
                <input type="date" style={inputS} value={answers['S4.1'] || ''}
                  onChange={(e) => set('S4.1', e.target.value)} />
                <div style={hintS}>Дата совершения оборота для НДС (ст. 460 п. 13).</div>
              </div>
              <div>
                <span style={label}>Дата выплаты — перечисления, зачёта, передачи</span>
                <input type="date" style={inputS} value={answers['S4.2'] || ''}
                  onChange={(e) => set('S4.2', e.target.value)} />
                <div style={hintS}>Определяет период формы 101.04 и срок уплаты КПН (ст. 684).</div>
              </div>
            </div>

            <div style={{ marginBottom: 18 }}>
              <span style={label}>Сумма по акту или инвойсу, {answers['S1.5'] || 'валюта договора'}</span>
              <input
                style={{ ...inputS, maxWidth: 260 }} type="number" min="0"
                value={answers['S4.4'] ?? ''}
                onChange={(e) => set('S4.4', e.target.value === '' ? null : Number(e.target.value))}
              />
            </div>

            {answers['S1.5'] && answers['S1.5'] !== 'KZT' && (
              <>
                <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>Курсы</div>
                <div style={{ ...hintS, marginTop: 0, marginBottom: 10 }}>
                  Одна операция может требовать трёх разных курсов: у КПН и НДС
                  разные даты пересчёта, и переиспользовать один курс нельзя.
                </div>

                <RateField
                  label="Курс на дату выплаты — база КПН"
                  basis="ст. 684 п. 1"
                  currency={answers['S1.5']}
                  day={answers['S4.2']}
                  value={answers['S4.5']}
                  onChange={(v) => set('S4.5', v)}
                />

                {answers['S2.1'] === 'advance' && (
                  <RateField
                    label="Курс на дату начисления дохода — база КПН по авансу"
                    basis="ст. 684 п. 1 пп. 3)"
                    currency={answers['S1.5']}
                    day={answers['S4.3'] || answers['S4.2']}
                    value={answers['S4.5a']}
                    onChange={(v) => set('S4.5a', v)}
                  />
                )}

                {answers['S1.4'] === 'yes' && (
                  <RateField
                    label="Курс на дату совершения оборота — база НДС"
                    basis="ст. 463 п. 2"
                    currency={answers['S1.5']}
                    day={answers['S4.1']}
                    value={answers['S4.5b']}
                    onChange={(v) => set('S4.5b', v)}
                  />
                )}

                {singleRateReused() && (
                  <div style={{
                    background: '#fff7ed', border: '1px solid #fed7aa', color: '#9a3412',
                    borderRadius: 8, padding: '11px 13px', fontSize: 13.5, lineHeight: 1.55,
                  }}>
                    Дата оборота и дата выплаты — разные дни, а курс указан только
                    один. Он будет подставлен и в базу НДС. Заполните курс на дату
                    оборота отдельно либо убедитесь, что на обе даты курс совпадает.
                  </div>
                )}
              </>
            )}
          </>
        )}

        {step?.id === 'S9' && (
          <>
            <h3 style={{ marginTop: 0, fontSize: 17 }}>НДС за нерезидента</h3>
            <div style={{ ...hintS, marginTop: 0, marginBottom: 16 }}>
              Место реализации для НДС и место оказания для КПН — разные понятия.
              Помогайка считает их отдельно, здесь уточняются только исключения.
            </div>

            <div style={{ marginBottom: 20 }}>
              <span style={label}>Применимо ли одно из исключений статьи 454 пункта 3?</span>
              <select
                style={inputS}
                value={answers['S10'] || ''}
                onChange={(e) => set('S10', e.target.value || null)}
              >
                <option value="">Нет, исключения не применяются</option>
                {refbooks.vat_exemptions.map((e) => (
                  <option key={e.id} value={e.id}>{e.label}</option>
                ))}
              </select>
              <div style={hintS}>
                Любое из них означает, что НДС за нерезидента не возникает.
              </div>
            </div>

            <Radio
              question="Если вид услуги требует уточнения — где фактически выполнялись работы или находится имущество?"
              options={PLACE_OF_SUPPLY.slice(0, 2)}
              value={answers['S9.3']}
              onChange={(v) => set('S9.3', v)}
              hint="Нужно для работ с недвижимостью, монтажа, ремонта, обучения и мероприятий. Для остальных видов услуг ответ не влияет на вывод."
            />
          </>
        )}

        {step && !['S1', 'S2', 'S5', 'S3', 'S6', 'S7', 'S8', 'S4', 'S9', 'R'].includes(step.id) && (
          <div style={{ color: '#64748b', fontSize: 14, lineHeight: 1.6 }}>
            <h3 style={{ marginTop: 0, fontSize: 17, color: '#0f172a' }}>{step.title}</h3>
            Шаг <b>{step.id}</b> — следующая итерация. Порядок шагов и условия их показа
            уже работают: попробуйте вернуться и поменять ответы, набор шагов сверху изменится.
          </div>
        )}
      </div>
      )}

      {step?.id !== 'R' && liveFlags().map((f) => <FlagCard key={f.code} flag={f} />)}

      {step?.id !== 'R' && (
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <button
          className="btn btn-secondary"
          onClick={() => go(stepIndex - 1)}
          disabled={stepIndex === 0}
        >
          Назад
        </button>
        <button
          className="btn btn-primary"
          onClick={() => go(stepIndex + 1)}
          disabled={stepIndex >= visibleSteps.length - 1 || !canAdvance()}
        >
          Далее
        </button>
        <button className="btn btn-secondary" onClick={resetDraft}>Очистить</button>
        <span style={{ color: '#94a3b8', fontSize: 12.5, marginLeft: 'auto' }}>
          {saved ? 'Черновик сохранён' : 'Черновик хранится 3 дня в этом браузере'}
        </span>
      </div>

      )}

      {step?.id !== 'R' && !canAdvance() && (
        <div style={{ color: '#94a3b8', fontSize: 12.5, marginTop: 8 }}>
          Заполните обязательные поля шага, чтобы продолжить.
        </div>
      )}
    </div>
  )
}
