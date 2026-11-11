# Manual técnico

Sistema Contable para la gestión de centros de costo, presupuesto y flujo de efectivo (caso de uso: banco).
Este manual está dirigido a quien instala, mantiene o extiende el sistema. El funcionamiento para los usuarios está en `MANUAL_USUARIO.md`; las reglas de negocio y el detalle de cada módulo, en `docs/tareas/T*.md`.

---

## 1. Arquitectura

```
Navegador ──► frontend (React 18 + Vite, :5173) ──► backend (Django 5.2 + DRF, :8000, /api/) ──► Oracle XE 21c (:1521, XEPDB1)
```

| Servicio (docker compose) | Imagen / base | Función |
|---|---|---|
| `oracle-db` | `gvenzl/oracle-xe:21-slim` | Base de datos. Volumen `oracle-data`. Al crearse ejecuta `docker/oracle-init/` |
| `backend` | `python:3.12-slim` | API REST. Al arrancar aplica las migraciones (`migrate`) |
| `frontend` | `node:20-alpine` | Interfaz (servidor de desarrollo de Vite) |

- **Autenticación:** JWT (`djangorestframework-simplejwt`): token de acceso (30 min) y de refresco (8 h), lista negra al cerrar sesión.
- **Roles:** grupos de Django — Contador, Tesorero, Jefe de área, Auditor. El superusuario es el administrador.
- **Zona horaria:** `America/El_Salvador`. **Idioma:** español.

## 2. Instalación

Requisitos: Docker Desktop (o Docker Engine + Compose v2), 4 GB de RAM libres para Oracle.

```bash
cp .env.example .env            # ajuste contraseñas y SECRET_KEY
docker compose up --build       # la primera vez Oracle tarda 2-4 min en quedar "healthy"
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py crear_usuarios_demo   # contador, tesorero, jefe, auditor (Demo_2026!)
```

| URL | |
|---|---|
| http://localhost:5173 | Aplicación |
| http://localhost:8000/api/health/ | Salud del backend y de la conexión a Oracle |
| http://localhost:8000/admin/ | Administración de usuarios y roles (superusuario) |

### Variables de entorno (`.env`)
| Variable | Uso |
|---|---|
| `ORACLE_PASSWORD` | Contraseña de SYS/SYSTEM (solo la usan Oracle y los scripts de respaldo) |
| `DB_USER`, `DB_PASSWORD` | Usuario/esquema de la aplicación (se crea al iniciar el volumen) |
| `DB_NAME` | Servicio de Oracle: **XEPDB1** (no cambiar) |
| `DB_PORT` | 1521 |
| `SECRET_KEY` | Clave de Django (≥ 32 caracteres, distinta por instalación) |
| `DEBUG` | `True` solo en desarrollo |
| `ALLOWED_HOSTS` | Hosts permitidos, separados por coma |
| `JWT_ACCESS_MINUTOS`, `JWT_REFRESH_HORAS` | Vigencia de los tokens |
| `EMPRESA_NOMBRE`, `EMPRESA_NIT`, `EMPRESA_NRC` | Encabezado de los libros exportados a Excel (T7.1) |

`.env` nunca se sube a git; `.env.example` se mantiene actualizado.

### Datos de ejemplo (en este orden)
```bash
docker compose exec backend python manage.py cargar_catalogo_base --usuario contador      # catálogo bancario y su clasificación
docker compose exec backend python manage.py cargar_centros_base --usuario contador       # casa matriz, agencias, proyectos
docker compose exec backend python manage.py cargar_asignacion_base --usuario contador    # proveedores y reglas cuenta/proveedor → centro
docker compose exec backend python manage.py cargar_prorrateo_base --usuario contador --anio 2026   # bases, medidas y reglas de prorrateo
docker compose exec backend python manage.py cargar_flujo_base --usuario contador         # cuentas de efectivo y actividades del flujo
docker compose exec backend python manage.py cargar_datos_demo --usuario contador --desde 2026-08-01 --hasta 2026-11-30   # T7.4: meses de operación de demostración
```
Todos son idempotentes (no pisan lo existente). El ejercicio contable se crea desde la pantalla *Periodos contables*.

