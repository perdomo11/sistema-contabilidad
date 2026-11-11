# Sistema Contable: Centros de Costo, Presupuesto y Flujo de Efectivo

## Qué es
Sistema informático contable para un **banco** (caso de uso). Automatiza la asignación de partidas contables a centros de costo, distribuye el presupuesto institucional a departamentos (top-down), genera estados de resultados segmentados y proyecta el flujo de efectivo.

Documento base completo (marco teórico, objetivos, propuesta): `docs/DOCUMENTO_BASE.md`. **Léelo antes de diseñar cualquier módulo.**
Plan de trabajo por tareas: `docs/PLAN_TAREAS.md`. Especificación de cada tarea: `docs/tareas/`.

## Stack
- **Backend:** Django 5.2 + Django REST Framework, driver `oracledb`, Python 3.12
- **Frontend:** React 18 (Vite) + Bootstrap 5 / React-Bootstrap
- **Base de datos:** Oracle XE 21c (imagen `gvenzl/oracle-xe:21-slim`), servicio `XEPDB1`
- **Despliegue:** Docker Compose (3 servicios: `oracle-db`, `backend`, `frontend`). Todo debe levantar con `docker compose up --build`.
- **Auth (T0.2):** JWT + roles (Contador, Tesorero, Jefe de área, Auditor) + bitácora de auditoría

## Cómo trabajamos
- Trabajo **por tareas pequeñas y validables** (T0.1, T0.2, ...). **Una tarea a la vez**, un commit por tarea con el mensaje `T#.#: descripción`.
- Al terminar cada tarea: indicar cómo validarla (checklist) y **esperar confirmación** antes de pasar a la siguiente.
- No implementar tareas futuras por adelantado.
- Idioma de la interfaz, mensajes y documentación: **español**. Nombres de código (modelos, variables): español técnico contable o inglés, pero consistente (ver convenciones).

## Reglas contables NO negociables
1. **Montos en `DecimalField(max_digits=18, decimal_places=2)`** (Oracle `NUMBER(18,2)`). Nunca `float`.
2. **Partida doble:** total cargos = total abonos, validado en servicio **y** a nivel de base de datos antes de confirmar un asiento.
3. **Cada línea de asiento lleva centro de costo** (dimensión analítica obligatoria), salvo cuentas de balance que se definan explícitamente como exentas.
4. **Asientos inmutables** una vez contabilizados. Las correcciones se hacen con **asiento de reversión**, nunca editando ni borrando.
5. **Trazabilidad:** toda línea generada por prorrateo conserva referencia al asiento/línea de origen. Todo cambio guarda usuario y marca de tiempo.
6. **Periodos contables:** no se puede registrar en un periodo cerrado.
7. **Catálogo de cuentas jerárquico** (padre-hijo, profundidad variable).
8. **Centros de costo jerárquicos** con vigencia temporal (fecha desde/hasta) para no invalidar historia. Tipos: costo, ingreso, utilidad, inversión.
9. **Bitácora de auditoría** de acciones sensibles (quién, qué, cuándo, valor anterior/nuevo).

## Presupuesto (Bloque 4): modelo TOP-DOWN
La gerencia fija el **monto institucional** por ejercicio y luego lo **distribuye a cada departamento** (centro de costo), y dentro de este por cuenta/mes. Reglas:
- La suma de lo distribuido a departamentos no puede exceder el monto institucional.
- Debe mostrarse el saldo sin distribuir.
- Cambios de presupuesto quedan versionados y auditados.
- Más adelante: ejecución vs. presupuesto y alertas de desviación.

Implementación por tareas: T4.1 monto institucional, T4.2 distribución, T4.3 ejecución y alertas.

## Módulos (resumen; detalle en `docs/PLAN_TAREAS.md`)
- **B0** Fundamentos: entorno Docker, auth/roles/bitácora
- **B1** Núcleo contable: catálogo de cuentas, periodos, asientos, diario/mayor/balanza
- **B2** Centros de costo: jerarquía, asignación directa y por regla, motor de prorrateo (bases: m², personal, transacciones)
- **B3** Reportes segmentados: costeo absorbente, enfoque de contribución (Tabla 1 del documento), indicadores
- **B4** Presupuesto top-down y ejecución
- **B5** Tesorería: cuentas por pagar, proyección de egresos 30/60/90 días, flujo de efectivo con alertas de déficit, dashboard
- **B6** Cierre: pruebas, respaldos, manuales
- **B7** Libros legales y datos de demostración: exportación a Excel, IVA y libro de compras, ventas y libro de ventas, datos de demostración

