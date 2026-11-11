import { useCallback, useEffect, useState } from 'react'
import { Alert, Card, Col, Container, Form, Row, Spinner, Table } from 'react-bootstrap'
import { api, mensajeError } from '../api'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import { AccionesReporte } from '../components/FiltroRango'
import { descargarCSV, descargarDesdeApi } from '../exportar'
import { formatoFecha, formatoMonto, hoyISO } from '../formato'

const MONTOS = [
  ['compras_exentas', 'Compras exentas'],
  ['compras_gravadas', 'Compras gravadas'],
  ['iva_credito_fiscal', 'IVA crédito fiscal'],
  ['iva_retenido', 'Retención / percepción 1 %'],
  ['total', 'Total compras'],
]

const aParametros = (mes) => ({ anio: Number(mes.slice(0, 4)), mes: Number(mes.slice(5, 7)) })

/** Libro de compras mensual (T7.2): CCF recibidos con su desglose fiscal. */
export default function LibroCompras() {
  const [mes, setMes] = useState(() => hoyISO().slice(0, 7))
  const [consultado, setConsultado] = useState(mes)
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [exportando, setExportando] = useState(false)

  const cargar = useCallback(async () => {
    setDatos(null)
    const resp = await api(`/api/tesoreria/libro-compras/?${new URLSearchParams(aParametros(consultado))}`)
    if (!resp.ok) return setError(await mensajeError(resp))
    setError('')
    setDatos(await resp.json())
  }, [consultado])

  useEffect(() => {
    cargar()
  }, [cargar])

  const exportarCSV = () => {
    const filas = datos.filas.map((f) => [
      f.correlativo,
      formatoFecha(f.fecha_emision),
      f.tipo_documento,
      f.numero_documento,
      f.proveedor.nrc,
      f.proveedor.nit,
      f.proveedor.nombre,
      ...MONTOS.map(([k]) => f[k]),
    ])
    filas.push(['', '', '', '', '', '', 'TOTALES', ...MONTOS.map(([k]) => datos.totales[k])])
    descargarCSV(
      `libro_compras_${consultado}.csv`,
      ['N.º', 'Fecha de emisión', 'Tipo de documento', 'N.º de documento', 'NRC', 'NIT', 'Proveedor', ...MONTOS.map(([, t]) => t)],
      filas,
    )
  }

  const exportarExcel = async () => {
    setExportando(true)
    const fallo = await descargarDesdeApi(
      `/api/tesoreria/libro-compras/exportar/?${new URLSearchParams(aParametros(consultado))}`,
      `libro_compras_${consultado}.xlsx`,
    )
    setExportando(false)
    if (fallo) setError(fallo)
  }

  return (
    <Container fluid className="px-0">
      <EncabezadoPagina
        titulo="Libro de compras"
        descripcion="Comprobantes de crédito fiscal recibidos en el mes, con compras exentas, gravadas, IVA crédito fiscal y retención."
        migas={[{ texto: 'Tesorería' }, { texto: 'Libro de compras' }]}
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
                <Form.Label htmlFor="lc-mes" className="small text-muted mb-1">
                  Mes
                </Form.Label>
                <Form.Control id="lc-mes" size="sm" type="month" value={mes} onChange={(e) => setMes(e.target.value)} required />
              </Col>
              <AccionesReporte
                onExportar={exportarCSV}
                onExportarExcel={exportarExcel}
                exportandoExcel={exportando}
                deshabilitado={!datos || exportando}
              />
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {error && <Alert variant="danger">{error}</Alert>}
      {!datos && !error && <Spinner animation="border" />}

      {datos && (
        <>
          <div className="encabezado-reporte">
            <strong>Libro de compras</strong> · mes de {datos.periodo}
          </div>
          <div className="small text-muted mb-2">
            {datos.filas.length} documento(s). Solo se anotan los CCF vigentes; las facturas de consumidor final, recibos y documentos
            anulados no generan crédito fiscal.
          </div>
          <Card className="shadow-sm mb-3">
            <div className="table-responsive">
              <Table size="sm" hover className="mb-0 align-middle">
                <thead className="table-light">
                  <tr className="small text-muted">
                    <th>N.º</th>
                    <th>Fecha de emisión</th>
                    <th>Documento</th>
                    <th>NRC</th>
                    <th>NIT</th>
                    <th>Proveedor</th>
                    {MONTOS.map(([k, t]) => (
                      <th key={k} className="text-end">
                        {t}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {datos.filas.map((f) => (
                    <tr key={f.id}>
                      <td>{f.correlativo}</td>
                      <td className="text-nowrap">{formatoFecha(f.fecha_emision)}</td>
                      <td className="text-nowrap">
                        <span className="small text-suave me-1">{f.tipo_documento}</span>
                        <code>{f.numero_documento}</code>
                      </td>
                      <td className="text-nowrap">{f.proveedor.nrc}</td>
                      <td className="text-nowrap">{f.proveedor.nit}</td>
                      <td>{f.proveedor.nombre}</td>
                      {MONTOS.map(([k]) => (
                        <td key={k} className={`monto ${k === 'total' ? 'fw-semibold' : ''}`}>
                          {formatoMonto(f[k], { vacioSiCero: k !== 'total' })}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {datos.filas.length === 0 && (
                    <tr>
                      <td colSpan={11}>
                        <EstadoVacio icono="bi-journal-text">No hay comprobantes de crédito fiscal registrados en el mes.</EstadoVacio>
                      </td>
                    </tr>
                  )}
                </tbody>
                <tfoot className="table-light">
                  <tr className="fw-bold">
                    <td colSpan={6}>Totales del mes</td>
                    {MONTOS.map(([k]) => (
                      <td key={k} className="monto">
                        {formatoMonto(datos.totales[k])}
                      </td>
                    ))}
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
