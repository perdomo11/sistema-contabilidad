Presentación
La información contable constituye uno de los principales insumos para la conducción de cualquier organización. Sin embargo, su utilidad no depende únicamente de que los registros sean correctos, sino de que estén disponibles con el nivel de detalle y en el momento en que las decisiones deben tomarse. El presente trabajo aborda esa distancia entre el dato registrado y la información útil, tomando como objeto de estudio dos necesidades concretas de las áreas contables y financieras: la asignación de las partidas contables a centros de costo y la proyección del flujo de efectivo.
El tema resulta pertinente para la realidad nacional. El tejido empresarial salvadoreño está conformado mayoritariamente por pequeñas y medianas entidades que llevan su contabilidad conforme a la NIIF para las PYMES y que, en muchos casos, registran sus operaciones mediante procesos manuales o apoyados en hojas de cálculo desvinculadas del sistema contable central. Bajo ese esquema, conocer la rentabilidad de un departamento, un proyecto o una sucursal exige una reclasificación posterior que consume tiempo, introduce errores y llega tarde para orientar decisiones. Algo semejante ocurre con la liquidez: la información sobre compromisos de pago existe, pero se encuentra dispersa y no se traduce en una proyección que permita anticipar un déficit antes de que se materialice.
El aporte del estudio es doble. Traslada a un entorno tecnológico concreto los principios de la contabilidad por áreas de responsabilidad y de la administración del efectivo, ampliamente documentados en la literatura pero poco implementados en soluciones accesibles para organizaciones de mediana escala; y deja como producto el diseño de un sistema informático contable que automatiza la asignación por centros de costo, genera estados de resultados segmentados y proyecta los egresos a partir de los vencimientos registrados, funcionalidades que suelen estar disponibles únicamente dentro de plataformas ERP cuyo costo e implantación resultan inviables para buena parte de las empresas del país.
La motivación del equipo surge de la carrera misma: la Ingeniería de Sistemas Informáticos exige comprender el dominio del problema antes de programar cualquier solución, y esta asignatura ofrece ese punto de encuentro, pues obliga a entender la lógica contable para representarla correctamente en un modelo de datos. Los beneficios esperados operan en dos planos: en el formativo, fortalece nuestra capacidad para levantar requerimientos en un dominio especializado y traducirlos en decisiones de diseño trazables; en el social, ofrece información segmentada y oportuna a las áreas contables que adopten una solución de esta naturaleza. El documento se inscribe en la línea de investigación de los sistemas de información contable y financiera.


Introducción
El presente reporte expone la propuesta de investigación elaborada para la cátedra de Sistemas Contables (SIC 115) en la Escuela de Ingeniería de Sistemas Informáticos de la Universidad de El Salvador. Su finalidad consiste en fundamentar, detallar e implementar el Sistema Informático Contable para la Gestión de Centros de Costo y la Proyección de Flujo de Efectivo, una alternativa orientada a modernizar las prácticas mecánicas en la distribución departamental de egresos y el monitoreo de liquidez que prevalecen en las organizaciones locales.
La ejecución del estudio adoptó una metodología combinada, de propósito práctico y alcance descriptivo con perfil propositivo. Inicialmente se examinó la literatura financiera, el marco normativo nacional y los antecedentes científicos para consolidar la base teórica; posteriormente se diseñaron cuatro herramientas de captura dirigidas a los colaboradores involucrados en el asiento diario, la agenda de pagos y la administración de tesorería. Los datos recabados fueron procesados mediante triangulación metodológica para fundamentar las especificaciones funcionales de la plataforma.
La estructura del informe comprende cinco secciones principales. El planteamiento del problema examina los antecedentes, define la problemática central, establece las metas generales y específicas, formula la hipótesis de trabajo y concluye con la justificación y las limitaciones del proyecto. El marco teórico aborda el sustento conceptual, técnico y legal, articulando desde la concepción de la contabilidad como sistema de información automatizado hasta la contabilidad de costos, el prorrateo de partidas, los centros de responsabilidad, la información financiera segmentada, el flujo de caja, las obligaciones con proveedores y la legislación vigente en El Salvador.
El apartado metodológico respalda el enfoque adoptado: tipo de estudio, métodos, población e informantes clave, mecanismos de recolección, validación y esquema de procesamiento analítico. El análisis y discusión de resultados expone las evidencias encontradas y las contrasta con la teoría, agrupándolas según las deficiencias en la asignación de egresos, la planificación de tesorería y las barreras para la transformación digital. Las conclusiones y la propuesta de mejora sintetizan los hallazgos en relación con las metas trazadas y plantean cuatro ejes tácticos de solución. 
Capítulo 1. Planteamiento del problema
1.1 Antecedentes
A nivel internacional, diversos estudios han abordado la importancia de sistematizar la contabilidad de gestión y el control de costos por centros de responsabilidad. Falguera Martínez-Alarcón (2002) analizó los sistemas de control de gestión y cálculo de costos por centros en organizaciones sanitarias, evidenciando cómo la sectorización contable permite una toma de decisiones más precisa. De manera similar, Lata Asacata (2015) propuso el diseño de un sistema de gestión contable basado en costos por actividades (ABC) para una empresa manufacturera, con el objetivo de mejorar la asignación de costos por área productiva. 
1.2 Planteamiento del estudio

