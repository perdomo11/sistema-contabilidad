// Formato de montos y fechas. Los montos llegan de la API como texto ("1500.00")
// y se suman en centavos enteros para no arrastrar errores de punto flotante.

const numero = new Intl.NumberFormat('es-SV', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** "1500.5" → 150050 (centavos). Texto vacío o inválido → 0. */
export function aCentavos(valor) {
  if (valor === null || valor === undefined || valor === '') return 0
  const texto = String(valor).replace(/,/g, '').trim()
  if (!/^\d*(\.\d{0,2})?$/.test(texto) || texto === '.') return NaN
  const [enteros, decimales = ''] = texto.split('.')
  return Number(enteros || 0) * 100 + Number((decimales + '00').slice(0, 2))
}

/** 150050 → "1,500.50" */
export function centavosATexto(centavos) {
  return numero.format(centavos / 100)
}

/** "1500.50" → "1,500.50"; cero o vacío → "" si `vacioSiCero`. */
export function formatoMonto(valor, { vacioSiCero = false } = {}) {
  const centavos = aCentavos(valor)
  if (Number.isNaN(centavos)) return String(valor)
  if (vacioSiCero && centavos === 0) return ''
  return centavosATexto(centavos)
}

/** "2026-03-15" → "15/03/2026" */
export function formatoFecha(iso) {
  if (!iso) return ''
  const [a, m, d] = iso.slice(0, 10).split('-')
  return `${d}/${m}/${a}`
}

const fechaHora = new Intl.DateTimeFormat('es-SV', {
  dateStyle: 'short',
  timeStyle: 'short',
  timeZone: 'America/El_Salvador',
})

export function formatoFechaHora(iso) {
  return iso ? fechaHora.format(new Date(iso)) : ''
}

/** Fecha de hoy en El Salvador como "YYYY-MM-DD". */
export function hoyISO() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/El_Salvador' }).format(new Date())
}
