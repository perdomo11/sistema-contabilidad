import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Button, ButtonGroup, Col, Container, Form, Modal, Row, Spinner, Table } from 'react-bootstrap'
import { api, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import CuentaFormModal, { NOMBRE_TIPO, TIPOS } from '../components/CuentaFormModal'

const normalizar = (texto) =>
  texto
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')

/** Ids de los nodos visibles con el filtro: los que coinciden y sus ancestros. */
function filtrarArbol(raices, busqueda, tipo) {
  const visibles = new Set()
  const q = normalizar(busqueda.trim())
  const coincide = (n) => !q || n.codigo.startsWith(q) || normalizar(n.nombre).includes(q)
  const visitar = (nodo) => {
    let alguno = coincide(nodo)
    for (const hijo of nodo.hijos) if (visitar(hijo)) alguno = true
    if (alguno) visibles.add(nodo.id)
    return alguno
  }
  raices.filter((r) => !tipo || r.tipo === tipo).forEach(visitar)
  return visibles
}

export default function Catalogo() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR)

  const [arbol, setArbol] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [expandidos, setExpandidos] = useState(new Set())
  const [busqueda, setBusqueda] = useState('')
  const [tipo, setTipo] = useState('')
  const [formulario, setFormulario] = useState({ show: false, cuenta: null, padre: null })
  const [porEliminar, setPorEliminar] = useState(null)

  const cargar = useCallback(async () => {
    const resp = await api('/api/cuentas/arbol/')
    if (!resp.ok) {
      setError(await mensajeError(resp))
      setArbol([])
      return
    }
    const datos = await resp.json()
    setArbol(datos)
    // La primera vez se muestran expandidos los dos primeros niveles.
    setExpandidos((prev) => (prev.size ? prev : new Set(datos.map((r) => r.id))))
  }, [])

  useEffect(() => {
    cargar()
  }, [cargar])

  const filtrando = busqueda.trim() !== '' || tipo !== ''
  const visibles = useMemo(() => (arbol ? filtrarArbol(arbol, busqueda, tipo) : new Set()), [arbol, busqueda, tipo])
  const total = useMemo(() => {
    let n = 0
    const contar = (nodos) => nodos.forEach((x) => (n++, contar(x.hijos)))
    contar(arbol || [])
    return n
  }, [arbol])

  const alternar = (id) =>
    setExpandidos((prev) => {
      const nuevo = new Set(prev)
      nuevo.has(id) ? nuevo.delete(id) : nuevo.add(id)
      return nuevo
    })

  const expandirTodo = (expandir) => {
    if (!expandir) return setExpandidos(new Set())
    const ids = new Set()
    const recorrer = (nodos) => nodos.forEach((n) => n.hijos.length && (ids.add(n.id), recorrer(n.hijos)))
    recorrer(arbol || [])
    setExpandidos(ids)
  }

  const notificar = (texto) => {
    setError('')
    setAviso(texto)
  }

  const alGuardar = (cuenta) => {
    const era = formulario.cuenta ? 'actualizada' : 'creada'
    setFormulario({ show: false, cuenta: null, padre: null })
    if (formulario.padre) setExpandidos((prev) => new Set(prev).add(formulario.padre.id))
    notificar(`Cuenta ${cuenta.codigo} ${era}.`)
    cargar()
  }

  const cambiarActiva = async (nodo) => {
    const resp = await api(`/api/cuentas/${nodo.id}/`, { method: 'PATCH', body: { activa: !nodo.activa } })
    if (!resp.ok) return setError(await mensajeError(resp))
    notificar(`Cuenta ${nodo.codigo} ${nodo.activa ? 'desactivada' : 'activada'}.`)
    cargar()
  }

  const eliminar = async () => {
    const nodo = porEliminar
    setPorEliminar(null)
    const resp = await api(`/api/cuentas/${nodo.id}/`, { method: 'DELETE' })
    if (!resp.ok) return setError(await mensajeError(resp))
    notificar(`Cuenta ${nodo.codigo} eliminada.`)
    cargar()
  }

  const filas = []
  const agregarFilas = (nodos) => {
    for (const nodo of nodos) {
      if (!visibles.has(nodo.id)) continue
      filas.push(nodo)
      if (nodo.hijos.length && (filtrando || expandidos.has(nodo.id))) agregarFilas(nodo.hijos)
    }
  }
  if (arbol) agregarFilas(arbol)

  return (
    <Container fluid="lg">
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <h1 className="h4 mb-0">Catálogo de cuentas</h1>
        {puedeEditar && (
          <Button onClick={() => setFormulario({ show: true, cuenta: null, padre: null })}>Nueva cuenta raíz</Button>
        )}
      </div>

      <Row className="g-2 mb-3 align-items-end">
        <Col xs={12} md={5}>
          <Form.Label htmlFor="busqueda">Buscar</Form.Label>
          <Form.Control
            id="busqueda"
            placeholder="Código o nombre"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
          />
        </Col>
        <Col xs={12} md={4}>
          <Form.Label htmlFor="filtro-tipo">Tipo</Form.Label>
          <Form.Select id="filtro-tipo" value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="">Todos</option>
            {TIPOS.map(([valor, texto]) => (
              <option key={valor} value={valor}>
                {texto}
              </option>
            ))}
          </Form.Select>
        </Col>
        <Col xs={12} md={3}>
          <ButtonGroup className="w-100">
            <Button variant="outline-secondary" onClick={() => expandirTodo(true)} disabled={filtrando}>
              Expandir todo
            </Button>
            <Button variant="outline-secondary" onClick={() => expandirTodo(false)} disabled={filtrando}>
              Contraer
            </Button>
          </ButtonGroup>
        </Col>
      </Row>

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

      {!arbol ? (
        <Spinner animation="border" />
      ) : (
        <>
          <div className="text-muted small mb-2">
            {total} cuenta(s) en el catálogo{filtrando && ` · ${visibles.size} coinciden con el filtro`}
          </div>
          <div className="table-responsive">
            <Table hover size="sm" className="align-middle">
              <thead>
                <tr>
                  <th>Cuenta</th>
                  <th>Tipo</th>
                  <th>Naturaleza</th>
                  <th>Uso</th>
                  {puedeEditar && <th className="text-end">Acciones</th>}
                </tr>
              </thead>
              <tbody>
                {filas.map((nodo) => (
                  <Fragment key={nodo.id}>
                    <tr className={nodo.activa ? '' : 'text-muted'}>
                      <td style={{ paddingLeft: `${(nodo.nivel - 1) * 1.5 + 0.5}rem` }}>
                        {nodo.hijos.length > 0 ? (
                          <Button
                            variant="link"
                            size="sm"
                            className="p-0 me-1 text-decoration-none"
                            style={{ width: '1.2rem' }}
                            onClick={() => alternar(nodo.id)}
                            disabled={filtrando}
                            aria-label={expandidos.has(nodo.id) ? 'Contraer' : 'Expandir'}
                          >
                            {filtrando || expandidos.has(nodo.id) ? '▾' : '▸'}
                          </Button>
                        ) : (
                          <span className="d-inline-block me-1" style={{ width: '1.2rem' }} />
                        )}
                        <span className={nodo.acepta_movimientos ? '' : 'fw-semibold'}>
                          <code className="me-2">{nodo.codigo}</code>
                          {nodo.nombre}
                        </span>
                        {!nodo.activa && (
                          <Badge bg="secondary" className="ms-2">
                            Inactiva
                          </Badge>
                        )}
                      </td>
                      <td className="small">{NOMBRE_TIPO[nodo.tipo]}</td>
                      <td className="small">{nodo.naturaleza === 'DEUDORA' ? 'Deudora' : 'Acreedora'}</td>
                      <td className="small">
                        {nodo.acepta_movimientos ? (
                          <Badge bg="primary">Detalle</Badge>
                        ) : (
                          <Badge bg="light" text="dark">
                            Agrupación
                          </Badge>
                        )}
                        {nodo.exenta_centro_costo && (
                          <Badge bg="warning" text="dark" className="ms-1" title="Exenta de centro de costo">
                            Sin CC
                          </Badge>
                        )}
                      </td>
                      {puedeEditar && (
                        <td className="text-end text-nowrap">
                          {!nodo.acepta_movimientos && nodo.activa && (
                            <Button
                              size="sm"
                              variant="outline-primary"
                              className="me-1"
                              onClick={() => setFormulario({ show: true, cuenta: null, padre: nodo })}
                            >
                              + Subcuenta
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="outline-secondary"
                            className="me-1"
                            onClick={() => setFormulario({ show: true, cuenta: nodo, padre: null })}
                          >
                            Editar
                          </Button>
                          <Button
                            size="sm"
                            variant={nodo.activa ? 'outline-warning' : 'outline-success'}
                            className="me-1"
                            onClick={() => cambiarActiva(nodo)}
                          >
                            {nodo.activa ? 'Desactivar' : 'Activar'}
                          </Button>
                          {nodo.hijos.length === 0 && (
                            <Button size="sm" variant="outline-danger" onClick={() => setPorEliminar(nodo)}>
                              Eliminar
                            </Button>
                          )}
                        </td>
                      )}
                    </tr>
                  </Fragment>
                ))}
                {filas.length === 0 && (
                  <tr>
                    <td colSpan={puedeEditar ? 5 : 4} className="text-center text-muted">
                      {total === 0 ? 'El catálogo está vacío.' : 'Ninguna cuenta coincide con el filtro.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </Table>
          </div>
        </>
      )}

      <CuentaFormModal
        show={formulario.show}
        cuenta={formulario.cuenta}
        padre={formulario.padre}
        onHide={() => setFormulario({ show: false, cuenta: null, padre: null })}
        onGuardada={alGuardar}
      />

      <Modal show={Boolean(porEliminar)} onHide={() => setPorEliminar(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            Eliminar cuenta
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          ¿Eliminar la cuenta{' '}
          <strong>
            {porEliminar?.codigo} {porEliminar?.nombre}
          </strong>
          ? La acción queda registrada en la bitácora.
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
    </Container>
  )
}