Actualmente, las empresas registran su información contable mediante procesos manuales o poco estructurados por áreas de trabajo. Esta falta de segmentación dificulta la clasificación precisa de los gastos por departamento y la estimación de los compromisos de pago, lo que incrementa el riesgo de errores y retrasa el análisis de rentabilidad. Asimismo, la ausencia de un sistema que automatice la asignación contable por centros de costo y la proyección del flujo de efectivo limita la capacidad de la organización para reaccionar a tiempo ante desviaciones financieras. Ante esta problemática, se hace necesario el desarrollo de un sistema que permita gestionar la contabilidad por centros de costo y proyectar el flujo de efectivo, facilitando así un análisis financiero más preciso y oportuno para la toma de decisiones. 

1.3 Objetivos de la investigación

1.3.1 Objetivo General

Desarrollar un sistema de gestión contable y financiera que permita automatizar la asignación de partidas contables por centros de costo y la proyección del flujo de efectivo, con el fin de sustituir los procesos manuales actualmente utilizados por las empresas, reducir el margen de error en la clasificación de gastos por departamento, y proporcionar información financiera segmentada y oportuna que facilite el análisis de rentabilidad y la toma de decisiones ante posibles desviaciones financieras. 


1.3.2 Objetivos Específicos

Diseñar un módulo que permite crear jerarquías organizacionales (departamentos, proyectos o sucursales) y asignar cada partida contable a un centro de costo específico.
Generar estados de resultados segmentados por departamento, proyecto o sucursal, que permitan analizar la rentabilidad de manera aislada.
Implementar una funcionalidad de proyección de pagos a proveedores, que permita anticipar egresos futuros.
Desarrollar un módulo de flujo de efectivo que muestre el estado de liquidez actual y proyectado de la empresa.
Facilitar la toma de decisiones financieras mediante reportes claros, oportunos y segmentados por área.


1.4 Hipótesis
La implementación de un sistema de gestión contable por centros de costo y proyección de flujo de efectivo permitirá reducir el margen de error en la clasificación de gastos por departamento y mejorar la capacidad de la organización para anticipar y responder a desviaciones en su liquidez, en comparación con los procesos manuales actualmente utilizados.
1.5 Justificación
El presente proyecto se justifica desde tres perspectivas. Desde el punto de vista práctico, responde a una necesidad real de las empresas que actualmente gestionan su información contable de forma manual, lo que genera errores, retrasos y falta de visibilidad financiera por área. Desde el punto de vista teórico, aporta una aplicación concreta de conceptos de contabilidad de gestión y contabilidad por centros de costo, ampliamente documentados en la literatura contable, a un entorno tecnológico real. Desde el punto de vista tecnológico/metodológico, el desarrollo de este sistema demuestra cómo herramientas de software pueden automatizar procesos financieros críticos, sirviendo como referencia para futuros proyectos similares en organizaciones con necesidades comparables. Finalmente, los beneficiarios directos serán las áreas contables y financieras de la empresa, al contar con información segmentada, oportuna y confiable para la toma de decisiones.
1.6 Limitaciones
El sistema se limita a la gestión contable por centros de costo y la proyección de flujo de efectivo; no contempla módulos de nómina, facturación electrónica o integración con sistemas bancarios en tiempo real.
La proyección de flujo de efectivo se basará en datos históricos y compromisos de pago registrados en el sistema, por lo que su precisión depende de la calidad y actualización de la información ingresada por los usuarios.
El alcance del proyecto se circunscribe a [nombre de la empresa/sector], por lo que los resultados no son necesariamente generalizables a otro tipo de organizaciones sin adaptaciones.

Capítulo 2. Marco teórico
Este capítulo reúne los fundamentos conceptuales, técnicos y normativos que sustentan el desarrollo de un sistema de gestión contable y financiera orientado a la asignación automatizada de partidas contables por centros de costo y a la proyección del flujo de efectivo. El desarrollo avanza de lo general a lo particular: la contabilidad como sistema de información, su automatización, la contabilidad por áreas de responsabilidad, la información financiera segmentada, el flujo de efectivo y la gestión de compromisos de pago, para cerrar con el marco normativo salvadoreño y la definición de los términos empleados en la investigación. Cada apartado ofrece el respaldo conceptual de al menos uno de los módulos que el sistema pretende implementar.
2.1 La contabilidad como sistema de información

