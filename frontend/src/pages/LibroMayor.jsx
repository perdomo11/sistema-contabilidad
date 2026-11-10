import { useCallback, useEffect, useState } from 'react'
import { Alert, Card, Col, Container, Form, Row, Spinner, Table } from 'react-bootstrap'
import { Link, useSearchParams } from 'react-router-dom'
import { api, mensajeError } from '../api'
import { AccionesReporte, CamposRango, rangoPorDefecto } from '../components/FiltroRango'
import SelectorCuenta from '../components/SelectorCuenta'
import { descargarCSV } from '../exportar'
import { formatoFecha, formatoMonto } from '../formato'

export default function LibroMayor() {
  const [params, setParams] = useSearchParams()
  const [cuentas, setCuentas] = useState(null)
  const [cuenta, setCuenta] = useState(null)
  const [rango, setRango] = useState(() => ({
    ...rangoPorDefecto(),
    ...(params.get('desde') && { desde: params.get('desde') }),
    ...(params.get('hasta') && { hasta: params.get('hasta') }),
  }))
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  // Todas las cuentas (detalle y agrupación) para el selector.
  useEffect(() => {
    api('/api/cuentas/arbol/').then(async (r) => {
      const lista = []
      const recorrer = (nodos) =>
        nodos.forEach((n) => {
          lista.push({ id: n.id, codigo: n.codigo, nombre: n.nombre })
          recorrer(n.hijos)
        })
      if (r.ok) recorrer(await r.json())
      setCuentas(lista)
      const inicial = lista.find((c) => String(c.id) === params.get('cuenta'))
      if (inicial) setCuenta(inicial)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const consultar = useCallback(async (c, r) => {
    if (!c) return
    setCargando(true)
    const resp = await api(`/api/libros/mayor/?${new URLSearchParams({ cuenta: c.id, desde: r.desde, hasta: r.hasta })}`)
    setCargando(false)
    if (!resp.ok) {
      setDatos(null)
      return setError(await mensajeError(resp))
    }
    setError('')
    setDatos(await resp.json())
  }, [])

  // Consulta automática cuando se llega con ?cuenta= (por ejemplo, desde la balanza).
  useEffect(() => {
    if (cuenta && !datos) consultar(cuenta, rango)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cuenta])

  const enviar = (e) => {
    e.preventDefault()
    if (!cuenta) return setError('Seleccione una cuenta.')
    setParams({ cuenta: cuenta.id, desde: rango.desde, hasta: rango.hasta }, { replace: true })
    consultar(cuenta, rango)
  }

  const exportar = () =>
    descargarCSV(
      `mayor_${datos.cuenta.codigo}_${datos.desde}_${datos.hasta}.csv`,
      ['Fecha', 'Asiento', 'Concepto', 'Cuenta', 'Descripción', 'Cargo', 'Abono', 'Saldo'],
      [
        ['', '', 'Saldo inicial', '', '', '', '', datos.saldo_inicial],
        ...datos.movimientos.map((m) => [
          formatoFecha(m.fecha),
          m.asiento_codigo,
          m.concepto,
          m.cuenta_codigo,
          m.descripcion,
          m.debe,
          m.haber,
          m.saldo,
        ]),
        ['', '', 'Totales y saldo final', '', '', datos.totales.debe, datos.totales.haber, datos.saldo_final],
      ],
    )

  const esAgrupacion = datos && !datos.cuenta.acepta_movimientos

  return (
    <Container fluid="xl">
      <div className="mb-3">
        <h1 className="h4 mb-0">Libro mayor</h1>
        <div className="text-muted small no-imprimir">
          Movimientos y saldo corriente de una cuenta. En cuentas de agrupación se incluyen todas sus subcuentas.
        </div>
      </div>

      <Card className="mb-3 shadow-sm no-imprimir">
        <Card.Body>
          <Form onSubmit={enviar}>
            <Row className="g-2 align-items-end">
              <Col xs={12} md={4}>
                <Form.Label htmlFor="cuenta-mayor" className="small text-muted mb-1">
                  Cuenta
                </Form.Label>
                {cuentas ? (
                  <SelectorCuenta id="cuenta-mayor" cuentas={cuentas} valor={cuenta} onChange={setCuenta} />
                ) : (
                  <Spinner animation="border" size="sm" />
                )}
              </Col>
              <CamposRango rango={rango} onChange={setRango} />
              <AccionesReporte onExportar={exportar} deshabilitado={!datos} />
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {error && <Alert variant="danger">{error}</Alert>}
      {cargando && <Spinner animation="border" />}
      {!datos && !cargando && !error && (
        <Alert variant="light" className="border">
          Seleccione una cuenta y un rango de fechas.
        </Alert>
      )}

      {datos && !cargando && (
        <>
          <div className="encabezado-reporte">
            <strong>Libro mayor</strong> del {formatoFecha(datos.desde)} al {formatoFecha(datos.hasta)}
          </div>
          <Card className="shadow-sm mb-3">
            <Card.Body className="d-flex flex-wrap justify-content-between gap-3">
              <div>
                <div className="small text-muted">Cuenta</div>
                <div className="fs-5">
                  <code className="me-2">{datos.cuenta.codigo}</code>
                  {datos.cuenta.nombre}
                </div>
                <div className="small text-muted">
                  Naturaleza {datos.cuenta.naturaleza === 'DEUDORA' ? 'deudora' : 'acreedora'}
                  {esAgrupacion && ' · cuenta de agrupación (incluye subcuentas)'}
                </div>
              </div>
              <div className="d-flex gap-4 text-end">
                <div>
                  <div className="small text-muted">Saldo inicial</div>
                  <div className="monto fs-5">{formatoMonto(datos.saldo_inicial)}</div>
                </div>
                <div>
                  <div className="small text-muted">Saldo final</div>
                  <div className="monto fs-5 fw-semibold">{formatoMonto(datos.saldo_final)}</div>
                </div>
              </div>
            </Card.Body>
          </Card>

          <Card className="shadow-sm mb-4">
            <div className="table-responsive">
              <Table hover size="sm" className="mb-0 align-middle">
                <thead className="table-light">
                  <tr className="small text-muted text-uppercase">
                    <th>Fecha</th>
                    <th>Asiento</th>
                    <th>Concepto</th>
                    {esAgrupacion && <th>Cuenta</th>}
                    <th className="text-end">Cargo</th>
                    <th className="text-end">Abono</th>
                    <th className="text-end">Saldo</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="text-muted fst-italic">
                    <td colSpan={esAgrupacion ? 6 : 5}>Saldo inicial al {formatoFecha(datos.desde)}</td>
                    <td className="monto">{formatoMonto(datos.saldo_inicial)}</td>
                  </tr>
                  {datos.movimientos.map((m, i) => (
                    <tr key={i}>
                      <td className="text-nowrap">{formatoFecha(m.fecha)}</td>
                      <td className="text-nowrap">
                        <Link to={`/asientos/${m.asiento_id}`}>
                          <code>{m.asiento_codigo}</code>
                        </Link>
                      </td>
                      <td>
                        {m.concepto}
                        {m.descripcion && <div className="small text-muted">{m.descripcion}</div>}
                      </td>
                      {esAgrupacion && (
                        <td className="small">
                          <code>{m.cuenta_codigo}</code> {m.cuenta_nombre}
                        </td>
                      )}
                      <td className="monto">{formatoMonto(m.debe, { vacioSiCero: true })}</td>
                      <td className="monto">{formatoMonto(m.haber, { vacioSiCero: true })}</td>
                      <td className="monto">{formatoMonto(m.saldo)}</td>
                    </tr>
                  ))}
                  {datos.movimientos.length === 0 && (
                    <tr>
                      <td colSpan={esAgrupacion ? 7 : 6} className="text-center text-muted py-3">
                        Sin movimientos en el rango.
                      </td>
                    </tr>
                  )}
                </tbody>
                <tfoot className="table-light">
                  <tr className="fw-bold">
                    <td colSpan={esAgrupacion ? 4 : 3}>Totales</td>
                    <td className="monto">{formatoMonto(datos.totales.debe)}</td>
                    <td className="monto">{formatoMonto(datos.totales.haber)}</td>
                    <td className="monto">{formatoMonto(datos.saldo_final)}</td>
                  </tr>
                </tfoot>
              </Table>
            </div>
          </Card>
        </>
      )}
    </Container>
  )
}
