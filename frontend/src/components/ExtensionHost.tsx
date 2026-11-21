import { useEffect, useRef, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { API_URL, Extension, extensionsApi } from '../api/client'

// Хост для разделов, которые сервер разрешил текущему пользователю (/users/me/extensions).
// Бандл раздела отдаётся сервером только после проверки роли и в основную сборку не входит:
// здесь нет ни его названия, ни маршрутов, ни кода.
type View = 'page' | 'settings'

interface ExtensionModule {
  mount: (el: HTMLElement, ctx: { apiUrl: string; getToken: () => string | null; basePath: string; view: View }) => void
  unmount?: (el: HTMLElement) => void
}

// Встраивает бандл раздела в элемент. view='settings' — блок раздела на странице «Настройки».
export function ExtensionMount({ ext, view }: { ext: Extension; view: View }) {
  const ref = useRef<HTMLDivElement>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!ref.current) return
    const el = ref.current
    let mod: ExtensionModule | null = null
    let cancelled = false
    let blobUrl = ''
    extensionsApi
      .loadBundle(ext.bundle)
      .then((code) => {
        blobUrl = URL.createObjectURL(new Blob([code], { type: 'text/javascript' }))
        return import(/* @vite-ignore */ blobUrl)
      })
      .then((m: ExtensionModule) => {
        if (cancelled) return
        mod = m
        m.mount(el, { apiUrl: API_URL, getToken: () => localStorage.getItem('token'), basePath: ext.path, view })
      })
      .catch(() => !cancelled && setError('Раздел не загрузился'))
    return () => {
      cancelled = true
      if (mod?.unmount) mod.unmount(el)
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }
  }, [ext.key, ext.bundle, view])

  return (
    <>
      {error && <div className="card">{error}</div>}
      <div ref={ref} />
    </>
  )
}

export default function ExtensionHost() {
  const { key } = useParams()
  const { extensions } = useAuth()
  const ext = extensions.find((x) => x.key === key)
  if (!ext) return <Navigate to="/" replace />
  return (
    <div className="container">
      <ExtensionMount ext={ext} view="page" />
    </div>
  )
}