`cargar_datos_demo` (T7.4, datos en `config/datos_demo.py`) ejecuta antes los comandos anteriores y crea el ejercicio si falta; luego carga, con los servicios de cada módulo, 18 proveedores, 25 clientes, saldos iniciales y aporte de capital, compras (CCF con IVA y retención, factura, servicio exento, equipo), pagos en su vencimiento, ventas (CCF a empresas con intereses exentos y comisiones gravadas; facturas semanales de ventanilla y a personas), planilla con ISSS/AFP/renta y su pago, intereses sobre depósitos, depreciación, movimientos de cartera y depósitos y el prorrateo de cada mes completo. Rechaza el rango si algún periodo está cerrado (sin cargar nada), es idempotente (claves: NIT, número de documento, referencia del asiento; cada mes se genera con semilla fija) y termina con un resumen por mes y `verificar_integridad` (código de salida 1 si falla). Si el prorrateo de un mes ya estaba ejecutado, avisa en lugar de anularlo.

## 3. Estructura del código

```
backend/
  config/          settings, urls, excepciones (ValidationError → 400), health, tests_integracion.py
  usuarios/        roles, permisos (TieneRol, EsSuperusuario), bitácora inmutable, JWT
  contabilidad/    catálogo, periodos, asientos (services.py), libros (libros.py)
  centros_costo/   jerarquía, reglas de asignación, prorrateo (prorrateo.py)
  reportes/        estado de resultados, contribución, indicadores (services.py), integridad.py
  presupuesto/     presupuesto institucional (services.py), distribución, ejecución
  tesoreria/       proveedores, cuentas por pagar, proyección, flujo, dashboard
  ventas/          clientes, documentos de venta (documentos.py), libro de ventas (libro.py, exportacion.py)
frontend/src/
  layout/Layout.jsx          menú lateral (MENU)
  pages/                     una pantalla por ruta (App.jsx)
  components/                comunes: EncabezadoPagina, EstadoVacio, SelectorCuenta, reportes/, graficos/
  estilos.css                tema (variables de Bootstrap y tokens --viz-* de los gráficos)
docker/oracle-init/          privilegios para la base de pruebas
scripts/                     respaldo, verificación y restauración
docs/                        documento base, plan, especificación por tarea, manuales, pruebas
```

### Convenciones
- **Lógica de negocio en `services.py`** (o módulos de servicio de la app); vistas y serializers solo validan forma y delegan.
- Los servicios lanzan `django.core.exceptions.ValidationError`; `config/excepciones.py` responde 400 con `{"campo": [...]}` o `{"detail": "..."}`.
- Montos: `DecimalField(max_digits=18, decimal_places=2)`; en la API viajan como texto (`"1500.00"`); el frontend suma en centavos enteros (`formato.js`).
- Toda acción sensible llama a `usuarios.services.registrar_evento(...)` con valor anterior y nuevo.
- En Oracle un texto nulo llega como `""`: tratar ambos igual.
- En Oracle no usar `select_for_update()` con `.first()` o cortes (`[:n]`).
- Commits por tarea: `T#.#: descripción`.

## 4. Reglas en la base de datos

Además de las restricciones `CHECK`/`UNIQUE` de cada modelo, 14 triggers garantizan las reglas aunque se acceda a la base por fuera de la aplicación:

