import { Alert, Container, Spinner } from 'react-bootstrap'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { tieneRol } from './roles'

/** Exige sesión iniciada y, si se indican, alguno de los roles. */
export default function RutaProtegida({ roles, children }) {
  const { usuario, cargando } = useAuth()
  const ubicacion = useLocation()

  if (cargando) {
    return (
      <Container className="py-5 text-center">
        <Spinner animation="border" />
      </Container>
    )
  }
  if (!usuario) return <Navigate to="/login" replace state={{ desde: ubicacion.pathname }} />
  if (roles && !tieneRol(usuario, ...roles)) {
    return (
      <Container>
        <Alert variant="warning">No tiene permiso para ver esta sección.</Alert>
      </Container>
    )
  }
  return children
}
