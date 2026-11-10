import { Fragment } from 'react'
import { Link } from 'react-router-dom'

/**
 * Encabezado común de las pantallas.
 * - migas: [{texto, a?}] (la última suele no tener enlace)
 * - children: acciones (botones) alineadas a la derecha
 */
export default function EncabezadoPagina({ titulo, descripcion, migas, children }) {
  return (
    <div className="encabezado-pagina d-flex flex-wrap justify-content-between align-items-end gap-2">
      <div>
        {migas && (
          <div className="migas no-imprimir">
            {migas.map((m, i) => (
              <Fragment key={i}>
                {i > 0 && <i className="bi bi-chevron-right mx-1" style={{ fontSize: '0.65rem' }} />}
                {m.a ? <Link to={m.a}>{m.texto}</Link> : <span>{m.texto}</span>}
              </Fragment>
            ))}
          </div>
        )}
        <h1>{titulo}</h1>
        {descripcion && <div className="text-suave small mt-1 no-imprimir">{descripcion}</div>}
      </div>
      {children && <div className="d-flex flex-wrap gap-2 no-imprimir">{children}</div>}
    </div>
  )
}
