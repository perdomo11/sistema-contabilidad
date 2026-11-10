import { Badge } from 'react-bootstrap'

/** Insignia de estado de un asiento (tonos suaves), incluida la condición de revertido. */
export default function EstadoAsiento({ asiento }) {
  if (asiento.estado === 'BORRADOR') {
    return (
      <Badge bg="warning-subtle" text="warning-emphasis">
        <i className="bi bi-pencil me-1" />
        Borrador
      </Badge>
    )
  }
  return (
    <span className="d-inline-flex flex-wrap gap-1">
      <Badge bg="success-subtle" text="success-emphasis">
        <i className="bi bi-check2 me-1" />
        Contabilizado
      </Badge>
      {asiento.tipo === 'REVERSION' && (
        <Badge bg="info-subtle" text="info-emphasis">
          <i className="bi bi-arrow-counterclockwise me-1" />
          Reversión
        </Badge>
      )}
      {asiento.revertido_por && (
        <Badge bg="secondary-subtle" text="secondary-emphasis">
          Revertido
        </Badge>
      )}
    </span>
  )
}
