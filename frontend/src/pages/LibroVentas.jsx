import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Card, Col, Container, Form, Row, Spinner, Table } from 'react-bootstrap'
import { api, mensajeError } from '../api'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import { AccionesReporte } from '../components/FiltroRango'
import { descargarCSV, descargarDesdeApi } from '../exportar'
import { formatoFecha, formatoMonto, hoyISO } from '../formato'

const MONTOS_CCF = [
  ['ventas_exentas', 'Ventas exentas'],
  ['ventas_gravadas', 'Ventas gravadas'],
  ['iva_debito_fiscal', 'IVA débito fiscal'],
  ['total', 'Total'],
]
const MONTOS_CF = [
  ['ventas_exentas', 'Ventas exentas'],
  ['ventas_gravadas', 'Ventas gravadas (IVA incluido)'],
  ['iva_debito_fiscal', 'IVA débito fiscal incluido'],
  ['total', 'Total ventas'],
]

const aParametros = (mes) => ({ anio: Number(mes.slice(0, 4)), mes: Number(mes.slice(5, 7)) })

function Montos({ fila, columnas, negrita }) {
  return columnas.map(([k]) => (
    <td key={k} className={`monto ${negrita || k === 'total' ? 'fw-semibold' : ''}`}>
      {formatoMonto(fila[k], { vacioSiCero: !negrita && k !== 'total' })}
    </td>
  ))
}

