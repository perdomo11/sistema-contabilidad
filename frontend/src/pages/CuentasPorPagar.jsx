import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Modal, Pagination, Row, Spinner, Table } from 'react-bootstrap'
import { Link, useSearchParams } from 'react-router-dom'
import { api, apiTodas, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import SelectorCuenta from '../components/SelectorCuenta'
import { aCentavos, centavosATexto, formatoFecha, formatoMonto, hoyISO } from '../formato'

const TAMANO_PAGINA = 50
const TIPOS = { FACTURA: 'Factura', CCF: 'Comprobante de crédito fiscal', RECIBO: 'Recibo', OTRO: 'Otro' }
const COLOR_ESTADO = { PENDIENTE: 'warning', PARCIAL: 'info', PAGADA: 'success', ANULADA: 'secondary' }
const TRAMOS = { '1-30': '1 a 30 días', '31-60': '31 a 60 días', '61-90': '61 a 90 días', mas_90: 'Más de 90 días' }

const sumarDias = (iso, dias) => {
  const d = new Date(`${iso}T12:00:00`)
  d.setDate(d.getDate() + dias)
  return d.toISOString().slice(0, 10)
}

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
  const c = COLOR_ESTADO[estado]
  return (
    <Badge bg={`${c}-subtle`} text={`${c}-emphasis`}>
      {texto}
    </Badge>
  )
}

