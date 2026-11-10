import { Card, Container } from 'react-bootstrap'
import { useAuth } from '../auth/AuthContext'
import EstadoSistema from '../components/EstadoSistema'

export default function Inicio() {
  const { usuario } = useAuth()
  const roles = usuario.roles.length ? usuario.roles.join(', ') : 'sin rol asignado'

  return (
    <Container>
      <h1 className="h4 mb-3">Bienvenido, {usuario.nombre}</h1>
      <Card className="mb-3">
        <Card.Body>
          <div>
            <strong>Usuario:</strong> {usuario.username}
          </div>
          <div>
            <strong>Roles:</strong> {usuario.es_admin ? `Administrador (${roles})` : roles}
          </div>
        </Card.Body>
      </Card>
      <h2 className="h5 mb-3">Estado del sistema</h2>
      <EstadoSistema />
    </Container>
  )
}
