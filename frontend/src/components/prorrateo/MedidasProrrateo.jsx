import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Col, Form, Modal, Row, Spinner, Table } from 'react-bootstrap'
import { api, mensajeError } from '../../api'
import EstadoVacio from '../EstadoVacio'
import SelectorPeriodo from '../SelectorPeriodo'

const numero = (v) => Number(v).toLocaleString('es-SV', { maximumFractionDigits: 4 })
const valido = (v) => v === '' || /^\d+(\.\d{0,4})?$/.test(v)

/** Alta y edición de una base de prorrateo. */
function BaseModal({ show, base, onHide, onGuardado }) {
  const editando = Boolean(base)
  const [datos, setDatos] = useState({})
  const [errores, setErrores] = useState({})

  useEffect(() => {
    if (!show) return
    setErrores({})
    setDatos(editando ? { nombre: base.nombre, unidad: base.unidad, activa: base.activa } : { codigo: '', nombre: '', unidad: '', activa: true })
  }, [show, base, editando])

  const cambiar = (campo, valor) => setDatos((d) => ({ ...d, [campo]: valor }))
  const guardar = async (e) => {
    e.preventDefault()
    const resp = await api(editando ? `/api/prorrateo/bases/${base.id}/` : '/api/prorrateo/bases/', {
      method: editando ? 'PATCH' : 'POST',
      body: datos,
    })
    if (resp.ok) return onGuardado(await resp.json())
    const err = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
    setErrores(Object.fromEntries(Object.entries(err).map(([c, m]) => [c, [].concat(m).join(' ')])))
  }
  const error = (c) => errores[c] && <Form.Control.Feedback type="invalid">{errores[c]}</Form.Control.Feedback>

  return (
    <Modal show={show} onHide={onHide} centered>
      <Form onSubmit={guardar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            {editando ? `Editar base ${base.codigo}` : 'Nueva base de prorrateo'}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {errores.detail && <Alert variant="danger">{errores.detail}</Alert>}
          <Row className="g-3">
            {!editando && (
              <Col xs={12}>
                <Form.Group controlId="base-codigo">
                  <Form.Label>Código</Form.Label>
                  <Form.Control
                    value={datos.codigo || ''}
                    maxLength={20}
                    placeholder="METROS2"
                    onChange={(e) => cambiar('codigo', e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ''))}
                    isInvalid={Boolean(errores.codigo)}
                    autoFocus
                  />
                  {error('codigo')}
                </Form.Group>
              </Col>
            )}
            <Col md={8}>
              <Form.Group controlId="base-nombre">
                <Form.Label>Nombre</Form.Label>
                <Form.Control
                  value={datos.nombre || ''}
                  maxLength={100}
                  onChange={(e) => cambiar('nombre', e.target.value)}
                  isInvalid={Boolean(errores.nombre)}
                />
                {error('nombre')}
              </Form.Group>
            </Col>
            <Col md={4}>
              <Form.Group controlId="base-unidad">
                <Form.Label>Unidad</Form.Label>
                <Form.Control
                  value={datos.unidad || ''}
                  maxLength={30}
                  placeholder="m²"
                  onChange={(e) => cambiar('unidad', e.target.value)}
                  isInvalid={Boolean(errores.unidad)}
                />
                {error('unidad')}
              </Form.Group>
            </Col>
            <Col xs={12}>
              <Form.Check type="switch" id="base-activa" label="Activa" checked={Boolean(datos.activa)} onChange={(e) => cambiar('activa', e.target.checked)} />
            </Col>
          </Row>
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={onHide}>
            Cancelar
          </Button>
          <Button type="submit">Guardar</Button>
        </Modal.Footer>
      </Form>
    </Modal>
  )
}

