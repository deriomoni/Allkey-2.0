// Отдельный бандл раздела «Компании» (модуль «Операции», этап A).
// Собирается `npm run build:ops` в dist-ops/ops.js и отдаётся сервером только admin
// (GET /api/ops/ui/bundle.js за гейтом). В основную сборку не входит.
import { createRoot, Root } from 'react-dom/client'
import { makeApi, Ctx } from './api'
import OpsApp from './OpsApp'
import AdminsPanel from './AdminsPanel'
import { CSS } from './styles'

const roots = new WeakMap<HTMLElement, Root>()

export function mount(el: HTMLElement, ctx: Ctx) {
  const style = document.createElement('style')
  style.dataset.opsx = '1'
  style.textContent = CSS
  el.appendChild(style)
  const host = document.createElement('div')
  host.className = 'opsx'
  el.appendChild(host)
  const root = createRoot(host)
  roots.set(el, root)
  const api = makeApi(ctx)
  root.render(ctx.view === 'settings' ? <AdminsPanel api={api} /> : <OpsApp api={api} basePath={ctx.basePath} />)
}

export function unmount(el: HTMLElement) {
  roots.get(el)?.unmount()
  roots.delete(el)
  el.innerHTML = ''
}
