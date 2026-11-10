import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Container, Form, Modal, Row, Spinner, Table } from 'react-bootstrap'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, mensajeError } from '../api'
import { useAuth } from '../auth/AuthContext'
import { ROLES, tieneRol } from '../auth/roles'
import EncabezadoPagina from '../components/EncabezadoPagina'
import EstadoAsiento from '../components/EstadoAsiento'
import { formatoFecha, formatoFechaHora, formatoMonto, hoyISO } from '../formato'

function Dato({ etiqueta, children }) {
  return (
    <div className="mb-2">
      <div className="small text-muted text-uppercase" style={{ fontSize: '0.7rem', letterSpacing: '0.05em' }}>
        {etiqueta}
      </div>
      <div>{children || '—'}</div>
    </div>
  )
}

export default function AsientoDetalle() {
  const { id } = useParams()
  const { usuario } = useAuth()
  const puedeEditar = tieneRol(usuario, ROLES.CONTADOR)
  const navegar = useNavigate()
  const ubicacion = useLocation()

  const [asiento, setAsiento] = useState(null)
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState(ubicacion.state?.aviso || '')
  const [trabajando, setTrabajando] = useState(false)
  const [modal, setModal] = useState(null) // 'eliminar' | 'revertir'
  const [reversion, setReversion] = useState({ fecha: hoyISO(), motivo: '' })
  const [errorModal, setErrorModal] = useState('')

  const cargar = useCallback(async () => {
    const resp = await api(`/api/asientos/${id}/`)
    if (!resp.ok) return setError(await mensajeError(resp))
    setAsiento(await resp.json())
  }, [id])

  useEffect(() => {
    setAsiento(null)
    setError('')
    cargar()
  }, [cargar])

  useEffect(() => {
    setAviso(ubicacion.state?.aviso || '')
  }, [ubicacion])

  const accion = async (url, opciones, alExito) => {
    setTrabajando(true)
    setError('')
    setErrorModal('')
    const resp = await api(url, opciones)
    setTrabajando(false)
    if (!resp.ok) {
      const mensaje = await mensajeError(resp)
      return modal ? setErrorModal(mensaje) : setError(mensaje)
    }
    setModal(null)
    alExito(resp.status === 204 ? null : await resp.json())
  }

  const contabilizar = () =>
    accion(`/api/asientos/${id}/contabilizar/`, { method: 'POST' }, (a) => {
      setAsiento(a)
      setAviso(`Asiento contabilizado con el número ${a.codigo}.`)
    })

  const eliminar = () => accion(`/api/asientos/${id}/`, { method: 'DELETE' }, () => navegar('/asientos'))

  const revertir = (e) => {
    e.preventDefault()
    accion(`/api/asientos/${id}/revertir/`, { method: 'POST', body: reversion }, (r) =>
      navegar(`/asientos/${r.id}`, { state: { aviso: `Reversión ${r.codigo} registrada.` } }),
    )
  }

  if (error && !asiento) {
    return (
      <Container>
        <Alert variant="danger">{error}</Alert>
      </Container>
    )
  }
  if (!asiento) {
    return (
      <Container className="py-5 text-center">
        <Spinner animation="border" />
      </Container>
    )
  }

  const esBorrador = asiento.estado === 'BORRADOR'
  const puedeRevertir = !esBorrador && asiento.tipo !== 'REVERSION' && !asiento.revertido_por

  return (
    <Container fluid className="px-0">
      <EncabezadoPagina
        titulo={
          <span className="d-inline-flex flex-wrap align-items-center gap-2">
            {asiento.numero ? `Asiento ${asiento.codigo}` : 'Asiento en borrador'}
            <span className="fs-6">
              <EstadoAsiento asiento={asiento} />
            </span>
          </span>
        }
        descripcion={asiento.concepto}
        migas={[{ texto: 'Asientos', a: '/asientos' }, { texto: asiento.codigo }]}
      >
        {puedeEditar && esBorrador && (
          <>
            <Button as={Link} to={`/asientos/${asiento.id}/editar`} variant="outline-secondary">
              <i className="bi bi-pencil me-1" /> Editar
            </Button>
            <Button variant="outline-danger" onClick={() => setModal('eliminar')}>
              <i className="bi bi-trash me-1" /> Eliminar
            </Button>
            <Button
              onClick={contabilizar}
              disabled={trabajando || !asiento.cuadrado}
              title={asiento.cuadrado ? '' : 'El asiento no está cuadrado'}
            >
              {trabajando ? <Spinner animation="border" size="sm" className="me-2" /> : <i className="bi bi-check2-circle me-1" />}
              Contabilizar
            </Button>
          </>
        )}
        {puedeEditar && puedeRevertir && (
          <Button variant="outline-warning" onClick={() => setModal('revertir')}>
            <i className="bi bi-arrow-counterclockwise me-1" /> Revertir
          </Button>
        )}
      </EncabezadoPagina>

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
      {asiento.reversion_de && (
        <Alert variant="info">
          Este asiento revierte al asiento <Link to={`/asientos/${asiento.reversion_de.id}`}>{asiento.reversion_de.codigo}</Link>.
        </Alert>
      )}
      {asiento.revertido_por && (
        <Alert variant="secondary">
          Este asiento fue revertido por el asiento{' '}
          <Link to={`/asientos/${asiento.revertido_por.id}`}>{asiento.revertido_por.codigo}</Link>.
        </Alert>
      )}
      {esBorrador && !asiento.cuadrado && (
        <Alert variant="warning">El borrador no está cuadrado: los cargos deben igualar a los abonos para contabilizarlo.</Alert>
      )}

      <Row className="g-3 mb-3">
        <Col lg={8}>
          <Card className="shadow-sm h-100">
            <Card.Body>
              <Row>
                <Col sm={4}>
                  <Dato etiqueta="Fecha">{formatoFecha(asiento.fecha)}</Dato>
                </Col>
                <Col sm={4}>
                  <Dato etiqueta="Periodo">{asiento.periodo_nombre}</Dato>
                </Col>
                <Col sm={4}>
                  <Dato etiqueta="Tipo">{asiento.tipo_display}</Dato>
                </Col>
                <Col sm={8}>
                  <Dato etiqueta="Concepto">{asiento.concepto}</Dato>
                </Col>
                <Col sm={4}>
                  <Dato etiqueta="Referencia">{asiento.referencia}</Dato>
                </Col>
              </Row>
            </Card.Body>
          </Card>
        </Col>
        <Col lg={4}>
          <Card className="shadow-sm h-100">
            <Card.Body>
              <Dato etiqueta="Registrado por">
                {asiento.creado_por} · {formatoFechaHora(asiento.creado_en)}
              </Dato>
              {asiento.contabilizado_por && (
                <Dato etiqueta="Contabilizado por">
                  {asiento.contabilizado_por} · {formatoFechaHora(asiento.contabilizado_en)}
                </Dato>
              )}
              {esBorrador && (
                <Dato etiqueta="Última modificación">
                  {asiento.modificado_por} · {formatoFechaHora(asiento.modificado_en)}
                </Dato>
              )}
            </Card.Body>
          </Card>
        </Col>
      </Row>

      <Card className="shadow-sm mb-4">
        <div className="table-responsive">
          <Table className="mb-0 align-middle">
            <thead className="table-light">
              <tr className="small text-uppercase text-muted">
                <th style={{ width: '3rem' }}>#</th>
                <th>Cuenta</th>
                <th>Descripción</th>
                <th className="text-end">Cargo</th>
                <th className="text-end">Abono</th>
              </tr>
            </thead>
            <tbody>
              {asiento.lineas.map((l) => (
                <tr key={l.id}>
                  <td className="text-muted small">{l.numero_linea}</td>
                  <td>
                    <code className="me-2">{l.cuenta_codigo}</code>
                    {l.cuenta_nombre}
                  </td>
                  <td className="small text-muted">{l.descripcion}</td>
                  <td className="text-end font-monospace">{formatoMonto(l.debe, { vacioSiCero: true })}</td>
                  <td className="text-end font-monospace">{formatoMonto(l.haber, { vacioSiCero: true })}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="table-light">
              <tr className="fw-semibold">
                <td colSpan={3} className="text-end">
                  Totales
                </td>
                <td className="text-end font-monospace">{formatoMonto(asiento.total_debe)}</td>
                <td className={`text-end font-monospace ${asiento.cuadrado ? '' : 'text-danger'}`}>
                  {formatoMonto(asiento.total_haber)}
                </td>
              </tr>
            </tfoot>
          </Table>
        </div>
      </Card>

      <Modal show={modal === 'eliminar'} onHide={() => setModal(null)} centered>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            Eliminar borrador
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {errorModal && <Alert variant="danger">{errorModal}</Alert>}
          Se eliminará el borrador «{asiento.concepto}». La acción queda en la bitácora.
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setModal(null)}>
            Cancelar
          </Button>
          <Button variant="danger" onClick={eliminar} disabled={trabajando}>
            Eliminar
          </Button>
        </Modal.Footer>
      </Modal>

      <Modal show={modal === 'revertir'} onHide={() => setModal(null)} centered>
        <Form onSubmit={revertir}>
          <Modal.Header closeButton>
            <Modal.Title as="h2" className="h5">
              Revertir asiento {asiento.codigo}
            </Modal.Title>
          </Modal.Header>
          <Modal.Body>
            {errorModal && <Alert variant="danger">{errorModal}</Alert>}
            <p className="small text-muted">
              Se registrará y contabilizará un asiento nuevo con los cargos y abonos invertidos. El asiento original no se
              modifica.
            </p>
            <Form.Group className="mb-3" controlId="fecha-reversion">
              <Form.Label>Fecha de la reversión</Form.Label>
              <Form.Control
                type="date"
                min={asiento.fecha}
                value={reversion.fecha}
                onChange={(e) => setReversion({ ...reversion, fecha: e.target.value })}
                required
              />
            </Form.Group>
            <Form.Group controlId="motivo-reversion">
              <Form.Label>Motivo</Form.Label>
              <Form.Control
                as="textarea"
                rows={3}
                maxLength={250}
                value={reversion.motivo}
                onChange={(e) => setReversion({ ...reversion, motivo: e.target.value })}
                required
                autoFocus
              />
            </Form.Group>
          </Modal.Body>
          <Modal.Footer>
            <Button variant="secondary" onClick={() => setModal(null)}>
              Cancelar
            </Button>
            <Button type="submit" variant="warning" disabled={trabajando || !reversion.motivo.trim()}>
              Revertir
            </Button>
          </Modal.Footer>
        </Form>
      </Modal>
    </Container>
  )
}