## Fuera de alcance (según el documento)
Nómina, facturación electrónica e integración bancaria en tiempo real.

## Convenciones
- Estructura: `backend/` (Django, proyecto `config`, una app por módulo: `usuarios`, `contabilidad`, `centros_costo`, `presupuesto`, `tesoreria`, `reportes`, `ventas`), `frontend/` (React + Vite).
- API REST bajo `/api/`, versionada solo si hace falta. Endpoint de salud: `/api/health/`.
- Lógica de negocio en `services.py` de cada app, no en las vistas ni en los serializers.
- Pruebas con `pytest` o `manage.py test`; toda regla contable lleva prueba.
- Secretos solo en `.env` (ignorado por git); mantener `.env.example` actualizado.
- Zona horaria `America/El_Salvador`.

## Comandos
```bash
cp .env.example .env
docker compose up --build            # levanta todo
docker compose logs -f backend       # logs
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py test
```

## Estado actual
- [x] T0.1 Entorno (ver `docs/tareas/T0.1.md`)
- [x] T0.2 Autenticación JWT, roles y bitácora (ver `docs/tareas/T0.2.md`)
- [x] T1.1 Catálogo de cuentas jerárquico (ver `docs/tareas/T1.1.md`)
- [x] T1.2 Periodos contables (ver `docs/tareas/T1.2.md`)
- [x] T1.3 Asientos con partida doble, inmutabilidad y reversión (ver `docs/tareas/T1.3.md`)
- [x] T1.4 Libro diario, mayor y balanza de comprobación (ver `docs/tareas/T1.4.md`)
- [x] T1.5 Rediseño visual (ver `docs/tareas/T1.5.md`)
- [x] T2.1 Jerarquía de centros de costo y centro en líneas de asiento (ver `docs/tareas/T2.1.md`)
- [x] T2.2 Asignación directa y por regla: cuenta→centro, proveedor→centro (ver `docs/tareas/T2.2.md`)
- [x] T2.3 Motor de prorrateo con bases configurables y trazabilidad (ver `docs/tareas/T2.3.md`)
- [x] T3.1 Estado de resultados por centro, costeo absorbente (ver `docs/tareas/T3.1.md`)
- [x] T3.2 Enfoque de contribución y clasificación de cuentas (ver `docs/tareas/T3.2.md`)
- [x] T3.3 Indicadores de rentabilidad por área (ver `docs/tareas/T3.3.md`)
- [x] T4.1 Presupuesto institucional anual (ver `docs/tareas/T4.1.md`)
- [x] T4.2 Distribución del presupuesto a departamentos (ver `docs/tareas/T4.2.md`)
- [x] T4.3 Ejecución vs. presupuesto y alertas de desviación (ver `docs/tareas/T4.3.md`)
- [x] T5.1 Cuentas por pagar con vencimientos (ver `docs/tareas/T5.1.md`)
- [x] T5.2 Proyección de egresos a 30/60/90 días (ver `docs/tareas/T5.2.md`)
- [x] T5.3 Flujo de efectivo actual y proyectado con alertas de déficit (ver `docs/tareas/T5.3.md`)
- [x] T5.4 Dashboard de tesorería (ver `docs/tareas/T5.4.md`)
- [x] T6.1 Pruebas, respaldos y manuales (ver `docs/tareas/T6.1.md`)
- [x] T7.1 Exportación a Excel: catálogo, libro diario y libro mayor (ver `docs/tareas/T7.1.md`)
- [x] T7.2 IVA en compras y Libro de compras (ver `docs/tareas/T7.2.md`)
- [x] T7.3 Ventas y Libro de ventas (ver `docs/tareas/T7.3.md`)
- [x] T7.4 Datos de demostración realistas (ver `docs/tareas/T7.4.md`)