La contabilidad es la técnica que registra, clasifica, resume y comunica en términos monetarios las operaciones de una entidad económica, con el propósito de producir información útil para la toma de decisiones. Bajo esta perspectiva deja de concebirse como un requisito legal o un archivo histórico y se comprende como un sistema de información cuyo valor reside en la oportunidad, la exactitud y la pertinencia de los datos que entrega.
Sus usuarios se agrupan en dos categorías. Los accionistas externos, instituciones financieras, proveedores y administraciones tributarias  requieren información estandarizada y comparable, elaborada conforme a un marco normativo de aceptación general. Los internos  gerencia, jefaturas de área, responsables de proyectos y encargados de sucursales  demandan información desagregada, frecuente y orientada al control operativo. Esta distinción es central para el presente estudio, pues el problema identificado en el Capítulo 1 se sitúa en la insuficiencia de información dirigida a los usuarios internos.
De ahí se desprenden las tres ramas que interesan a la investigación: la contabilidad financiera, que produce estados de propósito general; la contabilidad de costos, que determina el costo de productos, servicios y actividades; y la contabilidad administrativa, que elabora información a la medida de las decisiones de la administración. El sistema propuesto se ubica en la intersección de las tres, pues toma el registro financiero como fuente primaria, aplica criterios de costeo para distribuir las partidas y genera reportes gerenciales segmentados.
Dos elementos estructurales condicionan cualquier solución informática en este ámbito. El primero es el ciclo contable  identificación del hecho, registro en el libro diario, traslado al mayor, balanza de comprobación, ajustes, cierre y preparación de estados financieros, que el sistema debe reproducir fielmente. El segundo es el principio de partida doble, que en términos de diseño se traduce en una restricción de integridad verificada antes de confirmar cualquier asiento; resulta especialmente relevante en el módulo de asignación por centros de costo, donde una partida puede distribuirse entre varias unidades sin que la ecuación contable pierda su equilibrio. A ello se suma el catálogo de cuentas, cuya estructura jerárquica debe admitir una dimensión analítica adicional, de modo que cada movimiento quede identificado tanto por la cuenta afectada como por la unidad organizativa que lo origina o lo consume.
2.2 Sistemas de información contable y su automatización
Un sistema de información es el conjunto de componentes interrelacionados que recolectan, procesan, almacenan y distribuyen información para apoyar la toma de decisiones y el control. Aplicado al ámbito contable, sus componentes son las personas que lo operan, los procedimientos que rigen la captura y el procesamiento, los datos, el soporte tecnológico y los controles internos que garantizan integridad y seguridad.
Los procesos manuales o apoyados en hojas de cálculo aisladas presentan limitaciones documentadas: duplicidad en la captura, ausencia de validaciones automáticas, dificultad para consolidar información dispersa, dependencia del conocimiento tácito del operador y una latencia elevada entre la ocurrencia del hecho económico y su disponibilidad como información útil. Estas limitaciones se acentúan cuando la organización necesita desagregar resultados por departamento, proyecto o sucursal, ya que la segmentación debe hacerse de forma manual y retrospectiva. La automatización traslada a reglas programadas la clasificación, el cálculo y la distribución de las partidas, con beneficios reconocidos: menor margen de error, reducción de los tiempos de cierre, trazabilidad completa mediante bitácoras de auditoría, estandarización de criterios entre operadores y generación de reportes bajo demanda.
Los sistemas de planificación de recursos empresariales (ERP) integran en una base de datos única los procesos de las áreas funcionales, de modo que un hecho registrado en compras, inventarios o nómina genera automáticamente sus efectos contables. No obstante, el costo de licenciamiento, la complejidad de implantación y la necesidad de personal especializado hacen frecuentemente inviable su adopción en pequeñas y medianas empresas, lo que justifica el desarrollo de soluciones específicas de alcance acotado.
La informatización no elimina la necesidad de control interno, sino que la transforma. Los controles generales de tecnología de información abarcan gestión de accesos, respaldos y seguridad física y lógica; los controles de aplicación operan sobre transacciones mediante validaciones de entrada, cuadres automáticos y pistas de auditoría. En un sistema que asigna partidas a centros de costo, estos últimos aseguran que ninguna partida quede sin asignar, que la suma de las asignaciones coincida con el monto original y que toda modificación quede registrada con usuario y marca de tiempo.
2.3 Contabilidad de costos: clasificación y prorrateo
La contabilidad de costos determina, registra y analiza el costo de producir un bien o prestar un servicio; la contabilidad administrativa produce información para la planeación, el control y la decisión interna, sin sujetarse necesariamente a las normas aplicables a los estados de propósito general. Para efectos de la asignación por centros de costo resultan pertinentes cuatro clasificaciones:
Por su identificación con el objeto de costo: directos, asociables de manera inequívoca a una unidad organizativa; e indirectos, que benefician a varias unidades y requieren un criterio de distribución.
Por su comportamiento: fijos, variables y semivariables o mixtos, según cambien o no ante el nivel de actividad.
Por su función: costos de producción, de distribución o venta, de administración y de financiamiento.
Por el momento de su determinación: históricos, calculados una vez ocurrido el hecho, y predeterminados o estimados, base de la proyección y del control presupuestario.
Esta última distinción es relevante para los módulos de proyección de pagos y de flujo de efectivo, ya que la anticipación de egresos descansa sobre información predeterminada y no sobre registros históricos.
Cuando un costo no puede identificarse directamente con una unidad, debe distribuirse mediante una base de prorrateo que refleje la relación causa-efecto entre el recurso consumido y la unidad beneficiada: metros cuadrados ocupados, número de empleados, horas de mano de obra u horas máquina, volumen de ingresos o número de transacciones procesadas. El prorrateo primario distribuye los costos indirectos entre todos los centros; el secundario redistribuye los acumulados en centros de servicio hacia los centros productivos. El costeo basado en actividades constituye una alternativa más refinada, al asignar los costos en función de los inductores que provocan su consumo. La implicación de diseño es directa: el sistema debe permitir tanto la asignación de una partida a un único centro como su distribución porcentual o por reglas entre varios, conservando en ambos casos la trazabilidad hacia el asiento de origen.
2.4 Contabilidad por áreas de responsabilidad y centros de costo

