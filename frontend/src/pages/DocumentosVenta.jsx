import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Modal, Pagination, Row, Spinner, Table } from 'react-bootstrap'
import { Link } from 'react-router-dom'
import { api, apiTodas, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import SelectorCuenta from '../components/SelectorCuenta'
import { aCentavos, centavosATexto, formatoFecha, formatoMonto, hoyISO } from '../formato'

const TAMANO_PAGINA = 50
const TIPOS = { CCF: 'Comprobante de crédito fiscal', FACTURA: 'Factura de consumidor final' }

function aplanar(arbol, incluir) {
  const lista = []
  const recorrer = (nodos) =>
    nodos.forEach((n) => {
      if (incluir(n)) lista.push(n)
      recorrer(n.hijos)
    })
  recorrer(arbol)
  return lista
}

const erroresDe = async (resp) => {
  const err = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
  return Object.fromEntries(Object.entries(err).map(([c, m]) => [c, [].concat(m).map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join(' ')]))
}

function InsigniaEstado({ estado, texto }) {
  return estado === 'ANULADO' ? (
    <Badge bg="secondary-subtle" text="secondary-emphasis">
      {texto}
    </Badge>
  ) : (
    <Badge bg="success-subtle" text="success-emphasis">
      {texto}
    </Badge>
  )
}

function Campo({ id, etiqueta, error, children, ayuda }) {
  return (
    <Form.Group controlId={id}>
      <Form.Label className="small mb-1">{etiqueta}</Form.Label>
      {children}
      {error && <div className="invalid-feedback d-block">{error}</div>}
      {ayuda && <Form.Text>{ayuda}</Form.Text>}
    </Form.Group>
  )
}

const LINEA_VACIA = () => ({ cuenta: null, centro_costo: '', descripcion: '', monto: '', exenta: false })

/** Emisión de un CCF o una factura con sus líneas de ingreso. */
function EmisionModal({ show, catalogos, onHide, onGuardado }) {
  const [datos, setDatos] = useState({})
  const [lineas, setLineas] = useState([LINEA_VACIA()])
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!show) return
    setDatos({
      cliente: '',
      tipo_documento: 'CCF',
      numero_documento: '',
      fecha_emision: hoyISO(),
      concepto: '',
      cuenta_cobro: catalogos.cobro.find((c) => c.codigo === '1103')?.id || '',
    })
    setLineas([LINEA_VACIA()])
    setErrores({})
  }, [show, catalogos.cobro])

  const cambiar = (campo, valor) => setDatos((d) => ({ ...d, [campo]: valor }))
  const cambiarLinea = (i, campo, valor) => setLineas((ls) => ls.map((l, j) => (j === i ? { ...l, [campo]: valor } : l)))
  const elegirCliente = (id) => {
    const cliente = catalogos.clientes.find((c) => String(c.id) === id)
    setDatos((d) => ({ ...d, cliente: id, tipo_documento: cliente?.tipo === 'CONSUMIDOR_FINAL' ? 'FACTURA' : d.tipo_documento }))
  }

  const centavos = (l) => (Number.isNaN(aCentavos(l.monto)) ? 0 : aCentavos(l.monto))
  const gravadas = lineas.filter((l) => !l.exenta).reduce((s, l) => s + centavos(l), 0)
  const exentas = lineas.filter((l) => l.exenta).reduce((s, l) => s + centavos(l), 0)
  const iva = Math.round(gravadas * 0.13)
  const total = gravadas + exentas + iva

  const guardar = async (e) => {
    e.preventDefault()
    if (lineas.some((l) => !l.cuenta || !l.monto || Number.isNaN(aCentavos(l.monto))))
      return setErrores({ lineas: 'Cada línea necesita cuenta de ingreso y monto válido (máximo 2 decimales).' })
    setGuardando(true)
    const resp = await api('/api/ventas/documentos/', {
      method: 'POST',
      body: {
        ...datos,
        cuenta_cobro: datos.cuenta_cobro || null,
        lineas: lineas.map((l) => ({
          cuenta: l.cuenta.id,
          centro_costo: l.centro_costo || null,
          descripcion: l.descripcion,
          monto: String(l.monto).replace(/,/g, ''),
          exenta: l.exenta,
        })),
      },
    })
    setGuardando(false)
    if (resp.ok) return onGuardado(await resp.json())
    setErrores(await erroresDe(resp))
  }

  const conocidos = ['cliente', 'tipo_documento', 'numero_documento', 'fecha_emision', 'concepto', 'cuenta_cobro', 'lineas']
  const generales = Object.entries(errores).filter(([c]) => !conocidos.includes(c))

  return (
    <Modal show={show} onHide={onHide} size="xl" centered>
      <Form onSubmit={guardar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            Emitir documento de venta
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {generales.map(([c, m]) => (
            <Alert key={c} variant="danger">
              {m}
            </Alert>
          ))}
          <Row className="g-3">
            <Col md={6}>
              <Campo id="dv-cliente" etiqueta="Cliente" error={errores.cliente}>
                <Form.Select value={datos.cliente || ''} onChange={(e) => elegirCliente(e.target.value)} autoFocus>
                  <option value="">Seleccione…</option>
                  {catalogos.clientes.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.nombre}
                      {c.tipo === 'CONTRIBUYENTE' ? ` (NRC ${c.nrc})` : ' (consumidor final)'}
                    </option>
                  ))}
                </Form.Select>
              </Campo>
            </Col>
            <Col md={3}>
              <Campo id="dv-tipo" etiqueta="Tipo de documento" error={errores.tipo_documento}>
                <Form.Select value={datos.tipo_documento || ''} onChange={(e) => cambiar('tipo_documento', e.target.value)}>
                  {Object.entries(TIPOS).map(([v, t]) => (
                    <option key={v} value={v}>
                      {t}
                    </option>
                  ))}
                </Form.Select>
              </Campo>
            </Col>
            <Col md={3}>
              <Campo id="dv-numero" etiqueta="Número" error={errores.numero_documento} ayuda="El número emitido no se reutiliza.">
                <Form.Control maxLength={40} value={datos.numero_documento || ''} onChange={(e) => cambiar('numero_documento', e.target.value)} />
              </Campo>
            </Col>
            <Col md={3}>
              <Campo id="dv-fecha" etiqueta="Fecha de emisión" error={errores.fecha_emision} ayuda="Fecha del asiento contable.">
                <Form.Control type="date" value={datos.fecha_emision || ''} onChange={(e) => cambiar('fecha_emision', e.target.value)} />
              </Campo>
            </Col>
            <Col md={4}>
              <Campo id="dv-cobro" etiqueta="Cobrado en / por cobrar en" error={errores.cuenta_cobro}>
                <Form.Select value={datos.cuenta_cobro || ''} onChange={(e) => cambiar('cuenta_cobro', e.target.value)}>
                  <option value="">Seleccione…</option>
                  {catalogos.cobro.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.codigo} · {c.nombre}
                    </option>
                  ))}
                </Form.Select>
              </Campo>
            </Col>
            <Col md={5}>
              <Campo id="dv-concepto" etiqueta="Concepto" error={errores.concepto}>
                <Form.Control maxLength={300} value={datos.concepto || ''} onChange={(e) => cambiar('concepto', e.target.value)} />
              </Campo>
            </Col>
          </Row>

          <h3 className="h6 mt-4 mb-2">Ingresos (abono, sin IVA)</h3>
          {errores.lineas && <Alert variant="danger" className="small py-2">{errores.lineas}</Alert>}
          <Table size="sm" className="align-middle">
            <thead className="table-light">
              <tr>
                <th style={{ width: '30%' }}>Cuenta de ingreso</th>
                <th style={{ width: '22%' }}>Centro de costo</th>
                <th>Descripción</th>
                <th className="text-center">Exenta</th>
                <th className="text-end" style={{ width: '13%' }}>
                  Monto
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {lineas.map((l, i) => (
                <tr key={i}>
                  <td>
                    <SelectorCuenta id={`dv-cuenta-${i}`} cuentas={catalogos.ingresos} valor={l.cuenta} onChange={(c) => cambiarLinea(i, 'cuenta', c)} />
                  </td>
                  <td>
                    <Form.Select size="sm" aria-label="Centro de costo" value={l.centro_costo} onChange={(e) => cambiarLinea(i, 'centro_costo', e.target.value)}>
                      <option value="">Según regla</option>
                      {catalogos.centros.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.codigo} · {c.nombre}
                        </option>
                      ))}
                    </Form.Select>
                  </td>
                  <td>
                    <Form.Control size="sm" aria-label="Descripción" maxLength={200} value={l.descripcion} onChange={(e) => cambiarLinea(i, 'descripcion', e.target.value)} />
                  </td>
                  <td className="text-center">
                    <Form.Check aria-label="Exenta de IVA" checked={l.exenta} onChange={(e) => cambiarLinea(i, 'exenta', e.target.checked)} />
                  </td>
                  <td>
                    <Form.Control
                      size="sm"
                      inputMode="decimal"
                      className="text-end"
                      aria-label="Monto"
                      value={l.monto}
                      isInvalid={Number.isNaN(aCentavos(l.monto))}
                      onChange={(e) => cambiarLinea(i, 'monto', e.target.value)}
                    />
                  </td>
                  <td>
                    <Button variant="link" size="sm" className="text-danger p-1" disabled={lineas.length === 1} title="Quitar línea" onClick={() => setLineas((ls) => ls.filter((_, j) => j !== i))}>
                      <i className="bi bi-x-lg" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Button variant="outline-secondary" size="sm" onClick={() => setLineas((ls) => [...ls, LINEA_VACIA()])}>
            <i className="bi bi-plus-lg me-1" /> Agregar línea
          </Button>

          <Row className="g-3 mt-2 small">
            {[
              ['Ventas exentas', exentas],
              ['Ventas gravadas', gravadas],
              ['IVA débito fiscal 13 %', iva],
            ].map(([t, v]) => (
              <Col key={t} xs={6} md={2}>
                <div className="text-suave">{t}</div>
                <div className="monto text-start">{centavosATexto(v)}</div>
              </Col>
            ))}
            <Col xs={6} md={3}>
              <div className="text-suave">Total del documento</div>
              <div className="fs-5 fw-semibold monto text-start">{centavosATexto(total)}</div>
            </Col>
          </Row>
          <div className="small text-suave mt-2">
            <i className="bi bi-info-circle me-1" />
            Al guardar se contabiliza el asiento: cargo a la cuenta de cobro por el total, abono a cada ingreso con su centro de costo y abono al
            IVA débito fiscal (2406). Marque como exentas las líneas sin IVA (p. ej. intereses de préstamos).
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={onHide}>
            Cancelar
          </Button>
          <Button type="submit" disabled={guardando}>
            {guardando && <Spinner animation="border" size="sm" className="me-2" />}
            Emitir y contabilizar
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  )
}

