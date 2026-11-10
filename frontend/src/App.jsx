import { Navigate, Route, Routes } from 'react-router-dom'
import RutaProtegida from './auth/RutaProtegida'
import { ROLES } from './auth/roles'
import BarraNavegacion from './components/BarraNavegacion'
import AsientoDetalle from './pages/AsientoDetalle'
import AsientoEditor from './pages/AsientoEditor'
import Asientos from './pages/Asientos'
import Balanza from './pages/Balanza'
import Bitacora from './pages/Bitacora'
import LibroDiario from './pages/LibroDiario'
import LibroMayor from './pages/LibroMayor'
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
          path="/asientos"
          element={
            <RutaProtegida>
              <Asientos />
            </RutaProtegida>
          }
        />
        <Route
          path="/asientos/nuevo"
          element={
            <RutaProtegida roles={[ROLES.CONTADOR]}>
              <AsientoEditor />
            </RutaProtegida>
          }
        />
        <Route
          path="/asientos/:id"
          element={
            <RutaProtegida>
              <AsientoDetalle />
            </RutaProtegida>
          }
        />
        <Route
          path="/asientos/:id/editar"
          element={
            <RutaProtegida roles={[ROLES.CONTADOR]}>
              <AsientoEditor />
            </RutaProtegida>
          }
        />
        <Route
          path="/libros/diario"
          element={
            <RutaProtegida>
              <LibroDiario />
            </RutaProtegida>
          }
        />
        <Route
          path="/libros/mayor"
          element={
            <RutaProtegida>
              <LibroMayor />
            </RutaProtegida>
          }
        />
        <Route
          path="/libros/balanza"
          element={
            <RutaProtegida>
              <Balanza />
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