| Trigger | Tabla | Regla |
|---|---|---|
| `TRG_BITACORA_INMUTABLE` | bitácora | No se modifica ni elimina |
| `TRG_ASIENTO_REGLAS` | asientos | Partida doble, periodo abierto, centro obligatorio al contabilizar; contabilizado inmutable |
| `TRG_LINEA_ASIENTO_INMUTABLE` | líneas | Líneas de un asiento contabilizado inmutables |
| `TRG_PRESUPUESTO_REGLAS` | presupuesto | No se elimina; cerrado inmutable; monto = última versión |
| `TRG_VERSION_PPTO_INMUTABLE` | versiones | Historial inmutable |
| `TRG_ASIG_PPTO_TOPE`, `TRG_DET_PPTO_TOPE`, `TRG_PPTO_TOPE_DISTRIBUIDO` | distribución | Σ asignaciones ≤ institucional; Σ detalle ≤ asignación |
| `TRG_ASIG_PPTO_REGLAS`, `TRG_DET_PPTO_REGLAS` | distribución | Sin cambios con el presupuesto cerrado |
| `TRG_CAMBIO_DIST_INMUTABLE` | historial de distribución | Inmutable |
| `TRG_CXP_REGLAS`, `TRG_PAGO_CXP_REGLAS` | cuentas por pagar y pagos | No se eliminan; datos registrados inmutables (incluido el desglose fiscal, T7.2); anulados inmutables |
| `TRG_DOC_VENTA_REGLAS` | documentos de venta | No se eliminan; datos emitidos inmutables; anulados inmutables (T7.3) |

Además de los triggers, restricciones `CHECK` del desglose fiscal de compras (T7.2): `cxp_desglose_cuadra` (total = gravadas + exentas + IVA − retención), `cxp_desglose_no_negativo` y `cxp_iva_solo_ccf` (IVA y retención solo en CCF).

Se crean en migraciones `RunPython` con el cursor nativo de `oracledb` (el de Django recorta el `;` final del PL/SQL). `verificar_integridad` comprueba que existan y estén habilitados.

## 5. API REST

Todas bajo `/api/`, con `Authorization: Bearer <token>` salvo `health` y `auth/login`. Lectura: cualquier usuario autenticado salvo donde se indica; escritura según rol.

| Módulo | Rutas principales | Escritura |
|---|---|---|
| Autenticación | `auth/login/`, `auth/refresh/`, `auth/logout/`, `auth/me/` | — |
| Usuarios y bitácora | `usuarios/` (lista para selectores), `bitacora/` (solo Auditor) | Usuarios y roles: `/admin/` (superusuario) |
| Catálogo | `cuentas/`, `cuentas/arbol/`, `cuentas/exportar/` (.xlsx) | Contador |
| Periodos | `periodos/`, `periodos/ejercicios/`, `periodos/{id}/cerrar/`, `…/reabrir/` (superusuario) | Contador |
| Asientos | `asientos/`, `asientos/{id}/contabilizar/`, `asientos/{id}/revertir/` | Contador |
| Libros | `libros/diario/`, `libros/mayor/`, `libros/balanza/`; Excel: `libros/diario/exportar/`, `libros/mayor/exportar/` (sin `cuenta` = mayor general) | — |
| Centros de costo | `centros-costo/`, `centros-costo/arbol/`, `reglas-asignacion/`, `reglas-asignacion/resolver/` | Contador |
| Prorrateo | `prorrateo/bases/`, `prorrateo/medidas/`, `prorrateo/reglas/`, `prorrateo/ejecuciones/` (`previsualizar/`, `pendientes/`, `{id}/anular/`) | Contador |
| Reportes | `reportes/estado-resultados/`, `reportes/enfoque-contribucion/`, `reportes/indicadores/` | — |
| Presupuesto | `presupuestos/` (`cambiar-monto/`, `aprobar/`, `cerrar/`, `distribucion/`, `distribucion/{centro}/`, `historial-distribucion/`, `ejecucion/`) | Contador |
| Tesorería | `proveedores/`, `cuentas-por-pagar/` (`resumen/`, `pagos/`, `anular/`, `programar/`), `egresos-programados/`, `tesoreria/proyeccion-egresos/`, `tesoreria/flujo-efectivo/`, `tesoreria/flujo-proyectado/`, `tesoreria/clasificacion-flujo/`, `tesoreria/configuracion/`, `tesoreria/dashboard/`, `tesoreria/libro-compras/` (`?anio=&mes=`; Excel: `exportar/`) | Contador o Tesorero |
| Ventas | `clientes/`, `ventas/documentos/` (`anular/`), `ventas/libro/` (`?anio=&mes=`; Excel: `exportar/`) | Contador o Tesorero |

