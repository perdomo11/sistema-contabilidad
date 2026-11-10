import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Container, Form, Pagination, Row, Spinner, Table } from 'react-bootstrap'
import { Link, useNavigate } from 'react-router-dom'
import { api, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoAsiento from '../components/EstadoAsiento'
import { formatoFecha, formatoMonto } from '../formato'

const FILTROS_VACIOS = { q: '', estado: '', tipo: '', desde: '', hasta: '' }
const TAMANO_PAGINA = 50

export default function Asientos() {
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR)
  const navegar = useNavigate()

  const [filtros, setFiltros] = useState(FILTROS_VACIOS)
  const [aplicados, setAplicados] = useState(FILTROS_VACIOS)
  const [pagina, setPagina] = useState(1)
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState('')

  const cargar = useCallback(async () => {
    const params = new URLSearchParams({ page: pagina })
    Object.entries(aplicados).forEach(([k, v]) => v && params.set(k, v))
    const resp = await api(`/api/asientos/?${params}`)
    if (!resp.ok) {
      setError(await mensajeError(resp))
      return setDatos({ count: 0, results: [] })
    }
    setError('')
    setDatos(await resp.json())
  }, [pagina, aplicados])

  useEffect(() => {
    cargar()
  }, [cargar])

  const cambiar = (campo) => (e) => setFiltros({ ...filtros, [campo]: e.target.value })
  const buscar = (e) => {
    e.preventDefault()
    setPagina(1)
    setAplicados(filtros)
  }
  const limpiar = () => {
    setFiltros(FILTROS_VACIOS)
    setAplicados(FILTROS_VACIOS)
    setPagina(1)
  }
  const totalPaginas = datos ? Math.max(1, Math.ceil(datos.count / TAMANO_PAGINA)) : 1

  return (
    <Container fluid className="px-0">
      <EncabezadoPagina
        titulo="Asientos contables"
        descripcion="Asientos de diario: borradores, contabilizados y reversiones."
        migas={[{ texto: 'Contabilidad' }, { texto: 'Asientos' }]}
      >
        {puedeEditar && (
          <Button as={Link} to="/asientos/nuevo">
            <i className="bi bi-plus-lg me-1" /> Nuevo asiento
          </Button>
        )}
      </EncabezadoPagina>

      <Card className="mb-3 shadow-sm">
        <Card.Body>
          <Form onSubmit={buscar}>
            <Row className="g-2 align-items-end">
              <Col xs={12} lg={4}>
                <Form.Label className="small text-muted mb-1">Concepto o referencia</Form.Label>
                <Form.Control size="sm" value={filtros.q} onChange={cambiar('q')} placeholder="Buscar…" />
              </Col>
              <Col xs={6} lg={2}>
                <Form.Label className="small text-muted mb-1">Estado</Form.Label>
                <Form.Select size="sm" value={filtros.estado} onChange={cambiar('estado')}>
                  <option value="">Todos</option>
                  <option value="BORRADOR">Borrador</option>
                  <option value="CONTABILIZADO">Contabilizado</option>
                </Form.Select>
              </Col>
              <Col xs={6} lg={2}>
                <Form.Label className="small text-muted mb-1">Tipo</Form.Label>
                <Form.Select size="sm" value={filtros.tipo} onChange={cambiar('tipo')}>
                  <option value="">Todos</option>
                  <option value="DIARIO">Diario</option>
                  <option value="REVERSION">Reversión</option>
                  <option value="PRORRATEO">Prorrateo</option>
                </Form.Select>
              </Col>
              <Col xs={6} lg={1}>
                <Form.Label className="small text-muted mb-1">Desde</Form.Label>
                <Form.Control size="sm" type="date" value={filtros.desde} onChange={cambiar('desde')} />
              </Col>
              <Col xs={6} lg={1}>
                <Form.Label className="small text-muted mb-1">Hasta</Form.Label>
                <Form.Control size="sm" type="date" value={filtros.hasta} onChange={cambiar('hasta')} />
              </Col>
              <Col xs={12} lg={2} className="d-flex gap-1">
                <Button size="sm" type="submit" className="flex-grow-1">
                  Filtrar
                </Button>
                <Button size="sm" variant="outline-secondary" onClick={limpiar}>
                  Limpiar
                </Button>
              </Col>
            </Row>
          </Form>
        </Card.Body>
      </Card>

      {error && <Alert variant="danger">{error}</Alert>}

      {!datos ? (
        <Spinner animation="border" />
      ) : (
        <Card className="shadow-sm">
          <div className="table-responsive">
            <Table hover className="mb-0 align-middle">
              <thead className="table-light">
                <tr className="small text-uppercase text-muted">
                  <th>Número</th>
                  <th>Fecha</th>
                  <th>Concepto</th>
                  <th>Referencia</th>
                  <th className="text-end">Cargos</th>
                  <th className="text-end">Abonos</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {datos.results.map((a) => (
                  <tr key={a.id} role="button" onClick={() => navegar(`/asientos/${a.id}`)}>
                    <td className="text-nowrap">
                      {a.numero ? <code>{a.codigo}</code> : <span className="text-muted fst-italic">Sin número</span>}
                    </td>
                    <td className="text-nowrap">{formatoFecha(a.fecha)}</td>
                    <td>{a.concepto}</td>
                    <td className="small text-muted">{a.referencia}</td>
                    <td className="text-end font-monospace">{formatoMonto(a.total_debe)}</td>
                    <td className={`text-end font-monospace ${a.cuadrado ? '' : 'text-danger'}`}>
                      {formatoMonto(a.total_haber)}
                    </td>
                    <td className="text-nowrap">
                      <EstadoAsiento asiento={a} />
                    </td>
                  </tr>
                ))}
                {datos.results.length === 0 && (
                  <tr>
                    <td colSpan={7} className="text-center text-muted py-4">
                      No hay asientos que coincidan.
                    </td>
                  </tr>
                )}
              </tbody>
            </Table>
          </div>
          <Card.Footer className="d-flex justify-content-between align-items-center small text-muted">
            <span>{datos.count} asiento(s)</span>
            {totalPaginas > 1 && (
              <Pagination size="sm" className="mb-0">
                <Pagination.Prev disabled={pagina === 1} onClick={() => setPagina(pagina - 1)} />
                <Pagination.Item active>
                  {pagina} / {totalPaginas}
                </Pagination.Item>
                <Pagination.Next disabled={pagina === totalPaginas} onClick={() => setPagina(pagina + 1)} />
              </Pagination>
            )}
          </Card.Footer>
        </Card>
      )}
    </Container>
  )
}
