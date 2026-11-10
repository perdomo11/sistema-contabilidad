import { Fragment, useState } from 'react'
import { Alert, Badge, Button, Card, Spinner, Table } from 'react-bootstrap'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoVacio from '../components/EstadoVacio'
import {
  EncabezadoUnidad,
  FiltrosReporte,
  Monto,
  NavegacionUnidad,
  Porcentaje,
  nombreColumna,
  useReporteSegmentado,
} from '../components/reportes/ReporteSegmentado'
import { descargarCSV } from '../exportar'
import { formatoFecha } from '../formato'

const SECCIONES = ['ingresos', 'variables', 'fijos_controlables', 'no_controlables']
const MARGEN_TRAS = {
  variables: ['margen_contribucion', '= Margen de contribución'],
  fijos_controlables: ['margen_controlable', '= Margen controlable del segmento'],
  no_controlables: ['resultado_segmento', '= Resultado del segmento'],
}

export default function EnfoqueContribucion() {
  const reporte = useReporteSegmentado('/api/reportes/enfoque-contribucion/')
  const { datos, error, cargando, irA } = reporte
  const [detalle, setDetalle] = useState(true)

  const exportar = () => {
    const columnas = datos.columnas.map(nombreColumna)
    const filas = []
    for (const clave of SECCIONES) {
      const s = datos[clave]
      filas.push([s.titulo, ...s.valores, s.total])
      if (detalle) {
        s.filas.forEach((f) =>
          filas.push([`   ${f.cuenta.codigo} ${f.cuenta.nombre}${f.prorrateo ? ' (prorrateo)' : ''}`, ...f.valores, f.total]),
        )
      }
      if (MARGEN_TRAS[clave]) {
        const [m, titulo] = MARGEN_TRAS[clave]
        filas.push([titulo, ...datos[m].valores, datos[m].total])
        filas.push([`   % sobre ingresos`, ...datos[m].razon])
      }
    }
    filas.push(['(−) Costos comunes no asignados', ...columnas.map(() => ''), datos.costos_comunes])
    filas.push(['= Resultado de la institución', ...columnas.map(() => ''), datos.resultado])
    const sufijo = datos.centro ? `_${datos.centro.codigo}` : ''
    descargarCSV(`enfoque_contribucion${sufijo}_${datos.desde}_${datos.hasta}.csv`, ['Concepto', ...columnas, 'Total'], filas)
  }

  const vector = (etiqueta, v, clase, { alertar = false, sangria = false } = {}) => (
    <tr className={clase}>
      <td className={sangria ? 'ps-4' : ''}>{etiqueta}</td>
      {v.valores.map((x, i) => (
        <td key={i} className="monto">
          <Monto valor={x} alertar={alertar} />
        </td>
      ))}
      <td className="monto col-total">
        <Monto valor={v.total} alertar={alertar} />
      </td>
    </tr>
  )

  const razon = (valores) => (
    <tr className="small text-suave">
      <td className="ps-4 fst-italic">% sobre ingresos</td>
      {valores.map((p, i) => (
        <td key={i} className={`monto${i === valores.length - 1 ? ' col-total' : ''}`}>
          <Porcentaje valor={p} alertar />
        </td>
      ))}
    </tr>
  )

  const nColumnas = datos ? datos.columnas.length + 2 : 0
  const sinDatos = datos && SECCIONES.every((c) => datos[c].filas.length === 0)

  return (
    <>
      <EncabezadoPagina
        titulo="Enfoque de contribución"
        descripcion="Estado segmentado según la Tabla 1 del documento base: separa lo que el responsable controla de los costos asignados que no controla."
        migas={[{ texto: 'Reportes' }, { texto: 'Enfoque de contribución' }]}
      >
        <Button variant="outline-secondary" size="sm" onClick={() => setDetalle(!detalle)}>
          <i className={`bi ${detalle ? 'bi-list-nested' : 'bi-list'} me-1`} />
          {detalle ? 'Ocultar cuentas' : 'Mostrar cuentas'}
        </Button>
      </EncabezadoPagina>
      <FiltrosReporte reporte={reporte} onExportar={exportar} />
      <NavegacionUnidad datos={datos} irA={irA} />

      {error && <Alert variant="danger">{error}</Alert>}
      {cargando && <Spinner animation="border" />}

      {datos && !cargando && (
        <>
          <div className="encabezado-reporte">
            <strong>Estado de resultados segmentado: enfoque de contribución</strong>
            {datos.centro && ` · ${datos.centro.codigo} ${datos.centro.nombre}`} · del {formatoFecha(datos.desde)} al{' '}
            {formatoFecha(datos.hasta)}
          </div>
          {sinDatos && Number(datos.costos_comunes) === 0 ? (
            <EstadoVacio icono="bi-pie-chart">No hay ingresos ni gastos contabilizados en el rango para esta unidad.</EstadoVacio>
          ) : (
            <Card className="mb-3">
              <div className="table-responsive">
                <Table size="sm" className="tabla-matriz align-middle mb-0">
                  <thead className="table-light">
                    <tr>
                      <th className="small text-muted text-uppercase">Concepto</th>
                      {datos.columnas.map((c) => (
                        <EncabezadoUnidad key={c.id} columna={c} irA={irA} />
                      ))}
                      <th className="text-end col-total" style={{ minWidth: '8.5rem' }}>
                        Total
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {SECCIONES.map((clave) => {
                      const s = datos[clave]
                      const margen = MARGEN_TRAS[clave]
                      return (
                        <Fragment key={clave}>
                          {vector(<strong>{s.titulo}</strong>, s, 'fila-subtotal')}
                          {detalle &&
                            s.filas.map((f) => (
                              <Fragment key={`${f.cuenta.id}-${f.prorrateo}`}>
                                {vector(
                                  <span className="small">
                                    <code className="me-2">{f.cuenta.codigo}</code>
                                    {f.cuenta.nombre}
                                    {f.prorrateo && (
                                      <Badge bg="primary-subtle" text="primary-emphasis" className="ms-2 fw-normal">
                                        <i className="bi bi-shuffle me-1" />
                                        prorrateo
                                      </Badge>
                                    )}
                                  </span>,
                                  f,
                                  'small',
                                  { sangria: true },
                                )}
                              </Fragment>
                            ))}
                          {margen && (
                            <>
                              {vector(margen[1], datos[margen[0]], clave === 'no_controlables' ? 'fila-resultado' : 'fila-subtotal table-light', {
                                alertar: true,
                              })}
                              {razon(datos[margen[0]].razon)}
                            </>
                          )}
                        </Fragment>
                      )
                    })}
                  </tbody>
                  <tfoot className="table-light">
                    <tr>
                      <td>(−) Costos comunes no asignados</td>
                      <td colSpan={datos.columnas.length} className="small text-suave text-center">
                        Solo en el total: no se atribuyen a ningún segmento
                      </td>
                      <td className="monto col-total">
                        <Monto valor={datos.costos_comunes} />
                      </td>
                    </tr>
                    <tr className="fila-resultado">
                      <td colSpan={nColumnas - 1}>= Resultado de {datos.centro ? `${datos.centro.codigo} ${datos.centro.nombre}` : 'la institución'}</td>
                      <td className="monto col-total">
                        <Monto valor={datos.resultado} alertar />
                      </td>
                    </tr>
                  </tfoot>
                </Table>
              </div>
            </Card>
          )}
          <div className="small text-suave mb-4 no-imprimir">
            <i className="bi bi-info-circle me-1" />
            El <strong>margen controlable</strong> mide la gestión del responsable de cada unidad: no incluye costos asignados por
            prorrateo ni costos fijos que decide la gerencia (alquileres, depreciaciones…). La clasificación variable/fija y
            controlable se configura por cuenta en el Catálogo. El resultado del segmento coincide con el resultado neto del costeo
            absorbente.
          </div>
        </>
      )}
    </>
  )
}
