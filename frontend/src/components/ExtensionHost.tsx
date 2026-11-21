import { useEffect, useRef, useState } from 'react'
import { Navigate, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { API_URL, extensionsApi } from '../api/client'

// Хост для разделов, которые сервер разрешил текущему пользователю (/users/me/extensions).
// Бандл раздела отдаётся сервером только после проверки роли и в основную сборку не входит:
// здесь нет ни его названия, ни маршрутов, ни кода.
interface ExtensionModule {
  mount: (el: HTMLElement, ctx: { apiUrl: string; getToken: () => string | null; basePath: string }) => void
  unmount?: (el: HTMLElement) => void
}

export default function ExtensionHost() {
  const { key } = useParams()
  const { extensions } = useAuth()
  const ext = extensions.find((x) => x.key === key)
  const ref = useRef<HTMLDivElement>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!ext || !ref.current) return
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
        m.mount(el, { apiUrl: API_URL, getToken: () => localStorage.getItem('token'), basePath: ext.path })
      })
      .catch(() => !cancelled && setError('Раздел не загрузился'))
    return () => {
      cancelled = true
      if (mod?.unmount) mod.unmount(el)
      if (blobUrl) URL.revokeObjectURL(blobUrl)
    }
  }, [ext?.key])

  if (!ext) return <Navigate to="/" replace />
  return (
    <div className="container">
      {error && <div className="card">{error}</div>}
      <div ref={ref} />
    </div>
  )
}