/** Detalle del documento con su anulación. */
function DetalleModal({ id, puedeEditar, onHide, onCambio }) {
  const [doc, setDoc] = useState(null)
  const [error, setError] = useState('')
  const [anulando, setAnulando] = useState(false)
  const [motivo, setMotivo] = useState('')

  const cargar = useCallback(async () => {
    const resp = await api(`/api/ventas/documentos/${id}/`)
    if (!resp.ok) return setError(await mensajeError(resp))
    setDoc(await resp.json())
  }, [id])

  useEffect(() => {
    setDoc(null)
    setError('')
    setAnulando(false)
    setMotivo('')
    if (id) cargar()
  }, [id, cargar])

  const anular = async () => {
    const resp = await api(`/api/ventas/documentos/${id}/anular/`, { method: 'POST', body: { motivo } })
    if (!resp.ok) return setError(await mensajeError(resp))
    setDoc(await resp.json())
    setAnulando(false)
    setError('')
    onCambio()
  }

  return (
    <Modal show={Boolean(id)} onHide={onHide} size="lg" centered>
      <Modal.Header closeButton>
        <Modal.Title as="h2" className="h5">
          {doc ? `${doc.tipo_documento_display} ${doc.numero_documento}` : 'Documento de venta'}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {error && <Alert variant="danger">{error}</Alert>}
        {!doc ? (
          <Spinner animation="border" />
        ) : (
          <>
            <Row className="g-3 small mb-3">
              <Col md={6}>
                <div className="text-suave">Cliente</div>
                <div className="fw-semibold">{doc.cliente.nombre}</div>
                {doc.cliente.nit && (
                  <div className="text-suave">
                    NIT {doc.cliente.nit}
                    {doc.cliente.nrc && ` · NRC ${doc.cliente.nrc}`}
                  </div>
                )}
              </Col>
              <Col xs={6} md={3}>
                <div className="text-suave">Emisión</div>
                <div>{formatoFecha(doc.fecha_emision)}</div>
              </Col>
              <Col xs={6} md={3}>
                <div className="text-suave">Estado</div>
                <InsigniaEstado estado={doc.estado} texto={doc.estado_display} />
              </Col>
              <Col xs={12}>
                <div className="text-suave">Concepto</div>
                <div>{doc.concepto}</div>
              </Col>
              <Col xs={12}>
                <div className="d-flex flex-wrap gap-3 p-2 rounded bg-body-tertiary">
                  {[
                    ['Ventas exentas', doc.ventas_exentas],
                    ['Ventas gravadas', doc.ventas_gravadas],
                    ['IVA débito fiscal', doc.iva_debito_fiscal],
                    ['Total', doc.total],
                  ].map(([t, v]) => (
                    <div key={t}>
                      <span className="text-suave">{t}: </span>
                      <span className="monto fw-semibold">{formatoMonto(v)}</span>
                    </div>
                  ))}
                </div>
              </Col>
              <Col xs={12}>
                <span className="text-suave">Asiento: </span>
                <Link to={`/asientos/${doc.asiento.id}`}>{doc.asiento.codigo}</Link>
                <span className="text-suave">
                  {' '}
                  · cobro en {doc.cuenta_cobro.codigo} {doc.cuenta_cobro.nombre}
                </span>
                {doc.asiento_anulacion && (
                  <>
                    <span className="text-suave"> · anulado con </span>
                    <Link to={`/asientos/${doc.asiento_anulacion.id}`}>{doc.asiento_anulacion.codigo}</Link>
                    <span className="text-suave"> ({doc.motivo_anulacion})</span>
                  </>
                )}
              </Col>
            </Row>
            <h3 className="h6">Ingresos</h3>
            <Table size="sm">
              <tbody>
                {doc.lineas.map((l, i) => (
                  <tr key={i} className="small">
                    <td>
                      <code className="me-1">{l.cuenta.codigo}</code>
                      {l.cuenta.nombre}
                    </td>
                    <td>{l.centro_costo ? `${l.centro_costo.codigo} ${l.centro_costo.nombre}` : '—'}</td>
                    <td className="text-suave">{l.descripcion}</td>
                    <td className="monto">{formatoMonto(l.monto)}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
            {anulando && (
              <Card body className="bg-body-tertiary">
                <p className="small mb-2">Se registrará la reversión del asiento. El número del documento no se podrá volver a usar.</p>
                <Form.Group controlId="dv-motivo">
                  <Form.Label className="small">Motivo de la anulación</Form.Label>
                  <Form.Control size="sm" maxLength={300} value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus />
                </Form.Group>
                <div className="text-end mt-2">
                  <Button size="sm" variant="secondary" className="me-2" onClick={() => setAnulando(false)}>
                    Cancelar
                  </Button>
                  <Button size="sm" variant="danger" disabled={!motivo.trim()} onClick={anular}>
                    Anular
                  </Button>
                </div>
              </Card>
            )}
          </>
        )}
      </Modal.Body>
      <Modal.Footer className="justify-content-between">
        <div>
          {puedeEditar && doc?.estado === 'VIGENTE' && !anulando && (
            <Button variant="outline-danger" size="sm" onClick={() => setAnulando(true)}>
              Anular documento
            </Button>
          )}
        </div>
        <Button variant="secondary" onClick={onHide}>
          Cerrar
        </Button>
      </Modal.Footer>
    </Modal>
  )
}

export default function DocumentosVenta() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR, ROLES.TESORERO)
  const hoy = hoyISO()

  const [filtros, setFiltros] = useState({ desde: `${hoy.slice(0, 7)}-01`, hasta: hoy, tipo_documento: '', estado: '', q: '' })
  const [busqueda, setBusqueda] = useState('')
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [catalogos, setCatalogos] = useState({ clientes: [], cobro: [], ingresos: [], centros: [] })
  const [emision, setEmision] = useState(false)
  const [detalle, setDetalle] = useState(null)

  const cargar = useCallback(async () => {
    const q = new URLSearchParams({ page: pagina })
    Object.entries(filtros).forEach(([k, v]) => v && q.set(k, v))
    const resp = await api(`/api/ventas/documentos/?${q}`)
    if (!resp.ok) {
      setDatos({ count: 0, results: [] })
      return setError(await mensajeError(resp))
    }
    setDatos(await resp.json())
  }, [filtros, pagina])

  useEffect(() => {
    cargar()
  }, [cargar])

  useEffect(() => {
    Promise.all([
      apiTodas('/api/clientes/?activo=true'),
      api('/api/cuentas/arbol/').then((r) => (r.ok ? r.json() : [])),
      api('/api/centros-costo/arbol/').then((r) => (r.ok ? r.json() : [])),
    ]).then(([clientes, cuentas, centros]) => {
      const detalle = (n) => n.acepta_movimientos && n.activa
      const simple = (n) => ({ id: n.id, codigo: n.codigo, nombre: n.nombre })
      setCatalogos({
        clientes,
        cobro: aplanar(cuentas, (n) => detalle(n) && n.tipo === 'ACTIVO' && n.exenta_centro_costo && /^1[14]/.test(n.codigo)).map(simple),
        ingresos: aplanar(cuentas, (n) => detalle(n) && n.tipo === 'INGRESO').map(simple),
        centros: aplanar(centros, (n) => n.acepta_movimientos && (!n.vigente_hasta || n.vigente_hasta >= hoyISO())),
      })
    })
  }, [])

  const filtrar = (cambios) => {
    setPagina(1)
    setFiltros((f) => ({ ...f, ...cambios }))
  }

  const alEmitir = (doc) => {
    setEmision(false)
    setError('')
    setAviso(`${doc.tipo_documento_display} ${doc.numero_documento} emitido (asiento ${doc.asiento.codigo}).`)
    cargar()
    setDetalle(doc.id)
  }

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.count / TAMANO_PAGINA)) : 1

  return (
    <>
      <EncabezadoPagina
        titulo="Documentos de venta"
        descripcion="Comprobantes de crédito fiscal y facturas de consumidor final. Cada documento se contabiliza al emitirlo."
        migas={[{ texto: 'Ventas' }, { texto: 'Documentos de venta' }]}
      >
        {puedeEditar && (
          <Button onClick={() => setEmision(true)}>
            <i className="bi bi-plus-lg me-1" /> Emitir documento
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
              <Col xs={6} md={2}>
                <Form.Label htmlFor="dv-desde" className="small text-suave mb-1">
                  Desde
                </Form.Label>
                <Form.Control id="dv-desde" size="sm" type="date" value={filtros.desde} onChange={(e) => filtrar({ desde: e.target.value })} />
              </Col>
              <Col xs={6} md={2}>
                <Form.Label htmlFor="dv-hasta" className="small text-suave mb-1">
                  Hasta
                </Form.Label>
                <Form.Control id="dv-hasta" size="sm" type="date" value={filtros.hasta} onChange={(e) => filtrar({ hasta: e.target.value })} />
              </Col>
              <Col xs={6} md={2}>
                <Form.Label htmlFor="dv-f-tipo" className="small text-suave mb-1">
                  Tipo
                </Form.Label>
                <Form.Select id="dv-f-tipo" size="sm" value={filtros.tipo_documento} onChange={(e) => filtrar({ tipo_documento: e.target.value })}>
                  <option value="">Todos</option>
                  <option value="CCF">CCF</option>
                  <option value="FACTURA">Facturas</option>
                </Form.Select>
              </Col>
              <Col xs={6} md={2}>
                <Form.Label htmlFor="dv-f-estado" className="small text-suave mb-1">
                  Estado
                </Form.Label>
                <Form.Select id="dv-f-estado" size="sm" value={filtros.estado} onChange={(e) => filtrar({ estado: e.target.value })}>
                  <option value="">Todos</option>
                  <option value="VIGENTE">Vigentes</option>
                  <option value="ANULADO">Anulados</option>
                </Form.Select>
              </Col>
              <Col xs={8} md={2}>
                <Form.Label htmlFor="dv-buscar" className="small text-suave mb-1">
                  Buscar
                </Form.Label>
                <Form.Control id="dv-buscar" size="sm" placeholder="Número, cliente o concepto" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
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
          <div className="text-suave small mb-2">{datos.count} documento(s)</div>
          <Card className="mb-3">
            <div className="table-responsive">
              <Table hover className="align-middle mb-0">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Documento</th>
                    <th>Cliente</th>
                    <th className="text-end">Exentas</th>
                    <th className="text-end">Gravadas</th>
                    <th className="text-end">IVA</th>
                    <th className="text-end">Total</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.results.map((d) => (
                    <tr key={d.id} role="button" onClick={() => setDetalle(d.id)} className={d.estado === 'ANULADO' ? 'text-suave' : ''}>
                      <td className="small text-nowrap">{formatoFecha(d.fecha_emision)}</td>
                      <td className="text-nowrap">
                        <span className="small text-suave me-1">{d.tipo_documento}</span>
                        <code>{d.numero_documento}</code>
                      </td>
                      <td>{d.cliente.nombre}</td>
                      <td className="monto">{formatoMonto(d.ventas_exentas, { vacioSiCero: true })}</td>
                      <td className="monto">{formatoMonto(d.ventas_gravadas, { vacioSiCero: true })}</td>
                      <td className="monto">{formatoMonto(d.iva_debito_fiscal, { vacioSiCero: true })}</td>
                      <td className="monto fw-semibold">{formatoMonto(d.total)}</td>
                      <td>
                        <InsigniaEstado estado={d.estado} texto={d.estado_display} />
                      </td>
                    </tr>
                  ))}
                  {datos.results.length === 0 && (
                    <tr>
                      <td colSpan={8}>
                        <EstadoVacio icono="bi-receipt-cutoff">No hay documentos de venta que coincidan.</EstadoVacio>
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

      <EmisionModal show={emision} catalogos={catalogos} onHide={() => setEmision(false)} onGuardado={alEmitir} />
      <DetalleModal id={detalle} puedeEditar={puedeEditar} onHide={() => setDetalle(null)} onCambio={cargar} />
    </>
  )
}
