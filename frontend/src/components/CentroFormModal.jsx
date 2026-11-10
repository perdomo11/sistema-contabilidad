import { useEffect, useState } from 'react'
import { Alert, Button, Col, Form, Modal, Row, Spinner } from 'react-bootstrap'
import { api } from '../api'
import { hoyISO } from '../formato'

export const TIPOS_CENTRO = [
  ['COSTO', 'Centro de costo'],
  ['INGRESO', 'Centro de ingreso'],
  ['UTILIDAD', 'Centro de utilidad'],
  ['INVERSION', 'Centro de inversión'],
]
export const CLASES_CENTRO = [
  ['SUCURSAL', 'Sucursal'],
  ['DEPARTAMENTO', 'Departamento'],
  ['AREA', 'Área'],
  ['PROYECTO', 'Proyecto'],
]

/** Alta (raíz o subunidad) y edición de un centro de costo. */
export default function CentroFormModal({ show, centro, padre, onHide, onGuardado }) {
  const editando = Boolean(centro)
  const [datos, setDatos] = useState({})
  const [usuarios, setUsuarios] = useState([])
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!show) return
    setErrores({})
    api('/api/usuarios/').then(async (r) => setUsuarios(r.ok ? await r.json() : []))
    if (editando) {
      setDatos({
        nombre: centro.nombre,
        tipo: centro.tipo,
        clase: centro.clase,
        responsable: centro.responsable ?? '',
        acepta_movimientos: centro.acepta_movimientos,
        vigente_desde: centro.vigente_desde,
        vigente_hasta: centro.vigente_hasta ?? '',
      })
    } else {
      setDatos({
        codigo: padre ? `${padre.codigo}-` : '',
        nombre: '',
        tipo: 'COSTO',
        clase: padre ? 'DEPARTAMENTO' : 'SUCURSAL',
        responsable: '',
        acepta_movimientos: true,
        vigente_desde: padre?.vigente_desde > hoyISO() ? padre.vigente_desde : hoyISO(),
        vigente_hasta: '',
      })
    }
  }, [show, centro, padre, editando])

  const cambiar = (campo, valor) => setDatos((d) => ({ ...d, [campo]: valor }))

  const guardar = async (e) => {
    e.preventDefault()
    setGuardando(true)
    setErrores({})
    const cuerpo = {
      ...datos,
      responsable: datos.responsable === '' ? null : Number(datos.responsable),
      vigente_hasta: datos.vigente_hasta || null,
      ...(!editando && { padre: padre?.id ?? null }),
    }
    const resp = await api(editando ? `/api/centros-costo/${centro.id}/` : '/api/centros-costo/', {
      method: editando ? 'PATCH' : 'POST',
      body: cuerpo,
    })
    setGuardando(false)
    if (resp.ok) return onGuardado(await resp.json())
    const err = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
    setErrores(Object.fromEntries(Object.entries(err).map(([c, m]) => [c, [].concat(m).join(' ')])))
  }

  const conocidos = ['codigo', 'nombre', 'tipo', 'clase', 'responsable', 'vigente_desde', 'vigente_hasta', 'acepta_movimientos']
  const generales = Object.entries(errores).filter(([c]) => !conocidos.includes(c))
  const error = (campo) =>
    errores[campo] && <Form.Control.Feedback type="invalid">{errores[campo]}</Form.Control.Feedback>

  let titulo = 'Nueva unidad raíz'
  if (editando) titulo = `Editar ${centro.codigo} ${centro.nombre}`
  else if (padre) titulo = `Nueva subunidad de ${padre.codigo} ${padre.nombre}`

  return (
    <Modal show={show} onHide={onHide} centered size="lg">
      <Form onSubmit={guardar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            {titulo}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {generales.map(([c, m]) => (
            <Alert key={c} variant="danger">
              {m}
            </Alert>
          ))}
          <Row className="g-3">
            {!editando && (
              <Col md={4}>
                <Form.Group controlId="centro-codigo">
                  <Form.Label>Código</Form.Label>
                  <Form.Control
                    value={datos.codigo || ''}
                    onChange={(e) => cambiar('codigo', e.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, ''))}
                    isInvalid={Boolean(errores.codigo)}
                    maxLength={20}
                    autoFocus
                  />
                  {error('codigo')}
                  {padre && <Form.Text>Debe empezar con {padre.codigo}.</Form.Text>}
                </Form.Group>
              </Col>
            )}
            <Col md={editando ? 12 : 8}>
              <Form.Group controlId="centro-nombre">
                <Form.Label>Nombre</Form.Label>
                <Form.Control
                  value={datos.nombre || ''}
                  maxLength={150}
                  onChange={(e) => cambiar('nombre', e.target.value)}
                  isInvalid={Boolean(errores.nombre)}
                />
                {error('nombre')}
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group controlId="centro-tipo">
                <Form.Label>Tipo de centro</Form.Label>
                <Form.Select value={datos.tipo || ''} onChange={(e) => cambiar('tipo', e.target.value)}>
                  {TIPOS_CENTRO.map(([v, t]) => (
                    <option key={v} value={v}>
                      {t}
                    </option>
                  ))}
                </Form.Select>
                <Form.Text>Define qué controla el responsable: costos, ingresos, utilidad o inversión.</Form.Text>
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group controlId="centro-clase">
                <Form.Label>Clase</Form.Label>
                <Form.Select value={datos.clase || ''} onChange={(e) => cambiar('clase', e.target.value)}>
                  {CLASES_CENTRO.map(([v, t]) => (
                    <option key={v} value={v}>
                      {t}
                    </option>
                  ))}
                </Form.Select>
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group controlId="centro-responsable">
                <Form.Label>Responsable</Form.Label>
                <Form.Select
                  value={datos.responsable ?? ''}
                  onChange={(e) => cambiar('responsable', e.target.value)}
                  isInvalid={Boolean(errores.responsable)}
                >
                  <option value="">Sin responsable</option>
                  {usuarios.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.nombre}
                      {u.roles.length ? ` (${u.roles.join(', ')})` : ''}
                    </option>
                  ))}
                </Form.Select>
                {error('responsable')}
              </Form.Group>
            </Col>
            <Col md={3}>
              <Form.Group controlId="centro-desde">
                <Form.Label>Vigente desde</Form.Label>
                <Form.Control
                  type="date"
                  value={datos.vigente_desde || ''}
                  onChange={(e) => cambiar('vigente_desde', e.target.value)}
                  isInvalid={Boolean(errores.vigente_desde)}
                />
                {error('vigente_desde')}
              </Form.Group>
            </Col>
            <Col md={3}>
              <Form.Group controlId="centro-hasta">
                <Form.Label>Vigente hasta</Form.Label>
                <Form.Control
                  type="date"
                  value={datos.vigente_hasta || ''}
                  onChange={(e) => cambiar('vigente_hasta', e.target.value)}
                  isInvalid={Boolean(errores.vigente_hasta)}
                />
                {error('vigente_hasta')}
                <Form.Text>Vacío = indefinida.</Form.Text>
              </Form.Group>
            </Col>
            <Col xs={12}>
              <Form.Check
                type="switch"
                id="centro-movimientos"
                label="Recibe movimientos (unidad de detalle)"
                checked={Boolean(datos.acepta_movimientos)}
                onChange={(e) => cambiar('acepta_movimientos', e.target.checked)}
                isInvalid={Boolean(errores.acepta_movimientos)}
                feedback={errores.acepta_movimientos}
                feedbackType="invalid"
              />
              <Form.Text>Desactívelo si la unidad agrupará subunidades (sucursal, gerencia, etc.).</Form.Text>
            </Col>
          </Row>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={onHide}>
            Cancelar
          </Button>
          <Button type="submit" disabled={guardando}>
            {guardando && <Spinner animation="border" size="sm" className="me-2" />}
            Guardar
          </Button>
        </Modal.Footer>
      </Form>
    </Modal>
  )
}
