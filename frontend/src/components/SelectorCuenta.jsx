import { useEffect, useMemo, useRef, useState } from 'react'
import { Form, ListGroup } from 'react-bootstrap'

const normalizar = (t) =>
  t
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')

const etiqueta = (c) => (c ? `${c.codigo} · ${c.nombre}` : '')

/**
 * Buscador de cuentas de detalle por código o nombre.
 * `cuentas`: [{id, codigo, nombre}], `valor`: cuenta seleccionada ({id, codigo, nombre}) o null.
 */
export default function SelectorCuenta({ cuentas, valor, onChange, isInvalid, id }) {
  const [texto, setTexto] = useState(etiqueta(valor))
  const [abierto, setAbierto] = useState(false)
  const [activo, setActivo] = useState(0)
  const contenedor = useRef(null)

  useEffect(() => setTexto(etiqueta(valor)), [valor])

  const opciones = useMemo(() => {
    const q = normalizar(texto.trim())
    if (!q || texto === etiqueta(valor)) return cuentas.slice(0, 50)
    return cuentas.filter((c) => c.codigo.startsWith(q) || normalizar(c.nombre).includes(q)).slice(0, 50)
  }, [texto, cuentas, valor])

  const elegir = (cuenta) => {
    onChange(cuenta)
    setTexto(etiqueta(cuenta))
    setAbierto(false)
  }

  const alSalir = (e) => {
    if (contenedor.current?.contains(e.relatedTarget)) return
    setAbierto(false)
    setTexto(etiqueta(valor)) // descarta texto que no corresponde a una cuenta
  }

  const teclado = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setAbierto(true)
      setActivo((i) => Math.min(i + 1, opciones.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActivo((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && abierto && opciones[activo]) {
      e.preventDefault()
      elegir(opciones[activo])
    } else if (e.key === 'Escape') {
      setAbierto(false)
    }
  }

  return (
    <div ref={contenedor} className="position-relative" onBlur={alSalir}>
      <Form.Control
        id={id}
        size="sm"
        value={texto}
        placeholder="Código o nombre de la cuenta"
        isInvalid={isInvalid}
        autoComplete="off"
        onFocus={(e) => {
          setAbierto(true)
          e.target.select()
        }}
        onChange={(e) => {
          setTexto(e.target.value)
          setAbierto(true)
          setActivo(0)
        }}
        onKeyDown={teclado}
      />
      {abierto && (
        <ListGroup
          className="position-absolute w-100 shadow-sm overflow-auto"
          style={{ zIndex: 1050, maxHeight: '16rem', minWidth: '20rem' }}
        >
          {opciones.length === 0 && <ListGroup.Item className="small text-muted">Sin coincidencias</ListGroup.Item>}
          {opciones.map((c, i) => (
            <ListGroup.Item
              key={c.id}
              action
              active={i === activo}
              className="small py-1"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => elegir(c)}
            >
              <code className={i === activo ? 'text-white' : ''}>{c.codigo}</code> {c.nombre}
            </ListGroup.Item>
          ))}
        </ListGroup>
      )}
    </div>
  )
}
