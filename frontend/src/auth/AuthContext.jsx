import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import {
  EVENTO_SESION_EXPIRADA,
  api,
  guardarTokens,
  limpiarTokens,
  mensajeError,
  tokenAccess,
  tokenRefresh,
} from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null)
  const [cargando, setCargando] = useState(true)

  // Al cargar la página, recupera la sesión si hay tokens guardados.
  useEffect(() => {
    if (!tokenAccess() && !tokenRefresh()) {
      setCargando(false)
      return
    }
    api('/api/auth/me/')
      .then(async (resp) => setUsuario(resp.ok ? await resp.json() : null))
      .catch(() => setUsuario(null))
      .finally(() => setCargando(false))
  }, [])

  useEffect(() => {
    const alExpirar = () => setUsuario(null)
    window.addEventListener(EVENTO_SESION_EXPIRADA, alExpirar)
    return () => window.removeEventListener(EVENTO_SESION_EXPIRADA, alExpirar)
  }, [])

  const login = useCallback(async (username, password) => {
    const resp = await api('/api/auth/login/', { method: 'POST', body: { username, password } }, false)
    if (!resp.ok) throw new Error(await mensajeError(resp))
    const datos = await resp.json()
    guardarTokens(datos)
    setUsuario(datos.usuario)
    return datos.usuario
  }, [])

  const logout = useCallback(async () => {
    const refresh = tokenRefresh()
    try {
      if (refresh) await api('/api/auth/logout/', { method: 'POST', body: { refresh } })
    } finally {
      limpiarTokens()
      setUsuario(null)
    }
  }, [])

  return (
    <AuthContext.Provider value={{ usuario, cargando, login, logout }}>{children}</AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
