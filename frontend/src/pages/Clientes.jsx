import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Modal, Pagination, Row, Spinner, Table } from 'react-bootstrap'
import { api, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'

const TAMANO_PAGINA = 50
const TIPOS = { CONTRIBUYENTE: 'Contribuyente', CONSUMIDOR_FINAL: 'Consumidor final' }

/** Alta y edición de un cliente. */
function ClienteFormModal({ show, cliente, onHide, onGuardado }) {
  const editando = Boolean(cliente)
  const [datos, setDatos] = useState({})
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!show) return
    setErrores({})
    setDatos(
      editando
        ? { nombre: cliente.nombre, tipo: cliente.tipo, nit: cliente.nit, nrc: cliente.nrc, activo: cliente.activo }
        : { nombre: '', tipo: 'CONTRIBUYENTE', nit: '', nrc: '', activo: true },
    )
  }, [show, cliente, editando])

  const cambiar = (campo, valor) => setDatos((d) => ({ ...d, [campo]: valor }))
  const contribuyente = datos.tipo === 'CONTRIBUYENTE'

  const guardar = async (e) => {
    e.preventDefault()
    setGuardando(true)
    setErrores({})
    const resp = await api(editando ? `/api/clientes/${cliente.id}/` : '/api/clientes/', {
      method: editando ? 'PATCH' : 'POST',
      body: datos,
    })
    setGuardando(false)
    if (resp.ok) return onGuardado(await resp.json())
    const err = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
    setErrores(Object.fromEntries(Object.entries(err).map(([c, m]) => [c, [].concat(m).join(' ')])))
  }

  const generales = Object.entries(errores).filter(([c]) => !['nombre', 'tipo', 'nit', 'nrc', 'activo'].includes(c))
  const error = (campo) => errores[campo] && <Form.Control.Feedback type="invalid">{errores[campo]}</Form.Control.Feedback>

  return (
    <Modal show={show} onHide={onHide} centered>
      <Form onSubmit={guardar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            {editando ? `Editar ${cliente.nombre}` : 'Nuevo cliente'}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {generales.map(([c, m]) => (
            <Alert key={c} variant="danger">
              {m}
            </Alert>
          ))}
          <Row className="g-3">
            <Col xs={12}>
              <Form.Group controlId="cliente-nombre">
                <Form.Label>Nombre o razón social</Form.Label>
                <Form.Control
                  value={datos.nombre || ''}
                  maxLength={200}
                  onChange={(e) => cambiar('nombre', e.target.value)}
                  isInvalid={Boolean(errores.nombre)}
                  autoFocus
                />
                {error('nombre')}
              </Form.Group>
            </Col>
            <Col xs={12}>
              <Form.Group controlId="cliente-tipo">
                <Form.Label>Tipo</Form.Label>
                <Form.Select value={datos.tipo || ''} onChange={(e) => cambiar('tipo', e.target.value)} isInvalid={Boolean(errores.tipo)}>
                  {Object.entries(TIPOS).map(([v, t]) => (
                    <option key={v} value={v}>
                      {t}
                    </option>
                  ))}
                </Form.Select>
                {error('tipo')}
                <Form.Text>Al contribuyente se le emite comprobante de crédito fiscal (CCF); al consumidor final, factura.</Form.Text>
              </Form.Group>
            </Col>
            <Col md={7}>
              <Form.Group controlId="cliente-nit">
                <Form.Label>NIT</Form.Label>
                <Form.Control
                  value={datos.nit || ''}
                  maxLength={20}
                  placeholder="0614-010190-101-3"
                  onChange={(e) => cambiar('nit', e.target.value.replace(/[^0-9-]/g, ''))}
                  isInvalid={Boolean(errores.nit)}
                />
                {error('nit')}
                {!contribuyente && <Form.Text>Opcional.</Form.Text>}
              </Form.Group>
            </Col>
            <Col md={5}>
              <Form.Group controlId="cliente-nrc">
                <Form.Label>NRC</Form.Label>
                <Form.Control
                  value={datos.nrc || ''}
                  maxLength={20}
                  onChange={(e) => cambiar('nrc', e.target.value.replace(/[^0-9-]/g, ''))}
                  isInvalid={Boolean(errores.nrc)}
                />
                {error('nrc')}
                {!contribuyente && <Form.Text>Opcional.</Form.Text>}
              </Form.Group>
            </Col>
            <Col xs={12}>
              <Form.Check
                type="switch"
                id="cliente-activo"
                label="Activo"
                checked={Boolean(datos.activo)}
                onChange={(e) => cambiar('activo', e.target.checked)}
              />
              <Form.Text>A un cliente inactivo no se le emiten documentos nuevos.</Form.Text>
            </Col>
          </Row>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={onHide}>
            Cancelar
          </Button>
          <Button type="submit" disabled={guardando}>
            {guardando && <Spinner animation="border" size="sm" className="me-2" />}
            Guardar
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  )
}

