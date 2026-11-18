# Gestión Escolar

Sistema de gestión para un colegio chileno, inspirado en [Frappe Education](https://github.com/frappe/education).
Incluye **estudiantes, profesores, apoderados, cursos, asignaturas, horarios, admisiones**
(con expediente de documentos, entrevistas y puntajes), **asistencia, notas** (escala chilena de
1.0 a 7.0) con **evaluaciones formales**, **pagos**
(matrícula, mensualidades y cuotas) con **pago en línea** (Webpay o simulación local) y **conciliación
bancaria**, **reportes** (planillas Excel y certificado firmado electrónicamente con verificación
pública), **notificaciones** a las familias (con envío opcional por correo o WhatsApp), un **control
de planificaciones UTP** contra las Bases Curriculares, un **portal de familias** y un **portal público
de postulación**, con validación de **RUT** y **roles de usuario**.

- **Backend:** Python + FastAPI + SQLAlchemy (SQLite por defecto, PostgreSQL opcional)
- **Frontend:** Next.js + TypeScript
- **Entrada al sistema:** login con correo y contraseña (JWT); el panel es para el personal y el
  portal para apoderados y estudiantes

## Cómo encenderlo

Necesitas dos terminales abiertas al mismo tiempo.

### Terminal 1: backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
python seed.py                   # (opcional) carga datos de ejemplo
uvicorn app.main:app --reload --port 8000
```

La documentación automática de la API queda en http://localhost:8000/docs

Los datos de ejemplo incluyen asignaturas, horarios, admisiones, asistencia, notas, cobros con sus
pagos y cuentas del portal. Si vienes de la versión anterior, las tablas y columnas nuevas se crean
solas al iniciar; para cargar los datos de ejemplo nuevos necesitas partir de una base vacía (o crear
los datos desde el sistema).

### Terminal 2: frontend

```bash
cd frontend
npm install
npm run dev
```

Abre http://localhost:3000

### Usuario inicial

| Correo | Contraseña | Rol |
|---|---|---|
| `admin@colegio.cl` | `admin1234` | Administrador |

Se crea solo la primera vez. **Cámbialo antes de usarlo en serio** con las variables
`ADMIN_EMAIL`, `ADMIN_PASSWORD` y `SECRET_KEY` (ver abajo).

Los demás usuarios se crean desde **Usuarios** (solo el administrador puede entrar a esa sección).
Si cargas los datos de ejemplo con `seed.py`, también se crean estas cuentas del portal:

| Correo | Contraseña | Rol | Vinculada a |
|---|---|---|---|
| `apoderado@colegio.cl` | `apoderado1234` | Apoderado | primer apoderado de la base |
| `estudiante@colegio.cl` | `estudiante1234` | Estudiante | primer estudiante de la base |

## Roles y permisos

| Rol | Puede hacer |
|---|---|
| **Administrador** | Todo, incluida la gestión de usuarios |
| **Secretaría** | Estudiantes, apoderados, cursos, asignaturas, horarios, admisiones, pagos (incluida la conciliación de pagos en línea), notificaciones y panel; no gestiona usuarios |
| **Profesor** | Ver estudiantes, asignaturas, horarios y panel; marcar asistencia y registrar notas |
| **Apoderado** | Entra al portal de familias y ve la asistencia, notas, cobros y avisos de sus estudiantes; puede pagar en línea |
| **Estudiante** | Entra al portal y ve su propia asistencia, notas, cobros y avisos; puede pagar en línea |

Los apoderados y estudiantes quedan vinculados a una ficha de apoderado o de estudiante al crear su
usuario. El login redirige automáticamente al panel o al portal según el rol.

## Qué hace cada parte

| Sección | Qué puedes hacer |
|---|---|
| Panel | Ver totales, la asistencia de hoy y cuántos estudiantes hay en cada curso |
| Asistencia | Marcar el día completo de un curso y ver el resumen mensual por estudiante |
| Notas | Registrar notas de 1.0 a 7.0, con ponderación, y ver promedios por asignatura |
| Evaluaciones | Definir pruebas, controles y trabajos por curso y asignatura, con tipo, fecha y ponderación |
| Reportes | Descargar planillas Excel de notas y asistencia, el resumen del curso y el certificado de alumno regular firmado electrónicamente |
| Estudiantes | Crear, editar, buscar por nombre o RUT, filtrar por curso, retirar |
| Profesores | Crear, editar, buscar, ver de qué curso son profesor jefe |
| Apoderados | Crear, editar, buscar; se asignan a cada estudiante |
| Cursos | Crear cursos por año, asignar profesor jefe, ver cupos |
| Asignaturas | Crear los ramos que se dictan en el colegio |
| Horarios | Asignar asignaturas y profesores a cada curso, y armar el horario semanal (también por profesor) |
| UTP | Subir planificaciones de unidad en Word, comparar sus OA con las Bases Curriculares y descargar el Excel de control con el semáforo por planificación |
| Admisiones | Registrar postulaciones, seguir su estado y matricular al postulante creando su ficha de estudiante; adjuntar documentos, agendar entrevistas y registrar puntajes; recibir postulaciones en línea |
| Pagos | Registrar matrículas, mensualidades, cuotas y otros cobros; generar cobros por curso; abonar pagos parciales y ver saldos; revisar los pagos en línea e importar la cartola bancaria para conciliarla |
| Notificaciones | Generar avisos por inasistencia, notas o deuda, crear avisos manuales, enviarlos por correo o WhatsApp y publicarlos en el portal de las familias |
| Usuarios | Crear cuentas del panel (administrador, secretaría, profesor) y del portal (apoderado, estudiante), activarlas o desactivarlas |
| Portal de familias | Cada apoderado o estudiante entra con su cuenta y ve asistencia, notas, deuda y avisos del estudiante; puede pagar en línea los cobros con saldo |
| Postulación en línea | Página pública donde una familia completa los datos del postulante y del apoderado, y luego adjunta documentos con su número de seguimiento |

Detalles que conviene saber:

- **RUT:** se valida el dígito verificador (también en el navegador) y se guarda sin puntos. No se pueden repetir.
- **Retirar un estudiante** no borra su ficha: queda inactivo y con estado "retirado".
- **Borrar un profesor, apoderado o curso** no borra a los estudiantes: solo quedan sin ese dato asignado.
  Un curso con asistencia o notas registradas no se puede eliminar, para no perder historial.
- **Asistencia:** se marca por curso y día, con los estados *presente*, *ausente*, *atrasado* y *justificado*.
  Queda un registro por estudiante y fecha; se puede corregir el mismo día o dejar a alguien sin marcar.
  El porcentaje de asistencia cuenta como asistencia los estados "presente" y "atrasado".
- **Notas:** cada nota tiene evaluación, fecha y ponderación. El promedio de la asignatura es ponderado;
  el promedio general del curso es el promedio de los promedios por asignatura. La aprobación es desde 4.0.
  Una asignatura con notas no se puede eliminar.
- **Evaluaciones:** cada evaluación pertenece a una asignatura de un curso y tiene tipo (prueba, control,
  tarea, proyecto, examen u otro), fecha y ponderación. Al registrar notas desde **Notas** se puede elegir
  la evaluación y la nota hereda su nombre, fecha y ponderación; también se puede registrar una nota sin
  evaluación ("registro libre"). Solo puede existir una evaluación con el mismo nombre en la misma
  asignatura del curso. Una evaluación con notas no se elimina ni cambia de curso o asignatura, y al
  editarla se actualizan también sus notas.
- **Reportes:** la planilla de notas genera un libro Excel con una hoja de resumen (promedios por
  asignatura) y una hoja por asignatura con las evaluaciones, las notas y el promedio ponderado de
  cada estudiante. El libro de asistencia muestra un casillero por día del mes (P/T/A/J) y el
  porcentaje de cada estudiante. El resumen del curso agrega la asistencia del año y la deuda total y
  vencida por estudiante (solo administración y secretaría). El certificado de alumno regular se abre
  en una hoja imprimible; desde el navegador se puede guardar como PDF.
- **Horarios:** cada curso tiene sus asignaturas con un profesor a cargo (o sin asignar). El horario es
  semanal, de lunes a viernes, y no permite dos clases del mismo curso, del mismo profesor ni en la misma
  sala a la vez. Una asignatura asignada a un curso no se puede eliminar. También hay una vista por profesor.
- **Control UTP:** se suben una o varias planificaciones de unidad en Word (`.docx`); el sistema lee
  docente, asignatura, curso, unidad, fechas, clases, evaluaciones, OA basales y OAT, y compara los OA
  citados con las **Bases Curriculares de Lengua y Literatura 7° y 8°** incluidas (se puede subir otro
  archivo `.txt` o `.pdf`). Muestra un resumen con semáforo (CUMPLE, REVISAR, NO CUMPLE, POR MARCAR),
  el detalle por clase, evaluación, OA basal y OAT, y permite descargar el **Excel de control**. Si se
  sube el Excel de una revisión anterior, se conservan las clases creadas, fechas y observaciones
  escritas a mano. El Excel descargado queda disponible durante 24 horas; solo lo usa el personal.
- **Admisiones:** cada postulación guarda los datos del postulante y de su apoderado, el curso al que
  postula y su estado (postulada, en revisión, aceptada, rechazada o matriculada). Al matricular se crea
  la ficha del estudiante y, si el apoderado tiene RUT, se reutiliza su ficha o se crea una nueva. Se
  valida que el curso tenga cupos y que el RUT no exista ya como estudiante.
- **Expediente de admisión:** cada postulación tiene su expediente con documentos adjuntos (PDF, JPG o
  PNG de hasta 5 MB), entrevistas (fecha y hora, entrevistador, modalidad presencial/online/teléfono,
  estado y observaciones) y puntajes por criterio de 0 a 100 con ponderación, que se resumen en un
  puntaje ponderado. Los documentos se guardan en la base de datos y se pueden descargar o eliminar;
  el expediente se elimina junto con la postulación. Solo administración y secretaría lo gestionan.
- **Postulación en línea:** la página pública `/postular` (enlazada desde el login) lista los cursos del
  año con sus cupos y permite a la familia enviar la solicitud. Al crearla se entrega un número de
  seguimiento (token); con el enlace `/postular/{token}` la familia consulta el estado y adjunta PDF,
  JPG o PNG de hasta 5 MB. La postulación queda como *postulada* y aparece de inmediato en
  **Admisiones**, donde el colegio la revisa y matricula. El token no sirve para ver otras postulaciones.
- **Pagos:** cada cobro tiene tipo (matrícula, mensualidad, cuota u otro), período (`AAAA-MM`), monto en
  pesos, vencimiento y uno o varios pagos. El estado se calcula solo: *pagada* si el saldo es 0,
  *vencida* si el vencimiento ya pasó y queda saldo, *parcial* si hay abonos, *pendiente* si no hay
  abonos. "Generar por curso" crea el mismo cobro para todos los estudiantes activos y omite a quienes
  ya lo tienen en ese tipo y período. Un cobro con pagos no se puede editar ni eliminar: primero se
  elimina el pago equivocado.
- **Pago en línea:** desde el portal, cada cobro con saldo tiene el botón "Pagar en línea". Con
  `WEBPAY_COMMERCE_CODE` y `WEBPAY_API_KEY` configurados se crea una transacción en **Webpay Plus**
  (ambiente de integración o producción), la familia paga en Transbank y el retorno confirma el cobro de
  forma idempotente; el abono queda con medio *tarjeta* y referencia `WEBPAY-...`. Sin credenciales se
  usa una **simulación local** que imita el mismo flujo (no cobra dinero real) con referencia `ONLINE-...`.
  En **Pagos** el colegio ve la lista de transacciones (pendientes, pagadas y canceladas) y puede
  conciliar la cartola bancaria: se importa un CSV con fecha, descripción y monto, y el sistema busca el
  cobro por RUT o por referencia; los movimientos sin coincidencia se asignan a mano a un cobro.
  Confirmar dos veces no duplica el pago, y una transacción cancelada no se puede confirmar.
- **Notificaciones:** "Generar avisos" recorre a los estudiantes activos con apoderado y crea un aviso
  por cada caso: asistencia bajo 85% en el mes (con al menos 5 días registrados), promedio general bajo
  4.0 o cobros vencidos con saldo. No se duplican avisos del mismo estudiante, motivo y período. Los
  avisos nacen *pendientes*; al marcarlos como *enviados* aparecen en el portal de la familia. También
  se pueden crear avisos manuales (por ejemplo, una reunión de apoderados) para un estudiante. Si el
  apoderado tiene correo, el botón "Enviar por correo" lo manda por SMTP y deja el aviso como enviado
  con el canal *email*; sin `SMTP_HOST` configurado el envío se rechaza con un mensaje claro. Si tiene
  teléfono, "Enviar WhatsApp" usa la API de WhatsApp Cloud (normaliza el número chileno a `56…`) y deja
  el aviso como enviado; sin `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_ID` también se rechaza con un mensaje claro.
- **Portal:** el apoderado ve a todos sus estudiantes (los activos con su `guardian_id`) y el estudiante
  solo su propia ficha. Muestra asistencia de los últimos 60 días, promedio ponderado por asignatura,
  promedio general, la lista de cobros con saldo pendiente y vencido, y los avisos ya enviados por el
  colegio.

## Configuración (variables de entorno)

| Variable | Para qué sirve | Valor por defecto |
|---|---|---|
| `DATABASE_URL` | Base de datos | `sqlite:///./colegio.db` |
| `SECRET_KEY` | Clave para firmar las sesiones | una de ejemplo (cámbiala) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Usuario inicial | `admin@colegio.cl` / `admin1234` |
| `CORS_ORIGINS` | Direcciones del frontend permitidas | `http://localhost:3000` |
| `SMTP_HOST` / `SMTP_PORT` | Servidor de correo saliente | vacío (envío deshabilitado) / `587` |
| `SMTP_USER` / `SMTP_PASSWORD` | Credenciales SMTP (si el servidor las pide) | vacío |
| `SMTP_FROM` | Remitente de los avisos por correo | vacío |
| `SMTP_TLS` / `SMTP_SSL` | Usar STARTTLS / conexión SSL | `1` / `0` |
| `WHATSAPP_TOKEN` | Token de WhatsApp Cloud API | vacío (envío deshabilitado) |
| `WHATSAPP_PHONE_ID` | ID del número emisor de WhatsApp | vacío |
| `WHATSAPP_API_URL` | Base de la API de WhatsApp | `https://graph.facebook.com/v20.0` |
| `WEBPAY_COMMERCE_CODE` / `WEBPAY_API_KEY` | Credenciales de Webpay Plus (sin ellas se usa la simulación) | vacío |
| `WEBPAY_ENVIRONMENT` | Ambiente de Webpay (`integration` o `production`) | `integration` |
| `PUBLIC_API_URL` | URL pública del backend para el retorno de Webpay | `http://localhost:8000/api` |
| `FRONTEND_URL` | URL pública del frontend para volver desde Webpay | `http://localhost:3000` |
| `SIGNATURE_KEY` | Clave de la firma de certificados (usa `SECRET_KEY` si está vacía) | vacío |
| `NEXT_PUBLIC_API_URL` (frontend) | Dónde está el backend | `http://localhost:8000/api` |

Para PostgreSQL instala además `psycopg[binary]` y usa
`DATABASE_URL=postgresql+psycopg://usuario:clave@localhost/colegio`.

## Pruebas

```bash
cd backend
pytest
```

Revisan el RUT, el login, el flujo completo (profesor → curso → apoderado → estudiante),
la asistencia por curso y día, las notas y promedios, las evaluaciones formales, los horarios y sus
choques, las admisiones y la matrícula, los cobros y pagos con sus saldos, la generación de cobros por
curso, el portal de apoderado y estudiante, los reportes Excel y el certificado, las notificaciones
(generación, duplicados, envío y visibilidad en el portal), el expediente de admisión (documentos,
entrevistas y puntajes), los pagos en línea (checkout, confirmación idempotente, cancelación y
conciliación), la postulación en línea (envío, seguimiento, documentos y matrícula), el envío de
avisos por correo y WhatsApp, el checkout con Webpay y la firma de certificados, la conciliación
bancaria (importación de cartola y asignación manual), la verificación pública de certificados, el
control UTP (lectura de planificaciones Word, análisis contra las Bases y descarga del Excel), los
permisos por rol y los errores esperados.

## Estructura

```
backend/
  app/
    main.py          arranque de la API
    models.py        tablas de la base de datos
    schemas.py       datos que entran y salen de la API
    rut.py           validación del RUT
    security.py      login, sesiones y permisos por rol
    mailer.py        envío de correos por SMTP
    whatsapp.py      envío de avisos por WhatsApp Cloud API
    webpay.py        cliente de Webpay Plus (Transbank)
    signing.py       firma HMAC-SHA256 de certificados
    utp_engine.py    motor de revisión de planificaciones (Word, Bases y Excel)
    utp_bases/       Bases Curriculares de Lengua y Literatura 7° y 8° incluidas
    routers/         un archivo por sección (incluye fees.py, payments.py, public.py,
                     evaluations.py, reports.py, notifications.py, utp.py, users.py y portal.py)
  tests/             pruebas automáticas
  seed.py            datos de ejemplo
frontend/
  app/               pantallas: panel, estudiantes, pagos, usuarios, portal de familias, ...
  components/CrudPage.tsx   lista + formulario reutilizable
  lib/               conexión con la API, RUT, fechas y formato de dinero
```

## Qué falta respecto a Frappe Education

Ya están implementadas las **evaluaciones formales**, las **planillas y reportes**, las
**notificaciones** a las familias (con envío por correo o WhatsApp), el **expediente de admisión**
(documentos, entrevistas y puntajes), el **pago en línea** con Webpay y conciliación bancaria, la
**firma electrónica** de certificados con verificación pública y el **portal público de postulación**.
Los siguientes pasos posibles, en orden de utilidad, serían:

1. **Plantillas y programación de avisos** por tipo, con reintentos y registro de entregas.
2. **Boleta o factura electrónica** del SII para los cobros, y devoluciones desde la pasarela.
3. **Carga masiva** de asistencia, notas y apoderados, y roles con permisos configurables.
4. **Firma electrónica avanzada** (Ley 19.799) mediante un proveedor certificado, en lugar de la firma
   HMAC interna.

## Limitaciones actuales

- Los roles son fijos (administrador, secretaría, profesor, apoderado, estudiante); no se pueden crear
  roles personalizados ni permisos por sección.
- El pago en línea funciona con Webpay Plus si se configuran las credenciales del comercio; sin ellas
  queda la simulación local y no se cobra dinero real. No hay comprobantes adjuntos ni devoluciones
  automáticas, y la conciliación bancaria se hace importando un CSV (no se conecta a la API del banco).
- La asistencia se marca día por día (no hay carga masiva por rango de fechas).
- Las evaluaciones no admiten notas por curso completo en una sola pantalla: se cargan desde **Notas**,
  curso por curso y asignatura por asignatura.
- Los reportes se generan por curso (no por profesor ni por rango de fechas libre). El certificado se
  firma con HMAC-SHA256 y se verifica en `/verificar/{código}`, pero no se emite como PDF firmado
  digitalmente: se imprime o se guarda como PDF desde el navegador.
- El horario es semanal fijo (lunes a viernes), sin semanas A/B, feriados ni períodos académicos.
  Las salas son texto libre y se comparan por nombre sin distinguir mayúsculas.
- Los avisos por correo y WhatsApp requieren configurar SMTP o la WhatsApp Cloud API; sin esas
  variables se pueden marcar como enviadas a mano y se publican en el portal. No hay plantillas por
  tipo de aviso, reintentos automáticos ni historial de mensajes rechazados.
- La postulación en línea no tiene cuenta de familia: el seguimiento depende del enlace con token. No
  permite editar ni retirar la solicitud, y no incluye captcha ni límite de intentos por IP.
- Los documentos de admisión se guardan dentro de la base de datos (máximo 5 MB cada uno; PDF, JPG o
  PNG). Para muchos archivos conviene usar almacenamiento externo (S3 o similar).
- El control UTP compara los OA contra las Bases de **Lengua y Literatura 7° y 8°** cargadas; para otras
  asignaturas revisa fechas, clases, evaluaciones y OAT, pero no compara OA. La relación de los OAT y
  de las clases con las Bases es una ayuda por palabras, no un juicio definitivo. El Excel se conserva
  24 horas en el servidor y no queda un historial de análisis en la base de datos.
- El puntaje de admisión usa una escala fija de 0 a 100 con ponderación por criterio; no hay escalas
  ni baremos configurables por colegio. Una postulación ya matriculada no se puede editar: los cambios
  se hacen en la ficha del estudiante.
- Las listas desplegables de cursos, apoderados y profesores cargan hasta 200 registros.
  Con colegios más grandes conviene cambiarlas por un buscador.
- Las tablas se crean automáticamente al iniciar. Para cambios futuros del esquema conviene agregar [Alembic](https://alembic.sqlalchemy.org/).
