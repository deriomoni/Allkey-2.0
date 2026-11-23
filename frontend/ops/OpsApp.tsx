import { useEffect, useState } from 'react'
import { Api } from './api'
import CompaniesList from './CompaniesList'
import CompanyCard from './CompanyCard'

type View = { kind: 'list' } | { kind: 'card'; id: number }

// Навигация внутри раздела — через ?c=<id>, без роутера основного приложения.
// Синхронизация и импорт отчётов — в разделе «Служебное» (ServiceScreen, /x/ops-service).
function readView(): View {
  const c = Number(new URLSearchParams(window.location.search).get('c'))
  return c ? { kind: 'card', id: c } : { kind: 'list' }
}

export default function OpsApp({ api, basePath }: { api: Api; basePath: string }) {
  const [view, setView] = useState<View>(readView)

  useEffect(() => {
    const onPop = () => setView(readView())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  // Адрес списка с фильтрами (?tab=…&regime=…) запоминаем при переходе в карточку и возвращаем на «Назад».
  const [listSearch, setListSearch] = useState(() => (readView().kind === 'list' ? window.location.search : ''))
  const go = (v: View) => {
    if (v.kind === 'card' && view.kind === 'list') setListSearch(window.location.search)
    window.history.pushState(null, '', basePath + (v.kind === 'card' ? `?c=${v.id}` : listSearch))
    setView(v)
    window.scrollTo(0, 0)
  }

  if (view.kind === 'card') return <CompanyCard api={api} id={view.id} onBack={() => go({ kind: 'list' })} />
  return <CompaniesList api={api} onOpen={(id) => go({ kind: 'card', id })} />
}
