import { Navigate, Route, Routes } from 'react-router-dom'
import RutaProtegida from './auth/RutaProtegida'
import { ROLES } from './auth/roles'
import BarraNavegacion from './components/BarraNavegacion'
import Bitacora from './pages/Bitacora'
import Catalogo from './pages/Catalogo'
import Inicio from './pages/Inicio'
import Login from './pages/Login'
import Periodos from './pages/Periodos'

export default function App() {
  return (
    <>
      <BarraNavegacion />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <RutaProtegida>
              <Inicio />
            </RutaProtegida>
          }
        />
        <Route
          path="/catalogo"
          element={
            <RutaProtegida>
              <Catalogo />
            </RutaProtegida>
          }
        />
        <Route
          path="/periodos"
          element={
            <RutaProtegida>
              <Periodos />
            </RutaProtegida>
          }
        />
        <Route
          path="/bitacora"
          element={
            <RutaProtegida roles={[ROLES.AUDITOR]}>
              <Bitacora />
            </RutaProtegida>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  )
}