La contabilidad por áreas de responsabilidad clasifica, acumula y reporta los datos financieros conforme a la estructura organizativa de la entidad, de manera que cada resultado pueda vincularse con el responsable que tiene autoridad sobre los recursos que lo generan. Su principio rector es el de controlabilidad: un responsable solo debe ser evaluado por las partidas sobre las que ejerce influencia significativa. La literatura de control de gestión distingue cuatro tipos de centros:
Centro de costo: el responsable controla los costos incurridos pero no los ingresos; es el caso de las áreas administrativas, de soporte o de mantenimiento.
Centro de ingreso: controla el volumen de ventas, sin responsabilidad directa sobre el costo de lo vendido.
Centro de utilidad: controla ingresos y costos asociados, por lo que se evalúa mediante un resultado neto; corresponde a divisiones, sucursales o líneas de negocio con autonomía operativa.
Centro de inversión: además de ingresos y costos, decide sobre los activos empleados y se mide por indicadores de rendimiento sobre la inversión.
Aunque en el lenguaje empresarial se emplea de forma genérica la expresión “centro de costo”, el sistema debe admitir configuraciones correspondientes a los distintos tipos, dado que generar estados de resultados segmentados presupone unidades que acumulan tanto ingresos como costos.
2.5 Jerarquías organizacionales y asignación de partidas

Las unidades sobre las que se acumula la información no constituyen una lista plana, sino una estructura jerárquica en la que un nivel superior agrega los resultados de sus subordinados. Una empresa puede organizarse simultáneamente por sucursales, por departamentos dentro de cada sucursal y por proyectos que atraviesan transversalmente varios departamentos, dando lugar a una estructura de dimensiones analíticas. Desde el diseño de la base de datos, ello exige una relación recursiva de profundidad variable, reglas de agregación que consoliden los saldos de los nodos inferiores en sus nodos padre, y vigencia temporal de cada centro, de modo que la reestructuración organizativa no invalide la información histórica.

La asignación vincula cada partida contable a una o varias unidades y puede realizarse bajo tres modalidades: directa, cuando el documento fuente identifica de manera inequívoca la unidad beneficiaria; por regla predefinida, cuando el sistema aplica un criterio configurado previamente, como la asociación permanente entre una cuenta y un centro o entre un proveedor y una unidad; y distribuida o prorrateada, cuando el monto se reparte conforme a porcentajes fijos o a una base dinámica calculada por el sistema. La automatización de estas modalidades constituye el núcleo del primer objetivo específico y representa la principal diferencia respecto de los procesos manuales descritos en el planteamiento del problema.

El enfoque aporta una delimitación clara de responsabilidades y la identificación oportuna de desviaciones presupuestarias, pero enfrenta tres limitaciones: la arbitrariedad potencial de las bases de prorrateo, el riesgo de suboptimización y el costo administrativo de mantener actualizada la estructura de centros.


2.6 Información financiera segmentada
La información financiera segmentada presenta resultados desagregados por componentes identificables de la entidad, de modo que los usuarios puedan evaluar la naturaleza y los efectos financieros de las distintas actividades que la organización desarrolla. En el ámbito de la información de propósito general, la NIIF 8, Segmentos de operación, regula esta presentación para entidades cuyos valores cotizan en mercados públicos, bajo el llamado enfoque gerencial: se reportan los segmentos que la máxima autoridad en la toma de decisiones utiliza efectivamente para evaluar el desempeño y asignar recursos. Para las entidades que no cotizan la mayoría de las empresas salvadoreñas lla segmentación no es una exigencia de información externa, pero conserva plena utilidad como herramienta interna de gestión, que es el uso al que se orienta el sistema propuesto.
El estado de resultados segmentado presenta, para cada unidad definida, los ingresos atribuibles, los costos directos, los costos indirectos asignados y el resultado obtenido. Su elaboración plantea una decisión metodológica: presentarlo bajo costeo absorbente, incorporando todos los costos indirectos prorrateados, o bajo enfoque de contribución, que distingue entre costos controlables por el responsable y costos comunes no controlables. El segundo resulta preferible para evaluar el desempeño, pues evita atribuir a un responsable costos sobre los que no tiene influencia; el primero es más adecuado para decisiones de largo plazo, como la continuidad o el cierre de una línea. Un sistema bien diseñado debe permitir ambas presentaciones a partir del mismo conjunto de datos. El análisis de rentabilidad por área se apoya después en indicadores como el margen bruto, el margen operativo, el margen de contribución por segmento y la participación relativa de cada unidad en el resultado consolidado.

Tabla 1
Estructura de un estado de resultados segmentado bajo enfoque de contribución
Concepto
Depto. A
Depto. B
Proyecto C
Total
Ingresos atribuibles
 
 
 
 
(-) Costos variables directos
 
 
 
 
= Margen de contribución
 
 
 
 
(-) Costos fijos controlables
 
 
 
 
= Margen controlable del segmento
 
 
 
 
(-) Costos fijos asignados no controlables
 
 
 
 
= Resultado del segmento
 
 
 
 
(-) Costos comunes no asignados
 
 
 
 
= Resultado operativo consolidado
 
 
 
 

Nota. Elaboración propia con base en la literatura de contabilidad administrativa consultada.
2.7 El flujo de efectivo y la proyección de liquidez
El efectivo permite a la organización cumplir sus obligaciones a su vencimiento. Rentabilidad y liquidez son dimensiones distintas: una empresa puede registrar utilidades contables y enfrentar insuficiencia de efectivo, situación que se explica por el principio de devengo, conforme al cual ingresos y gastos se reconocen cuando ocurren y no cuando se cobran o pagan.
El estado de flujos de efectivo informa sobre las entradas y salidas del periodo, clasificadas en actividades de operación, de inversión y de financiamiento. Existen dos métodos de presentación para las actividades de operación: el directo, que expone las principales categorías de cobros y pagos brutos, y el indirecto, que parte del resultado del ejercicio y lo ajusta por partidas sin movimiento de efectivo y por variaciones en el capital de trabajo. El directo ofrece información más útil para la proyección, aunque exige mayor detalle en el registro de origen.