/** Libro de ventas mensual (T7.3): contribuyentes (CCF) y consumidor final (facturas por día). */
export default function LibroVentas() {
  const [mes, setMes] = useState(() => hoyISO().slice(0, 7))
  const [consultado, setConsultado] = useState(mes)
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [exportando, setExportando] = useState(false)

  const cargar = useCallback(async () => {
    setDatos(null)
    const resp = await api(`/api/ventas/libro/?${new URLSearchParams(aParametros(consultado))}`)
    if (!resp.ok) return setError(await mensajeError(resp))
    setError('')
    setDatos(await resp.json())
  }, [consultado])

  useEffect(() => {
    cargar()
  }, [cargar])

  const exportarCSV = () => {
    const filas = [['VENTAS A CONTRIBUYENTES'], ['N.º', 'Fecha', 'Documento', 'NRC', 'NIT', 'Cliente', ...MONTOS_CCF.map(([, t]) => t)]]
    datos.contribuyentes.filas.forEach((f) =>
      filas.push([f.correlativo, formatoFecha(f.fecha_emision), f.numero_documento, f.cliente.nrc, f.cliente.nit,
        f.anulado ? `${f.cliente.nombre} (ANULADO)` : f.cliente.nombre, ...MONTOS_CCF.map(([k]) => f[k])]),
    )
    filas.push(['', '', '', '', '', 'TOTALES', ...MONTOS_CCF.map(([k]) => datos.contribuyentes.totales[k])], [])
    filas.push(['VENTAS A CONSUMIDOR FINAL'], ['Fecha', 'Del N.º', 'Al N.º', 'Documentos', 'Anulados', ...MONTOS_CF.map(([, t]) => t)])
    datos.consumidor_final.filas.forEach((f) =>
      filas.push([formatoFecha(f.fecha), f.del_numero, f.al_numero, f.documentos, f.anulados, ...MONTOS_CF.map(([k]) => f[k])]),
    )
    filas.push(['TOTALES', '', '', '', '', ...MONTOS_CF.map(([k]) => datos.consumidor_final.totales[k])])
    descargarCSV(`libro_ventas_${consultado}.csv`, [`Libro de ventas · ${datos.periodo}`], filas)
  }

  const exportarExcel = async () => {
    setExportando(true)
    const fallo = await descargarDesdeApi(`/api/ventas/libro/exportar/?${new URLSearchParams(aParametros(consultado))}`, `libro_ventas_${consultado}.xlsx`)
    setExportando(false)
    if (fallo) setError(fallo)
  }

  return (
    <Container fluid className="px-0">
      <EncabezadoPagina
        titulo="Libro de ventas"
        descripcion="Ventas a contribuyentes (CCF) y a consumidor final (facturas) del mes, con su IVA débito fiscal."
        migas={[{ texto: 'Ventas' }, { texto: 'Libro de ventas' }]}
      />

      <Card className="mb-3 shadow-sm no-imprimir">
        <Card.Body>
          <Form
            onSubmit={(e) => {
              e.preventDefault()
              if (mes) setConsultado(mes)
            }}
          >
            <Row className="g-2 align-items-end">
              <Col xs={6} md={2}>
                <Form.Label htmlFor="lv-mes" className="small text-muted mb-1">
                  Mes
                </Form.Label>
                <Form.Control id="lv-mes" size="sm" type="month" value={mes} onChange={(e) => setMes(e.target.value)} required />
              </Col>
              <AccionesReporte onExportar={exportarCSV} onExportarExcel={exportarExcel} exportandoExcel={exportando} deshabilitado={!datos || exportando} />
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {error && <Alert variant="danger">{error}</Alert>}
      {!datos && !error && <Spinner animation="border" />}

      {datos && (
        <>
          <div className="encabezado-reporte">
            <strong>Libro de ventas</strong> · mes de {datos.periodo}
          </div>
          <Row className="g-3 mb-3">
            <Col xs={6} md={3}>
              <Card body>
                <div className="small text-suave">Total de ventas del mes</div>
                <div className="fs-5 fw-semibold">{formatoMonto(datos.resumen.total_ventas)}</div>
              </Card>
            </Col>
            <Col xs={6} md={3}>
              <Card body>
                <div className="small text-suave">IVA débito fiscal del mes</div>
                <div className="fs-5 fw-semibold">{formatoMonto(datos.resumen.iva_debito_fiscal)}</div>
              </Card>
            </Col>
          </Row>

          <h2 className="h6 mt-3">Ventas a contribuyentes (CCF)</h2>
          <Card className="shadow-sm mb-4">
            <div className="table-responsive">
              <Table size="sm" hover className="mb-0 align-middle">
                <thead className="table-light">
                  <tr className="small text-muted">
                    <th>N.º</th>
                    <th>Fecha</th>
                    <th>Documento</th>
                    <th>NRC</th>
                    <th>NIT</th>
                    <th>Cliente</th>
                    {MONTOS_CCF.map(([k, t]) => (
                      <th key={k} className="text-end">
                        {t}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {datos.contribuyentes.filas.map((f) => (
                    <tr key={f.id} className={f.anulado ? 'text-suave' : ''}>
                      <td>{f.correlativo}</td>
                      <td className="text-nowrap">{formatoFecha(f.fecha_emision)}</td>
                      <td>
                        <code>{f.numero_documento}</code>
                      </td>
                      <td className="text-nowrap">{f.cliente.nrc}</td>
                      <td className="text-nowrap">{f.cliente.nit}</td>
                      <td>
                        {f.cliente.nombre}
                        {f.anulado && (
                          <Badge bg="secondary-subtle" text="secondary-emphasis" className="ms-2">
                            Anulado
                          </Badge>
                        )}
                      </td>
                      <Montos fila={f} columnas={MONTOS_CCF} />
                    </tr>
                  ))}
                  {datos.contribuyentes.filas.length === 0 && (
                    <tr>
                      <td colSpan={10}>
                        <EstadoVacio icono="bi-receipt">No se emitieron comprobantes de crédito fiscal en el mes.</EstadoVacio>
                      </td>
                    </tr>
                  )}
                </tbody>
                <tfoot className="table-light">
                  <tr className="fw-bold">
                    <td colSpan={6}>Totales del mes</td>
                    <Montos fila={datos.contribuyentes.totales} columnas={MONTOS_CCF} negrita />
                  </tr>
                </tfoot>
              </Table>
            </div>
          </Card>

          <h2 className="h6">Ventas a consumidor final (facturas, por día)</h2>
          <Card className="shadow-sm mb-3">
            <div className="table-responsive">
              <Table size="sm" hover className="mb-0 align-middle">
                <thead className="table-light">
                  <tr className="small text-muted">
                    <th>Fecha</th>
                    <th>Del N.º</th>
                    <th>Al N.º</th>
                    <th className="text-end">Documentos</th>
                    <th className="text-end">Anulados</th>
                    {MONTOS_CF.map(([k, t]) => (
                      <th key={k} className="text-end">
                        {t}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {datos.consumidor_final.filas.map((f) => (
                    <tr key={f.fecha}>
                      <td className="text-nowrap">{formatoFecha(f.fecha)}</td>
                      <td>
                        <code>{f.del_numero}</code>
                      </td>
                      <td>
                        <code>{f.al_numero}</code>
                      </td>
                      <td className="text-end">{f.documentos}</td>
                      <td className="text-end">{f.anulados || ''}</td>
                      <Montos fila={f} columnas={MONTOS_CF} />
                    </tr>
                  ))}
                  {datos.consumidor_final.filas.length === 0 && (
                    <tr>
                      <td colSpan={9}>
                        <EstadoVacio icono="bi-receipt-cutoff">No se emitieron facturas de consumidor final en el mes.</EstadoVacio>
                      </td>
                    </tr>
                  )}
                </tbody>
                <tfoot className="table-light">
                  <tr className="fw-bold">
                    <td colSpan={5}>Totales del mes</td>
                    <Montos fila={datos.consumidor_final.totales} columnas={MONTOS_CF} negrita />
                  </tr>
                </tfoot>
              </Table>
            </div>
          </Card>
          <div className="small text-suave">
            Los CCF anulados se anotan con montos en cero. En consumidor final, las facturas anuladas cuentan en el rango de números pero no en los montos.
          </div>
        </>
      )}
    </Container>
  )
}
