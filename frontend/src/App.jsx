import { Navigate, Route, Routes } from 'react-router-dom'
import RutaProtegida from './auth/RutaProtegida'
import { ROLES } from './auth/roles'
import Layout from './layout/Layout'
import AsientoDetalle from './pages/AsientoDetalle'
import AsientoEditor from './pages/AsientoEditor'
import Asientos from './pages/Asientos'
import Balanza from './pages/Balanza'
import Bitacora from './pages/Bitacora'
import Catalogo from './pages/Catalogo'
import Inicio from './pages/Inicio'
import LibroDiario from './pages/LibroDiario'
import LibroMayor from './pages/LibroMayor'
import Login from './pages/Login'
import Periodos from './pages/Periodos'

const soloContador = (pagina) => <RutaProtegida roles={[ROLES.CONTADOR]}>{pagina}</RutaProtegida>

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RutaProtegida>
            <Layout />
          </RutaProtegida>
        }
      >
        <Route index element={<Inicio />} />
        <Route path="asientos" element={<Asientos />} />
        <Route path="asientos/nuevo" element={soloContador(<AsientoEditor />)} />
        <Route path="asientos/:id" element={<AsientoDetalle />} />
        <Route path="asientos/:id/editar" element={soloContador(<AsientoEditor />)} />
        <Route path="libros/diario" element={<LibroDiario />} />
        <Route path="libros/mayor" element={<LibroMayor />} />
        <Route path="libros/balanza" element={<Balanza />} />
        <Route path="catalogo" element={<Catalogo />} />
        <Route path="periodos" element={<Periodos />} />
        <Route path="bitacora" element={<RutaProtegida roles={[ROLES.AUDITOR]}>{<Bitacora />}</RutaProtegida>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