export default function MedidasProrrateo({ periodos, periodo, onPeriodo, puedeEditar }) {
  const [bases, setBases] = useState(null)
  const [base, setBase] = useState(null)
  const [cuadricula, setCuadricula] = useState(null)
  const [valores, setValores] = useState({})
  const [error, setError] = useState('')
  const [aviso, setAviso] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [modalBase, setModalBase] = useState({ show: false, base: null })

  const cargarBases = useCallback(async () => {
    const resp = await api('/api/prorrateo/bases/')
    const lista = resp.ok ? await resp.json() : []
    setBases(lista)
    setBase((actual) => actual ?? lista[0]?.id ?? null)
  }, [])

  useEffect(() => {
    cargarBases()
  }, [cargarBases])

  const aplicar = (datos) => {
    setCuadricula(datos)
    setValores(Object.fromEntries(datos.filas.map((f) => [f.centro_costo, f.valor === null ? '' : String(Number(f.valor))])))
  }

  const cargar = useCallback(async () => {
    if (!base || !periodo) return
    setCuadricula(null)
    const resp = await api(`/api/prorrateo/medidas/?base=${base}&periodo=${periodo}`)
    if (!resp.ok) return setError(await mensajeError(resp))
    aplicar(await resp.json())
  }, [base, periodo])

  useEffect(() => {
    cargar()
  }, [cargar])

  const notificar = (texto) => {
    setError('')
    setAviso(texto)
  }

  const guardar = async () => {
    setGuardando(true)
    const cuerpo = {
      base,
      periodo,
      valores: cuadricula.filas.map((f) => ({ centro_costo: f.centro_costo, valor: valores[f.centro_costo] ?? '' })),
    }
    const resp = await api('/api/prorrateo/medidas/', { method: 'PUT', body: cuerpo })
    setGuardando(false)
    if (!resp.ok) return setError(await mensajeError(resp))
    aplicar(await resp.json())
    notificar('Medidas guardadas.')
  }

  const copiar = async () => {
    setGuardando(true)
    const resp = await api('/api/prorrateo/medidas/copiar/', { method: 'POST', body: { base, periodo } })
    setGuardando(false)
    if (!resp.ok) return setError(await mensajeError(resp))
    const datos = await resp.json()
    aplicar(datos)
    notificar(`Se copiaron ${datos.copiadas} medida(s) del periodo anterior.`)
  }

  const datosBase = bases?.find((b) => b.id === base)
  const total = Object.values(valores).reduce((t, v) => t + (valido(v) && v !== '' ? Number(v) : 0), 0)
  const hayInvalidos = Object.values(valores).some((v) => !valido(v))
  const editable = puedeEditar && cuadricula?.editable

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
            <Card.Header className="d-flex justify-content-between align-items-center bg-transparent">
              <span className="fw-semibold">Bases</span>
              {puedeEditar && (
                <Button size="sm" variant="outline-primary" onClick={() => setModalBase({ show: true, base: null })}>
                  <i className="bi bi-plus-lg" /> Nueva
                </Button>
              )}
            </Card.Header>
            {!bases ? (
              <Card.Body>
                <Spinner animation="border" size="sm" />
              </Card.Body>
            ) : (
              <div className="list-group list-group-flush">
                {bases.map((b) => (
                  <div
                    key={b.id}
                    role="button"
                    tabIndex={0}
                    className={`list-group-item list-group-item-action d-flex justify-content-between align-items-center ${b.id === base ? 'active' : ''}`}
                    onClick={() => setBase(b.id)}
                    onKeyDown={(e) => e.key === 'Enter' && setBase(b.id)}
                  >
                    <span>
                      <div>{b.nombre}</div>
                      <small className={b.id === base ? '' : 'text-suave'}>
                        <code className="text-reset">{b.codigo}</code> · {b.unidad}
                        {!b.activa && ' · inactiva'}
                      </small>
                    </span>
                    {puedeEditar && (
                      <Button
                        size="sm"
                        variant={b.id === base ? 'light' : 'outline-secondary'}
                        title="Editar base"
                        onClick={(e) => {
                          e.stopPropagation()
                          setModalBase({ show: true, base: b })
                        }}
                      >
                        <i className="bi bi-pencil" />
                      </Button>
                    )}
                  </div>
                ))}
                {bases.length === 0 && <div className="list-group-item small text-suave">No hay bases.</div>}
              </div>
            )}
          </Card>
        </Col>

        <Col lg={8}>
          <Card className="mb-3">
            <Card.Body>
              <Row className="g-2 align-items-end">
                <Col xs={12} md={5}>
                  <Form.Label htmlFor="periodo-medidas" className="small text-suave mb-1">
                    Periodo
                  </Form.Label>
                  <SelectorPeriodo id="periodo-medidas" periodos={periodos} valor={periodo} onChange={onPeriodo} />
                </Col>
                {editable && (
                  <Col xs={12} md="auto" className="ms-md-auto d-flex gap-2">
                    <Button variant="outline-secondary" size="sm" disabled={guardando} onClick={copiar}>
                      <i className="bi bi-files me-1" /> Copiar del periodo anterior
                    </Button>
                    <Button size="sm" disabled={guardando || hayInvalidos} onClick={guardar}>
                      {guardando && <Spinner animation="border" size="sm" className="me-2" />}
                      Guardar medidas
                    </Button>
                  </Col>
                )}
              </Row>
              {puedeEditar && cuadricula && !cuadricula.editable && (
                <div className="small text-suave mt-2">
                  <i className="bi bi-lock me-1" />
                  Solo lectura: el periodo está cerrado o la base ya se usó en un prorrateo ejecutado (anúlelo para cambiar las medidas).
                </div>
              )}
            </Card.Body>
          </Card>

          {!datosBase ? (
            <EstadoVacio icono="bi-rulers">Cree una base de prorrateo para capturar medidas.</EstadoVacio>
          ) : !cuadricula ? (
            <Spinner animation="border" />
          ) : (
            <Card className="mb-4">
              <div className="table-responsive">
                <Table size="sm" className="align-middle mb-0">
                  <thead className="table-light">
                    <tr className="small text-uppercase text-muted">
                      <th>Centro de costo</th>
                      <th className="text-end" style={{ width: '11rem' }}>
                        {datosBase.unidad}
                      </th>
                      <th className="text-end" style={{ width: '7rem' }}>
                        %
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {cuadricula.filas.map((f) => {
                      const v = valores[f.centro_costo] ?? ''
                      const n = valido(v) && v !== '' ? Number(v) : 0
                      return (
                        <tr key={f.centro_costo}>
                          <td>
                            <code className="me-2">{f.codigo}</code>
                            {f.nombre}
                          </td>
                          <td>
                            {editable ? (
                              <Form.Control
                                size="sm"
                                className="text-end font-monospace"
                                inputMode="decimal"
                                value={v}
                                isInvalid={!valido(v)}
                                aria-label={`${datosBase.unidad} de ${f.codigo}`}
                                onChange={(e) => setValores((vs) => ({ ...vs, [f.centro_costo]: e.target.value.trim() }))}
                              />
                            ) : (
                              <div className="monto">{v === '' ? <span className="text-suave">—</span> : numero(v)}</div>
                            )}
                          </td>
                          <td className="monto small text-suave">{total > 0 && n > 0 ? `${((n * 100) / total).toFixed(2)} %` : ''}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                  <tfoot className="table-light">
                    <tr className="fw-semibold">
                      <td>Total</td>
                      <td className="monto">{numero(total)}</td>
                      <td className="monto">{total > 0 ? '100.00 %' : ''}</td>
                    </tr>
                  </tfoot>
                </Table>
              </div>
              <Card.Footer className="small text-suave bg-transparent">
                <Badge bg="info-subtle" text="info-emphasis" className="me-2">
                  Nota
                </Badge>
                Los porcentajes de cada regla se calculan solo entre sus centros destino. Deje vacío un centro que no aplique.
              </Card.Footer>
            </Card>
          )}
        </Col>
      </Row>

      <BaseModal
        show={modalBase.show}
        base={modalBase.base}
        onHide={() => setModalBase({ show: false, base: null })}
        onGuardado={(b) => {
          notificar(`Base ${b.codigo} guardada.`)
          setModalBase({ show: false, base: null })
          setBase(b.id)
          cargarBases()
        }}
      />
    </>
  )
}
