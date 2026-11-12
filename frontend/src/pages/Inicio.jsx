import { useEffect, useState } from 'react'
import { Button, Card, Col, Row, Spinner, Table } from 'react-bootstrap'
import { Link, useNavigate } from 'react-router-dom'
import { api, urlApi } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoAsiento from '../components/EstadoAsiento'
import EstadoVacio from '../components/EstadoVacio'
import { formatoFecha, formatoMonto, hoyISO } from '../formato'

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

function Indicador({ icono, color, etiqueta, valor, detalle, a }) {
  const contenido = (
    <Card className="indicador h-100">
      <Card.Body className="d-flex gap-3 align-items-start">
        <span className={`icono bg-${color}-subtle text-${color}-emphasis`}>
          <i className={`bi ${icono}`} />
        </span>
        <div className="min-w-0">
          <div className="etiqueta">{etiqueta}</div>
          <div className="valor">{valor}</div>
          {detalle && <div className="small text-suave">{detalle}</div>}
        </div>
      </Card.Body>
    </Card>
  )
  return a ? (
    <Link to={a} className="text-decoration-none text-reset d-block h-100">
      {contenido}
    </Link>
  ) : (
    contenido
  )
}

async function obtener(url) {
  const resp = await api(url)
  return resp.ok ? resp.json() : null
}