export default function Clientes() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR, ROLES.TESORERO)

  const [datos, setDatos] = useState(null)
  const [busqueda, setBusqueda] = useState('')
  const [consulta, setConsulta] = useState({ q: '', tipo: '', activo: '' })
  const [pagina, setPagina] = useState(1)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [formulario, setFormulario] = useState({ show: false, cliente: null })
  const [porEliminar, setPorEliminar] = useState(null)

  const cargar = useCallback(async () => {
    const params = new URLSearchParams({ page: pagina })
    Object.entries(consulta).forEach(([k, v]) => v && params.set(k, v))
    const resp = await api(`/api/clientes/?${params}`)
    if (!resp.ok) {
      setDatos({ count: 0, results: [] })
      return setError(await mensajeError(resp))
    }
    setDatos(await resp.json())
  }, [consulta, pagina])

  useEffect(() => {
    cargar()
  }, [cargar])

  const notificar = (texto) => {
    setError('')
    setAviso(texto)
  }

  const filtrar = (cambios) => {
    setPagina(1)
    setConsulta((c) => ({ ...c, ...cambios }))
  }

  const alGuardar = (c) => {
    notificar(`Cliente ${c.nombre} ${formulario.cliente ? 'actualizado' : 'creado'}.`)
    setFormulario({ show: false, cliente: null })
    cargar()
  }

  const eliminar = async () => {
    const c = porEliminar
    setPorEliminar(null)
    const resp = await api(`/api/clientes/${c.id}/`, { method: 'DELETE' })
    if (!resp.ok) return setError(await mensajeError(resp))
    notificar(`Cliente ${c.nombre} eliminado.`)
    cargar()
  }

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.count / TAMANO_PAGINA)) : 1

  return (
    <>
      <EncabezadoPagina
        titulo="Clientes"
        descripcion="Contribuyentes (reciben CCF) y consumidores finales (reciben factura)."
        migas={[{ texto: 'Ventas' }, { texto: 'Clientes' }]}
      >
        {puedeEditar && (
          <Button onClick={() => setFormulario({ show: true, cliente: null })}>
            <i className="bi bi-plus-lg me-1" /> Nuevo cliente
          </Button>
        )}
      </EncabezadoPagina>

      <Card className="mb-3">
        <Card.Body>
          <Form
            onSubmit={(e) => {
              e.preventDefault()
              filtrar({ q: busqueda.trim() })
            }}
          >
            <Row className="g-2 align-items-end">
              <Col xs={12} md={5}>
                <Form.Label htmlFor="buscar-cliente" className="small text-suave mb-1">
                  Buscar
                </Form.Label>
                <Form.Control id="buscar-cliente" size="sm" placeholder="Nombre, NIT o NRC" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
              </Col>
              <Col xs={6} md={2}>
                <Form.Label htmlFor="tipo-cliente" className="small text-suave mb-1">
                  Tipo
                </Form.Label>
                <Form.Select id="tipo-cliente" size="sm" value={consulta.tipo} onChange={(e) => filtrar({ tipo: e.target.value })}>
                  <option value="">Todos</option>
                  {Object.entries(TIPOS).map(([v, t]) => (
                    <option key={v} value={v}>
                      {t}
                    </option>
                  ))}
                </Form.Select>
              </Col>
              <Col xs={6} md={2}>
                <Form.Label htmlFor="estado-cliente" className="small text-suave mb-1">
                  Estado
                </Form.Label>
                <Form.Select id="estado-cliente" size="sm" value={consulta.activo} onChange={(e) => filtrar({ activo: e.target.value })}>
                  <option value="">Todos</option>
                  <option value="true">Activos</option>
                  <option value="false">Inactivos</option>
                </Form.Select>
              </Col>
              <Col xs={12} md="auto">
                <Button type="submit" size="sm" variant="outline-primary">
                  <i className="bi bi-search me-1" /> Buscar
                </Button>
              </Col>
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {error && (
        <Alert variant="danger" dismissible onClose={() => setError('')}>
          {error}
        </Alert>
      )}
      {aviso && (
        <Alert variant="success" dismissible onClose={() => setAviso('')}>
          {aviso}
        </Alert>
      )}

      {!datos ? (
        <Spinner animation="border" />
      ) : (
        <>
          <div className="text-suave small mb-2">{datos.count} cliente(s)</div>
          <Card className="mb-3">
            <div className="table-responsive">
              <Table hover className="align-middle mb-0">
                <thead>
                  <tr>
                    <th>Nombre</th>
                    <th>Tipo</th>
                    <th>NIT</th>
                    <th>NRC</th>
                    <th>Estado</th>
                    {puedeEditar && <th className="text-end">Acciones</th>}
                  </tr>
                </thead>
                <tbody>
                  {datos.results.map((c) => (
                    <tr key={c.id} className={c.activo ? '' : 'text-suave'}>
                      <td>{c.nombre}</td>
                      <td>
                        <Badge bg={c.tipo === 'CONTRIBUYENTE' ? 'primary-subtle' : 'secondary-subtle'} text={c.tipo === 'CONTRIBUYENTE' ? 'primary-emphasis' : 'secondary-emphasis'}>
                          {c.tipo_display}
                        </Badge>
                      </td>
                      <td>{c.nit ? <code>{c.nit}</code> : <span className="text-suave">—</span>}</td>
                      <td className="small">{c.nrc || <span className="text-suave">—</span>}</td>
                      <td>
                        {c.activo ? (
                          <Badge bg="success-subtle" text="success-emphasis">
                            Activo
                          </Badge>
                        ) : (
                          <Badge bg="secondary-subtle" text="secondary-emphasis">
                            Inactivo
                          </Badge>
                        )}
                      </td>
                      {puedeEditar && (
                        <td className="text-end text-nowrap">
                          <Button size="sm" variant="outline-secondary" className="me-1" title="Editar" onClick={() => setFormulario({ show: true, cliente: c })}>
                            <i className="bi bi-pencil" />
                          </Button>
                          <Button size="sm" variant="outline-danger" title="Eliminar" onClick={() => setPorEliminar(c)}>
                            <i className="bi bi-trash" />
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                  {datos.results.length === 0 && (
                    <tr>
                      <td colSpan={puedeEditar ? 6 : 5}>
                        <EstadoVacio icono="bi-people">No hay clientes que coincidan.</EstadoVacio>
                      </td>
                    </tr>
                  )}
                </tbody>
              </Table>
            </div>
          </Card>
          {totalPaginas > 1 && (
            <Pagination size="sm">
              <Pagination.Prev disabled={pagina === 1} onClick={() => setPagina(pagina - 1)} />
              <Pagination.Item active>
                {pagina} / {totalPaginas}
              </Pagination.Item>
              <Pagination.Next disabled={pagina === totalPaginas} onClick={() => setPagina(pagina + 1)} />
            </Pagination>
          )}
        </>
      )}

      <ClienteFormModal show={formulario.show} cliente={formulario.cliente} onHide={() => setFormulario({ show: false, cliente: null })} onGuardado={alGuardar} />

      <Modal show={Boolean(porEliminar)} onHide={() => setPorEliminar(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            Eliminar cliente
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          ¿Eliminar <strong>{porEliminar?.nombre}</strong>? Si ya tiene documentos de venta no se podrá: en ese caso desactívelo.
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setPorEliminar(null)}>
            Cancelar
          </Button>
          <Button variant="danger" onClick={eliminar}>
            Eliminar
          </Button>
        </Modal.Footer>
      </Modal>
    </>
  )
}
