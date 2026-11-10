import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Modal, Row, Spinner, Table } from 'react-bootstrap'
import { api, apiTodas, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import { aCentavos, formatoFecha, formatoMonto, hoyISO } from '../formato'

const CATEGORIAS = {
  PLANILLA: 'Planilla',
  IMPUESTOS: 'Impuestos',
  ALQUILERES: 'Alquileres',
  SERVICIOS: 'Servicios',
  PRESTAMOS: 'Préstamos',
  INVERSION: 'Inversión',
  OTROS: 'Otros',
}

const VACIO = () => ({
  concepto: '',
  categoria: 'PLANILLA',
  monto: '',
  frecuencia: 'MENSUAL',
  fecha_inicio: hoyISO(),
  fecha_fin: '',
  dia_mes: '30',
  proveedor: '',
  activo: true,
})

function EgresoModal({ show, egreso, proveedores, onHide, onGuardado }) {
  const [datos, setDatos] = useState(VACIO())
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!show) return
    setErrores({})
    setDatos(
      egreso
        ? {
            ...egreso,
            fecha_fin: egreso.fecha_fin || '',
            dia_mes: egreso.dia_mes ? String(egreso.dia_mes) : '30',
            proveedor: egreso.proveedor ? String(egreso.proveedor) : '',
          }
        : VACIO(),
    )
  }, [show, egreso])

  const cambiar = (campo, valor) => setDatos((d) => ({ ...d, [campo]: valor }))
  const mensual = datos.frecuencia === 'MENSUAL'

  const guardar = async (e) => {
    e.preventDefault()
    if (Number.isNaN(aCentavos(datos.monto)) || !datos.monto) return setErrores({ monto: 'Monto inválido (máximo 2 decimales).' })
    setGuardando(true)
    const cuerpo = {
      concepto: datos.concepto,
      categoria: datos.categoria,
      monto: String(datos.monto).replace(/,/g, ''),
      frecuencia: datos.frecuencia,
      fecha_inicio: datos.fecha_inicio,
      fecha_fin: mensual && datos.fecha_fin ? datos.fecha_fin : null,
      dia_mes: mensual ? Number(datos.dia_mes) : null,
      proveedor: datos.proveedor || null,
      activo: datos.activo,
    }
    const resp = await api(egreso ? `/api/egresos-programados/${egreso.id}/` : '/api/egresos-programados/', {
      method: egreso ? 'PATCH' : 'POST',
      body: cuerpo,
    })
    setGuardando(false)
    if (resp.ok) return onGuardado(await resp.json())
    const err = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
    setErrores(Object.fromEntries(Object.entries(err).map(([c, m]) => [c, [].concat(m).join(' ')])))
  }

  const campos = ['concepto', 'categoria', 'monto', 'frecuencia', 'fecha_inicio', 'fecha_fin', 'dia_mes', 'proveedor', 'activo']
  const generales = Object.entries(errores).filter(([c]) => !campos.includes(c))
  const invalido = (c) => Boolean(errores[c])
  const feedback = (c) => errores[c] && <Form.Control.Feedback type="invalid">{errores[c]}</Form.Control.Feedback>

  return (
    <Modal show={show} onHide={onHide} centered>
      <Form onSubmit={guardar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            {egreso ? `Editar ${egreso.concepto}` : 'Nuevo egreso programado'}
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
              <Form.Group controlId="egreso-concepto">
                <Form.Label>Concepto</Form.Label>
                <Form.Control maxLength={200} value={datos.concepto} onChange={(e) => cambiar('concepto', e.target.value)} isInvalid={invalido('concepto')} autoFocus />
                {feedback('concepto')}
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group controlId="egreso-categoria">
                <Form.Label>Categoría</Form.Label>
                <Form.Select value={datos.categoria} onChange={(e) => cambiar('categoria', e.target.value)}>
                  {Object.entries(CATEGORIAS).map(([v, t]) => (
                    <option key={v} value={v}>
                      {t}
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group controlId="egreso-monto">
                <Form.Label>Monto</Form.Label>
                <Form.Control inputMode="decimal" className="text-end" value={datos.monto} onChange={(e) => cambiar('monto', e.target.value)} isInvalid={invalido('monto')} />
                {feedback('monto')}
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group controlId="egreso-frecuencia">
                <Form.Label>Frecuencia</Form.Label>
                <Form.Select value={datos.frecuencia} onChange={(e) => cambiar('frecuencia', e.target.value)}>
                  <option value="MENSUAL">Mensual</option>
                  <option value="UNICA">Única</option>
                </Form.Select>
              </Form.Group>
            </Col>
            {mensual && (
              <Col md={6}>
                <Form.Group controlId="egreso-dia">
                  <Form.Label>Día del mes</Form.Label>
                  <Form.Control type="number" min="1" max="31" value={datos.dia_mes} onChange={(e) => cambiar('dia_mes', e.target.value)} isInvalid={invalido('dia_mes')} />
                  {feedback('dia_mes')}
                  <Form.Text>Si el mes tiene menos días, se usa el último.</Form.Text>
                </Form.Group>
              </Col>
            )}
            <Col md={6}>
              <Form.Group controlId="egreso-inicio">
                <Form.Label>{mensual ? 'Desde' : 'Fecha del egreso'}</Form.Label>
                <Form.Control type="date" value={datos.fecha_inicio} onChange={(e) => cambiar('fecha_inicio', e.target.value)} isInvalid={invalido('fecha_inicio')} />
                {feedback('fecha_inicio')}
              </Form.Group>
            </Col>
            {mensual && (
              <Col md={6}>
                <Form.Group controlId="egreso-fin">
                  <Form.Label>Hasta (opcional)</Form.Label>
                  <Form.Control type="date" value={datos.fecha_fin} onChange={(e) => cambiar('fecha_fin', e.target.value)} isInvalid={invalido('fecha_fin')} />
                  {feedback('fecha_fin')}
                </Form.Group>
              </Col>
            )}
            <Col md={mensual ? 12 : 6}>
              <Form.Group controlId="egreso-proveedor">
                <Form.Label>Proveedor (opcional)</Form.Label>
                <Form.Select value={datos.proveedor} onChange={(e) => cambiar('proveedor', e.target.value)} isInvalid={invalido('proveedor')}>
                  <option value="">—</option>
                  {proveedores.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre}
                    </option>
                  ))}
                </Form.Select>
                {feedback('proveedor')}
              </Form.Group>
            </Col>
            <Col xs={12}>
              <Form.Check type="switch" id="egreso-activo" label="Activo (se incluye en la proyección)" checked={datos.activo} onChange={(e) => cambiar('activo', e.target.checked)} />
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

export default function EgresosProgramados() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR, ROLES.TESORERO)
  const [lista, setLista] = useState(null)
  const [proveedores, setProveedores] = useState([])
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [modal, setModal] = useState({ show: false, egreso: null })
  const [porEliminar, setPorEliminar] = useState(null)

  const cargar = useCallback(async () => {
    const resp = await api('/api/egresos-programados/')
    if (!resp.ok) {
      setLista([])
      return setError(await mensajeError(resp))
    }
    setLista(await resp.json())
  }, [])

  useEffect(() => {
    cargar()
    apiTodas('/api/proveedores/?activo=true').then(setProveedores)
  }, [cargar])

  const notificar = (texto) => {
    setError('')
    setAviso(texto)
  }

  const alGuardar = (e) => {
    notificar(`Egreso programado "${e.concepto}" ${modal.egreso ? 'actualizado' : 'creado'}.`)
    setModal({ show: false, egreso: null })
    cargar()
  }

  const alternar = async (e) => {
    const resp = await api(`/api/egresos-programados/${e.id}/`, { method: 'PATCH', body: { activo: !e.activo } })
    if (!resp.ok) return setError(await mensajeError(resp))
    notificar(`"${e.concepto}" ${e.activo ? 'desactivado' : 'activado'}.`)
    cargar()
  }

  const eliminar = async () => {
    const e = porEliminar
    setPorEliminar(null)
    const resp = await api(`/api/egresos-programados/${e.id}/`, { method: 'DELETE' })
    if (!resp.ok) return setError(await mensajeError(resp))
    notificar(`"${e.concepto}" eliminado.`)
    cargar()
  }

  return (
    <>
      <EncabezadoPagina
        titulo="Egresos programados"
        descripcion="Obligaciones de fecha conocida que no son facturas de proveedores (planilla, impuestos, alquileres, cuotas de préstamos, inversiones). Alimentan la proyección de egresos."
        migas={[{ texto: 'Tesorería' }, { texto: 'Egresos programados' }]}
      >
        {puedeEditar && (
          <Button onClick={() => setModal({ show: true, egreso: null })}>
            <i className="bi bi-plus-lg me-1" /> Nuevo egreso
          </Button>
        )}
      </EncabezadoPagina>

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

      {!lista ? (
        <Spinner animation="border" />
      ) : (
        <Card>
          <div className="table-responsive">
            <Table hover className="align-middle mb-0">
              <thead>
                <tr>
                  <th>Concepto</th>
                  <th>Categoría</th>
                  <th>Frecuencia</th>
                  <th className="text-end">Monto</th>
                  <th>Próxima fecha</th>
                  <th>Estado</th>
                  {puedeEditar && <th className="text-end">Acciones</th>}
                </tr>
              </thead>
              <tbody>
                {lista.map((e) => (
                  <tr key={e.id} className={e.activo ? '' : 'text-suave'}>
                    <td>
                      {e.concepto}
                      {e.proveedor_nombre && <div className="small text-suave">{e.proveedor_nombre}</div>}
                    </td>
                    <td>{e.categoria_display}</td>
                    <td className="small">
                      {e.frecuencia === 'MENSUAL' ? (
                        <>
                          Mensual, día {e.dia_mes}
                          <div className="text-suave">
                            desde {formatoFecha(e.fecha_inicio)}
                            {e.fecha_fin && ` hasta ${formatoFecha(e.fecha_fin)}`}
                          </div>
                        </>
                      ) : (
                        `Única: ${formatoFecha(e.fecha_inicio)}`
                      )}
                    </td>
                    <td className="monto">{formatoMonto(e.monto)}</td>
                    <td className="small">{e.proxima_fecha ? formatoFecha(e.proxima_fecha) : <span className="text-suave">—</span>}</td>
                    <td>
                      {e.activo ? (
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
                        <Button size="sm" variant="outline-secondary" className="me-1" title="Editar" onClick={() => setModal({ show: true, egreso: e })}>
                          <i className="bi bi-pencil" />
                        </Button>
                        <Button size="sm" variant="outline-secondary" className="me-1" title={e.activo ? 'Desactivar' : 'Activar'} onClick={() => alternar(e)}>
                          <i className={`bi ${e.activo ? 'bi-pause' : 'bi-play'}`} />
                        </Button>
                        <Button size="sm" variant="outline-danger" title="Eliminar" onClick={() => setPorEliminar(e)}>
                          <i className="bi bi-trash" />
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
                {lista.length === 0 && (
                  <tr>
                    <td colSpan={puedeEditar ? 7 : 6}>
                      <EstadoVacio icono="bi-calendar-plus">No hay egresos programados.</EstadoVacio>
                    </td>
                  </tr>
                )}
              </tbody>
            </Table>
          </div>
        </Card>
      )}

      <EgresoModal
        show={modal.show}
        egreso={modal.egreso}
        proveedores={proveedores}
        onHide={() => setModal({ show: false, egreso: null })}
        onGuardado={alGuardar}
      />

      <Modal show={Boolean(porEliminar)} onHide={() => setPorEliminar(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            Eliminar egreso programado
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          ¿Eliminar <strong>{porEliminar?.concepto}</strong>? Dejará de aparecer en la proyección. Si solo es temporal, desactívelo.
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
