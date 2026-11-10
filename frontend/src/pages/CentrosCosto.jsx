import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Button, ButtonGroup, Card, Col, Form, Modal, Row, Spinner, Table } from 'react-bootstrap'
import { api, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import CentroFormModal, { CLASES_CENTRO, TIPOS_CENTRO } from '../components/CentroFormModal'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import { formatoFecha, hoyISO } from '../formato'

const NOMBRE_TIPO = Object.fromEntries(TIPOS_CENTRO)
const NOMBRE_CLASE = Object.fromEntries(CLASES_CENTRO)
const COLOR_TIPO = { COSTO: 'secondary', INGRESO: 'success', UTILIDAD: 'primary', INVERSION: 'warning' }
const ICONO_CLASE = { SUCURSAL: 'bi-building', DEPARTAMENTO: 'bi-people', AREA: 'bi-grid', PROYECTO: 'bi-kanban' }

const normalizar = (t) =>
  t
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')

const vigenteEn = (n, fecha) => n.vigente_desde <= fecha && (!n.vigente_hasta || n.vigente_hasta >= fecha)

export default function CentrosCosto() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR)

  const [arbol, setArbol] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [busqueda, setBusqueda] = useState('')
  const [tipo, setTipo] = useState('')
  const [fecha, setFecha] = useState(hoyISO())
  const [soloVigentes, setSoloVigentes] = useState(false)
  const [contraidos, setContraidos] = useState(new Set())
  const [formulario, setFormulario] = useState({ show: false, centro: null, padre: null })
  const [porEliminar, setPorEliminar] = useState(null)

  const cargar = useCallback(async () => {
    const resp = await api('/api/centros-costo/arbol/')
    if (!resp.ok) {
      setArbol([])
      return setError(await mensajeError(resp))
    }
    setArbol(await resp.json())
  }, [])

  useEffect(() => {
    cargar()
  }, [cargar])

  // Nodos visibles: los que cumplen el filtro y sus ancestros.
  const visibles = useMemo(() => {
    const ids = new Set()
    const q = normalizar(busqueda.trim())
    const cumple = (n) =>
      (!q || normalizar(n.codigo).startsWith(q) || normalizar(n.nombre).includes(q)) &&
      (!tipo || n.tipo === tipo) &&
      (!soloVigentes || vigenteEn(n, fecha))
    const visitar = (n) => {
      let alguno = cumple(n)
      n.hijos.forEach((h) => {
        if (visitar(h)) alguno = true
      })
      if (alguno) ids.add(n.id)
      return alguno
    }
    ;(arbol || []).forEach(visitar)
    return ids
  }, [arbol, busqueda, tipo, soloVigentes, fecha])

  const filas = []
  const recorrer = (nodos) =>
    nodos.forEach((n) => {
      if (!visibles.has(n.id)) return
      filas.push(n)
      if (!contraidos.has(n.id)) recorrer(n.hijos)
    })
  recorrer(arbol || [])

  const alternar = (id) =>
    setContraidos((prev) => {
      const s = new Set(prev)
      s.has(id) ? s.delete(id) : s.add(id)
      return s
    })

  const notificar = (texto) => {
    setError('')
    setAviso(texto)
  }

  const alGuardar = (c) => {
    const accion = formulario.centro ? 'actualizada' : 'creada'
    setFormulario({ show: false, centro: null, padre: null })
    notificar(`Unidad ${c.codigo} ${accion}.`)
    cargar()
  }

  const eliminar = async () => {
    const n = porEliminar
    setPorEliminar(null)
    const resp = await api(`/api/centros-costo/${n.id}/`, { method: 'DELETE' })
    if (!resp.ok) return setError(await mensajeError(resp))
    notificar(`Unidad ${n.codigo} eliminada.`)
    cargar()
  }

  const total = useMemo(() => {
    let t = 0
    const contar = (ns) => ns.forEach((n) => (t++, contar(n.hijos)))
    contar(arbol || [])
    return t
  }, [arbol])

  return (
    <>
      <EncabezadoPagina
        titulo="Centros de costo"
        descripcion="Unidades de responsabilidad: sucursales, departamentos, áreas y proyectos, con su vigencia."
        migas={[{ texto: 'Centros de costo' }, { texto: 'Estructura' }]}
      >
        {puedeEditar && (
          <Button onClick={() => setFormulario({ show: true, centro: null, padre: null })}>
            <i className="bi bi-plus-lg me-1" /> Nueva unidad raíz
          </Button>
        )}
      </EncabezadoPagina>

      <Card className="mb-3">
        <Card.Body>
          <Row className="g-2 align-items-end">
            <Col xs={12} md={4}>
              <Form.Label htmlFor="buscar-centro" className="small text-suave mb-1">
                Buscar
              </Form.Label>
              <Form.Control
                id="buscar-centro"
                size="sm"
                placeholder="Código o nombre"
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
              />
            </Col>
            <Col xs={6} md={3}>
              <Form.Label htmlFor="tipo-centro" className="small text-suave mb-1">
                Tipo
              </Form.Label>
              <Form.Select id="tipo-centro" size="sm" value={tipo} onChange={(e) => setTipo(e.target.value)}>
                <option value="">Todos</option>
                {TIPOS_CENTRO.map(([v, t]) => (
                  <option key={v} value={v}>
                    {t}
                  </option>
                ))}
              </Form.Select>
            </Col>
            <Col xs={6} md={2}>
              <Form.Label htmlFor="fecha-vigencia" className="small text-suave mb-1">
                Vigencia al
              </Form.Label>
              <Form.Control id="fecha-vigencia" size="sm" type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
            </Col>
            <Col xs={12} md="auto" className="pb-1">
              <Form.Check
                id="solo-vigentes"
                className="small"
                label="Solo vigentes a esa fecha"
                checked={soloVigentes}
                onChange={(e) => setSoloVigentes(e.target.checked)}
              />
            </Col>
            <Col xs={12} md="auto" className="ms-md-auto">
              <ButtonGroup size="sm">
                <Button variant="outline-secondary" onClick={() => setContraidos(new Set())}>
                  <i className="bi bi-arrows-expand me-1" /> Expandir
                </Button>
                <Button
                  variant="outline-secondary"
                  onClick={() => setContraidos(new Set((arbol || []).map((n) => n.id)))}
                >
                  <i className="bi bi-arrows-collapse me-1" /> Contraer
                </Button>
              </ButtonGroup>
            </Col>
          </Row>
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

      {!arbol ? (
        <Spinner animation="border" />
      ) : (
        <>
          <div className="text-suave small mb-2">{total} unidad(es) en la estructura</div>
          <Card className="mb-4">
            <div className="table-responsive">
              <Table hover className="align-middle">
                <thead>
                  <tr>
                    <th>Unidad</th>
                    <th>Tipo</th>
                    <th>Clase</th>
                    <th>Responsable</th>
                    <th>Vigencia</th>
                    {puedeEditar && <th className="text-end">Acciones</th>}
                  </tr>
                </thead>
                <tbody>
                  {filas.map((n) => {
                    const vigente = vigenteEn(n, fecha)
                    return (
                      <tr key={n.id} className={vigente ? '' : 'text-suave'}>
                        <td style={{ paddingLeft: `${(n.nivel - 1) * 1.5 + 0.5}rem` }}>
                          {n.hijos.length > 0 ? (
                            <Button
                              variant="link"
                              size="sm"
                              className="p-0 me-1 text-decoration-none"
                              style={{ width: '1.2rem' }}
                              onClick={() => alternar(n.id)}
                              aria-label={contraidos.has(n.id) ? 'Expandir' : 'Contraer'}
                            >
                              <i className={`bi ${contraidos.has(n.id) ? 'bi-chevron-right' : 'bi-chevron-down'}`} />
                            </Button>
                          ) : (
                            <span className="d-inline-block me-1" style={{ width: '1.2rem' }} />
                          )}
                          <i className={`bi ${ICONO_CLASE[n.clase]} me-2 text-suave`} />
                          <code className="me-2">{n.codigo}</code>
                          <span className={n.acepta_movimientos ? '' : 'fw-semibold'}>{n.nombre}</span>
                        </td>
                        <td>
                          <Badge bg={`${COLOR_TIPO[n.tipo]}-subtle`} text={`${COLOR_TIPO[n.tipo]}-emphasis`}>
                            {NOMBRE_TIPO[n.tipo]}
                          </Badge>
                        </td>
                        <td className="small">
                          {NOMBRE_CLASE[n.clase]}
                          {!n.acepta_movimientos && <span className="text-suave"> · agrupación</span>}
                        </td>
                        <td className="small">{n.responsable_nombre || <span className="text-suave">—</span>}</td>
                        <td className="small text-nowrap">
                          {formatoFecha(n.vigente_desde)} – {n.vigente_hasta ? formatoFecha(n.vigente_hasta) : 'indefinida'}
                          {!vigente && (
                            <Badge bg="secondary-subtle" text="secondary-emphasis" className="ms-2">
                              No vigente
                            </Badge>
                          )}
                        </td>
                        {puedeEditar && (
                          <td className="text-end text-nowrap">
                            {!n.acepta_movimientos && (
                              <Button
                                size="sm"
                                variant="outline-primary"
                                className="me-1"
                                title="Agregar subunidad"
                                onClick={() => setFormulario({ show: true, centro: null, padre: n })}
                              >
                                <i className="bi bi-plus-lg" />
                              </Button>
                            )}
                            <Button
                              size="sm"
                              variant="outline-secondary"
                              className="me-1"
                              title="Editar"
                              onClick={() => setFormulario({ show: true, centro: n, padre: null })}
                            >
                              <i className="bi bi-pencil" />
                            </Button>
                            {n.hijos.length === 0 && (
                              <Button size="sm" variant="outline-danger" title="Eliminar" onClick={() => setPorEliminar(n)}>
                                <i className="bi bi-trash" />
                              </Button>
                            )}
                          </td>
                        )}
                      </tr>
                    )
                  })}
                  {filas.length === 0 && (
                    <tr>
                      <td colSpan={puedeEditar ? 6 : 5}>
                        <EstadoVacio icono="bi-diagram-3">
                          {total === 0 ? 'No hay unidades registradas.' : 'Ninguna unidad coincide con el filtro.'}
                        </EstadoVacio>
                      </td>
                    </tr>
                  )}
                </tbody>
              </Table>
            </div>
          </Card>
        </>
      )}

      <CentroFormModal
        show={formulario.show}
        centro={formulario.centro}
        padre={formulario.padre}
        onHide={() => setFormulario({ show: false, centro: null, padre: null })}
        onGuardado={alGuardar}
      />

      <Modal show={Boolean(porEliminar)} onHide={() => setPorEliminar(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            Eliminar unidad
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          ¿Eliminar <strong>{porEliminar?.codigo} {porEliminar?.nombre}</strong>? Si ya tiene movimientos no se podrá:
          en ese caso cierre su vigencia.
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
