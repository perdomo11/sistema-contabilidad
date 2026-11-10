import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Card, Container, Form, Row, Col, Spinner, Table } from 'react-bootstrap'
import { Link } from 'react-router-dom'
import { api, mensajeError } from '../api'
import EncabezadoPagina from '../components/EncabezadoPagina'
import { AccionesReporte, CamposRango, rangoPorDefecto } from '../components/FiltroRango'
import { descargarCSV } from '../exportar'
import { formatoFecha, formatoMonto } from '../formato'

const COLUMNAS = [
  ['inicial_deudor', 'Saldo inicial deudor'],
  ['inicial_acreedor', 'Saldo inicial acreedor'],
  ['cargos', 'Cargos'],
  ['abonos', 'Abonos'],
  ['final_deudor', 'Saldo final deudor'],
  ['final_acreedor', 'Saldo final acreedor'],
]

export default function Balanza() {
  const [filtros, setFiltros] = useState({ ...rangoPorDefecto(), nivel: '', incluir_sin_movimiento: false })
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  const consultar = useCallback(async (f) => {
    setCargando(true)
    const params = new URLSearchParams({ desde: f.desde, hasta: f.hasta, incluir_sin_movimiento: f.incluir_sin_movimiento })
    if (f.nivel) params.set('nivel', f.nivel)
    const resp = await api(`/api/libros/balanza/?${params}`)
    setCargando(false)
    if (!resp.ok) {
      setDatos(null)
      return setError(await mensajeError(resp))
    }
    setError('')
    setDatos(await resp.json())
  }, [])

  useEffect(() => {
    consultar(filtros)
    // Solo la primera vez; después se consulta con el botón.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const exportar = () =>
    descargarCSV(
      `balanza_${datos.desde}_${datos.hasta}.csv`,
      ['Código', 'Cuenta', 'Nivel', ...COLUMNAS.map(([, t]) => t)],
      [
        ...datos.filas.map((f) => [f.codigo, f.nombre, f.nivel, ...COLUMNAS.map(([c]) => f[c])]),
        ['', 'TOTALES', '', ...COLUMNAS.map(([c]) => datos.totales[c])],
      ],
    )

  return (
    <Container fluid className="px-0">
      <EncabezadoPagina
        titulo="Balanza de comprobación"
        descripcion="Saldos y movimientos de los asientos contabilizados. Haga clic en una cuenta para ver su libro mayor."
        migas={[{ texto: 'Libros' }, { texto: 'Balanza de comprobación' }]}
      />

      <Card className="mb-3 shadow-sm no-imprimir">
        <Card.Body>
          <Form
            onSubmit={(e) => {
              e.preventDefault()
              consultar(filtros)
            }}
          >
            <Row className="g-2 align-items-end">
              <CamposRango rango={filtros} onChange={setFiltros} />
              <Col xs={6} md={2}>
                <Form.Label htmlFor="nivel" className="small text-muted mb-1">
                  Nivel de detalle
                </Form.Label>
                <Form.Select id="nivel" size="sm" value={filtros.nivel} onChange={(e) => setFiltros({ ...filtros, nivel: e.target.value })}>
                  <option value="">Todos</option>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <option key={n} value={n}>
                      Hasta nivel {n}
                    </option>
                  ))}
                </Form.Select>
              </Col>
              <Col xs={6} md="auto" className="pb-1">
                <Form.Check
                  id="sin-movimiento"
                  label="Incluir cuentas sin movimiento"
                  className="small"
                  checked={filtros.incluir_sin_movimiento}
                  onChange={(e) => setFiltros({ ...filtros, incluir_sin_movimiento: e.target.checked })}
                />
              </Col>
              <AccionesReporte onExportar={exportar} deshabilitado={!datos} />
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {error && <Alert variant="danger">{error}</Alert>}
      {cargando && !datos && <Spinner animation="border" />}

      {datos && (
        <>
          <div className="encabezado-reporte">
            <strong>Balanza de comprobación</strong> del {formatoFecha(datos.desde)} al {formatoFecha(datos.hasta)}
          </div>
          <div className="d-flex justify-content-between align-items-center mb-2 small">
            <span className="text-muted">
              Del {formatoFecha(datos.desde)} al {formatoFecha(datos.hasta)} · {datos.filas.length} cuenta(s)
            </span>
            {datos.cuadra ? (
              <Badge bg="success">✓ Cuadra</Badge>
            ) : (
              <Badge bg="danger">No cuadra: revise los saldos</Badge>
            )}
          </div>
          <Card className="shadow-sm mb-4">
            <div className="table-responsive">
              <Table hover size="sm" className="mb-0 align-middle">
                <thead className="table-light">
                  <tr className="small text-muted text-center">
                    <th rowSpan={2} className="text-start align-middle">
                      Cuenta
                    </th>
                    <th colSpan={2}>Saldo inicial</th>
                    <th colSpan={2}>Movimientos</th>
                    <th colSpan={2}>Saldo final</th>
                  </tr>
                  <tr className="small text-muted text-end">
                    <th>Deudor</th>
                    <th>Acreedor</th>
                    <th>Cargos</th>
                    <th>Abonos</th>
                    <th>Deudor</th>
                    <th>Acreedor</th>
                  </tr>
                </thead>
                <tbody>
                  {datos.filas.map((f) => (
                    <tr key={f.id} className={f.acepta_movimientos ? '' : 'fw-semibold'}>
                      <td style={{ paddingLeft: `${(f.nivel - 1) * 1.1 + 0.5}rem` }}>
                        <Link
                          to={`/libros/mayor?cuenta=${f.id}&desde=${datos.desde}&hasta=${datos.hasta}`}
                          className="text-decoration-none text-reset"
                        >
                          <code className="me-2">{f.codigo}</code>
                          {f.nombre}
                        </Link>
                      </td>
                      {COLUMNAS.map(([c]) => (
                        <td key={c} className="monto">
                          {formatoMonto(f[c], { vacioSiCero: true })}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {datos.filas.length === 0 && (
                    <tr>
                      <td colSpan={7} className="text-center text-muted py-4">
                        No hay movimientos contabilizados en el rango.
                      </td>
                    </tr>
                  )}
                </tbody>
                <tfoot className="table-light">
                  <tr className="fw-bold">
                    <td>Totales</td>
                    {COLUMNAS.map(([c]) => (
                      <td key={c} className="monto">
                        {formatoMonto(datos.totales[c])}
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
