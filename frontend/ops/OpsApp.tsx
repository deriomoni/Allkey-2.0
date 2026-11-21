import { useEffect, useState } from 'react'
import { Api } from './api'
import CompaniesList from './CompaniesList'
import CompanyCard from './CompanyCard'
import ReportsImport from './ReportsImport'

type View = { kind: 'list' } | { kind: 'card'; id: number } | { kind: 'import' }

// Навигация внутри раздела — через ?c=<id> и ?view=import, без роутера основного приложения.
function readView(): View {
  const q = new URLSearchParams(window.location.search)
  const c = Number(q.get('c'))
  if (c) return { kind: 'card', id: c }
  if (q.get('view') === 'import') return { kind: 'import' }
  return { kind: 'list' }
}

export default function OpsApp({ api, basePath }: { api: Api; basePath: string }) {
  const [view, setView] = useState<View>(readView)

  useEffect(() => {
    const onPop = () => setView(readView())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const go = (v: View) => {
    const q = v.kind === 'card' ? `?c=${v.id}` : v.kind === 'import' ? '?view=import' : ''
    window.history.pushState(null, '', basePath + q)
    setView(v)
    window.scrollTo(0, 0)
  }

  if (view.kind === 'card') return <CompanyCard api={api} id={view.id} onBack={() => go({ kind: 'list' })} />
  if (view.kind === 'import') return <ReportsImport api={api} onBack={() => go({ kind: 'list' })} />
  return (
    <CompaniesList
      api={api}
      onOpen={(id) => go({ kind: 'card', id })}
      onImport={() => go({ kind: 'import' })}
    />
  )
}