export default function Inicio() {
  const { usuario } = useAuth()
  const esContador = tieneRol(usuario, ROLES.CONTADOR)
  const navegar = useNavigate()
  const hoy = hoyISO()
  const anio = hoy.slice(0, 4)
  const mes = Number(hoy.slice(5, 7))
  const inicioMes = `${hoy.slice(0, 7)}-01`

  const [datos, setDatos] = useState(null)
  const [salud, setSalud] = useState(null)

  useEffect(() => {
    Promise.all([
      obtener(`/api/periodos/?anio=${anio}`),
      obtener(`/api/asientos/?estado=CONTABILIZADO&desde=${inicioMes}&hasta=${hoy}`),
      obtener('/api/asientos/?estado=BORRADOR'),
      obtener(`/api/libros/balanza/?desde=${anio}-01-01&hasta=${hoy}`),
      obtener('/api/asientos/'),
    ]).then(([periodos, delMes, borradores, balanza, recientes]) =>
      setDatos({ periodos: periodos || [], delMes, borradores, balanza, recientes }),
    )
    fetch(urlApi('/api/health/'))
      .then((r) => r.json())
      .then(setSalud)
      .catch(() => setSalud({ status: 'error' }))
  }, [anio, hoy, inicioMes])

  const periodo = datos?.periodos.find((p) => p.mes === mes)
  const cerrados = datos?.periodos.filter((p) => p.estado === 'CERRADO').length ?? 0

  return (
    <>
      <EncabezadoPagina
        titulo={`Hola, ${usuario.nombre.split(' ')[0]}`}
        descripcion={`Resumen contable del ejercicio ${anio} al ${formatoFecha(hoy)}.`}
      >
        {esContador && (
          <Button as={Link} to="/asientos/nuevo">
            <i className="bi bi-plus-lg me-1" /> Nuevo asiento
          </Button>
        )}
        <Button as={Link} to="/libros/balanza" variant="outline-primary">
          <i className="bi bi-calculator me-1" /> Balanza
        </Button>
      </EncabezadoPagina>

      {!datos ? (
        <Spinner animation="border" />
      ) : (
        <>
          <Row className="g-3 mb-4">
            <Col sm={6} xl={3}>
              <Indicador
                icono="bi-calendar-check"
                color={periodo?.estado === 'ABIERTO' ? 'success' : 'secondary'}
                etiqueta="Periodo actual"
                valor={periodo ? `${MESES[mes - 1][0].toUpperCase()}${MESES[mes - 1].slice(1)}` : 'Sin periodo'}
                detalle={
                  periodo
                    ? `${periodo.estado_display} · ${cerrados} de 12 cerrados`
                    : `El ejercicio ${anio} no ha sido creado`
                }
                a="/periodos"
              />
            </Col>
            <Col sm={6} xl={3}>
              <Indicador
                icono="bi-journal-check"
                color="primary"
                etiqueta="Asientos del mes"
                valor={datos.delMes?.count ?? '—'}
                detalle="Contabilizados"
                a="/asientos"
              />
            </Col>
            <Col sm={6} xl={3}>
              <Indicador
                icono="bi-pencil-square"
                color={datos.borradores?.count ? 'warning' : 'secondary'}
                etiqueta="Borradores"
                valor={datos.borradores?.count ?? '—'}
                detalle={datos.borradores?.count ? 'Pendientes de contabilizar' : 'Sin pendientes'}
                a="/asientos"
              />
            </Col>
            <Col sm={6} xl={3}>
              <Indicador
                icono={datos.balanza?.cuadra ? 'bi-check2-circle' : 'bi-exclamation-triangle'}
                color={datos.balanza?.cuadra ? 'success' : 'danger'}
                etiqueta="Balanza del año"
                valor={datos.balanza ? (datos.balanza.cuadra ? 'Cuadra' : 'No cuadra') : '—'}
                detalle={datos.balanza ? `Cargos ${formatoMonto(datos.balanza.totales.cargos)}` : ''}
                a="/libros/balanza"
              />
            </Col>
          </Row>

          <Row className="g-3">
            <Col lg={8}>
              <Card className="h-100">
                <Card.Header className="bg-white d-flex justify-content-between align-items-center">
                  <span className="fw-semibold">Últimos asientos</span>
                  <Link to="/asientos" className="small">
                    Ver todos <i className="bi bi-arrow-right" />
                  </Link>
                </Card.Header>
                {datos.recientes?.results.length ? (
                  <div className="table-responsive">
                    <Table hover className="align-middle">
                      <thead>
                        <tr>
                          <th>Número</th>
                          <th>Fecha</th>
                          <th>Concepto</th>
                          <th className="text-end">Monto</th>
                          <th>Estado</th>
                        </tr>
                      </thead>
                      <tbody>
                        {datos.recientes.results.slice(0, 6).map((a) => (
                          <tr key={a.id} role="button" onClick={() => navegar(`/asientos/${a.id}`)}>
                            <td className="text-nowrap">
                              {a.numero ? <code>{a.codigo}</code> : <span className="text-suave fst-italic">Sin número</span>}
                            </td>
                            <td className="text-nowrap">{formatoFecha(a.fecha)}</td>
                            <td className="text-truncate" style={{ maxWidth: '18rem' }}>
                              {a.concepto}
                            </td>
                            <td className="monto">{formatoMonto(a.total_debe)}</td>
                            <td className="text-nowrap">
                              <EstadoAsiento asiento={a} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                ) : (
                  <EstadoVacio icono="bi-journal">Aún no hay asientos registrados.</EstadoVacio>
                )}
              </Card>
            </Col>
            <Col lg={4}>
              <Card className="mb-3">
                <Card.Header className="bg-white fw-semibold">Accesos rápidos</Card.Header>
                <div className="list-group list-group-flush">
                  {[
                    esContador && ['/asientos/nuevo', 'bi-plus-circle', 'Registrar asiento'],
                    ['/libros/diario', 'bi-book', 'Libro diario'],
                    ['/libros/mayor', 'bi-journal-bookmark', 'Libro mayor'],
                    ['/catalogo', 'bi-diagram-3', 'Catálogo de cuentas'],
                    tieneRol(usuario, ROLES.AUDITOR) && ['/bitacora', 'bi-shield-check', 'Bitácora de auditoría'],
                  ]
                    .filter(Boolean)
                    .map(([a, icono, texto]) => (
                      <Link key={a} to={a} className="list-group-item list-group-item-action d-flex align-items-center gap-2">
                        <i className={`bi ${icono} text-primary`} />
                        {texto}
                        <i className="bi bi-chevron-right ms-auto small text-suave" />
                      </Link>
                    ))}
                </div>
              </Card>
              <Card>
                <Card.Body className="d-flex align-items-center gap-3">
                  {salud === null ? (
                    <Spinner animation="border" size="sm" />
                  ) : (
                    <i
                      className={`bi ${salud.status === 'ok' ? 'bi-database-check text-success' : 'bi-database-x text-danger'} fs-4`}
                    />
                  )}
                  <div className="small">
                    <div className="fw-semibold">
                      {salud?.status === 'ok' ? 'Base de datos conectada' : salud ? 'Sin conexión a la base de datos' : 'Verificando…'}
                    </div>
                    <div className="text-suave">{salud?.db}</div>
                  </div>
                </Card.Body>
              </Card>
            </Col>
          </Row>
        </>
      )}
    </>
  )
}
