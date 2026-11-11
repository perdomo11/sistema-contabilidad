# Manual de usuario

Sistema Contable para la gestión de centros de costo, presupuesto y flujo de efectivo.
Este manual explica cómo usar cada pantalla. Las reglas contables que aplica el sistema se indican en cada capítulo: cuando algo no se permite, el mensaje en pantalla explica por qué.

---

## 1. Acceso y roles

Ingrese en **http://localhost:5173** con su usuario y contraseña. La sesión se cierra sola tras un tiempo sin uso; vuelva a ingresar.

| Rol | Puede |
|---|---|
| **Contador** | Catálogo, periodos, asientos, centros de costo, reglas de asignación, prorrateo, presupuesto; cuentas por pagar y tesorería |
| **Tesorero** | Proveedores, cuentas por pagar, pagos, egresos programados, configuración del flujo de efectivo |
| **Jefe de área** | Consultar libros, reportes, presupuesto y tesorería |
| **Auditor** | Consultar todo, incluida la **bitácora de auditoría** |
| **Administrador** | Todo, más usuarios y roles (en `/admin/`) y reabrir periodos cerrados |

Las pantallas muestran solo los botones que su rol permite usar.

### Elementos comunes
- **Montos:** dos decimales, separador de miles; los negativos entre paréntesis y en rojo cuando indican pérdida o faltante.
- **Exportar CSV e Imprimir:** en reportes y tableros. La impresión oculta menús y botones.
- **Exportar a Excel:** en el catálogo de cuentas, el libro diario y el libro mayor. Genera un libro .xlsx con el nombre, NIT y NRC de la empresa, el periodo, montos numéricos con dos decimales, totales y la fila de títulos fija.
- **Migas de pan** arriba de cada pantalla para volver a la sección.

---

## 2. Contabilidad

### 2.1 Catálogo de cuentas (*Configuración → Catálogo de cuentas*)
Árbol de cuentas por niveles (Activo, Pasivo, Patrimonio, Ingresos, Gastos, Orden).
- **Nueva cuenta:** elija la cuenta padre; el código debe empezar con el del padre. Solo las cuentas **de detalle** reciben movimientos; las de agrupación suman a sus subcuentas.
- **Exenta de centro de costo:** solo cuentas de balance (bancos, cuentas por pagar…). Ingresos y gastos siempre exigen centro.
- **Clasificación para reportes** (ingresos y gastos): rubro (de operación, costo de intermediación, no operacional), comportamiento (variable/fijo) y controlable. Si se deja en "Heredar", toma el valor de la cuenta padre.
- Una cuenta con movimientos no se elimina: desactívela.

### 2.2 Periodos contables (*Configuración → Periodos contables*)
- **Crear ejercicio:** genera los 12 meses abiertos.
- **Cerrar periodo:** en orden, y solo si no quedan asientos en borrador. En un periodo cerrado no se puede registrar.
- **Reabrir:** solo el administrador, el último cerrado y con motivo.

### 2.3 Asientos (*Contabilidad → Asientos*)
1. **Nuevo asiento:** fecha, concepto, referencia (documento fuente) y proveedor (opcional).
2. Agregue líneas: cuenta, **centro de costo**, descripción, cargo o abono. Si una línea de gasto no trae centro, el sistema aplica la **regla de asignación** (ver 3.2); la columna indica si el centro es directo o por regla.
3. **Guardar borrador** (se puede editar o eliminar) y luego **Contabilizar**.

Reglas: **cargos = abonos**; fecha en periodo abierto; cuentas de detalle y activas; centro de costo de detalle y vigente.
Un asiento **contabilizado no se modifica ni se elimina**: para corregirlo use **Revertir** (indica motivo y fecha) y registre el asiento correcto. Los asientos de prorrateo y de cuentas por pagar se anulan desde su propio módulo.

### 2.4 Libros (*Contabilidad*)
- **Libro diario:** asientos contabilizados por rango de fechas.
- **Libro mayor:** movimientos y saldo de una cuenta (o de un grupo con sus subcuentas). "Mayor general a Excel" descarga en un solo archivo el mayor de todas las cuentas con movimiento en el rango.
- **Balanza de comprobación:** saldos por cuenta al nivel elegido; cargos y abonos totales deben coincidir.

---

## 3. Centros de costo

### 3.1 Estructura de centros
Árbol de unidades: sucursales, departamentos, áreas, proyectos; tipos costo, ingreso, utilidad o inversión. Cada centro tiene **vigencia** (desde/hasta).
Para reestructurar, **cierre la vigencia** del centro y cree uno nuevo: la historia contable no se pierde. Código y padre no se cambian.

