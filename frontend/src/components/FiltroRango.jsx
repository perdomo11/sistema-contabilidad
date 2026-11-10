import { Button, Col, Form } from 'react-bootstrap'
import { hoyISO } from '../formato'

/** Rango por defecto: del 1 de enero del año actual a hoy. */
export function rangoPorDefecto() {
  const hoy = hoyISO()
  return { desde: `${hoy.slice(0, 4)}-01-01`, hasta: hoy }
}

/** Campos "Desde" / "Hasta" para los filtros de los libros. */
export function CamposRango({ rango, onChange }) {
  return (
    <>
      <Col xs={6} md={2}>
        <Form.Label htmlFor="desde" className="small text-muted mb-1">
          Desde
        </Form.Label>
        <Form.Control
          id="desde"
          size="sm"
          type="date"
          value={rango.desde}
          onChange={(e) => onChange({ ...rango, desde: e.target.value })}
          required
        />
      </Col>
      <Col xs={6} md={2}>
        <Form.Label htmlFor="hasta" className="small text-muted mb-1">
          Hasta
        </Form.Label>
        <Form.Control
          id="hasta"
          size="sm"
          type="date"
          value={rango.hasta}
          onChange={(e) => onChange({ ...rango, hasta: e.target.value })}
          required
        />
      </Col>
    </>
  )
}

/** Botones Consultar / Exportar CSV / Imprimir. */
export function AccionesReporte({ onExportar, deshabilitado }) {
  return (
    <Col xs={12} md="auto" className="d-flex gap-1 ms-md-auto">
      <Button size="sm" type="submit">
        Consultar
      </Button>
      <Button size="sm" variant="outline-secondary" onClick={onExportar} disabled={deshabilitado}>
        Exportar CSV
      </Button>
      <Button size="sm" variant="outline-secondary" onClick={() => window.print()} disabled={deshabilitado}>
        Imprimir
      </Button>
    </Col>
  )
}
