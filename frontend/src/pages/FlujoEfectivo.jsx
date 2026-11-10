import { Fragment, useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Row, Spinner, Tab, Table, Tabs } from 'react-bootstrap'
import { useSearchParams } from 'react-router-dom'
import { api, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import SelectorCuenta from '../components/SelectorCuenta'
import { Monto } from '../components/reportes/ReporteSegmentado'
import { descargarCSV } from '../exportar'
import { aCentavos, formatoFecha, formatoMonto, hoyISO } from '../formato'

const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
const NIVEL = {
  CRITICA: { variant: 'danger', icono: 'bi-exclamation-octagon' },
  ADVERTENCIA: { variant: 'warning', icono: 'bi-exclamation-triangle' },
  INFORMATIVA: { variant: 'info', icono: 'bi-info-circle' },
}
const ESTADO_SEMANA = {
  DEFICIT: { clase: 'text-danger fw-semibold', fila: 'table-danger', texto: 'Déficit' },
  BAJO_MINIMO: { clase: 'text-warning-emphasis fw-semibold', fila: 'table-warning', texto: 'Bajo el mínimo' },
  OK: { clase: '', fila: '', texto: '' },
}
const COLOR_ACTIVIDAD = { EFECTIVO: 'success', OPERACION: 'primary', INVERSION: 'info', FINANCIAMIENTO: 'secondary' }

const inicioDeAnio = () => `${new Date().getFullYear()}-01-01`

/** Mensaje cuando falta configurar las cuentas de efectivo, con acceso a la pestaña de configuración. */
function ErrorFlujo({ error, irAConfiguracion }) {
  if (!error) return null
  return (
    <Alert variant="warning">
      {error}
      {error.includes('efectivo configuradas') && (
        <div className="mt-2">
          <Button size="sm" variant="outline-dark" onClick={irAConfiguracion}>
            Ir a Configuración
          </Button>
        </div>
      )}
    </Alert>
  )
}

// =============================================================================
// Proyectado
// =============================================================================

function Proyectado({ irAConfiguracion }) {
  const [fecha, setFecha] = useState(hoyISO())
  const [entradas, setEntradas] = useState('historico')
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  const consultar = useCallback(async () => {
    setCargando(true)
    const resp = await api(`/api/tesoreria/flujo-proyectado/?fecha=${fecha}&entradas=${entradas}`)
    setCargando(false)
    if (!resp.ok) {
      setDatos(null)
      return setError(await mensajeError(resp))
    }
    setError('')
    setDatos(await resp.json())
  }, [fecha, entradas])

  useEffect(() => {
    consultar()
  }, [consultar])

  const exportar = () =>
    descargarCSV(
      `flujo_proyectado_${datos.fecha}.csv`,
      ['Semana', 'Desde', 'Hasta', 'Saldo inicial', 'Entradas estimadas', 'Salidas comprometidas', 'Saldo final', 'Estado'],
      datos.semanas.map((s) => [s.semana, s.desde, s.hasta, s.saldo_inicial, s.entradas, s.salidas, s.saldo_final, ESTADO_SEMANA[s.estado].texto]),
    )

  return (
    <>
      <Card className="mb-3 no-imprimir">
        <Card.Body>
          <Row className="g-2 align-items-end">
            <Col xs={6} md={3}>
              <Form.Label htmlFor="proy-fecha" className="small text-suave mb-1">
                Saldo al
              </Form.Label>
              <Form.Control id="proy-fecha" size="sm" type="date" value={fecha} onChange={(e) => e.target.value && setFecha(e.target.value)} />
            </Col>
            <Col xs={6} md={4}>
              <Form.Label htmlFor="proy-entradas" className="small text-suave mb-1">
                Entradas
              </Form.Label>
              <Form.Select id="proy-entradas" size="sm" value={entradas} onChange={(e) => setEntradas(e.target.value)}>
                <option value="historico">Estimadas por el promedio histórico</option>
                <option value="ninguna">Sin entradas (solo compromisos, conservador)</option>
              </Form.Select>
            </Col>
            <Col className="text-end">
              <Button size="sm" variant="outline-secondary" className="me-2" disabled={!datos} onClick={exportar}>
                <i className="bi bi-filetype-csv me-1" /> CSV
              </Button>
              <Button size="sm" variant="outline-secondary" disabled={!datos} onClick={() => window.print()}>
                <i className="bi bi-printer me-1" /> Imprimir
              </Button>
            </Col>
          </Row>
        </Card.Body>
      </Card>

      <ErrorFlujo error={error} irAConfiguracion={irAConfiguracion} />
      {cargando && <Spinner animation="border" />}

      {datos && !cargando && (
        <>
          <div className="encabezado-reporte">
            <strong>Flujo de efectivo proyectado</strong> · saldo al {formatoFecha(datos.fecha)} · 13 semanas
          </div>

          {datos.alertas.length === 0 ? (
            <Alert variant="success" className="d-flex align-items-center gap-2">
              <i className="bi bi-check-circle" /> Sin déficit proyectado: el saldo se mantiene por encima del mínimo ({formatoMonto(datos.saldo_minimo)}) en
              las próximas 13 semanas.
            </Alert>
          ) : (
            datos.alertas.map((a, i) => (
              <Alert key={i} variant={NIVEL[a.nivel].variant} className="d-flex align-items-start gap-2">
                <i className={`bi ${NIVEL[a.nivel].icono} mt-1`} />
                <span>{a.mensaje}</span>
              </Alert>
            ))
          )}

          <Row className="g-3 mb-3">
            <Col xs={6} lg={3}>
              <Card className="h-100">
                <Card.Body>
                  <div className="small text-suave">Saldo de efectivo actual</div>
                  <div className="fs-5 fw-semibold">
                    <Monto valor={datos.saldo_actual} alertar />
                  </div>
                  <div className="small text-suave">Mínimo de política: {formatoMonto(datos.saldo_minimo)}</div>
                </Card.Body>
              </Card>
            </Col>
            {['30', '60', '90'].map((d) => (
              <Col xs={6} lg={3} key={d}>
                <Card className="h-100">
                  <Card.Body>
                    <div className="small text-suave">Saldo proyectado a {d} días</div>
                    <div className={`fs-5 fw-semibold ${Number(datos.saldo_proyectado[d]) < Number(datos.saldo_minimo) ? 'text-warning-emphasis' : ''}`}>
                      <Monto valor={datos.saldo_proyectado[d]} alertar />
                    </div>
                  </Card.Body>
                </Card>
              </Col>
            ))}
          </Row>

          <Card className="mb-3">
            <Card.Header className="fw-semibold">Semana a semana</Card.Header>
            <div className="table-responsive">
              <Table size="sm" className="tabla-matriz align-middle mb-0">
                <thead className="table-light">
                  <tr>
                    <th>Semana</th>
                    <th className="text-end">Saldo inicial</th>
                    <th className="text-end">(+) Entradas estimadas</th>
                    <th className="text-end">(−) Salidas comprometidas</th>
                    <th className="text-end">Saldo final</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {datos.semanas.map((s) => {
                    const e = ESTADO_SEMANA[s.estado]
                    return (
                      <tr key={s.semana} className={e.fila}>
                        <td className="small text-nowrap">
                          {s.semana}. {formatoFecha(s.desde).slice(0, 5)} – {formatoFecha(s.hasta).slice(0, 5)}
                        </td>
                        <td className="monto">
                          <Monto valor={s.saldo_inicial} alertar />
                        </td>
                        <td className="monto">{formatoMonto(s.entradas)}</td>
                        <td className="monto">{formatoMonto(s.salidas)}</td>
                        <td className={`monto ${e.clase}`}>
                          <Monto valor={s.saldo_final} alertar />
                        </td>
                        <td className="small">{e.texto}</td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot className="table-light">
                  <tr className="fila-subtotal">
                    <td>Total 13 semanas</td>
                    <td />
                    <td className="monto">{formatoMonto(datos.total_entradas)}</td>
                    <td className="monto">{formatoMonto(datos.total_salidas)}</td>
                    <td className="monto">
                      <Monto valor={datos.semanas[datos.semanas.length - 1].saldo_final} alertar />
                    </td>
                    <td />
                  </tr>
                </tfoot>
              </Table>
            </div>
          </Card>
          <div className="small text-suave mb-4 no-imprimir">
            <i className="bi bi-info-circle me-1" />
            Salidas: cuentas por pagar (fecha programada o vencimiento; las vencidas, en la semana 1) y egresos programados (ver Proyección de
            egresos). Entradas: promedio diario de las entradas de operación de los últimos {datos.base_historica.dias} días (
            {formatoMonto(datos.base_historica.entradas_operacion)} → {formatoMonto(datos.entradas_diarias)} por día).
          </div>
        </>
      )}
    </>
  )
}

// =============================================================================
// Real del periodo
// =============================================================================

function Real({ irAConfiguracion }) {
  const [rango, setRango] = useState({ desde: inicioDeAnio(), hasta: hoyISO() })
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  const consultar = useCallback(async (r) => {
    setCargando(true)
    const resp = await api(`/api/tesoreria/flujo-efectivo/?desde=${r.desde}&hasta=${r.hasta}`)
    setCargando(false)
    if (!resp.ok) {
      setDatos(null)
      return setError(await mensajeError(resp))
    }
    setError('')
    setDatos(await resp.json())
  }, [])

  useEffect(() => {
    consultar(rango)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [consultar])

  const exportar = () => {
    const filas = [['Saldo inicial', '', '', datos.saldo_inicial]]
    datos.actividades.forEach((a) => {
      filas.push([`Actividades de ${a.nombre.toLowerCase()}`, a.entradas, a.salidas, a.neto])
      a.filas.forEach((f) => filas.push([`   ${f.cuenta.codigo} ${f.cuenta.nombre}`, f.entradas, f.salidas, f.neto]))
    })
    filas.push(['Variación neta', datos.entradas, datos.salidas, datos.neto], ['Saldo final', '', '', datos.saldo_final])
    descargarCSV(`flujo_efectivo_${datos.desde}_${datos.hasta}.csv`, ['Concepto', 'Entradas', 'Salidas', 'Neto'], filas)
  }

  return (
    <>
      <Card className="mb-3 no-imprimir">
        <Card.Body>
          <Form
            onSubmit={(e) => {
              e.preventDefault()
              consultar(rango)
            }}
          >
            <Row className="g-2 align-items-end">
              <Col xs={6} md={3}>
                <Form.Label htmlFor="real-desde" className="small text-suave mb-1">
                  Desde
                </Form.Label>
                <Form.Control id="real-desde" size="sm" type="date" value={rango.desde} onChange={(e) => setRango({ ...rango, desde: e.target.value })} />
              </Col>
              <Col xs={6} md={3}>
                <Form.Label htmlFor="real-hasta" className="small text-suave mb-1">
                  Hasta
                </Form.Label>
                <Form.Control id="real-hasta" size="sm" type="date" value={rango.hasta} onChange={(e) => setRango({ ...rango, hasta: e.target.value })} />
              </Col>
              <Col xs="auto">
                <Button type="submit" size="sm" variant="outline-primary">
                  <i className="bi bi-search me-1" /> Consultar
                </Button>
              </Col>
              <Col className="text-end">
                <Button size="sm" variant="outline-secondary" className="me-2" disabled={!datos} onClick={exportar}>
                  <i className="bi bi-filetype-csv me-1" /> CSV
                </Button>
                <Button size="sm" variant="outline-secondary" disabled={!datos} onClick={() => window.print()}>
                  <i className="bi bi-printer me-1" /> Imprimir
                </Button>
              </Col>
            </Row>
          </Form>
        </Card.Body>
      </Card>

      <ErrorFlujo error={error} irAConfiguracion={irAConfiguracion} />
      {cargando && <Spinner animation="border" />}

      {datos && !cargando && (
        <>
          <div className="encabezado-reporte">
            <strong>Estado de flujos de efectivo (método directo)</strong> · del {formatoFecha(datos.desde)} al {formatoFecha(datos.hasta)}
          </div>
          {!datos.cuadra && (
            <Alert variant="danger">
              El saldo final calculado ({formatoMonto(datos.saldo_final)}) no coincide con el saldo contable ({formatoMonto(datos.saldo_final_contable)}).
            </Alert>
          )}
          <Row className="g-3 mb-3">
            <Col lg={8}>
              <Card className="h-100">
                <div className="table-responsive">
                  <Table size="sm" className="tabla-matriz align-middle mb-0">
                    <thead className="table-light">
                      <tr>
                        <th>Concepto</th>
                        <th className="text-end">Entradas</th>
                        <th className="text-end">Salidas</th>
                        <th className="text-end">Neto</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="fila-subtotal">
                        <td>Saldo inicial de efectivo</td>
                        <td colSpan={2} />
                        <td className="monto">
                          <Monto valor={datos.saldo_inicial} alertar />
                        </td>
                      </tr>
                      {datos.actividades.map((a) => (
                        <Fragment key={a.actividad}>
                          <tr className="fila-subtotal table-light">
                            <td>
                              <strong>Actividades de {a.nombre.toLowerCase()}</strong>
                            </td>
                            <td className="monto">{formatoMonto(a.entradas)}</td>
                            <td className="monto">{formatoMonto(a.salidas)}</td>
                            <td className="monto">
                              <Monto valor={a.neto} alertar />
                            </td>
                          </tr>
                          {a.filas.map((f) => (
                            <tr key={f.cuenta.id} className="small">
                              <td className="ps-4">
                                <code className="me-2">{f.cuenta.codigo}</code>
                                {f.cuenta.nombre}
                              </td>
                              <td className="monto">{Number(f.entradas) ? formatoMonto(f.entradas) : <span className="text-suave">–</span>}</td>
                              <td className="monto">{Number(f.salidas) ? formatoMonto(f.salidas) : <span className="text-suave">–</span>}</td>
                              <td className="monto">
                                <Monto valor={f.neto} alertar />
                              </td>
                            </tr>
                          ))}
                          {a.filas.length === 0 && (
                            <tr className="small text-suave">
                              <td className="ps-4" colSpan={4}>
                                Sin movimientos.
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      ))}
                    </tbody>
                    <tfoot className="table-light">
                      <tr className="fila-subtotal">
                        <td>Variación neta del efectivo</td>
                        <td className="monto">{formatoMonto(datos.entradas)}</td>
                        <td className="monto">{formatoMonto(datos.salidas)}</td>
                        <td className="monto">
                          <Monto valor={datos.neto} alertar />
                        </td>
                      </tr>
                      <tr className="fila-resultado">
                        <td colSpan={3}>
                          Saldo final de efectivo
                          {datos.cuadra && <Badge bg="success-subtle" text="success-emphasis" className="ms-2 fw-normal">cuadra con la contabilidad</Badge>}
                        </td>
                        <td className="monto">
                          <Monto valor={datos.saldo_final} alertar />
                        </td>
                      </tr>
                    </tfoot>
                  </Table>
                </div>
              </Card>
            </Col>
            <Col lg={4}>
              <Card className="h-100">
                <Card.Header className="fw-semibold">Por mes</Card.Header>
                {datos.mensual.length === 0 ? (
                  <EstadoVacio icono="bi-cash-stack">Sin movimientos de efectivo en el rango.</EstadoVacio>
                ) : (
                  <Table size="sm" className="mb-0">
                    <thead className="table-light">
                      <tr className="small">
                        <th>Mes</th>
                        <th className="text-end">Entradas</th>
                        <th className="text-end">Salidas</th>
                        <th className="text-end">Neto</th>
                      </tr>
                    </thead>
                    <tbody>
                      {datos.mensual.map((m) => (
                        <tr key={`${m.anio}-${m.mes}`} className="small">
                          <td>
                            {MESES[m.mes - 1]} {m.anio}
                          </td>
                          <td className="monto">{formatoMonto(m.entradas)}</td>
                          <td className="monto">{formatoMonto(m.salidas)}</td>
                          <td className="monto">
                            <Monto valor={m.neto} alertar />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                )}
              </Card>
            </Col>
          </Row>
          <div className="small text-suave mb-4 no-imprimir">
            <i className="bi bi-info-circle me-1" />
            Cada movimiento de efectivo se clasifica por su contrapartida (Tabla 2 del documento base). Los traspasos entre cuentas de efectivo no
            son flujo.
          </div>
        </>
      )}
    </>
  )
}

// =============================================================================
// Configuración
// =============================================================================

function aplanar(arbol) {
  const lista = []
  const recorrer = (nodos) =>
    nodos.forEach((n) => {
      if (n.tipo !== 'ORDEN') lista.push({ id: n.id, codigo: n.codigo, nombre: n.nombre })
      recorrer(n.hijos)
    })
  recorrer(arbol)
  return lista
}

function Configuracion({ puedeEditar }) {
  const [config, setConfig] = useState(null)
  const [form, setForm] = useState({ saldo_minimo: '', dias_historia: '' })
  const [clasif, setClasif] = useState(null)
  const [cuentas, setCuentas] = useState([])
  const [nueva, setNueva] = useState({ cuenta: null, actividad: 'EFECTIVO' })
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')

  const cargar = useCallback(async () => {
    const [r1, r2] = await Promise.all([api('/api/tesoreria/configuracion/'), api('/api/tesoreria/clasificacion-flujo/')])
    if (r1.ok) {
      const c = await r1.json()
      setConfig(c)
      setForm({ saldo_minimo: c.saldo_minimo, dias_historia: String(c.dias_historia) })
    }
    if (r2.ok) setClasif(await r2.json())
  }, [])

  useEffect(() => {
    cargar()
    api('/api/cuentas/arbol/').then(async (r) => r.ok && setCuentas(aplanar(await r.json())))
  }, [cargar])

  const ok = (texto) => {
    setError('')
    setAviso(texto)
  }

  const guardarConfig = async (e) => {
    e.preventDefault()
    if (Number.isNaN(aCentavos(form.saldo_minimo))) return setError('Saldo mínimo inválido.')
    const resp = await api('/api/tesoreria/configuracion/', {
      method: 'PATCH',
      body: { saldo_minimo: String(form.saldo_minimo).replace(/,/g, '') || '0', dias_historia: Number(form.dias_historia) },
    })
    if (!resp.ok) return setError(await mensajeError(resp))
    setConfig(await resp.json())
    ok('Política de liquidez guardada.')
  }

  const asignar = async () => {
    const resp = await api('/api/tesoreria/clasificacion-flujo/', { method: 'POST', body: { cuenta: nueva.cuenta.id, actividad: nueva.actividad } })
    if (!resp.ok) return setError(await mensajeError(resp))
    setClasif(await resp.json())
    ok(`${nueva.cuenta.codigo} ${nueva.cuenta.nombre} clasificada.`)
    setNueva({ ...nueva, cuenta: null })
  }

  const quitar = async (a) => {
    const resp = await api(`/api/tesoreria/clasificacion-flujo/${a.id}/`, { method: 'DELETE' })
    if (!resp.ok) return setError(await mensajeError(resp))
    setClasif(await resp.json())
    ok(`${a.cuenta.codigo} vuelve a heredar su actividad.`)
  }

  if (!config || !clasif) return <Spinner animation="border" />

  return (
    <>
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
      <Row className="g-3">
        <Col lg={4}>
          <Card className="mb-3">
            <Card.Header className="fw-semibold">Política de liquidez</Card.Header>
            <Card.Body>
              <Form onSubmit={guardarConfig}>
                <Form.Group controlId="cfg-minimo" className="mb-3">
                  <Form.Label>Saldo mínimo de efectivo</Form.Label>
                  <Form.Control
                    inputMode="decimal"
                    className="text-end"
                    disabled={!puedeEditar}
                    value={form.saldo_minimo}
                    onChange={(e) => setForm({ ...form, saldo_minimo: e.target.value })}
                  />
                  <Form.Text>Por debajo se alerta "Bajo el mínimo".</Form.Text>
                </Form.Group>
                <Form.Group controlId="cfg-dias" className="mb-3">
                  <Form.Label>Días de historia para estimar entradas</Form.Label>
                  <Form.Control
                    type="number"
                    min="7"
                    max="730"
                    disabled={!puedeEditar}
                    value={form.dias_historia}
                    onChange={(e) => setForm({ ...form, dias_historia: e.target.value })}
                  />
                </Form.Group>
                {puedeEditar && (
                  <Button type="submit" size="sm">
                    Guardar
                  </Button>
                )}
                {config.modificado_por && (
                  <div className="small text-suave mt-2">
                    Último cambio: {config.modificado_por}, {new Date(config.modificado_en).toLocaleString('es-SV')}
                  </div>
                )}
              </Form>
            </Card.Body>
          </Card>
          <Card>
            <Card.Header className="fw-semibold">Cuentas de efectivo resultantes</Card.Header>
            {clasif.cuentas_efectivo.length === 0 ? (
              <EstadoVacio icono="bi-bank">
                Ninguna. Asigne «Efectivo y equivalentes» a caja y bancos (o ejecute <code>cargar_flujo_base</code>).
              </EstadoVacio>
            ) : (
              <Table size="sm" className="mb-0">
                <tbody>
                  {clasif.cuentas_efectivo.map((c) => (
                    <tr key={c.id} className="small">
                      <td>
                        <code className="me-2">{c.codigo}</code>
                        {c.nombre}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
        </Col>
        <Col lg={8}>
          <Card>
            <Card.Header className="fw-semibold">Clasificación de cuentas por actividad</Card.Header>
            {puedeEditar && (
              <Card.Body className="border-bottom">
                <Row className="g-2 align-items-end">
                  <Col md={6}>
                    <Form.Label htmlFor="clasif-cuenta" className="small text-suave mb-1">
                      Cuenta (cualquier nivel; la heredan sus subcuentas)
                    </Form.Label>
                    <SelectorCuenta id="clasif-cuenta" cuentas={cuentas} valor={nueva.cuenta} onChange={(c) => setNueva({ ...nueva, cuenta: c })} />
                  </Col>
                  <Col md={4}>
                    <Form.Label htmlFor="clasif-actividad" className="small text-suave mb-1">
                      Actividad
                    </Form.Label>
                    <Form.Select id="clasif-actividad" size="sm" value={nueva.actividad} onChange={(e) => setNueva({ ...nueva, actividad: e.target.value })}>
                      {clasif.actividades.map((a) => (
                        <option key={a.valor} value={a.valor}>
                          {a.nombre}
                        </option>
                      ))}
                    </Form.Select>
                  </Col>
                  <Col md={2}>
                    <Button size="sm" className="w-100" disabled={!nueva.cuenta} onClick={asignar}>
                      Asignar
                    </Button>
                  </Col>
                </Row>
              </Card.Body>
            )}
            <Table size="sm" className="align-middle mb-0">
              <thead className="table-light">
                <tr>
                  <th>Cuenta</th>
                  <th>Actividad</th>
                  <th>Modificado</th>
                  {puedeEditar && <th />}
                </tr>
              </thead>
              <tbody>
                {clasif.asignaciones.map((a) => (
                  <tr key={a.id} className="small">
                    <td>
                      <code className="me-2">{a.cuenta.codigo}</code>
                      {a.cuenta.nombre}
                    </td>
                    <td>
                      <Badge bg={`${COLOR_ACTIVIDAD[a.actividad]}-subtle`} text={`${COLOR_ACTIVIDAD[a.actividad]}-emphasis`} className="fw-normal">
                        {a.actividad_display}
                      </Badge>
                    </td>
                    <td className="text-suave">{a.modificado_por}</td>
                    {puedeEditar && (
                      <td className="text-end">
                        <Button size="sm" variant="link" className="text-danger p-0" onClick={() => quitar(a)}>
                          Quitar
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
                {clasif.asignaciones.length === 0 && (
                  <tr>
                    <td colSpan={puedeEditar ? 4 : 3}>
                      <EstadoVacio icono="bi-diagram-3">Sin asignaciones: todas las cuentas usan la actividad por tipo.</EstadoVacio>
                    </td>
                  </tr>
                )}
              </tbody>
            </Table>
            <Card.Footer className="small text-suave">
              Sin asignación en su rama, una cuenta usa la actividad por tipo: ingresos, gastos y pasivos → operación; activos → inversión;
              patrimonio → financiamiento.
            </Card.Footer>
          </Card>
        </Col>
      </Row>
    </>
  )
}

export default function FlujoEfectivo() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR, ROLES.TESORERO)
  const [params, setParams] = useSearchParams()
  const pestana = params.get('vista') || 'proyectado'
  const ir = (v) => setParams({ vista: v }, { replace: true })

  return (
    <>
      <EncabezadoPagina
        titulo="Flujo de efectivo"
        descripcion="Posición de efectivo real por actividad y proyección a 13 semanas con alertas de déficit de liquidez."
        migas={[{ texto: 'Tesorería' }, { texto: 'Flujo de efectivo' }]}
      />
      <Tabs activeKey={pestana} onSelect={(k) => ir(k)} className="mb-3 no-imprimir" mountOnEnter unmountOnExit>
        <Tab eventKey="proyectado" title="Proyectado">
          <Proyectado irAConfiguracion={() => ir('configuracion')} />
        </Tab>
        <Tab eventKey="real" title="Real del periodo">
          <Real irAConfiguracion={() => ir('configuracion')} />
        </Tab>
        <Tab eventKey="configuracion" title="Configuración">
          <Configuracion puedeEditar={puedeEditar} />
        </Tab>
      </Tabs>
    </>
  )
}
