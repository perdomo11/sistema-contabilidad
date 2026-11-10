import { useEffect, useState } from 'react'
import { Alert, Button, Form, Modal, Spinner } from 'react-bootstrap'
import { api } from '../api'

export const TIPOS = [
  ['ACTIVO', 'Activo'],
  ['PASIVO', 'Pasivo'],
  ['PATRIMONIO', 'Patrimonio'],
  ['INGRESO', 'Ingreso'],
  ['GASTO', 'Gasto'],
  ['ORDEN', 'Cuentas de orden y contingentes'],
]
export const NOMBRE_TIPO = Object.fromEntries(TIPOS)
const TIPOS_BALANCE = ['ACTIVO', 'PASIVO', 'PATRIMONIO', 'ORDEN']
const NATURALEZA_POR_TIPO = {
  ACTIVO: 'DEUDORA',
  GASTO: 'DEUDORA',
  ORDEN: 'DEUDORA',
  PASIVO: 'ACREEDORA',
  PATRIMONIO: 'ACREEDORA',
  INGRESO: 'ACREEDORA',
}


// Clasificación para reportes segmentados (T3.2/T3.3). Vacío = heredar de la cuenta padre.
export const RUBROS = {
  INGRESO: [
    ['INGRESO_OPERACION', 'Ingreso de operación'],
    ['INGRESO_NO_OPERACION', 'Ingreso no operacional'],
  ],
  GASTO: [
    ['COSTO_INTERMEDIACION', 'Costo de intermediación (costo de ventas)'],
    ['GASTO_OPERACION', 'Gasto de operación'],
    ['GASTO_NO_OPERACION', 'Gasto no operacional'],
  ],
}
const NOMBRE_RUBRO = Object.fromEntries([...RUBROS.INGRESO, ...RUBROS.GASTO])
const NOMBRE_COMPORTAMIENTO = { VARIABLE: 'Variable', FIJO: 'Fijo' }
const POR_DEFECTO = {
  INGRESO: { rubro_resultado: 'INGRESO_OPERACION', comportamiento_costo: null, controlable: null },
  GASTO: { rubro_resultado: 'GASTO_OPERACION', comportamiento_costo: 'FIJO', controlable: true },
}
const textoControlable = (v) => (v === true ? 'Controlable' : v === false ? 'No controlable' : '')
const aSelect = (v) => (v === true ? 'true' : v === false ? 'false' : '')
const deSelect = (v) => (v === 'true' ? true : v === 'false' ? false : null)

/**
 * Formulario de alta/edición de cuenta.
 * - Alta de raíz: cuenta = null, padre = null
 * - Alta de subcuenta: cuenta = null, padre = nodo padre
 * - Edición: cuenta = nodo a editar
 */