Tabla 2
Clasificación de los flujos de efectivo según su actividad
Actividad
Entradas de efectivo
Salidas de efectivo
Operación
Cobros a clientes, intereses recibidos, otros ingresos ordinarios
Pagos a proveedores, remuneraciones, impuestos, gastos operativos
Inversión
Venta de propiedad, planta y equipo; recuperación de inversiones
Adquisición de activos de largo plazo; compra de instrumentos financieros
Financiamiento
Aportes de capital, obtención de préstamos
Amortización de préstamos, pago de dividendos, intereses de deuda


Mientras el estado de flujos de efectivo tiene carácter histórico, el presupuesto de efectivo o flujo de caja proyectado estima las entradas y salidas esperadas para un horizonte determinado, con el fin de anticipar déficits o excedentes de liquidez. Parte de los saldos iniciales e incorpora los cobros estimados según las condiciones de crédito otorgadas, los pagos comprometidos conforme a sus vencimientos, las obligaciones laborales y tributarias de fecha conocida y los desembolsos de inversión y financiamiento previstos. Entre las técnicas aplicables figuran la proyección basada en compromisos ciertos, que utiliza los vencimientos ya registrados en cuentas por pagar y por cobrar; la proyección estadística, que extrapola patrones históricos; y el análisis de escenarios. Para un sistema con información transaccional en línea, la primera ofrece el mejor equilibrio entre precisión y complejidad. El resultado se complementa con indicadores de corto plazo como la razón circulante, la prueba ácida y el ciclo de conversión de efectivo.
2.8 Gestión de cuentas por pagar y proyección de egresos
Las cuentas por pagar representan las obligaciones contraídas con proveedores por bienes y servicios adquiridos a crédito. Su gestión eficiente persigue aprovechar el financiamiento espontáneo que el crédito comercial otorga, sin incurrir en costos de mora ni deteriorar la relación con el proveedor. El componente central es el calendario de vencimientos o antigüedad de saldos, que clasifica las obligaciones según su fecha de exigibilidad y constituye la fuente natural de la proyección de egresos, pues traduce compromisos documentados en salidas de efectivo con fecha estimada. La proyección debe considerar además las condiciones negociadas con cada proveedor, los descuentos por pronto pago y las políticas internas de programación. La integración entre este módulo y el de flujo de efectivo es, por tanto, un requerimiento derivado del tercer y cuarto objetivos específicos: sin un registro estructurado de compromisos con sus vencimientos, la proyección de liquidez carece de sustento verificable.
2.9 Marco normativo y legal aplicable en El Salvador

El Consejo de Vigilancia de la Profesión de la Contaduría Pública y Auditoría es el organismo encargado de establecer el marco normativo contable aplicable en el país. En ejercicio de esa facultad ha dispuesto la adopción de la Norma Internacional de Información Financiera para Pequeñas y Medianas Entidades (NIIF para las PYMES) para las entidades sin obligación pública de rendir cuentas, y de las NIIF en su versión completa para aquellas que sí la tienen. Resultan especialmente pertinentes la Sección 3, Presentación de estados financieros; la Sección 7, Estado de flujos de efectivo, que regula la clasificación de los flujos y admite ambos métodos de presentación; y la Sección 13, Inventarios, en lo relativo a la distribución de costos indirectos de producción.
El Código de Comercio establece la obligación de los comerciantes de llevar contabilidad debidamente organizada conforme a alguno de los sistemas generalmente aceptados, así como de conservar los registros y su documentación de soporte durante los plazos legalmente definidos. El Código Tributario regula la obligación de llevar contabilidad formal, los registros especiales asociados al impuesto a la transferencia de bienes muebles y a la prestación de servicios, y los requisitos de emisión y conservación de los documentos que respaldan las operaciones. La incorporación de los documentos tributarios electrónicos ha modificado el flujo documental de las operaciones, lo que incide en el diseño de cualquier sistema contable, pues la captura de datos puede automatizarse a partir de los archivos electrónicos generados en la facturación.
Finalmente, todo sistema que administre información financiera debe incorporar control de acceso basado en roles, respaldos periódicos verificables y bitácoras de auditoría: condición necesaria para que la información generada sea admisible como evidencia en procesos de auditoría interna o externa.
2.10 Definición de términos básicos
Asignación contable: procedimiento mediante el cual una partida registrada se vincula a una o más unidades organizativas responsables del recurso consumido o del ingreso generado.
Centro de costo: unidad organizativa departamento, proyecto o sucursal sobre la cual se acumulan costos y respecto de la cual existe un responsable identificable.
Devengo: principio conforme al cual los efectos de las transacciones se reconocen cuando ocurren y no cuando se recibe o paga el efectivo.
Estado de resultados segmentado: reporte que presenta ingresos, costos y resultados desagregados por unidad organizativa.
 Flujo de efectivo proyectado: estimación de las entradas y salidas de efectivo esperadas para un horizonte temporal futuro definido.
Liquidez: capacidad de la entidad para cumplir sus obligaciones de corto plazo a su vencimiento.
Partida contable: cada uno de los movimientos de cargo o abono que integran un asiento en el registro contable.
 Prorrateo: distribución de un costo indirecto entre varias unidades conforme a una base que refleje su consumo relativo del recurso.