Notas de implementación:
- Roles = grupos de Django (`usuarios/roles.py`). Proteger vistas con `permission_classes = [TieneRol(roles.X)]` (`usuarios/permissions.py`).
- Registrar acciones sensibles con `usuarios.services.registrar_evento(...)`. La bitácora es inmutable (modelo + trigger Oracle).
- Los services lanzan `django.core.exceptions.ValidationError`; `config/excepciones.py` los convierte en 400 (`{"campo": [...]}` o `{"detail": "..."}`).
- Catálogo de ejemplo: `docker compose exec backend python manage.py cargar_catalogo_base --usuario contador`. T1.3 debe impedir eliminar cuentas con movimientos y registrar solo en cuentas `acepta_movimientos=True` y activas.
- Periodos: T1.3 debe llamar a `contabilidad.services.validar_fecha_registrable(fecha)` al contabilizar y agregar a `cerrar_periodo` la verificación de asientos en borrador. Reabrir es solo para superusuario (`usuarios.permissions.EsSuperusuario`).
- Asientos: solo los `CONTABILIZADO` cuentan para libros y reportes. Triggers Oracle `TRG_ASIENTO_REGLAS` (versión vigente en `contabilidad/0006`, incluye regla 3) y `TRG_LINEA_ASIENTO_INMUTABLE`. `LineaAsiento.centro_costo` es obligatorio salvo `cuenta.exenta_centro_costo`; el centro debe ser de detalle y vigente en la fecha (`_validar_centro`). Las reversiones copian el centro sin revalidar. Los asientos 2026-000001/000002 (anteriores a T2.1) no tienen centro.
- Centros de costo: app `centros_costo`; ejemplo con `cargar_centros_base --usuario contador`. Reestructurar = cerrar vigencia y crear unidad nueva (código y padre inmutables).
- Asignación (T2.2): `centros_costo.ReglaAsignacion` (cuenta y/o proveedor → centro, con vigencia) y `services.resolver_regla` (proveedor+cuenta > proveedor > cuenta, ancestro más cercano). `_normalizar_lineas` la aplica al guardar el borrador si la línea no trae centro; `LineaAsiento.regla_asignacion` la traza (vacía = directa). Ejemplo: `cargar_asignacion_base --usuario contador`.
- Presupuesto (T4.1): app `presupuesto`. `PresupuestoInstitucional` (uno por año, BORRADOR → APROBADO → CERRADO; escribe solo Contador) y `VersionPresupuesto` (historial inmutable). Todo cambio de monto pasa por `services.cambiar_monto`, que crea la versión antes de actualizar el presupuesto: el trigger `TRG_PRESUPUESTO_REGLAS` exige que `MONTO`/`VERSION` coincidan con la última versión, prohíbe eliminar y modificar cerrados; `TRG_VERSION_PPTO_INMUTABLE` protege el historial. Aprobar exige referencia; modificar un aprobado exige motivo y referencia; `cambiar_monto` no baja el monto por debajo de lo distribuido.
- Distribución (T4.2): `presupuesto/distribucion.py`. `AsignacionPresupuesto` (monto anual por centro de detalle vigente en el año) y `DetallePresupuesto` (cuenta de gasto × mes; los ceros no se guardan). Topes Σ asignaciones ≤ institucional y Σ detalle ≤ asignación, en servicio y en triggers Oracle de sentencia (`TRG_ASIG_PPTO_TOPE`, `TRG_DET_PPTO_TOPE`, `TRG_PPTO_TOPE_DISTRIBUIDO`); por eso `guardar_detalle` aplica primero lo que baja y luego lo que sube. Cada cambio queda en `CambioDistribucion` (inmutable). En Oracle no usar `select_for_update()` con `.first()`/slices: se bloquea el presupuesto con `_bloquear`.
- Ejecución (T4.3): `presupuesto/ejecucion.py` (`/api/presupuestos/{id}/ejecucion/?corte=&umbral=&centro=`), solo lectura. Ejecutado = cargos − abonos de gastos contabilizados por centro, cuenta y mes del periodo, **sin** asientos `PRORRATEO` ni sus reversiones. Alertas: sobregiro (ejecutado al corte > asignación anual), desviación y subejecución (% al corte fuera de 100 ± umbral) y gasto sin presupuesto (centro sin asignación o cuenta sin detalle). El estado del departamento es el tipo de su alerta más grave.
- Tesorería: app `tesoreria` con catálogo básico `Proveedor` (T2.2; Contador o Tesorero). `Asiento.proveedor` opcional.
- Cuentas por pagar (T5.1): `tesoreria/cuentas_por_pagar.py`. `CuentaPorPagar` (documento, vencimiento, `saldo`, estado PENDIENTE/PARCIAL/PAGADA/ANULADA) y `PagoCuentaPorPagar`; escriben Contador o Tesorero. Registrar un documento crea y contabiliza su asiento (cargo a las líneas de imputación con centro, abono a la cuenta por pagar, por defecto 2401) y cada pago otro (2401 contra banco/caja); anular revierte con `revertir_asiento(..., permitir_tesoreria=True)`; desde Asientos está bloqueado (`_es_asiento_de_tesoreria`). Cuentas por pagar y de banco deben ser exentas de centro. Triggers `TRG_CXP_REGLAS` y `TRG_PAGO_CXP_REGLAS` (sin borrar ni cambiar datos registrados).
- Proyección de egresos (T5.2): `tesoreria/proyeccion.py` (`/api/tesoreria/proyeccion-egresos/?fecha=`). Compromisos ciertos: saldo de cada cuenta por pagar en `fecha_pago_programada` (si se programó, `POST /api/cuentas-por-pagar/{id}/programar/`) o en `fecha_vencimiento`, más `EgresoProgramado` activos (únicos o mensuales por `dia_mes`; dato de planificación editable con bitácora). Tramos VENCIDO / D30 / D60 / D90 y acumulados = vencido + tramos.
- Flujo de efectivo (T5.3): `tesoreria/flujo.py`. `ClasificacionFlujo` (cuenta de cualquier nivel → EFECTIVO/OPERACION/INVERSION/FINANCIAMIENTO; gana el ancestro asignado más cercano; sin asignación: activo → inversión, patrimonio → financiamiento, resto → operación) y `ConfiguracionTesoreria` (pk=1: `saldo_minimo`, `dias_historia`). Ejemplo: `cargar_flujo_base --usuario contador` (11 = efectivo). Real (`/api/tesoreria/flujo-efectivo/`): cada contrapartida de un asiento que mueve efectivo aporta abono − cargo; debe cuadrar con el saldo contable. Proyectado (`/api/tesoreria/flujo-proyectado/`): saldo al cierre de la fecha + promedio de entradas de operación − `egresos_proyectados` en 13 semanas; alertas DEFICIT, BAJO_MINIMO y VENCIDOS.
- Dashboard de tesorería (T5.4): `tesoreria/dashboard.py` (`/api/tesoreria/dashboard/?fecha=`) solo compone los servicios de T5.1–T5.3 (si falta configurar efectivo, `flujo` es nulo y `aviso_flujo` lo explica). Gráficos SVG propios en `frontend/src/components/graficos/Graficos.jsx` (`GraficoLinea`, `GraficoColumnas`, `GraficoBarras`, `TarjetaGrafico` con vista de tabla), sin dependencias; colores en tokens `--viz-*` de `estilos.css` (paleta validada con el validador de la guía de visualización sobre fondo blanco).
- Prorrateo (T2.3): `centros_costo/prorrateo.py` (bases, medidas por centro y periodo, reglas, ejecución). Método escalonado por `orden`; cada ejecución genera un asiento tipo `PRORRATEO` contabilizado con `linea_origen` en cada línea y guarda el detalle usado (JSON). Se anula con reversión desde Prorrateo (`revertir_asiento(..., permitir_prorrateo=True)`); desde Asientos está bloqueado. Ejemplo: `cargar_prorrateo_base --usuario contador --anio 2026`.
- Reportes (B3): app `reportes`, servicios de solo lectura en `reportes/services.py`. `estado_resultados` (T3.1) consolida por la jerarquía de centros (columnas = raíces o subunidades del centro elegido), separa directos (asientos de diario) de indirectos (asientos `PRORRATEO` vigentes; los anulados y sus reversiones se excluyen) y agrega una columna "Sin centro" para que el total cuadre con la balanza. Al agregar una app nueva a `config/urls.py`, crear antes su `urls.py` o reiniciar el backend.
- Clasificación de cuentas (T3.2): `rubro_resultado`, `comportamiento_costo`, `controlable` en `Cuenta`; vacío = heredar del padre (`contabilidad.services.clasificacion_resultados()`). En Oracle un texto nulo llega como "": tratar ambos como "heredar". El enfoque de contribución usa la misma base `_Segmentos` de `reportes/services.py`; su resultado por segmento debe igualar al absorbente.
- Indicadores (T3.3): `reportes.services.indicadores_rentabilidad` (`/api/reportes/indicadores/`) agrupa por `rubro_resultado` (margen bruto, operativo, neto) y reutiliza la categoría variable de T3.2 para el margen de contribución. El resultado neto debe igualar al absorbente; la participación se mide sobre el total de la vista y es nula si ese total no es positivo.
- Libros (diario, mayor, balanza): servicios de solo lectura en `contabilidad/libros.py` (separados de `services.py`). Saldos acumulados desde el inicio; las cuentas de resultado se ponen en cero con un asiento de cierre, no en el reporte. Agrupaciones = descendientes reales del árbol (no prefijo de código).
- Frontend (T1.5): las pantallas viven dentro de `layout/Layout.jsx` (menú lateral en `MENU`, agregar ahí los módulos nuevos). Cada página usa `EncabezadoPagina` (título, descripción, migas, acciones), filtros en `Card`, tablas dentro de `Card`, montos con clase `monto`, insignias en tonos `*-subtle`, íconos `bootstrap-icons` y `EstadoVacio` para listas vacías. Estilos del tema en `src/estilos.css`.
- Cierre (T6.1): `config/tests_integracion.py` (ciclo completo con todos los datos de ejemplo; al agregar módulos, extenderlo). `reportes/integridad.py` + comando `verificar_integridad [--anio]` (código 1 si falla; al crear un trigger nuevo, agregarlo a `TRIGGERS`). Respaldos con Data Pump en `scripts/` (`respaldo.sh`, `verificar_respaldo.sh`, `restaurar.sh`; credenciales del contenedor; `docker compose exec` que no lee entrada debe llevar `</dev/null`). Manuales: `docs/MANUAL_USUARIO.md`, `docs/MANUAL_TECNICO.md`; matriz de pruebas `docs/PRUEBAS.md` (actualizar conteos al agregar pruebas).
- Exportación a Excel (T7.1): `config/excel.py` da el formato común (encabezado con `EMPRESA_NOMBRE`/`EMPRESA_NIT`/`EMPRESA_NRC` de `.env`, títulos fijos en la fila 7, montos numéricos `#,##0.00`, filas `Fila(valores, estilo="grupo"|"subtotal"|"total")`); cada app arma sus filas desde sus servicios (`contabilidad/exportacion.py`) y responde con `respuesta_excel`. Rutas `…/exportar/`; en el frontend, `descargarDesdeApi` (`src/exportar.js`) y la prop `onExportarExcel` de `AccionesReporte`. Reutilizar en los libros de compras y ventas.
- IVA en compras (T7.2): `CuentaPorPagar` lleva `compras_gravadas`, `compras_exentas`, `iva_credito_fiscal`, `iva_retenido`; `monto_total` = gravadas + exentas + IVA − retención (servicio `cuentas_por_pagar.desglose_fiscal` y CHECK `cxp_desglose_cuadra`, `cxp_iva_solo_ccf`; `TRG_CXP_REGLAS` protege el desglose). Las líneas de imputación van sin IVA; solo el CCF da crédito fiscal (13 %, cargo a 1403) y retención del 1 % (gravadas ≥ US$100, abono a 2405); 1403 y 2405 vienen en `cargar_catalogo_base`. Libro de compras: `tesoreria/libro_compras.py` (CCF vigentes del mes) y `tesoreria/exportacion.py` (`/api/tesoreria/libro-compras/[exportar/]?anio=&mes=`).
- Ventas (T7.3): app `ventas`. `Cliente` (CONTRIBUYENTE con NIT y NRC → CCF; CONSUMIDOR_FINAL → factura; NIT nulo si no hay, en Oracle '' = NULL) y `DocumentoVenta` (`ventas/documentos.py`): líneas de ingreso sin IVA con centro y marca `exenta`; IVA débito 13 % de las gravadas a 2406; cargo a la cuenta de cobro (1103 por defecto). Número único por tipo y no reutilizable. Anular = `revertir_asiento(..., permitir_ventas=True)`; desde Asientos bloqueado (`_es_asiento_de_ventas`). Trigger `TRG_DOC_VENTA_REGLAS`; verificación VENTAS en `integridad.py`. Libro de ventas: `ventas/libro.py` (CCF por documento, anulados en cero; consumidor final por día con IVA incluido) y Excel de dos hojas con `config.excel.construir_libro_hojas`.
- Datos de demostración (T7.4): `cargar_datos_demo --usuario contador --desde AAAA-MM-DD --hasta AAAA-MM-DD` (comando en `reportes`, datos en `config/datos_demo.py`). Solo usa servicios; prepara los datos base; rechaza rangos con periodos cerrados sin cargar nada; idempotente por NIT, número de documento y referencia de asiento (plan mensual con semilla fija); ejecuta el prorrateo de cada mes completo (si ya estaba ejecutado, avisa); termina con resumen por mes y `verificar_integridad`. Al agregar módulos, sumar sus datos aquí y en `DatosDemoTests`.
- Usuarios de prueba: `docker compose exec backend python manage.py crear_usuarios_demo` (contraseña `Demo_2026!`).
- Desde Git Bash en Windows, anteponer `MSYS_NO_PATHCONV=1` a `docker compose exec` con rutas absolutas del contenedor.

(Actualiza esta lista al cerrar cada tarea.)