function InsigniaVencimiento({ vencimiento, dias }) {
  if (!vencimiento) return null
  if (vencimiento === 'VENCIDA')
    return (
      <Badge bg="danger-subtle" text="danger-emphasis" className="fw-normal">
        Vencida hace {dias} día{dias === 1 ? '' : 's'}
      </Badge>
    )
  if (vencimiento === 'POR_VENCER')
    return (
      <Badge bg="warning-subtle" text="warning-emphasis" className="fw-normal">
        {dias === 0 ? 'Vence hoy' : `Vence en ${dias} día${dias === 1 ? '' : 's'}`}
      </Badge>
    )
  return <span className="small text-suave">en {dias} días</span>
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

const LINEA_VACIA = () => ({ cuenta: null, centro_costo: '', descripcion: '', monto: '' })

/** Registro de un documento por pagar con sus líneas de imputación. */
function RegistroModal({ show, catalogos, onHide, onGuardado }) {
  const [datos, setDatos] = useState({})
  const [lineas, setLineas] = useState([LINEA_VACIA()])
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!show) return
    const hoy = hoyISO()
    setDatos({
      proveedor: '',
      tipo_documento: 'FACTURA',
      numero_documento: '',
      fecha_emision: hoy,
      fecha_vencimiento: sumarDias(hoy, 30),
      concepto: '',
      cuenta_pasivo: catalogos.pasivos.find((c) => c.codigo === '2401')?.id || '',
    })
    setLineas([LINEA_VACIA()])
    setErrores({})
  }, [show, catalogos.pasivos])

  const cambiar = (campo, valor) => setDatos((d) => ({ ...d, [campo]: valor }))
  const cambiarLinea = (i, campo, valor) => setLineas((ls) => ls.map((l, j) => (j === i ? { ...l, [campo]: valor } : l)))
  const total = lineas.reduce((s, l) => s + (Number.isNaN(aCentavos(l.monto)) ? 0 : aCentavos(l.monto)), 0)

  const guardar = async (e) => {
    e.preventDefault()
    if (lineas.some((l) => !l.cuenta || !l.monto || Number.isNaN(aCentavos(l.monto))))
      return setErrores({ lineas: 'Cada línea necesita cuenta y monto válido (máximo 2 decimales).' })
    setGuardando(true)
    const resp = await api('/api/cuentas-por-pagar/', {
      method: 'POST',
      body: {
        ...datos,
        cuenta_pasivo: datos.cuenta_pasivo || null,
        lineas: lineas.map((l) => ({
          cuenta: l.cuenta.id,
          centro_costo: l.centro_costo || null,
          descripcion: l.descripcion,
          monto: String(l.monto).replace(/,/g, ''),
        })),
      },
    })
    setGuardando(false)
    if (resp.ok) return onGuardado(await resp.json())
    setErrores(await erroresDe(resp))
  }

  const conocidos = ['proveedor', 'tipo_documento', 'numero_documento', 'fecha_emision', 'fecha_vencimiento', 'concepto', 'cuenta_pasivo', 'lineas']
  const generales = Object.entries(errores).filter(([c]) => !conocidos.includes(c))

  return (
    <Modal show={show} onHide={onHide} size="xl" centered>
      <Form onSubmit={guardar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            Registrar documento por pagar
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
              <Campo id="cxp-proveedor" etiqueta="Proveedor" error={errores.proveedor}>
                <Form.Select value={datos.proveedor || ''} onChange={(e) => cambiar('proveedor', e.target.value)} autoFocus>
                  <option value="">Seleccione…</option>
                  {catalogos.proveedores.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre} ({p.nit})
                    </option>
                  ))}
                </Form.Select>
              </Campo>
            </Col>
            <Col md={3}>
              <Campo id="cxp-tipo" etiqueta="Tipo de documento" error={errores.tipo_documento}>
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
              <Campo id="cxp-numero" etiqueta="Número" error={errores.numero_documento}>
                <Form.Control maxLength={40} value={datos.numero_documento || ''} onChange={(e) => cambiar('numero_documento', e.target.value)} />
              </Campo>
            </Col>
            <Col md={3}>
              <Campo id="cxp-emision" etiqueta="Fecha de emisión" error={errores.fecha_emision} ayuda="Fecha del asiento contable.">
                <Form.Control
                  type="date"
                  value={datos.fecha_emision || ''}
                  onChange={(e) => setDatos((d) => ({ ...d, fecha_emision: e.target.value, fecha_vencimiento: sumarDias(e.target.value, 30) }))}
                />
              </Campo>
            </Col>
            <Col md={3}>
              <Campo id="cxp-vence" etiqueta="Fecha de vencimiento" error={errores.fecha_vencimiento}>
                <Form.Control type="date" value={datos.fecha_vencimiento || ''} onChange={(e) => cambiar('fecha_vencimiento', e.target.value)} />
              </Campo>
            </Col>
            <Col md={6}>
              <Campo id="cxp-pasivo" etiqueta="Cuenta por pagar" error={errores.cuenta_pasivo}>
                <Form.Select value={datos.cuenta_pasivo || ''} onChange={(e) => cambiar('cuenta_pasivo', e.target.value)}>
                  <option value="">Seleccione…</option>
                  {catalogos.pasivos.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.codigo} · {c.nombre}
                    </option>
                  ))}
                </Form.Select>
              </Campo>
            </Col>
            <Col xs={12}>
              <Campo id="cxp-concepto" etiqueta="Concepto" error={errores.concepto}>
                <Form.Control maxLength={300} value={datos.concepto || ''} onChange={(e) => cambiar('concepto', e.target.value)} />
              </Campo>
            </Col>
          </Row>

          <h3 className="h6 mt-4 mb-2">Imputación (cargo)</h3>
          {errores.lineas && <Alert variant="danger" className="small py-2">{errores.lineas}</Alert>}
          <Table size="sm" className="align-middle">
            <thead className="table-light">
              <tr>
                <th style={{ width: '32%' }}>Cuenta</th>
                <th style={{ width: '22%' }}>Centro de costo</th>
                <th>Descripción</th>
                <th className="text-end" style={{ width: '14%' }}>
                  Monto
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {lineas.map((l, i) => (
                <tr key={i}>
                  <td>
                    <SelectorCuenta id={`cxp-cuenta-${i}`} cuentas={catalogos.imputables} valor={l.cuenta} onChange={(c) => cambiarLinea(i, 'cuenta', c)} />
                  </td>
                  <td>
                    <Form.Select size="sm" aria-label="Centro de costo" value={l.centro_costo} onChange={(e) => cambiarLinea(i, 'centro_costo', e.target.value)}>
                      <option value="">Según regla / no aplica</option>
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
            <tfoot>
              <tr>
                <td colSpan={3}>
                  <Button variant="outline-secondary" size="sm" onClick={() => setLineas((ls) => [...ls, LINEA_VACIA()])}>
                    <i className="bi bi-plus-lg me-1" /> Agregar línea
                  </Button>
                </td>
                <td className="monto fw-semibold">{centavosATexto(total)}</td>
                <td />
              </tr>
            </tfoot>
          </Table>
          <div className="small text-suave">
            <i className="bi bi-info-circle me-1" />
            Al guardar se contabiliza el asiento: cargo a estas líneas y abono a la cuenta por pagar por el total. Si una línea de gasto no
            trae centro, se aplica la regla de asignación del proveedor o de la cuenta.
          </div>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={onHide}>
            Cancelar
          </Button>
          <Button type="submit" disabled={guardando}>
            {guardando && <Spinner animation="border" size="sm" className="me-2" />}
            Registrar y contabilizar
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  )
}

/** Confirmación con motivo (anular documento o pago). */
function AnularModal({ show, titulo, texto, onHide, onConfirmar }) {
  const [motivo, setMotivo] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    if (show) {
      setMotivo('')
      setError('')
    }
  }, [show])

  const confirmar = async () => {
    setEnviando(true)
    const err = await onConfirmar(motivo)
    setEnviando(false)
    if (err) setError(err)
  }

  return (
    <Modal show={show} onHide={onHide} centered>
      <Modal.Header closeButton>
        <Modal.Title as="h2" className="h5">
          {titulo}
        </Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p className="small">{texto}</p>
        {error && <Alert variant="danger">{error}</Alert>}
        <Form.Group controlId="anular-motivo">
          <Form.Label>Motivo</Form.Label>
          <Form.Control maxLength={300} value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus />
        </Form.Group>
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onHide}>
          Cancelar
        </Button>
        <Button variant="danger" disabled={!motivo.trim() || enviando} onClick={confirmar}>
          Anular
        </Button>
      </Modal.Footer>
    </Modal>
  )
}