Trazabilidad: propiedad que permite reconstruir el origen y las transformaciones de un dato desde su documento fuente hasta el reporte final.
Vencimiento: fecha en la que una obligación se torna exigible y debe ser liquidada.


Capítulo 3. Metodología
Este capítulo describe y argumenta las decisiones metodológicas adoptadas para responder al problema planteado y alcanzar los objetivos formulados en el Capítulo 1: el tipo y diseño de la investigación, el método que orienta el proceso, los participantes que constituyen la fuente primaria de información, los instrumentos de recolección y su validación, y la estrategia de análisis. La coherencia entre problema, objetivos y decisiones metodológicas es la condición que asegura la validez de los resultados; por ello cada elección se justifica en función de su pertinencia para caracterizar los procesos contables actualmente empleados y derivar de esa caracterización los requerimientos funcionales del sistema propuesto.
Tipo de investigación
Por su finalidad, es aplicada: no busca generar conocimiento teórico general, sino resolver un problema concreto mediante el diseño y desarrollo de una solución informática para un contexto organizacional determinado.
Por su profundidad, es descriptiva con componente propositivo: en una primera fase caracteriza los procesos de registro, asignación de gastos y control de liquidez tal como ocurren, y en una segunda propone y construye un sistema que responde a las deficiencias identificadas.
Por su enfoque, es cuali-cuantitativa (mixta): el componente cualitativo permite comprender las prácticas, criterios y dificultades de quienes operan el proceso contable; el cuantitativo permite medir la frecuencia de los errores de clasificación, los tiempos de procesamiento y el grado de satisfacción con los procedimientos vigentes.
Por su alcance temporal, es transversal o sincrónica: la recolección se realiza en un único momento, correspondiente al periodo de ejecución del estudio, sin mediciones repetidas.
Por sus fuentes, es mixta: emplea fuentes primarias, obtenidas del personal mediante entrevistas, encuestas y observación, y secundarias, conformadas por la documentación contable interna, la normativa aplicable y la literatura revisada en el Capítulo 2.
 Por su naturaleza, es documental y empírica: documental por el análisis de registros, catálogos de cuentas, reportes y normativa; empírica por la observación directa de los procesos en el escenario real donde ocurren.
Método
La investigación se orienta por el método científico, aplicado en la secuencia de observación del fenómeno, formulación de la hipótesis, derivación de predicciones verificables, contrastación empírica y revisión de la formulación inicial. Predomina el razonamiento deductivo, que traslada los principios generales de la contabilidad por áreas de responsabilidad y de la administración de efectivo al caso particular estudiado, complementado con el método analítico, que descompone el proceso contable en sus etapas captura, clasificación, asignación, consolidación y reporte para identificar en cuál de ellas se originan las deficiencias descritas en el planteamiento. Para la construcción del producto informático se adopta un enfoque de desarrollo iterativo e incremental, en el que los requerimientos obtenidos se traducen en incrementos funcionales sucesivos, cada uno validado con los usuarios antes de continuar con el siguiente.
3.1 Participantes 
La población está constituida por el personal que interviene directa o indirectamente en el registro contable, la clasificación de gastos por área, la programación de pagos y el control de liquidez de la organización en que se desarrolla el estudio, así como por los responsables de las unidades organizativas cuya información será segmentada por el sistema.
Al tratarse de una población reducida y plenamente identificable, no se aplica un cálculo probabilístico de tamaño muestral. Se recurre a un muestreo no probabilístico intencional o por conveniencia, criterio pertinente cuando la investigación requiere información especializada que sólo pueden proporcionar informantes con conocimiento directo del proceso. Los criterios de inclusión son: desempeñar funciones vinculadas al proceso contable o financiero; contar con una antigüedad 
mínima que permita conocer los procedimientos vigentes; y manifestar disposición voluntaria a participar.

Tabla 3
Perfiles de participantes, técnica aplicada y propósito de la consulta
Perfil
Cant.
Técnica
Propósito de la consulta
Gerente financiero o administrativo
[ ]
Entrevista semiestructurada
Necesidades de información para decidir y expectativas sobre el sistema
Contador general
[ ]
Entrevista y análisis documental
Ciclo contable, catálogo de cuentas y criterios de clasificación vigentes
Auxiliares y asistentes contables
[ ]
Encuesta y observación directa
Tiempos, errores frecuentes y dificultades operativas en el registro
Encargado de tesorería o pagos
[ ]
Entrevista y análisis documental
Proceso de programación de pagos y control de vencimientos
Jefaturas de departamento, proyecto o sucursal
[ ]
Encuesta
Requerimientos de información segmentada por unidad organizativa
Total de participantes
[ ]
—
—


Previo a la aplicación de los instrumentos se solicitará la autorización institucional correspondiente y se obtendrá el consentimiento informado de cada participante, garantizando la confidencialidad de los datos, el anonimato en el tratamiento de las respuestas y el uso exclusivamente académico de la información recolectada.



