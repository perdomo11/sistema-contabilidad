import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Col, Container, Form, Pagination, Row, Spinner, Table } from 'react-bootstrap'
import { api, mensajeError } from '../api'

const ACCIONES = [
  ['', 'Todas'],
  ['LOGIN', 'Inicio de sesión'],
  ['LOGIN_FALLIDO', 'Inicio de sesión fallido'],
  ['LOGOUT', 'Cierre de sesión'],
  ['CREAR', 'Creación'],
  ['MODIFICAR', 'Modificación'],
  ['ELIMINAR', 'Eliminación'],
]

const FILTROS_VACIOS = { usuario: '', accion: '', desde: '', hasta: '' }

const formatoFecha = new Intl.DateTimeFormat('es-SV', {
  dateStyle: 'short',
  timeStyle: 'medium',
  timeZone: 'America/El_Salvador',
})

function Cambios({ anterior, nuevo }) {
  if (!anterior && !nuevo) return null
  const claves = [...new Set([...Object.keys(anterior || {}), ...Object.keys(nuevo || {})])]
  const mostrar = (v) => (v === undefined ? '—' : JSON.stringify(v))
  const cambiadas = claves.filter((k) => mostrar(anterior?.[k]) !== mostrar(nuevo?.[k]))
  return (
    <ul className="mb-0 ps-3 small">
      {cambiadas.map((k) => (
        <li key={k}>
          <strong>{k}</strong>: {mostrar(anterior?.[k])} → {mostrar(nuevo?.[k])}
        </li>
      ))}
    </ul>
  )
}

export default function Bitacora() {
  const [filtros, setFiltros] = useState(FILTROS_VACIOS)
  const [aplicados, setAplicados] = useState(FILTROS_VACIOS)
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')

  const cargar = useCallback(async () => {
    setError('')
    const params = new URLSearchParams({ page: pagina })
    Object.entries(aplicados).forEach(([k, v]) => v && params.set(k, v))
    const resp = await api(`/api/bitacora/?${params}`)
    if (!resp.ok) {
      setError(await mensajeError(resp))
      setDatos({ count: 0, results: [] })
      return
    }
    setDatos(await resp.json())
  }, [pagina, aplicados])

  useEffect(() => {
    cargar()
  }, [cargar])

  const buscar = (e) => {
    e.preventDefault()
    setPagina(1)
    setAplicados(filtros)
  }

  const cambiar = (campo) => (e) => setFiltros({ ...filtros, [campo]: e.target.value })
  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.count / 50)) : 1

  return (
    <Container fluid="lg">
      <h1 className="h4 mb-3">Bitácora de auditoría</h1>
      <Form onSubmit={buscar} className="mb-3">
        <Row className="g-2 align-items-end">
          <Col xs={12} md={3}>
            <Form.Label>Usuario</Form.Label>
            <Form.Control value={filtros.usuario} onChange={cambiar('usuario')} />
          </Col>
          <Col xs={12} md={3}>
            <Form.Label>Acción</Form.Label>
            <Form.Select value={filtros.accion} onChange={cambiar('accion')}>
              {ACCIONES.map(([valor, texto]) => (
                <option key={valor} value={valor}>
                  {texto}
                </option>
              ))}
            </Form.Select>
          </Col>
          <Col xs={6} md={2}>
            <Form.Label>Desde</Form.Label>
            <Form.Control type="date" value={filtros.desde} onChange={cambiar('desde')} />
          </Col>
          <Col xs={6} md={2}>
            <Form.Label>Hasta</Form.Label>
            <Form.Control type="date" value={filtros.hasta} onChange={cambiar('hasta')} />
          </Col>
          <Col xs={12} md={2}>
            <Button type="submit" className="w-100">
              Filtrar
            </Button>
          </Col>
        </Row>
      </Form>

      {error && <Alert variant="danger">{error}</Alert>}
      {!datos ? (
        <Spinner animation="border" />
      ) : (
        <>
          <div className="text-muted small mb-2">{datos.count} registro(s)</div>
          <div className="table-responsive">
            <Table striped bordered hover size="sm">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Usuario</th>
                  <th>Acción</th>
                  <th>Entidad</th>
                  <th>Descripción</th>
                  <th>Cambios</th>
                  <th>IP</th>
                </tr>
              </thead>
              <tbody>
                {datos.results.map((r) => (
                  <tr key={r.id}>
                    <td className="text-nowrap">{formatoFecha.format(new Date(r.fecha))}</td>
                    <td>{r.nombre_usuario || '—'}</td>
                    <td>{r.accion_display}</td>
                    <td>{r.entidad ? `${r.entidad} #${r.objeto_id}` : ''}</td>
                    <td>{r.descripcion}</td>
                    <td>
                      <Cambios anterior={r.valor_anterior} nuevo={r.valor_nuevo} />
                    </td>
                    <td>{r.ip}</td>
                  </tr>
                ))}
                {datos.results.length === 0 && (
                  <tr>
                    <td colSpan={7} className="text-center text-muted">
                      Sin registros
                    </td>
                  </tr>
                )}
              </tbody>
            </Table>
          </div>
          {totalPaginas > 1 && (
            <Pagination>
              <Pagination.Prev disabled={pagina === 1} onClick={() => setPagina(pagina - 1)} />
              <Pagination.Item active>
                {pagina} / {totalPaginas}
              </Pagination.Item>
              <Pagination.Next disabled={pagina === totalPaginas} onClick={() => setPagina(pagina + 1)} />
            </Pagination>
          )}
        </>
      )}
    </Container>
  )
}