/** Detalle del documento: imputación, pagos y acciones. */
function DetalleModal({ id, puedeEditar, bancos, onHide, onCambio }) {
  const [cxp, setCxp] = useState(null)
  const [error, setError] = useState('')
  const [pago, setPago] = useState(null)
  const [erroresPago, setErroresPago] = useState({})
  const [anular, setAnular] = useState(null) // {tipo: 'documento'} | {tipo: 'pago', pago}
  const [programando, setProgramando] = useState(null) // fecha en edición (texto) o null

  const cargar = useCallback(async () => {
    const resp = await api(`/api/cuentas-por-pagar/${id}/`)
    if (!resp.ok) return setError(await mensajeError(resp))
    setCxp(await resp.json())
  }, [id])

  useEffect(() => {
    setCxp(null)
    setPago(null)
    setProgramando(null)
    setError('')
    if (id) cargar()
  }, [id, cargar])

  const actualizar = (datos) => {
    setCxp(datos)
    setError('')
    onCambio()
  }

  const nuevoPago = () => {
    setErroresPago({})
    setPago({ fecha: hoyISO(), monto: cxp.saldo, cuenta_banco: bancos[0]?.id || '', referencia: '' })
  }

  const guardarPago = async (e) => {
    e.preventDefault()
    if (Number.isNaN(aCentavos(pago.monto)) || !pago.monto) return setErroresPago({ monto: 'Monto inválido.' })
    const resp = await api(`/api/cuentas-por-pagar/${id}/pagos/`, { method: 'POST', body: { ...pago, monto: String(pago.monto).replace(/,/g, '') } })
    if (!resp.ok) return setErroresPago(await erroresDe(resp))
    setPago(null)
    actualizar(await resp.json())
  }

  const confirmarAnulacion = async (motivo) => {
    const url = anular.tipo === 'documento' ? `/api/cuentas-por-pagar/${id}/anular/` : `/api/cuentas-por-pagar/${id}/pagos/${anular.pago.id}/anular/`
    const resp = await api(url, { method: 'POST', body: { motivo } })
    if (!resp.ok) return mensajeError(resp)
    setAnular(null)
    actualizar(await resp.json())
    return null
  }

  const programar = async (fechaPago) => {
    const resp = await api(`/api/cuentas-por-pagar/${id}/programar/`, { method: 'POST', body: { fecha_pago_programada: fechaPago || null } })
    if (!resp.ok) return setError(await mensajeError(resp))
    setProgramando(null)
    actualizar(await resp.json())
  }

  const conSaldo = cxp && ['PENDIENTE', 'PARCIAL'].includes(cxp.estado)
  const pagosVigentes = cxp?.pagos.some((p) => p.estado === 'VIGENTE')

  return (
    <>
      <Modal show={Boolean(id) && !anular} onHide={onHide} size="lg" centered>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            {cxp ? `${cxp.tipo_documento_display} ${cxp.numero_documento}` : 'Documento por pagar'}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {error && <Alert variant="danger">{error}</Alert>}
          {!cxp ? (
            <Spinner animation="border" />
          ) : (
            <>
              <Row className="g-3 small mb-3">
                <Col md={6}>
                  <div className="text-suave">Proveedor</div>
                  <div className="fw-semibold">{cxp.proveedor.nombre}</div>
                  <div className="text-suave">NIT {cxp.proveedor.nit}</div>
                </Col>
                <Col xs={6} md={3}>
                  <div className="text-suave">Emisión</div>
                  <div>{formatoFecha(cxp.fecha_emision)}</div>
                </Col>
                <Col xs={6} md={3}>
                  <div className="text-suave">Vencimiento</div>
                  <div>{formatoFecha(cxp.fecha_vencimiento)}</div>
                  <InsigniaVencimiento vencimiento={cxp.vencimiento} dias={cxp.dias} />
                </Col>
                {conSaldo && (
                  <Col xs={12}>
                    <div className="d-flex flex-wrap align-items-center gap-2 p-2 rounded bg-body-tertiary">
                      <i className="bi bi-calendar-event text-suave" />
                      <span className="text-suave">Pago programado:</span>
                      {programando !== null ? (
                        <>
                          <Form.Control
                            type="date"
                            size="sm"
                            style={{ width: 'auto' }}
                            aria-label="Fecha de pago programada"
                            value={programando}
                            min={cxp.fecha_emision}
                            onChange={(e) => setProgramando(e.target.value)}
                          />
                          <Button size="sm" disabled={!programando} onClick={() => programar(programando)}>
                            Guardar
                          </Button>
                          <Button size="sm" variant="link" onClick={() => setProgramando(null)}>
                            Cancelar
                          </Button>
                        </>
                      ) : (
                        <>
                          <strong>{cxp.fecha_pago_programada ? formatoFecha(cxp.fecha_pago_programada) : 'según vencimiento'}</strong>
                          {puedeEditar && (
                            <>
                              <Button size="sm" variant="link" className="p-0" onClick={() => setProgramando(cxp.fecha_pago_programada || cxp.fecha_vencimiento)}>
                                {cxp.fecha_pago_programada ? 'Cambiar' : 'Programar'}
                              </Button>
                              {cxp.fecha_pago_programada && (
                                <Button size="sm" variant="link" className="p-0 text-danger" onClick={() => programar(null)}>
                                  Quitar
                                </Button>
                              )}
                            </>
                          )}
                          <span className="small text-suave ms-auto">Fecha que usa la proyección de egresos.</span>
                        </>
                      )}
                    </div>
                  </Col>
                )}
                <Col md={6}>
                  <div className="text-suave">Concepto</div>
                  <div>{cxp.concepto}</div>
                </Col>
                <Col xs={4} md={2}>
                  <div className="text-suave">Total</div>
                  <div className="monto text-start">{formatoMonto(cxp.monto_total)}</div>
                </Col>
                <Col xs={4} md={2}>
                  <div className="text-suave">Saldo</div>
                  <div className="monto text-start fw-semibold">{formatoMonto(cxp.saldo)}</div>
                </Col>
                <Col xs={4} md={2}>
                  <div className="text-suave">Estado</div>
                  <InsigniaEstado estado={cxp.estado} texto={cxp.estado_display} />
                </Col>
                <Col xs={12}>
                  <span className="text-suave">Asiento de registro: </span>
                  <Link to={`/asientos/${cxp.asiento.id}`}>{cxp.asiento.codigo}</Link>
                  <span className="text-suave"> · contra {cxp.cuenta_pasivo.codigo} {cxp.cuenta_pasivo.nombre}</span>
                  {cxp.asiento_anulacion && (
                    <>
                      <span className="text-suave"> · anulado con </span>
                      <Link to={`/asientos/${cxp.asiento_anulacion.id}`}>{cxp.asiento_anulacion.codigo}</Link>
                      <span className="text-suave"> ({cxp.motivo_anulacion})</span>
                    </>
                  )}
                </Col>
              </Row>

              <h3 className="h6">Imputación</h3>
              <Table size="sm" className="mb-3">
                <tbody>
                  {cxp.lineas.map((l, i) => (
                    <tr key={i} className="small">
                      <td>
                        <code className="me-1">{l.cuenta.codigo}</code>
                        {l.cuenta.nombre}
                      </td>
                      <td>{l.centro_costo ? `${l.centro_costo.codigo} ${l.centro_costo.nombre}` : <span className="text-suave">—</span>}</td>
                      <td className="text-suave">{l.descripcion}</td>
                      <td className="monto">{formatoMonto(l.monto)}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>

              <div className="d-flex justify-content-between align-items-center mb-2">
                <h3 className="h6 mb-0">Pagos</h3>
                {puedeEditar && conSaldo && !pago && (
                  <Button size="sm" onClick={nuevoPago}>
                    <i className="bi bi-cash-coin me-1" /> Registrar pago
                  </Button>
                )}
              </div>
              {pago && (
                <Card body className="mb-3 bg-body-tertiary">
                  <Form onSubmit={guardarPago} noValidate>
                    {Object.entries(erroresPago)
                      .filter(([c]) => !['fecha', 'monto', 'cuenta_banco', 'referencia'].includes(c))
                      .map(([c, m]) => (
                        <Alert key={c} variant="danger" className="py-2 small">
                          {m}
                        </Alert>
                      ))}
                    <Row className="g-2 align-items-end">
                      <Col md={3}>
                        <Campo id="pago-fecha" etiqueta="Fecha" error={erroresPago.fecha}>
                          <Form.Control size="sm" type="date" value={pago.fecha} onChange={(e) => setPago({ ...pago, fecha: e.target.value })} />
                        </Campo>
                      </Col>
                      <Col md={3}>
                        <Campo id="pago-monto" etiqueta={`Monto (saldo ${formatoMonto(cxp.saldo)})`} error={erroresPago.monto}>
                          <Form.Control size="sm" inputMode="decimal" className="text-end" value={pago.monto} onChange={(e) => setPago({ ...pago, monto: e.target.value })} />
                        </Campo>
                      </Col>
                      <Col md={6}>
                        <Campo id="pago-banco" etiqueta="Pagado desde" error={erroresPago.cuenta_banco}>
                          <Form.Select size="sm" value={pago.cuenta_banco} onChange={(e) => setPago({ ...pago, cuenta_banco: e.target.value })}>
                            <option value="">Seleccione…</option>
                            {bancos.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.codigo} · {c.nombre}
                              </option>
                            ))}
                          </Form.Select>
                        </Campo>
                      </Col>
                      <Col md={6}>
                        <Campo id="pago-referencia" etiqueta="Referencia (cheque, transferencia)" error={erroresPago.referencia}>
                          <Form.Control size="sm" maxLength={60} value={pago.referencia} onChange={(e) => setPago({ ...pago, referencia: e.target.value })} />
                        </Campo>
                      </Col>
                      <Col md={6} className="text-end">
                        <Button size="sm" variant="secondary" className="me-2" onClick={() => setPago(null)}>
                          Cancelar
                        </Button>
                        <Button size="sm" type="submit">
                          Registrar y contabilizar
                        </Button>
                      </Col>
                    </Row>
                  </Form>
                </Card>
              )}
              {cxp.pagos.length === 0 ? (
                <div className="small text-suave mb-2">Sin pagos registrados.</div>
              ) : (
                <Table size="sm" className="align-middle">
                  <thead className="table-light">
                    <tr className="small">
                      <th>Fecha</th>
                      <th>Desde</th>
                      <th>Referencia</th>
                      <th>Asiento</th>
                      <th className="text-end">Monto</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {cxp.pagos.map((p) => (
                      <tr key={p.id} className={`small ${p.estado === 'ANULADO' ? 'text-suave text-decoration-line-through' : ''}`}>
                        <td>{formatoFecha(p.fecha)}</td>
                        <td>
                          <code>{p.cuenta_banco.codigo}</code> {p.cuenta_banco.nombre}
                        </td>
                        <td>{p.referencia}</td>
                        <td>
                          <Link to={`/asientos/${p.asiento.id}`}>{p.asiento.codigo}</Link>
                          {p.asiento_anulacion && (
                            <>
                              {' '}
                              → <Link to={`/asientos/${p.asiento_anulacion.id}`}>{p.asiento_anulacion.codigo}</Link>
                            </>
                          )}
                        </td>
                        <td className="monto">{formatoMonto(p.monto)}</td>
                        <td className="text-end">
                          {p.estado === 'VIGENTE' && puedeEditar ? (
                            <Button size="sm" variant="link" className="text-danger p-0" onClick={() => setAnular({ tipo: 'pago', pago: p })}>
                              Anular
                            </Button>
                          ) : (
                            p.estado === 'ANULADO' && <Badge bg="secondary-subtle" text="secondary-emphasis">Anulado</Badge>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </>
          )}
        </Modal.Body>
        <Modal.Footer className="justify-content-between">
          <div>
            {puedeEditar && cxp && cxp.estado !== 'ANULADA' && (
              <Button
                variant="outline-danger"
                size="sm"
                disabled={pagosVigentes}
                title={pagosVigentes ? 'Anule primero los pagos' : ''}
                onClick={() => setAnular({ tipo: 'documento' })}
              >
                Anular documento
              </Button>
            )}
          </div>
          <Button variant="secondary" onClick={onHide}>
            Cerrar
          </Button>
        </Modal.Footer>
      </Modal>
      <AnularModal
        show={Boolean(anular)}
        titulo={anular?.tipo === 'documento' ? 'Anular documento' : 'Anular pago'}
        texto={
          anular?.tipo === 'documento'
            ? 'Se registrará la reversión del asiento del documento. El documento queda anulado y no admite pagos.'
            : `Se registrará la reversión del asiento del pago y ${anular?.pago ? formatoMonto(anular.pago.monto) : ''} volverá al saldo.`
        }
        onHide={() => setAnular(null)}
        onConfirmar={confirmarAnulacion}
      />
    </>
  )
}

export default function CuentasPorPagar() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR, ROLES.TESORERO)

  const [filtros, setFiltros] = useState({ proveedor: '', estado: 'CON_SALDO', vencimiento: '', q: '', fecha: hoyISO() })
  const [busqueda, setBusqueda] = useState('')
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState(null)
  const [resumen, setResumen] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [catalogos, setCatalogos] = useState({ proveedores: [], pasivos: [], bancos: [], imputables: [], centros: [] })
  const [registro, setRegistro] = useState(false)
  const [params, setParams] = useSearchParams()
  const [detalle, setDetalleId] = useState(() => params.get('documento'))
  // El documento abierto queda en la URL (?documento=) para poder enlazarlo, p. ej. desde la proyección.
  const setDetalle = (id) => {
    setDetalleId(id)
    setParams(id ? { documento: id } : {}, { replace: true })
  }

  const cargar = useCallback(async () => {
    const q = new URLSearchParams({ page: pagina })
    Object.entries(filtros).forEach(([k, v]) => v && q.set(k, v))
    const [resp, resp2] = await Promise.all([api(`/api/cuentas-por-pagar/?${q}`), api(`/api/cuentas-por-pagar/resumen/?fecha=${filtros.fecha}`)])
    if (!resp.ok) {
      setDatos({ count: 0, results: [] })
      return setError(await mensajeError(resp))
    }
    setDatos(await resp.json())
    if (resp2.ok) setResumen(await resp2.json())
  }, [filtros, pagina])

  useEffect(() => {
    cargar()
  }, [cargar])

  useEffect(() => {
    Promise.all([
      apiTodas('/api/proveedores/?activo=true'),
      api('/api/cuentas/arbol/').then((r) => (r.ok ? r.json() : [])),
      api('/api/centros-costo/arbol/').then((r) => (r.ok ? r.json() : [])),
    ]).then(([proveedores, cuentas, centros]) => {
      const detalle = (n) => n.acepta_movimientos && n.activa
      const simple = (n) => ({ id: n.id, codigo: n.codigo, nombre: n.nombre })
      const efectivo = aplanar(cuentas, (n) => detalle(n) && n.tipo === 'ACTIVO' && n.exenta_centro_costo)
      const fondos = efectivo.filter((n) => n.codigo.startsWith('11'))
      setCatalogos({
        proveedores,
        pasivos: aplanar(cuentas, (n) => detalle(n) && n.tipo === 'PASIVO' && n.exenta_centro_costo).map(simple),
        // Fondos disponibles (grupo 11 del catálogo base); si el catálogo no lo usa, todo activo exento.
        bancos: (fondos.length ? fondos : efectivo).map(simple),
        imputables: aplanar(cuentas, (n) => detalle(n) && ['GASTO', 'ACTIVO'].includes(n.tipo)).map(simple),
        centros: aplanar(centros, (n) => n.acepta_movimientos && (!n.vigente_hasta || n.vigente_hasta >= hoyISO())),
      })
    })
  }, [])

  const filtrar = (cambios) => {
    setPagina(1)
    setFiltros((f) => ({ ...f, ...cambios }))
  }

  const alRegistrar = (cxp) => {
    setRegistro(false)
    setError('')
    setAviso(`${cxp.tipo_documento_display} ${cxp.numero_documento} registrada (asiento ${cxp.asiento.codigo}).`)
    cargar()
    setDetalle(cxp.id)
  }

  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.count / TAMANO_PAGINA)) : 1

  return (
    <>
      <EncabezadoPagina
        titulo="Cuentas por pagar"
        descripcion="Compromisos con proveedores y sus vencimientos. Cada documento y cada pago se contabilizan automáticamente."
        migas={[{ texto: 'Tesorería' }, { texto: 'Cuentas por pagar' }]}
      >
        {puedeEditar && (
          <Button onClick={() => setRegistro(true)}>
            <i className="bi bi-plus-lg me-1" /> Registrar documento
          </Button>
        )}
      </EncabezadoPagina>

      {resumen && (
        <Row className="g-3 mb-3">
          <Col xs={6} lg={3}>
            <Card className="h-100">
              <Card.Body>
                <div className="small text-suave">Saldo pendiente</div>
                <div className="fs-5 fw-semibold">{formatoMonto(resumen.pendiente)}</div>
                <div className="small text-suave">{resumen.documentos.total} documento(s)</div>
              </Card.Body>
            </Card>
          </Col>
          <Col xs={6} lg={3}>
            <Card className="h-100 border-danger-subtle" role="button" onClick={() => filtrar({ vencimiento: 'VENCIDA' })}>
              <Card.Body>
                <div className="small text-suave">Vencido</div>
                <div className={`fs-5 fw-semibold ${Number(resumen.vencido) ? 'text-danger' : ''}`}>{formatoMonto(resumen.vencido)}</div>
                <div className="small text-suave">{resumen.documentos.vencidos} documento(s)</div>
              </Card.Body>
            </Card>
          </Col>
          <Col xs={6} lg={3}>
            <Card className="h-100" role="button" onClick={() => filtrar({ vencimiento: 'POR_VENCER' })}>
              <Card.Body>
                <div className="small text-suave">Vence en {resumen.dias_por_vencer} días</div>
                <div className={`fs-5 fw-semibold ${Number(resumen.por_vencer) ? 'text-warning-emphasis' : ''}`}>{formatoMonto(resumen.por_vencer)}</div>
                <div className="small text-suave">{resumen.documentos.por_vencer} documento(s)</div>
              </Card.Body>
            </Card>
          </Col>
          <Col xs={6} lg={3}>
            <Card className="h-100">
              <Card.Body className="py-2">
                <div className="small text-suave mb-1">Antigüedad de saldos vencidos</div>
                {resumen.antiguedad.map((a) => (
                  <div key={a.tramo} className="d-flex justify-content-between small">
                    <span>{TRAMOS[a.tramo]}</span>
                    <span className={`monto ${Number(a.monto) ? 'text-danger' : 'text-suave'}`}>{formatoMonto(a.monto)}</span>
                  </div>
                ))}
              </Card.Body>
            </Card>
          </Col>
        </Row>
      )}

      <Card className="mb-3">
        <Card.Body>
          <Form
            onSubmit={(e) => {
              e.preventDefault()
              filtrar({ q: busqueda.trim() })
            }}
          >
            <Row className="g-2 align-items-end">
              <Col xs={12} md={3}>
                <Form.Label htmlFor="f-proveedor" className="small text-suave mb-1">
                  Proveedor
                </Form.Label>
                <Form.Select id="f-proveedor" size="sm" value={filtros.proveedor} onChange={(e) => filtrar({ proveedor: e.target.value })}>
                  <option value="">Todos</option>
                  {catalogos.proveedores.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre}
                    </option>
                  ))}
                </Form.Select>
              </Col>
              <Col xs={6} md={2}>
                <Form.Label htmlFor="f-estado" className="small text-suave mb-1">
                  Estado
                </Form.Label>
                <Form.Select id="f-estado" size="sm" value={filtros.estado} onChange={(e) => filtrar({ estado: e.target.value })}>
                  <option value="CON_SALDO">Con saldo</option>
                  <option value="">Todos</option>
                  <option value="PENDIENTE">Pendientes</option>
                  <option value="PARCIAL">Pago parcial</option>
                  <option value="PAGADA">Pagadas</option>
                  <option value="ANULADA">Anuladas</option>
                </Form.Select>
              </Col>
              <Col xs={6} md={2}>
                <Form.Label htmlFor="f-vencimiento" className="small text-suave mb-1">
                  Vencimiento
                </Form.Label>
                <Form.Select id="f-vencimiento" size="sm" value={filtros.vencimiento} onChange={(e) => filtrar({ vencimiento: e.target.value })}>
                  <option value="">Todos</option>
                  <option value="VENCIDA">Vencidas</option>
                  <option value="POR_VENCER">Por vencer</option>
                  <option value="AL_DIA">Al día</option>
                </Form.Select>
              </Col>
              <Col xs={6} md={2}>
                <Form.Label htmlFor="f-fecha" className="small text-suave mb-1">
                  A la fecha
                </Form.Label>
                <Form.Control id="f-fecha" size="sm" type="date" value={filtros.fecha} onChange={(e) => e.target.value && filtrar({ fecha: e.target.value })} />
              </Col>
              <Col xs={6} md={2}>
                <Form.Label htmlFor="f-buscar" className="small text-suave mb-1">
                  Buscar
                </Form.Label>
                <Form.Control id="f-buscar" size="sm" placeholder="Número o concepto" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
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
          <div className="text-suave small mb-2">{datos.count} documento(s)</div>
          <Card className="mb-3">
            <div className="table-responsive">
              <Table hover className="align-middle mb-0">
                <thead>
                  <tr>
                    <th>Proveedor</th>
                    <th>Documento</th>
                    <th>Emisión</th>
                    <th>Vencimiento</th>
                    <th className="text-end">Total</th>
                    <th className="text-end">Saldo</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.results.map((c) => (
                    <tr key={c.id} role="button" onClick={() => setDetalle(c.id)} className={c.estado === 'ANULADA' ? 'text-suave' : ''}>
                      <td>{c.proveedor.nombre}</td>
                      <td>
                        <span className="small text-suave">{c.tipo_documento_display}</span>
                        <div>
                          <code>{c.numero_documento}</code>
                        </div>
                      </td>
                      <td className="small">{formatoFecha(c.fecha_emision)}</td>
                      <td>
                        <div className="small">{formatoFecha(c.fecha_vencimiento)}</div>
                        <InsigniaVencimiento vencimiento={c.vencimiento} dias={c.dias} />
                        {c.fecha_pago_programada && c.vencimiento && (
                          <div className="small text-suave" title="Fecha de pago programada">
                            <i className="bi bi-calendar-event me-1" />
                            pago {formatoFecha(c.fecha_pago_programada)}
                          </div>
                        )}
                      </td>
                      <td className="monto">{formatoMonto(c.monto_total)}</td>
                      <td className="monto fw-semibold">{formatoMonto(c.saldo)}</td>
                      <td>
                        <InsigniaEstado estado={c.estado} texto={c.estado_display} />
                      </td>
                    </tr>
                  ))}
                  {datos.results.length === 0 && (
                    <tr>
                      <td colSpan={7}>
                        <EstadoVacio icono="bi-receipt">No hay documentos que coincidan.</EstadoVacio>
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

      <RegistroModal show={registro} catalogos={catalogos} onHide={() => setRegistro(false)} onGuardado={alRegistrar} />
      <DetalleModal id={detalle} puedeEditar={puedeEditar} bancos={catalogos.bancos} onHide={() => setDetalle(null)} onCambio={cargar} />
    </>
  )
}
