import { useState, useEffect } from 'react'
import { auth } from '@/lib/auth'
import { api } from '@/lib/api'

export function useAuth() {
  const [isLoggedIn, setIsLoggedIn] = useState(auth.isLoggedIn())
  const [setupRequired, setSetupRequired] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.authCheck()
      .then((data: { has_user: boolean; setup_required: boolean }) => {
        setSetupRequired(data.setup_required)
        setIsLoggedIn(auth.isLoggedIn())
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const login = async (username: string, password: string) => {
    const data = await api.login(username, password)
    auth.setToken(data.token)
    setIsLoggedIn(true)
  }

  const register = async (username: string, password: string) => {
    const data = await api.register(username, password)
    auth.setToken(data.token)
    setIsLoggedIn(true)
    setSetupRequired(false)
  }

  const logout = () => {
    auth.removeToken()
    setIsLoggedIn(false)
  }

  return { isLoggedIn, setupRequired, loading, login, register, logout }
}
