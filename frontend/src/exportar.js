/**
 * Descarga un CSV compatible con Excel en español: separador ";", UTF-8 con BOM
 * y montos con punto decimal sin separador de miles.
 */
export function descargarCSV(nombreArchivo, encabezados, filas) {
  const celda = (valor) => {
    const texto = valor === null || valor === undefined ? '' : String(valor)
    return /[";\n\r]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto
  }
  const lineas = [encabezados, ...filas].map((fila) => fila.map(celda).join(';'))
  const blob = new Blob(['﻿' + lineas.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombreArchivo
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  URL.revokeObjectURL(url)
}
