import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { authApi, usersApi, servicesApi, User, Service } from '../api/client'

interface AuthContextType {
  user: User | null
  services: Service[]
  isAuthenticated: boolean
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [services, setServices] = useState<Service[]>([])
  const [loading, setLoading] = useState(true)

  const loadSession = async () => {
    const [userData, serviceList] = await Promise.all([
      usersApi.getMe(),
      servicesApi.getMe().catch(() => [] as Service[]),
    ])
    setUser(userData)
    setServices(serviceList)
  }

  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      loadSession()
        .catch(() => {
          localStorage.removeItem('token')
        })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = async (email: string, password: string) => {
    const response = await authApi.login({ username: email, password })
    localStorage.setItem('token', response.access_token)
    await loadSession()
  }

  const register = async (email: string, password: string, fullName: string) => {
    await authApi.register({ email, password, full_name: fullName })
    await login(email, password)
  }

  const logout = () => {
    localStorage.removeItem('token')
    setUser(null)
    setServices([])
  }

  const refreshUser = async () => {
    await loadSession()
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        services,
        isAuthenticated: !!user,
        loading,
        login,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