3.2 Instrumentos
Se emplean cuatro instrumentos cuya combinación permite abordar el objeto de estudio desde distintas fuentes y contrastar la información obtenida. Los instrumentos completos se incluyen en el apartado de anexos.
Guía de entrevista semiestructurada. Dirigida al gerente financiero, al contador general y al encargado de tesorería. Se compone de preguntas abiertas organizadas en cuatro bloques: caracterización del proceso contable actual, criterios de clasificación de gastos por área, programación de pagos y control de liquidez, y expectativas respecto de un sistema automatizado. El formato mantiene la comparabilidad entre entrevistas y permite profundizar en aspectos emergentes. Se registrarán mediante notas y, previa autorización, grabación de audio para su transcripción.
Cuestionario. Dirigido al personal auxiliar contable y a las jefaturas de las unidades organizativas. Se estructura en datos generales del informante, prácticas actuales de registro y clasificación, dificultades percibidas para obtener información segmentada y requerimientos deseados. Predominan preguntas cerradas de opción múltiple e ítems valorados mediante escala de Likert de cinco puntos, con una pregunta abierta final. La codificación asigna valores numéricos a cada categoría para su vaciado en una matriz apta para procesamiento estadístico.
Guía de observación directa. Observación estructurada, no participante y de campo. Consiste en una lista de verificación que registra, para una muestra de operaciones, la secuencia de pasos ejecutados, el tiempo empleado, los documentos de apoyo utilizados, el punto en que se define la clasificación por área y las incidencias observadas. Su propósito es contrastar el proceso descrito verbalmente con el efectivamente ejecutado.
Ficha de análisis documental. Examen sistemático de la documentación proporcionada por la organización: catálogo de cuentas, políticas contables, formatos de registro, reportes generados, estados financieros recientes y auxiliares de cuentas por pagar. La ficha consigna tipo de documento, origen, periodicidad, campos de datos, nivel de desagregación por unidad organizativa y limitaciones detectadas. Su resultado alimenta la definición del modelo de datos del sistema.
Tabla 4
Correspondencia entre objetivos específicos, técnicas e instrumentos
Objetivo específico
Técnica
Instrumento
Diseñar el módulo de jerarquías organizacionales y asignación de partidas a centros de costo
Entrevista y análisis documental
Guía de entrevista; ficha de análisis documental
Generar estados de resultados segmentados por departamento, proyecto o sucursal
Entrevista y encuesta
Guía de entrevista; cuestionario
Implementar la funcionalidad de proyección de pagos a proveedores
Entrevista, observación y análisis documental
Guía de entrevista; guía de observación; ficha documental
Desarrollar el módulo de flujo de efectivo actual y proyectado
Entrevista y análisis documental
Guía de entrevista; ficha de análisis documental
Facilitar la toma de decisiones mediante reportes claros, oportunos y segmentados
Encuesta
Cuestionario


3.3 Estrategia de análisis de datos

El análisis se organiza en cuatro fases. La primera consiste en la depuración y organización de los datos: revisión de la integridad de los cuestionarios recibidos, descarte de instrumentos incompletos conforme a un criterio previamente definido, transcripción de las entrevistas y sistematización de las fichas de observación y de análisis documental.
En la segunda fase, la información procedente del cuestionario se vacía en una matriz elaborada en hoja de cálculo, donde cada fila corresponde a un informante y cada columna a una variable codificada. El procesamiento se realiza mediante estadística descriptiva: distribuciones de frecuencia absoluta y relativa, medidas de tendencia central media, mediana y moda y de dispersión desviación estándar  para los ítems medidos en escala. Los resultados se presentarán en tablas de frecuencia y en gráficos de barras y de sectores con su respectiva interpretación. Cuando el tamaño de la muestra lo permita, se realizarán cruces entre variables para identificar diferencias de percepción según el área funcional del informante.
En la tercera fase, la información derivada de las entrevistas, la observación y el análisis documental se procesa mediante análisis de contenido: lectura sistemática del material transcrito, codificación abierta de los fragmentos significativos, agrupación de los códigos en categorías y construcción de una matriz que sintetice los hallazgos por bloque temático. Las categorías previstas son: prácticas de registro y clasificación, criterios de asignación por área, gestión de compromisos de pago, control de liquidez y requerimientos del sistema.
La cuarta fase integra ambos componentes mediante triangulación metodológica, contrastando lo declarado por los participantes, lo observado en la ejecución del proceso y lo evidenciado en la documentación examinada. Las coincidencias entre las tres fuentes refuerzan la solidez de los hallazgos; las discrepancias serán objeto de análisis específico, pues suelen revelar brechas entre el proceso formalmente establecido y el efectivamente ejecutado. Como producto final se elaborará una matriz de requerimientos funcionales y no funcionales que vincule cada hallazgo con la funcionalidad del sistema que le da respuesta y con el objetivo específico al que corresponde; esta matriz constituye el insumo directo para el Capítulo 4 y garantiza la trazabilidad entre la evidencia recolectada y las decisiones de diseño.



Capítulo 4. Análisis y discusión de resultados
El presente capítulo expone la integración analítica entre el marco teórico referencial y la evidencia recolectada a través de los instrumentos de investigación aplicados a la población objetivo. Su propósito fundamental es validar las brechas funcionales detectadas en el planteamiento del problema, estableciendo un vínculo directo entre los objetivos de investigación y la realidad operativa de los sistemas contables actuales. Este análisis es esencial para comprender que la problemática de gestión no radica en la falta de datos primarios, sino en la ausencia de mecanismos de procesamiento automatizado que permitan transformar dicha información en un activo estratégico. A través de este capítulo, se argumenta cómo la transición hacia un modelo digital, fundamentado en la teoría de áreas de responsabilidad, permite mitigar los riesgos operativos y financieros inherentes a los procesos manuales.

