# Gestión Escolar

Sistema de gestión para un colegio chileno, inspirado en [Frappe Education](https://github.com/frappe/education).
La primera versión incluye **estudiantes, profesores, apoderados y cursos**, con validación de **RUT**.

- **Backend:** Python + FastAPI + SQLAlchemy (SQLite por defecto, PostgreSQL opcional)
- **Frontend:** Next.js + TypeScript
- **Entrada al sistema:** login con correo y contraseña (JWT)

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

### Terminal 2: frontend

```bash
cd frontend
npm install
npm run dev
```

Abre http://localhost:3000

### Usuario inicial

| Correo | Contraseña |
|---|---|
| `admin@colegio.cl` | `admin1234` |

Se crea solo la primera vez. **Cámbialo antes de usarlo en serio** con las variables
`ADMIN_EMAIL`, `ADMIN_PASSWORD` y `SECRET_KEY` (ver abajo).

## Qué hace cada parte

| Sección | Qué puedes hacer |
|---|---|
| Panel | Ver totales y cuántos estudiantes hay en cada curso |
| Estudiantes | Crear, editar, buscar por nombre o RUT, filtrar por curso, retirar |
| Profesores | Crear, editar, buscar, ver de qué curso son profesor jefe |
| Apoderados | Crear, editar, buscar; se asignan a cada estudiante |
| Cursos | Crear cursos por año, asignar profesor jefe, ver cupos |

Detalles que conviene saber:

- **RUT:** se valida el dígito verificador (también en el navegador) y se guarda sin puntos. No se pueden repetir.
- **Retirar un estudiante** no borra su ficha: queda inactivo y con estado "retirado".
- **Borrar un profesor, apoderado o curso** no borra a los estudiantes: solo quedan sin ese dato asignado.

## Configuración (variables de entorno)

| Variable | Para qué sirve | Valor por defecto |
|---|---|---|
| `DATABASE_URL` | Base de datos | `sqlite:///./colegio.db` |
| `SECRET_KEY` | Clave para firmar las sesiones | una de ejemplo (cámbiala) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Usuario inicial | `admin@colegio.cl` / `admin1234` |
| `CORS_ORIGINS` | Direcciones del frontend permitidas | `http://localhost:3000` |
| `NEXT_PUBLIC_API_URL` (frontend) | Dónde está el backend | `http://localhost:8000/api` |

Para PostgreSQL instala además `psycopg[binary]` y usa
`DATABASE_URL=postgresql+psycopg://usuario:clave@localhost/colegio`.

## Pruebas

```bash
cd backend
pytest
```

Revisan el RUT, el login, el flujo completo (profesor → curso → apoderado → estudiante) y los errores esperados.

## Estructura

```
backend/
  app/
    main.py          arranque de la API
    models.py        tablas de la base de datos
    schemas.py       datos que entran y salen de la API
    rut.py           validación del RUT
    security.py      login y sesiones
    routers/         un archivo por sección
  tests/             pruebas automáticas
  seed.py            datos de ejemplo
frontend/
  app/               pantallas (login, panel, estudiantes, ...)
  components/CrudPage.tsx   lista + formulario reutilizable
  lib/               conexión con la API y utilidades de RUT
```

## Qué falta respecto a Frappe Education

Frappe Education tiene más módulos. Estos serían los siguientes pasos, en el orden que más sentido tiene:

1. **Asistencia** por curso y por día
2. **Notas** (escala chilena 1.0 a 7.0) y promedios por asignatura
3. **Horarios** y asignaturas por curso y profesor
4. **Admisiones** (postulaciones de nuevos alumnos)
5. **Pagos** (mensualidades, matrícula, cuotas)
6. **Portal del estudiante/apoderado** con su propio login
7. Roles (administrador, secretaría, profesor) con distintos permisos

## Limitaciones actuales

- Hay un solo tipo de usuario (administrador).
- Las listas desplegables de cursos, apoderados y profesores cargan hasta 200 registros.
  Con colegios más grandes conviene cambiarlas por un buscador.
- Las tablas se crean automáticamente al iniciar. Para cambios futuros del esquema conviene agregar [Alembic](https://alembic.sqlalchemy.org/).
