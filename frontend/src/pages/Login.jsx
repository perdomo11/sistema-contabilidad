import { useState } from 'react'
import { Alert, Button, Form, InputGroup, Spinner } from 'react-bootstrap'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const RASGOS = [
  ['bi-diagram-3', 'Centros de costo', 'Asignación y prorrateo de partidas por departamento, sucursal y proyecto.'],
  ['bi-pie-chart', 'Presupuesto y resultados', 'Distribución del presupuesto y estados de resultados segmentados.'],
  ['bi-cash-coin', 'Flujo de efectivo', 'Proyección de egresos a 30, 60 y 90 días con alertas de déficit.'],
]

export default function Login() {
  const { usuario, login } = useAuth()
  const navegar = useNavigate()
  const ubicacion = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [verClave, setVerClave] = useState(false)
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  const destino = ubicacion.state?.desde || '/'
  if (usuario) return <Navigate to={destino} replace />

  const enviar = async (e) => {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      await login(username, password)
      navegar(destino, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="login">
      <section className="login-marca">
        <div className="d-flex align-items-center gap-2">
          <span className="app-logo">
            <i className="bi bi-bank2" />
          </span>
          <span className="fw-semibold">Sistema Contable</span>
        </div>
        <div>
          <h2 className="mb-3">Información contable segmentada y oportuna</h2>
          <p className="mb-4" style={{ color: '#b9c9dc', maxWidth: '32rem' }}>
            Contabilidad por áreas de responsabilidad y proyección de liquidez para la toma de decisiones.
          </p>
          <div className="rasgos">
            {RASGOS.map(([icono, titulo, texto]) => (
              <div className="rasgo" key={titulo}>
                <i className={`bi ${icono}`} />
                <div>
                  <div className="fw-semibold text-white">{titulo}</div>
                  <div className="small" style={{ color: '#9fb4cc' }}>
                    {texto}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="small" style={{ color: '#7f97b3' }}>
          Acceso restringido a personal autorizado. Toda acción queda registrada en la bitácora de auditoría.
        </div>
      </section>

      <section className="login-formulario">
        <div style={{ width: '100%', maxWidth: 380 }}>
          <h1 className="h3 fw-bold mb-1">Iniciar sesión</h1>
          <p className="text-suave mb-4">Ingrese sus credenciales para continuar.</p>
          {error && (
            <Alert variant="danger" className="py-2">
              <i className="bi bi-exclamation-circle me-2" />
              {error}
            </Alert>
          )}
          <Form onSubmit={enviar}>
            <Form.Group className="mb-3" controlId="usuario">
              <Form.Label className="small fw-semibold">Usuario</Form.Label>
              <InputGroup>
                <InputGroup.Text>
                  <i className="bi bi-person" />
                </InputGroup.Text>
                <Form.Control
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoFocus
                  required
                />
              </InputGroup>
            </Form.Group>
            <Form.Group className="mb-4" controlId="contrasena">
              <Form.Label className="small fw-semibold">Contraseña</Form.Label>
              <InputGroup>
                <InputGroup.Text>
                  <i className="bi bi-lock" />
                </InputGroup.Text>
                <Form.Control
                  type={verClave ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
                <Button
                  variant="outline-secondary"
                  onClick={() => setVerClave(!verClave)}
                  aria-label={verClave ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                >
                  <i className={`bi ${verClave ? 'bi-eye-slash' : 'bi-eye'}`} />
                </Button>
              </InputGroup>
            </Form.Group>
            <Button type="submit" className="w-100 py-2" disabled={enviando}>
              {enviando ? <Spinner animation="border" size="sm" className="me-2" /> : <i className="bi bi-box-arrow-in-right me-2" />}
              Entrar
            </Button>
          </Form>
        </div>
      </section>
    </div>
  )
}