export default function CuentaFormModal({ show, cuenta, padre, onHide, onGuardada }) {
  const editando = Boolean(cuenta)
  const [datos, setDatos] = useState({})
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    if (!show) return
    setErrores({})
    if (editando) {
      setDatos({
        nombre: cuenta.nombre,
        naturaleza: cuenta.naturaleza,
        acepta_movimientos: cuenta.acepta_movimientos,
        exenta_centro_costo: cuenta.exenta_centro_costo,
        rubro_resultado: cuenta.rubro_resultado || '',
        comportamiento_costo: cuenta.comportamiento_costo || '',
        controlable: aSelect(cuenta.controlable),
      })
    } else {
      const tipo = padre?.tipo || 'ACTIVO'
      setDatos({
        codigo: padre?.codigo || '',
        nombre: '',
        tipo,
        naturaleza: padre?.naturaleza || NATURALEZA_POR_TIPO[tipo],
        acepta_movimientos: true,
        exenta_centro_costo: padre ? padre.exenta_centro_costo : false,
        rubro_resultado: '',
        comportamiento_costo: '',
        controlable: '',
      })
    }
  }, [show, cuenta, padre, editando])

  const tipo = editando ? cuenta.tipo : datos.tipo
  const permiteExencion = TIPOS_BALANCE.includes(tipo)
  const esResultado = tipo === 'INGRESO' || tipo === 'GASTO'
  // Lo que la cuenta recibe si deja un campo en "heredar".
  const heredada = editando
    ? cuenta.clasificacion_heredada
    : padre
      ? padre.clasificacion_efectiva
      : POR_DEFECTO[tipo]
  const cambiar = (campo, valor) => setDatos((d) => ({ ...d, [campo]: valor }))

  const cambiarTipo = (nuevo) =>
    setDatos((d) => ({
      ...d,
      tipo: nuevo,
      naturaleza: NATURALEZA_POR_TIPO[nuevo],
      exenta_centro_costo: TIPOS_BALANCE.includes(nuevo) ? d.exenta_centro_costo : false,
    }))

  const guardar = async (e) => {
    e.preventDefault()
    setGuardando(true)
    setErrores({})
    const clasificacion = esResultado
      ? {
          rubro_resultado: datos.rubro_resultado || null,
          comportamiento_costo: tipo === 'GASTO' ? datos.comportamiento_costo || null : null,
          controlable: tipo === 'GASTO' ? deSelect(datos.controlable) : null,
        }
      : { rubro_resultado: null, comportamiento_costo: null, controlable: null }
    const base = { ...datos, ...clasificacion }
    const cuerpo = editando ? base : { ...base, padre: padre?.id ?? null, tipo: padre ? undefined : datos.tipo }
    const resp = await api(editando ? `/api/cuentas/${cuenta.id}/` : '/api/cuentas/', {
      method: editando ? 'PATCH' : 'POST',
      body: cuerpo,
    })
    setGuardando(false)
    if (resp.ok) {
      onGuardada(await resp.json())
      return
    }
    const err = await resp.json().catch(() => ({ detail: `Error ${resp.status}` }))
    const porCampo = Object.fromEntries(
      Object.entries(err).map(([campo, msgs]) => [campo, [].concat(msgs).join(' ')]),
    )
    setErrores(porCampo)
  }

  const errorDe = (campo) =>
    errores[campo] && <Form.Control.Feedback type="invalid">{errores[campo]}</Form.Control.Feedback>
  const camposConocidos = [
    'codigo', 'nombre', 'tipo', 'naturaleza', 'acepta_movimientos', 'exenta_centro_costo',
    'rubro_resultado', 'comportamiento_costo', 'controlable',
  ]
  const erroresGenerales = Object.entries(errores).filter(([campo]) => !camposConocidos.includes(campo))

  let titulo = 'Nueva cuenta raíz'
  if (editando) titulo = `Editar cuenta ${cuenta.codigo}`
  else if (padre) titulo = `Nueva subcuenta de ${padre.codigo} ${padre.nombre}`

  return (
    <Modal show={show} onHide={onHide} centered>
      <Form onSubmit={guardar} noValidate>
        <Modal.Header closeButton>
          <Modal.Title as="h2" className="h5">
            {titulo}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body>
          {erroresGenerales.map(([campo, msg]) => (
            <Alert key={campo} variant="danger">
              {campo === 'detail' ? msg : `${campo}: ${msg}`}
            </Alert>
          ))}

          {!editando && (
            <Form.Group className="mb-3" controlId="cuenta-codigo">
              <Form.Label>Código</Form.Label>
              <Form.Control
                value={datos.codigo || ''}
                onChange={(e) => cambiar('codigo', e.target.value.replace(/\D/g, ''))}
                isInvalid={Boolean(errores.codigo)}
                inputMode="numeric"
                maxLength={20}
                required
                autoFocus
              />
              {errorDe('codigo')}
              {padre && <Form.Text>Debe empezar con {padre.codigo} y ser más largo.</Form.Text>}
            </Form.Group>
          )}

          <Form.Group className="mb-3" controlId="cuenta-nombre">
            <Form.Label>Nombre</Form.Label>
            <Form.Control
              value={datos.nombre || ''}
              onChange={(e) => cambiar('nombre', e.target.value)}
              isInvalid={Boolean(errores.nombre)}
              maxLength={200}
              required
              autoFocus={editando}
            />
            {errorDe('nombre')}
          </Form.Group>

          <Form.Group className="mb-3" controlId="cuenta-tipo">
            <Form.Label>Tipo</Form.Label>
            {editando || padre ? (
              <Form.Control value={NOMBRE_TIPO[tipo] || ''} disabled />
            ) : (
              <Form.Select
                value={datos.tipo || ''}
                onChange={(e) => cambiarTipo(e.target.value)}
                isInvalid={Boolean(errores.tipo)}
              >
                {TIPOS.map(([valor, texto]) => (
                  <option key={valor} value={valor}>
                    {texto}
                  </option>
                ))}
              </Form.Select>
            )}
            {errorDe('tipo')}
            {(editando || padre) && <Form.Text>El tipo se hereda de la cuenta raíz y no se modifica.</Form.Text>}
          </Form.Group>

          <Form.Group className="mb-3" controlId="cuenta-naturaleza">
            <Form.Label>Naturaleza</Form.Label>
            <Form.Select
              value={datos.naturaleza || ''}
              onChange={(e) => cambiar('naturaleza', e.target.value)}
              isInvalid={Boolean(errores.naturaleza)}
            >
              <option value="DEUDORA">Deudora</option>
              <option value="ACREEDORA">Acreedora</option>
            </Form.Select>
            {errorDe('naturaleza')}
          </Form.Group>

          <Form.Group className="mb-2" controlId="cuenta-movimientos">
            <Form.Check
              type="switch"
              label="Acepta movimientos (cuenta de detalle)"
              checked={Boolean(datos.acepta_movimientos)}
              onChange={(e) => cambiar('acepta_movimientos', e.target.checked)}
              isInvalid={Boolean(errores.acepta_movimientos)}
              feedback={errores.acepta_movimientos}
              feedbackType="invalid"
            />
            <Form.Text>Desactívelo si la cuenta va a agrupar subcuentas.</Form.Text>
          </Form.Group>

          <Form.Group controlId="cuenta-exenta">
            <Form.Check
              type="switch"
              label="Exenta de centro de costo"
              checked={Boolean(datos.exenta_centro_costo)}
              onChange={(e) => cambiar('exenta_centro_costo', e.target.checked)}
              disabled={!permiteExencion}
              isInvalid={Boolean(errores.exenta_centro_costo)}
              feedback={errores.exenta_centro_costo}
              feedbackType="invalid"
            />
            {!permiteExencion && <Form.Text>Las cuentas de ingreso y gasto siempre exigen centro de costo.</Form.Text>}
          </Form.Group>

          {esResultado && heredada && (
            <fieldset className="border rounded p-3 mt-3">
              <legend className="float-none w-auto px-2 fs-6 mb-0">Clasificación para reportes</legend>
              <Form.Text className="d-block mb-2">
                Las subcuentas heredan estos valores. Úselos en las cuentas de agrupación (51, 52…) y cambie solo las excepciones.
              </Form.Text>
              <Form.Group className="mb-2" controlId="cuenta-rubro">
                <Form.Label className="small mb-1">Rubro (márgenes bruto y operativo)</Form.Label>
                <Form.Select
                  size="sm"
                  value={datos.rubro_resultado || ''}
                  onChange={(e) => cambiar('rubro_resultado', e.target.value)}
                  isInvalid={Boolean(errores.rubro_resultado)}
                >
                  <option value="">Heredar: {NOMBRE_RUBRO[heredada.rubro_resultado]}</option>
                  {RUBROS[tipo].map(([v, t]) => (
                    <option key={v} value={v}>
                      {t}
                    </option>
                  ))}
                </Form.Select>
                {errorDe('rubro_resultado')}
              </Form.Group>
              {tipo === 'GASTO' && (
                <div className="d-flex gap-2">
                  <Form.Group className="flex-fill" controlId="cuenta-comportamiento">
                    <Form.Label className="small mb-1">Comportamiento del costo</Form.Label>
                    <Form.Select
                      size="sm"
                      value={datos.comportamiento_costo || ''}
                      onChange={(e) => cambiar('comportamiento_costo', e.target.value)}
                      isInvalid={Boolean(errores.comportamiento_costo)}
                    >
                      <option value="">Heredar: {NOMBRE_COMPORTAMIENTO[heredada.comportamiento_costo]}</option>
                      <option value="VARIABLE">Variable</option>
                      <option value="FIJO">Fijo</option>
                    </Form.Select>
                    {errorDe('comportamiento_costo')}
                  </Form.Group>
                  <Form.Group className="flex-fill" controlId="cuenta-controlable">
                    <Form.Label className="small mb-1">Controlabilidad</Form.Label>
                    <Form.Select
                      size="sm"
                      value={datos.controlable ?? ''}
                      onChange={(e) => cambiar('controlable', e.target.value)}
                      isInvalid={Boolean(errores.controlable)}
                    >
                      <option value="">Heredar: {textoControlable(heredada.controlable)}</option>
                      <option value="true">Controlable</option>
                      <option value="false">No controlable</option>
                    </Form.Select>
                    {errorDe('controlable')}
                  </Form.Group>
                </div>
              )}
              {tipo === 'GASTO' && (
                <Form.Text className="d-block mt-2">
                  Variable: cambia con el volumen de actividad. Controlable: el responsable del centro decide sobre él.
                </Form.Text>
              )}
            </fieldset>
          )}
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
