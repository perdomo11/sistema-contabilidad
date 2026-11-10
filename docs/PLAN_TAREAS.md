# Plan de tareas

Trabajar una tarea a la vez; validar antes de avanzar.

## Bloque 0: Fundamentos
- **T0.1** Entorno: Docker (Oracle XE, Django, React), endpoint `/api/health/`, pantalla de verificación
- **T0.2** Autenticación JWT, roles (Contador, Tesorero, Jefe de área, Auditor) y bitácora de auditoría

## Bloque 1: Núcleo contable
- **T1.1** Catálogo de cuentas jerárquico
- **T1.2** Periodos contables (apertura/cierre)
- **T1.3** Asientos y líneas con validación de partida doble (e inmutabilidad/reversión)
- **T1.4** Libro diario, mayor y balanza de comprobación

## Bloque 2: Centros de costo (Objetivo específico 1)
- **T2.1** Jerarquía de centros (departamentos, sucursales, proyectos), tipos y vigencia
- **T2.2** Asignación directa y por regla (cuenta→centro, proveedor→centro)
- **T2.3** Motor de prorrateo con bases configurables (m², personal, transacciones), con trazabilidad al asiento de origen

## Bloque 3: Reportes segmentados (Objetivos 2 y 5)
- **T3.1** Estado de resultados por centro (costeo absorbente)
- **T3.2** Enfoque de contribución (Tabla 1 del documento base)
- **T3.3** Indicadores de rentabilidad por área (margen bruto, operativo, de contribución, participación en el resultado)

## Bloque 4: Presupuesto (top-down)
- **T4.1** Presupuesto institucional anual definido por la gerencia
- **T4.2** Distribución del monto institucional a departamentos (valida que la suma no exceda; muestra saldo sin distribuir)
- **T4.3** Ejecución vs. presupuesto y alertas de desviación

## Bloque 5: Tesorería (Objetivos 3 y 4)
- **T5.1** Proveedores y cuentas por pagar con vencimientos
- **T5.2** Proyección de egresos a 30/60/90 días
- **T5.3** Flujo de efectivo actual y proyectado con alertas de déficit
- **T5.4** Dashboard de tesorería

## Bloque 6: Cierre
- **T6.1** Pruebas, respaldos, manuales