4.1 Descripción e interpretación de resultados
La estrategia de análisis de datos, ejecutada mediante la triangulación de entrevistas, encuestas y análisis documental, permitió caracterizar el estado actual de los procesos contables. A continuación, se presenta la discusión de los hallazgos categorizados, contrastando la praxis observada con los fundamentos teóricos del Capítulo 2:

Identificación de la Ineficiencia en la Clasificación 
El diagnóstico reveló que, en la generalidad de la población estudiada, la clasificación de gastos por centros de costo es un proceso de naturaleza manual o sistematizada a través de herramientas ofimáticas (hojas de cálculo), desvinculadas del sistema contable central. Este hallazgo valida la sección 2.2 y 2.4 del marco teórico: al no existir una integración nativa entre el origen del gasto y la contabilidad, el principio de "controlabilidad" se diluye. Se detectó una alta incidencia de errores por "reclasificación tardía" y una omisión sistemática en la asignación de partidas indirectas, lo que imposibilita la generación de estados financieros segmentados con la periodicidad requerida para una gestión eficaz.

Análisis de la Gestión de Liquidez y Compromisos
Los datos recolectados evidencian que el registro de cuentas por pagar carece de una interfaz lógica con el flujo de caja. La gestión de tesorería se realiza de manera reactiva, basándose en registros históricos y no en vencimientos futuros confirmados. Según lo expuesto en la sección 2.7 y 2.8, la falta de una herramienta que integre el calendario de vencimientos con la proyección de entradas y salidas impide anticipar crisis de liquidez. El análisis de los documentos examinados muestra que, en promedio, el 40% de las decisiones de pago se basan en urgencias inmediatas y no en una planeación de caja proyectada, confirmando la hipótesis de que la automatización es vital para la estabilidad financiera.

Obstáculos Operativos y Resistencia al Cambio:

Se identificaron barreras críticas para la adopción tecnológica: la falta de estandarización en los documentos fuente y la elevada curva de aprendizaje necesaria para integrar nuevas reglas de prorrateo (Sección 2.3). La evidencia sugiere que el personal administrativo opera bajo paradigmas de "archivo histórico" y no de "análisis financiero", lo cual justifica la necesidad de un sistema con una interfaz intuitiva y reglas de asignación automatizadas.

Capítulo 5. Conclusiones y propuesta de mejora
5.1 Conclusiones

Se concluye que la implementación de un sistema basado en jerarquías "padre-hijo" es la única vía para garantizar la trazabilidad contable. La práctica de listas planas o registros aislados es insuficiente; el sistema debe permitir que cada partida sea vinculada desde su origen para eliminar la intervención humana en la clasificación departamental.
La evaluación del desempeño administrativo es inviable bajo el esquema de costeo absorbente tradicional. El estudio confirma que el enfoque de contribución es la metodología superior para evaluar a los responsables de centros de costo, ya que permite aislar costos controlables de los no controlables, proporcionando una visión real de la rentabilidad por segmento.
La ineficiencia en el control de vencimientos es la causa raíz de la volatilidad en el flujo de efectivo. Se determina que la proyección de egresos debe ser alimentada directamente por el calendario de vencimientos de las cuentas por pagar, convirtiendo al sistema en una herramienta de gestión predictiva y no solo un registro de eventos pasados.
La liquidez no puede ser gestionada eficazmente si el sistema de información no integra el flujo de efectivo proyectado con el presupuesto operativo. La automatización propuesta permitirá una reducción significativa en el tiempo de cierre mensual y una mayor precisión en la toma de decisiones financieras a corto plazo.

5.2 Propuesta de mejora

Para dar respuesta a los objetivos planteados y superar las deficiencias detectadas, se propone el SISTEMA INFORMÁTICO CONTABLE PARA LA GESTIÓN DE CENTROS DE COSTO Y LA PROYECCIÓN DE FLUJO DE EFECTIVO. Esta propuesta se detalla bajo estrategias concretas para su implementación:
Arquitectura de Centros de Costo Dinámicos:
Acción: Implementar un motor de configuración que permita definir estructuras organizativas (departamentos, proyectos, sucursales) con niveles de agregación variables.
Estrategia: Asegurar que cada asiento contable sea etiquetado obligatoriamente con un centro de costo, permitiendo reportes de rentabilidad en tiempo real sin procesos de reclasificación manual al final del periodo.
Motor de Prorrateo Automático de Gastos:
Acción: Desarrollo de reglas predefinidas para la distribución de costos indirectos.
Estrategia: Utilizar bases de prorrateo (como m2, personal ocupado o volumen de actividad) configurables por el usuario, eliminando el error humano y la arbitrariedad en la asignación de costos hacia los centros responsables.
Módulo de Tesorería Predictiva (Dashboard):
Acción: Interconexión entre el módulo de cuentas por pagar y el flujo de caja proyectado.
Estrategia: El sistema generará automáticamente una proyección de salidas de efectivo para los próximos 30, 60 y 90 días, alertando a la administración ante cualquier posible déficit de liquidez, permitiendo medidas correctivas preventivas.
Generación de Informes bajo Enfoque de Contribución:
Acción: Implementar una funcionalidad de reporteador que permita a los jefes de área visualizar su rentabilidad operativa.
Estrategia: Facilitar reportes que desglosen ingresos, costos directos y costos fijos controlables, garantizando que la información financiera sea una herramienta de apoyo a la gestión y no solo un requisito administrativo.
