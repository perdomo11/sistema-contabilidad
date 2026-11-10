import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Modal, Row, Spinner, Table } from 'react-bootstrap'
import { api, apiTodas, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import SelectorCuenta from '../components/SelectorCuenta'
import { formatoFecha, hoyISO } from '../formato'

const vigenteEn = (r, fecha) => r.vigente_desde <= fecha && (!r.vigente_hasta || r.vigente_hasta >= fecha)

/** Aplana un árbol ({hijos}) aplicando un filtro. */
function aplanar(arbol, incluir) {
  const lista = []
  const recorrer = (nodos) =>
    nodos.forEach((n) => {
      if (incluir(n)) lista.push({ id: n.id, codigo: n.codigo, nombre: n.nombre, desde: n.vigente_desde, hasta: n.vigente_hasta })
      recorrer(n.hijos)
    })
  recorrer(arbol)
  return lista
}

/** Alta de una regla o cambio de su vigencia y descripción. */
function ReglaFormModal({ show, regla, catalogos, onHide, onGuardado }) {
  const editando = Boolean(regla)
  const [datos, setDatos] = useState({})
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!show) return
    setErrores({})
    setDatos(
      editando
        ? { descripcion: regla.descripcion, vigente_desde: regla.vigente_desde, vigente_hasta: regla.vigente_hasta ?? '' }
        : { cuenta: null, proveedor: null, centro: null, descripcion: '', vigente_desde: hoyISO(), vigente_hasta: '' },
    )
  }, [show, regla, editando])

  const cambiar = (campo, valor) => setDatos((d) => ({ ...d, [campo]: valor }))

  const guardar = async (e) => {
    e.preventDefault()
    setGuardando(true)
    setErrores({})
    const comunes = {
      descripcion: datos.descripcion,
      vigente_desde: datos.vigente_desde,
      vigente_hasta: datos.vigente_hasta || null,
    }
    const cuerpo = editando
      ? comunes
      : {
          ...comunes,
          cuenta: datos.cuenta?.id ?? null,
          proveedor: datos.proveedor?.id ?? null,
          centro_costo: datos.centro?.id ?? null,
        }
    const resp = await api(editando ? `/api/reglas-asignacion/${regla.id}/` : '/api/reglas-asignacion/', {
      method: editando ? 'PATCH' : 'POST',
      body: cuerpo,
    })
    setGuardando(false)
    if (resp.ok) return onGuardado(await resp.json())
    const err = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
    setErrores(Object.fromEntries(Object.entries(err).map(([c, m]) => [c, [].concat(m).join(' ')])))
  }

  const conocidos = ['cuenta', 'proveedor', 'centro_costo', 'descripcion', 'vigente_desde', 'vigente_hasta']
  const generales = Object.entries(errores).filter(([c]) => !conocidos.includes(c))
  const error = (campo) => errores[campo] && <div className="invalid-feedback d-block">{errores[campo]}</div>

  return (
    <Modal show={show} onHide={onHide} centered size="lg">
      <Form onSubmit={guardar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            {editando ? `Regla: ${regla.criterio} → ${regla.centro_codigo}` : 'Nueva regla de asignación'}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {generales.map(([c, m]) => (
            <Alert key={c} variant="danger">
              {m}
            </Alert>
          ))}
          <Row className="g-3">
            {editando ? (
              <Col xs={12}>
                <Alert variant="light" className="border small mb-0">
                  La cuenta, el proveedor y el centro no se modifican: para cambiar el destino, cierre la vigencia de
                  esta regla y cree otra.
                </Alert>
              </Col>
            ) : (
              <>
                <Col md={6}>
                  <Form.Label htmlFor="regla-cuenta">Cuenta</Form.Label>
                  <SelectorCuenta
                    id="regla-cuenta"
                    cuentas={catalogos.cuentas}
                    valor={datos.cuenta}
                    onChange={(v) => cambiar('cuenta', v)}
                    isInvalid={Boolean(errores.cuenta)}
                    permitirVacio
                  />
                  {error('cuenta')}
                  <Form.Text>Una cuenta de agrupación aplica a todas sus subcuentas.</Form.Text>
                </Col>
                <Col md={6}>
                  <Form.Label htmlFor="regla-proveedor">Proveedor</Form.Label>
                  <SelectorCuenta
                    id="regla-proveedor"
                    cuentas={catalogos.proveedores}
                    valor={datos.proveedor}
                    onChange={(v) => cambiar('proveedor', v)}
                    isInvalid={Boolean(errores.proveedor)}
                    placeholder="NIT o nombre del proveedor"
                    permitirVacio
                  />
                  {error('proveedor')}
                  <Form.Text>Indique la cuenta, el proveedor o ambos.</Form.Text>
                </Col>
                <Col xs={12}>
                  <Form.Label htmlFor="regla-centro">Centro de costo destino</Form.Label>
                  <SelectorCuenta
                    id="regla-centro"
                    cuentas={catalogos.centros}
                    valor={datos.centro}
                    onChange={(v) => cambiar('centro', v)}
                    isInvalid={Boolean(errores.centro_costo)}
                    placeholder="Unidad de detalle"
                  />
                  {error('centro_costo')}
                </Col>
              </>
            )}
            <Col md={6}>
              <Form.Group controlId="regla-desde">
                <Form.Label>Vigente desde</Form.Label>
                <Form.Control
                  type="date"
                  value={datos.vigente_desde || ''}
                  onChange={(e) => cambiar('vigente_desde', e.target.value)}
                  isInvalid={Boolean(errores.vigente_desde)}
                />
                {error('vigente_desde')}
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group controlId="regla-hasta">
                <Form.Label>Vigente hasta</Form.Label>
                <Form.Control
                  type="date"
                  value={datos.vigente_hasta || ''}
                  onChange={(e) => cambiar('vigente_hasta', e.target.value)}
                  isInvalid={Boolean(errores.vigente_hasta)}
                />
                {error('vigente_hasta')}
                <Form.Text>Vacío = indefinida.</Form.Text>
              </Form.Group>
            </Col>
            <Col xs={12}>
              <Form.Group controlId="regla-descripcion">
                <Form.Label>Justificación</Form.Label>
                <Form.Control
                  value={datos.descripcion || ''}
                  maxLength={200}
                  onChange={(e) => cambiar('descripcion', e.target.value)}
                  placeholder="Por qué este gasto corresponde a esa unidad"
                />
              </Form.Group>
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

export default function ReglasAsignacion() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR)

  const [reglas, setReglas] = useState(null)
  const [catalogos, setCatalogos] = useState(null)
  const [busqueda, setBusqueda] = useState('')
  const [q, setQ] = useState('')
  const [fecha, setFecha] = useState(hoyISO())
  const [soloVigentes, setSoloVigentes] = useState(false)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [formulario, setFormulario] = useState({ show: false, regla: null })
  const [porEliminar, setPorEliminar] = useState(null)

  const cargar = useCallback(async () => {
    const params = new URLSearchParams()
    if (q) params.set('q', q)
    setReglas(await apiTodas(`/api/reglas-asignacion/?${params}`))
  }, [q])

  useEffect(() => {
    cargar()
  }, [cargar])

  // Catálogos para el formulario de alta (solo quien puede editar).
  useEffect(() => {
    if (!puedeEditar) return
    Promise.all([
      api('/api/cuentas/arbol/').then((r) => (r.ok ? r.json() : [])),
      api('/api/centros-costo/arbol/').then((r) => (r.ok ? r.json() : [])),
      apiTodas('/api/proveedores/?activo=true'),
    ]).then(([cuentas, centros, proveedores]) =>
      setCatalogos({
        cuentas: aplanar(cuentas, (n) => n.activa && !n.exenta_centro_costo),
        centros: aplanar(centros, (n) => n.acepta_movimientos),
        proveedores: proveedores.map((p) => ({ id: p.id, codigo: p.nit, nombre: p.nombre })),
      }),
    )
  }, [puedeEditar])

  const notificar = (texto) => {
    setError('')
    setAviso(texto)
  }

  const alGuardar = (r) => {
    notificar(`Regla ${r.criterio} → ${r.centro_codigo} ${formulario.regla ? 'actualizada' : 'creada'}.`)
    setFormulario({ show: false, regla: null })
    cargar()
  }

  const eliminar = async () => {
    const r = porEliminar
    setPorEliminar(null)
    const resp = await api(`/api/reglas-asignacion/${r.id}/`, { method: 'DELETE' })
    if (!resp.ok) return setError(await mensajeError(resp))
    notificar(`Regla ${r.criterio} eliminada.`)
    cargar()
  }

  const visibles = (reglas || []).filter((r) => !soloVigentes || vigenteEn(r, fecha))

  return (
    <>
      <EncabezadoPagina
        titulo="Reglas de asignación"
        descripcion="Asignan automáticamente el centro de costo a las líneas que no lo traen, según la cuenta y el proveedor. La asignación directa siempre prevalece."
        migas={[{ texto: 'Centros de costo' }, { texto: 'Reglas de asignación' }]}
      >
        {puedeEditar && (
          <Button disabled={!catalogos} onClick={() => setFormulario({ show: true, regla: null })}>
            <i className="bi bi-plus-lg me-1" /> Nueva regla
          </Button>
        )}
      </EncabezadoPagina>

      <Card className="mb-3">
        <Card.Body>
          <Form
            onSubmit={(e) => {
              e.preventDefault()
              setQ(busqueda.trim())
            }}
          >
            <Row className="g-2 align-items-end">
              <Col xs={12} md={5}>
                <Form.Label htmlFor="buscar-regla" className="small text-suave mb-1">
                  Buscar
                </Form.Label>
                <Form.Control
                  id="buscar-regla"
                  size="sm"
                  placeholder="Cuenta, proveedor, centro o justificación (Enter)"
                  value={busqueda}
                  onChange={(e) => setBusqueda(e.target.value)}
                />
              </Col>
              <Col xs={6} md={2}>
                <Form.Label htmlFor="fecha-regla" className="small text-suave mb-1">
                  Vigencia al
                </Form.Label>
                <Form.Control id="fecha-regla" size="sm" type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
              </Col>
              <Col xs={6} md="auto" className="pb-1">
                <Form.Check
                  id="reglas-vigentes"
                  className="small"
                  label="Solo vigentes a esa fecha"
                  checked={soloVigentes}
                  onChange={(e) => setSoloVigentes(e.target.checked)}
                />
              </Col>
            </Row>
          </Form>
        </Card.Body>
      </Card>

      <Alert variant="light" className="border small">
        <i className="bi bi-info-circle me-1" />
        Orden de aplicación: <strong>proveedor + cuenta</strong>, luego <strong>solo proveedor</strong> y por último{' '}
        <strong>cuenta</strong> (la más cercana en el catálogo). Las cuentas exentas no reciben centro.
      </Alert>

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

      {!reglas ? (
        <Spinner animation="border" />
      ) : (
        <>
          <div className="text-suave small mb-2">{visibles.length} regla(s)</div>
          <Card className="mb-4">
            <div className="table-responsive">
              <Table hover className="align-middle">
                <thead>
                  <tr>
                    <th>Criterio</th>
                    <th>Centro destino</th>
                    <th>Vigencia</th>
                    <th>Justificación</th>
                    {puedeEditar && <th className="text-end">Acciones</th>}
                  </tr>
                </thead>
                <tbody>
                  {visibles.map((r) => {
                    const vigente = vigenteEn(r, fecha)
                    return (
                      <tr key={r.id} className={vigente ? '' : 'text-suave'}>
                        <td>
                          {r.proveedor && (
                            <div>
                              <i className="bi bi-truck me-1 text-suave" />
                              {r.proveedor_nombre}
                            </div>
                          )}
                          {r.cuenta && (
                            <div className="small">
                              <code className="me-1">{r.cuenta_codigo}</code>
                              {r.cuenta_nombre}
                            </div>
                          )}
                        </td>
                        <td>
                          <code className="me-1">{r.centro_codigo}</code>
                          {r.centro_nombre}
                        </td>
                        <td className="small text-nowrap">
                          {formatoFecha(r.vigente_desde)} – {r.vigente_hasta ? formatoFecha(r.vigente_hasta) : 'indefinida'}
                          {!vigente && (
                            <Badge bg="secondary-subtle" text="secondary-emphasis" className="ms-2">
                              No vigente
                            </Badge>
                          )}
                          {r.aplicada && (
                            <Badge bg="info-subtle" text="info-emphasis" className="ms-2" title="Ya se aplicó a asientos">
                              Aplicada
                            </Badge>
                          )}
                        </td>
                        <td className="small">{r.descripcion || <span className="text-suave">—</span>}</td>
                        {puedeEditar && (
                          <td className="text-end text-nowrap">
                            <Button
                              size="sm"
                              variant="outline-secondary"
                              className="me-1"
                              title="Editar vigencia o justificación"
                              onClick={() => setFormulario({ show: true, regla: r })}
                            >
                              <i className="bi bi-pencil" />
                            </Button>
                            {!r.aplicada && (
                              <Button size="sm" variant="outline-danger" title="Eliminar" onClick={() => setPorEliminar(r)}>
                                <i className="bi bi-trash" />
                              </Button>
                            )}
                          </td>
                        )}
                      </tr>
                    )
                  })}
                  {visibles.length === 0 && (
                    <tr>
                      <td colSpan={puedeEditar ? 5 : 4}>
                        <EstadoVacio icono="bi-signpost-split">
                          {reglas.length === 0 && !q ? 'No hay reglas de asignación.' : 'Ninguna regla coincide con el filtro.'}
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

      {catalogos && (
        <ReglaFormModal
          show={formulario.show}
          regla={formulario.regla}
          catalogos={catalogos}
          onHide={() => setFormulario({ show: false, regla: null })}
          onGuardado={alGuardar}
        />
      )}

      <Modal show={Boolean(porEliminar)} onHide={() => setPorEliminar(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            Eliminar regla
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          ¿Eliminar la regla <strong>{porEliminar?.criterio}</strong> → {porEliminar?.centro_codigo}? Solo es posible
          porque aún no se ha aplicado a ningún asiento.
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