### 3.2 Reglas de asignación
Asignan automáticamente el centro a las líneas que no lo traen: por **cuenta**, por **proveedor** o por **proveedor + cuenta** (gana la más específica). La asignación directa en el asiento siempre prevalece.

### 3.3 Prorrateo
Distribuye los costos de centros de servicio (Gerencia, Tecnología, RR. HH.) a los que reciben el servicio.
1. **Bases:** m², personal, transacciones…
2. **Medidas:** valor de cada base por centro y mes (se pueden copiar del mes anterior).
3. **Reglas:** origen, cuentas a distribuir, base y destinos; el **orden** define el método escalonado.
4. **Ejecutar:** *Vista previa* muestra el cálculo; *Ejecutar* genera un asiento de prorrateo contabilizado en el que cada línea conserva la referencia a su origen. Una regla se ejecuta una vez por periodo; para repetirla, **anule** la ejecución (genera la reversión).

---

## 4. Reportes (*Reportes*)
Todos se basan en asientos contabilizados y permiten navegar por la jerarquía: clic en el código de una unidad para ver sus subunidades; las migas permiten subir.

- **Estado de resultados (costeo absorbente):** ingresos, costos directos y costos indirectos asignados por prorrateo; resultado directo y neto por unidad. La columna "Sin centro" aparece si hay movimientos antiguos sin centro, para que el total cuadre con la balanza.
- **Enfoque de contribución:** ingresos − costos variables = margen de contribución; − fijos controlables = margen controlable; − fijos no controlables y prorrateados = resultado del segmento. Útil para **evaluar al responsable** de cada área.
- **Indicadores de rentabilidad:** margen bruto, operativo, de contribución y neto (%), y participación de cada unidad en el resultado y los ingresos.

---

## 5. Presupuesto (*Presupuesto*)

### 5.1 Presupuesto institucional
1. **Nuevo presupuesto:** ejercicio y monto anual de egresos (borrador).
2. **Ajustar monto** mientras está en borrador; cada cambio crea una **versión**.
3. **Aprobar:** indique el documento de la gerencia (p. ej. acta de junta directiva).
4. Una vez aprobado, cambiar el monto es una **modificación presupuestaria** con motivo y documento.
5. **Cerrar** al terminar el ejercicio: ya no admite cambios.

### 5.2 Distribución a departamentos
1. Elija el ejercicio. Arriba verá el monto institucional, lo distribuido y el **saldo sin distribuir**.
2. **Asignar a departamento:** monto anual a cada centro de detalle. La suma no puede pasar del institucional.
3. **Detalle:** reparta lo asignado por cuenta de gasto y mes. Escriba el total anual en un mes y use *repartir* para dividirlo en 12. El **saldo sin detallar** se actualiza al escribir.
4. El **historial** muestra cada cambio con su valor anterior y nuevo.

### 5.3 Ejecución vs. presupuesto
Compara el gasto real de cada departamento (sin prorrateos) con lo presupuestado, acumulado al mes de corte.
- **Semáforo:** En rango, Subejecución, Desviación, Gasto sin presupuesto, **Sobregiro** (superó su presupuesto anual).
- **Tolerancia:** porcentaje alrededor del 100 % que no genera alerta (10 % por defecto).
- **Detalle** de un departamento: por cuenta y mes a mes.

---

## 6. Tesorería (*Tesorería*)

### 6.1 Dashboard
Vista de un vistazo: alertas de liquidez, **saldo de efectivo actual**, saldo proyectado a 30/60/90 días, gráficos (saldo proyectado, entradas y salidas, egresos por tramo, antigüedad de saldos), próximos pagos y egresos por categoría. Botón *Tabla* en cada gráfico para ver los valores.

### 6.2 Proveedores
Catálogo con NIT y NRC. Un proveedor con movimientos no se elimina: desactívelo.

### 6.3 Cuentas por pagar
1. **Registrar documento:** proveedor, tipo y número, fechas de emisión y vencimiento, concepto y **líneas de imputación** (cuenta de gasto o activo y centro). Al guardar se **contabiliza automáticamente** el asiento contra la cuenta por pagar.
   - **Desglose fiscal:** las líneas son el valor de la compra **sin IVA**. Indique las compras exentas (el resto son gravadas). En un **comprobante de crédito fiscal (CCF)** el IVA crédito fiscal del 13 % se calcula solo (puede corregirlo hasta en un centavo si el documento lo redondea distinto) y se carga a la cuenta 1403; marque **Retener 1 %** cuando el banco retenga IVA al proveedor (compras gravadas de US$100 o más): se abona a 2405 y se le paga el total menos la retención. Facturas, recibos y otros no dan crédito fiscal: el IVA forma parte del costo.
