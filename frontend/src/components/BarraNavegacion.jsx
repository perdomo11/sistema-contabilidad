import { Badge, Button, Container, Nav, Navbar } from 'react-bootstrap'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'

export default function BarraNavegacion() {
  const { usuario, logout } = useAuth()
  const navegar = useNavigate()

  const cerrarSesion = async () => {
    await logout()
    navegar('/login', { replace: true })
  }

  return (
    <Navbar bg="dark" variant="dark" expand="md" className="mb-4">
      <Container>
        <Navbar.Brand as={NavLink} to="/">
          Sistema Contable
        </Navbar.Brand>
        {usuario && (
          <>
            <Navbar.Toggle aria-controls="menu-principal" />
            <Navbar.Collapse id="menu-principal">
              <Nav className="me-auto">
                <Nav.Link as={NavLink} to="/" end>
                  Inicio
                </Nav.Link>
                {tieneRol(usuario, ROLES.AUDITOR) && (
                  <Nav.Link as={NavLink} to="/bitacora">
                    Bitácora
                  </Nav.Link>
                )}
              </Nav>
              <div className="d-flex align-items-center gap-2 text-light">
                <span>{usuario.nombre}</span>
                {usuario.es_admin && <Badge bg="danger">Administrador</Badge>}
                {usuario.roles.map((rol) => (
                  <Badge key={rol} bg="info" text="dark">
                    {rol}
                  </Badge>
                ))}
                <Button size="sm" variant="outline-light" onClick={cerrarSesion}>
                  Cerrar sesión
                </Button>
              </div>
            </Navbar.Collapse>
          </>
        )}
      </Container>
    </Navbar>
  )
}
