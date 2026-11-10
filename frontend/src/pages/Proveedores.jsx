import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Modal, Pagination, Row, Spinner, Table } from 'react-bootstrap'
import { api, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'

const TAMANO_PAGINA = 50

/** Alta y edición de un proveedor. */
function ProveedorFormModal({ show, proveedor, onHide, onGuardado }) {
  const editando = Boolean(proveedor)
  const [datos, setDatos] = useState({})
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!show) return
    setErrores({})
    setDatos(
      editando
        ? { nit: proveedor.nit, nombre: proveedor.nombre, nrc: proveedor.nrc, activo: proveedor.activo }
        : { nit: '', nombre: '', nrc: '', activo: true },
    )
  }, [show, proveedor, editando])

  const cambiar = (campo, valor) => setDatos((d) => ({ ...d, [campo]: valor }))

  const guardar = async (e) => {
    e.preventDefault()
    setGuardando(true)
    setErrores({})
    const resp = await api(editando ? `/api/proveedores/${proveedor.id}/` : '/api/proveedores/', {
      method: editando ? 'PATCH' : 'POST',
      body: datos,
    })
    setGuardando(false)
    if (resp.ok) return onGuardado(await resp.json())
    const err = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
    setErrores(Object.fromEntries(Object.entries(err).map(([c, m]) => [c, [].concat(m).join(' ')])))
  }

  const generales = Object.entries(errores).filter(([c]) => !['nit', 'nombre', 'nrc', 'activo'].includes(c))
  const error = (campo) =>
    errores[campo] && <Form.Control.Feedback type="invalid">{errores[campo]}</Form.Control.Feedback>

  return (
    <Modal show={show} onHide={onHide} centered>
      <Form onSubmit={guardar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            {editando ? `Editar ${proveedor.nombre}` : 'Nuevo proveedor'}
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
              <Form.Group controlId="proveedor-nombre">
                <Form.Label>Razón social</Form.Label>
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
            <Col md={7}>
              <Form.Group controlId="proveedor-nit">
                <Form.Label>NIT</Form.Label>
                <Form.Control
                  value={datos.nit || ''}
                  maxLength={20}
                  placeholder="0614-010190-101-3"
                  onChange={(e) => cambiar('nit', e.target.value.replace(/[^0-9-]/g, ''))}
                  isInvalid={Boolean(errores.nit)}
                />
                {error('nit')}
              </Form.Group>
            </Col>
            <Col md={5}>
              <Form.Group controlId="proveedor-nrc">
                <Form.Label>NRC</Form.Label>
                <Form.Control
                  value={datos.nrc || ''}
                  maxLength={20}
                  onChange={(e) => cambiar('nrc', e.target.value.replace(/[^0-9-]/g, ''))}
                  isInvalid={Boolean(errores.nrc)}
                />
                {error('nrc')}
                <Form.Text>Opcional.</Form.Text>
              </Form.Group>
            </Col>
            <Col xs={12}>
              <Form.Check
                type="switch"
                id="proveedor-activo"
                label="Activo"
                checked={Boolean(datos.activo)}
                onChange={(e) => cambiar('activo', e.target.checked)}
              />
              <Form.Text>Un proveedor inactivo no se puede usar en asientos ni reglas nuevas.</Form.Text>
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

export default function Proveedores() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR, ROLES.TESORERO)

  const [datos, setDatos] = useState(null)
  const [busqueda, setBusqueda] = useState('')
  const [consulta, setConsulta] = useState({ q: '', activo: '' })
  const [pagina, setPagina] = useState(1)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [formulario, setFormulario] = useState({ show: false, proveedor: null })
  const [porEliminar, setPorEliminar] = useState(null)

  const cargar = useCallback(async () => {
    const params = new URLSearchParams({ page: pagina })
    if (consulta.q) params.set('q', consulta.q)
    if (consulta.activo) params.set('activo', consulta.activo)
    const resp = await api(`/api/proveedores/?${params}`)
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

  const alGuardar = (p) => {
    notificar(`Proveedor ${p.nombre} ${formulario.proveedor ? 'actualizado' : 'creado'}.`)
    setFormulario({ show: false, proveedor: null })
    cargar()
  }

  const eliminar = async () => {
    const p = porEliminar
    setPorEliminar(null)
    const resp = await api(`/api/proveedores/${p.id}/`, { method: 'DELETE' })
    if (!resp.ok) return setError(await mensajeError(resp))
    notificar(`Proveedor ${p.nombre} eliminado.`)
    cargar()
  }

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.count / TAMANO_PAGINA)) : 1

  return (
    <>
      <EncabezadoPagina
        titulo="Proveedores"
        descripcion="Catálogo de proveedores. Se usan en los asientos y en las reglas de asignación a centros de costo."
        migas={[{ texto: 'Tesorería' }, { texto: 'Proveedores' }]}
      >
        {puedeEditar && (
          <Button onClick={() => setFormulario({ show: true, proveedor: null })}>
            <i className="bi bi-plus-lg me-1" /> Nuevo proveedor
          </Button>
        )}
      </EncabezadoPagina>

      <Card className="mb-3">
        <Card.Body>
          <Form
            onSubmit={(e) => {
              e.preventDefault()
              setPagina(1)
              setConsulta((c) => ({ ...c, q: busqueda.trim() }))
            }}
          >
            <Row className="g-2 align-items-end">
              <Col xs={12} md={5}>
                <Form.Label htmlFor="buscar-proveedor" className="small text-suave mb-1">
                  Buscar
                </Form.Label>
                <Form.Control
                  id="buscar-proveedor"
                  size="sm"
                  placeholder="Nombre, NIT o NRC"
                  value={busqueda}
                  onChange={(e) => setBusqueda(e.target.value)}
                />
              </Col>
              <Col xs={8} md={3}>
                <Form.Label htmlFor="estado-proveedor" className="small text-suave mb-1">
                  Estado
                </Form.Label>
                <Form.Select
                  id="estado-proveedor"
                  size="sm"
                  value={consulta.activo}
                  onChange={(e) => {
                    setPagina(1)
                    setConsulta((c) => ({ ...c, activo: e.target.value }))
                  }}
                >
                  <option value="">Todos</option>
                  <option value="true">Activos</option>
                  <option value="false">Inactivos</option>
                </Form.Select>
              </Col>
              <Col xs={4} md="auto">
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
          <div className="text-suave small mb-2">{datos.count} proveedor(es)</div>
          <Card className="mb-3">
            <div className="table-responsive">
              <Table hover className="align-middle">
                <thead>
                  <tr>
                    <th>Razón social</th>
                    <th>NIT</th>
                    <th>NRC</th>
                    <th>Estado</th>
                    {puedeEditar && <th className="text-end">Acciones</th>}
                  </tr>
                </thead>
                <tbody>
                  {datos.results.map((p) => (
                    <tr key={p.id} className={p.activo ? '' : 'text-suave'}>
                      <td>{p.nombre}</td>
                      <td>
                        <code>{p.nit}</code>
                      </td>
                      <td className="small">{p.nrc || <span className="text-suave">—</span>}</td>
                      <td>
                        {p.activo ? (
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
                          <Button
                            size="sm"
                            variant="outline-secondary"
                            className="me-1"
                            title="Editar"
                            onClick={() => setFormulario({ show: true, proveedor: p })}
                          >
                            <i className="bi bi-pencil" />
                          </Button>
                          <Button size="sm" variant="outline-danger" title="Eliminar" onClick={() => setPorEliminar(p)}>
                            <i className="bi bi-trash" />
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                  {datos.results.length === 0 && (
                    <tr>
                      <td colSpan={puedeEditar ? 5 : 4}>
                        <EstadoVacio icono="bi-truck">No hay proveedores que coincidan.</EstadoVacio>
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

      <ProveedorFormModal
        show={formulario.show}
        proveedor={formulario.proveedor}
        onHide={() => setFormulario({ show: false, proveedor: null })}
        onGuardado={alGuardar}
      />

      <Modal show={Boolean(porEliminar)} onHide={() => setPorEliminar(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            Eliminar proveedor
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          ¿Eliminar <strong>{porEliminar?.nombre}</strong>? Si ya se usó en asientos o reglas no se podrá: en ese caso
          desactívelo.
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