2. Abra un documento para ver su detalle:
   - **Registrar pago** (parcial o total, desde una cuenta de banco o caja): genera su asiento.
   - **Programar pago:** fecha en que se piensa pagar; la usa la proyección.
   - **Anular pago** o **anular documento** (sin pagos vigentes), con motivo: se revierte el asiento.
3. Las tarjetas superiores muestran saldo pendiente, vencido, por vencer y la **antigüedad de saldos**; un clic filtra la lista.

### 6.3.1 Libro de compras
Tesorería → **Libro de compras**: elija el mes. Lista los **CCF** vigentes del mes en orden de fecha con correlativo, tipo y número de documento, NRC, NIT y nombre del proveedor, compras exentas, gravadas, IVA crédito fiscal, retención y total de compras. Las facturas de consumidor final, recibos y documentos anulados no se anotan. **Exportar a Excel** genera el libro con el encabezado de la empresa.

### 6.4 Proyección de egresos y egresos programados
- **Egresos programados:** planilla, impuestos, alquileres, cuotas de préstamos… únicos o mensuales.
- **Proyección de egresos:** vencido y acumulado a **30, 60 y 90 días** con las cuentas por pagar y los egresos programados; por categoría, por semana y por proveedor.

### 6.5 Flujo de efectivo
- **Proyectado:** saldo actual + entradas estimadas (promedio histórico) − salidas comprometidas, semana a semana durante 13 semanas. Alertas de **déficit** (con el financiamiento necesario) y de saldo **bajo el mínimo**.
- **Real del periodo:** estado de flujos por actividad (operación, inversión, financiamiento); el saldo final cuadra con la contabilidad.
- **Configuración** (Contador o Tesorero): saldo mínimo, días de historia y qué cuentas son efectivo y a qué actividad pertenece cada grupo de cuentas.

---

## 7. Control (*Control → Bitácora de auditoría*, Auditor)
Registro de todas las acciones sensibles: quién, qué, cuándo, valor anterior y nuevo. Filtros por usuario, acción y rango de fechas. **No se puede modificar ni borrar.**

---

## 8. Ciclos de trabajo

### Cierre mensual (Contador)
1. Contabilizar todos los asientos del mes (no deben quedar borradores).
2. Registrar las **medidas** del mes y ejecutar el **prorrateo** en orden.
3. Revisar la **balanza**, el **estado de resultados** y el **enfoque de contribución**.
4. Revisar la **ejecución presupuestaria** del mes.
5. Pedir al administrador técnico un respaldo y la verificación de integridad.
6. **Cerrar el periodo.**

### Ciclo presupuestario (Contador, con la gerencia)
Crear el presupuesto del año siguiente → ajustarlo → aprobarlo con el acta → distribuirlo a departamentos y detallarlo por cuenta y mes → seguimiento mensual con *Ejecución vs. presupuesto* → modificaciones con motivo cuando haga falta → cerrar al fin del ejercicio.

### Ciclo de tesorería (Tesorero, semanal)
Registrar facturas recibidas → programar los pagos según la política interna → revisar el **Dashboard** y el **Flujo proyectado** → si hay alerta de déficit, reprogramar pagos o gestionar financiamiento → registrar los pagos realizados.

---

## 9. Mensajes frecuentes

| Mensaje | Qué hacer |
|---|---|
| "Partida doble: el total de cargos debe ser igual al total de abonos" | Revise los montos de las líneas |
| "El periodo … está cerrado" | Registre en un periodo abierto o pida al administrador reabrirlo |
| "La cuenta … exige centro de costo" | Indique el centro o cree una regla de asignación |
| "Es un asiento de prorrateo / de cuentas por pagar" | Anúlelo desde Prorrateo o desde Cuentas por pagar |
| "Excede el monto institucional: el saldo disponible es …" | Asigne como máximo el disponible o aumente el presupuesto |
| "El pago excede el saldo pendiente" | Pague como máximo el saldo |
| "No hay cuentas de efectivo configuradas" | Tesorería → Flujo de efectivo → Configuración |
| "No tiene el rol requerido para esta acción" | Solicite el rol al administrador |