Listas paginadas de 50 (`?page=`). Parámetros y respuestas de cada endpoint: `docs/tareas/T*.md`.

## 6. Pruebas
Ver `docs/PRUEBAS.md`. Resumen:
```bash
docker compose exec backend python manage.py test                  # 294 pruebas contra Oracle
docker compose exec backend python manage.py verificar_integridad  # reglas sobre los datos reales
```

## 7. Respaldos y restauración

Los scripts de `scripts/` usan **Oracle Data Pump** dentro del contenedor y leen las credenciales del propio contenedor (no las escriben en la línea de comandos). En Windows se ejecutan desde **Git Bash**.

| Acción | Comando | Resultado |
|---|---|---|
| Respaldar | `bash scripts/respaldo.sh` | `respaldos/AAAAMMDD_HHMMSS/` con `contable_*.dmp`, su log e `info.txt` (fecha, commit, filas por tabla) |
| Verificar un respaldo | `bash scripts/verificar_respaldo.sh respaldos/<carpeta>` | Lo importa en el esquema temporal `CONTABLE_VERIF`, compara filas por tabla con la base actual y borra el temporal. No toca los datos reales |
| Ensayar una restauración | `ESQUEMA_DESTINO=CONTABLE_ENSAYO bash scripts/restaurar.sh respaldos/<carpeta>` | Restaura en otro esquema (borrar luego con SQL o repitiendo el ensayo) |
| Restaurar | `bash scripts/restaurar.sh respaldos/<carpeta>` | Pide escribir el nombre del esquema; detiene el backend, borra el esquema, importa el respaldo y levanta el backend |

Recomendaciones:
- Respaldar a diario y antes de cada cierre de periodo, de cambios de versión o de restaurar.
- Verificar periódicamente que los respaldos se pueden importar (`verificar_respaldo.sh`).
- Copiar `respaldos/` fuera del equipo (la carpeta está en `.gitignore`; contiene datos sensibles).
- Después de restaurar: `python manage.py verificar_integridad`.
- Un respaldo corresponde al código del commit anotado en `info.txt`; restaurarlo con un código más nuevo es posible porque el backend aplica las migraciones pendientes al arrancar.

## 8. Solución de problemas

| Síntoma | Causa probable / solución |
|---|---|
| El backend no arranca: espera a `oracle-db` | Oracle aún inicia (2-4 min la primera vez). `docker compose logs -f oracle-db` hasta ver `DATABASE IS READY TO USE` |
| `ORA-12514` / no conecta | `DB_NAME` debe ser `XEPDB1` |
| `manage.py test` falla al crear la base de pruebas | Faltan privilegios: el volumen se creó antes de `docker/oracle-init/`. Ejecutar ese script como sysdba o recrear el volumen |
| Una ruta nueva de `config/urls.py` da 404 | La app no tenía `urls.py` al arrancar: reiniciar `docker compose restart backend` |
| Desde Git Bash, `docker compose exec … /ruta` falla | Anteponer `MSYS_NO_PATHCONV=1` |
| "No hay cuentas de efectivo configuradas" | Ejecutar `cargar_flujo_base` o asignar *Efectivo* en Tesorería → Flujo de efectivo → Configuración |
| Error al guardar con "excede" | Es una regla (tope de presupuesto, saldo de factura, etc.): el mensaje indica el disponible |
| Advertencia de Vite sobre el tamaño del paquete | Informativa; no afecta el funcionamiento |
| Se olvidó la contraseña del administrador | `docker compose exec backend python manage.py changepassword <usuario>` |

## 9. Puesta en producción (pendiente fuera del alcance)
El `docker-compose.yml` es de desarrollo (servidor de Django y de Vite). Para producción: `DEBUG=False`, `SECRET_KEY` propia, `gunicorn` (ya en `requirements.txt`) detrás de un proxy con HTTPS, `npm run build` servido como estático, `ALLOWED_HOSTS` y CORS ajustados, y respaldos programados (`scripts/respaldo.sh` en el programador de tareas).
