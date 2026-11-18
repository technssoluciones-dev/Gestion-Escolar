import os
from datetime import date

os.environ["DATABASE_URL"] = "sqlite://"  # base de datos en memoria para las pruebas

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app import database
from app.main import app, ensure_admin
from app.rut import calc_dv, format_rut, normalize_rut

# Una sola conexión en memoria compartida por todas las pruebas
database.engine.dispose()
from sqlalchemy import create_engine  # noqa: E402

test_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
database.SessionLocal.configure(bind=test_engine)
import app.main as main_module  # noqa: E402

main_module.engine = test_engine


@pytest.fixture()
def client():
    database.Base.metadata.drop_all(test_engine)
    database.Base.metadata.create_all(test_engine)
    ensure_admin()
    with TestClient(app) as c:
        token = c.post(
            "/api/auth/login", json={"email": "admin@colegio.cl", "password": "admin1234"}
        ).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


def rut(n: int) -> str:
    return f"{n}-{calc_dv(str(n))}"


# ---------- RUT ----------
def test_rut_valido_y_formato():
    assert normalize_rut("12.345.678-5") == "12345678-5"
    assert normalize_rut("123456785") == "12345678-5"
    assert format_rut("12345678-5") == "12.345.678-5"


def test_rut_con_k():
    n = next(n for n in range(10_000_000, 10_000_100) if calc_dv(str(n)) == "K")
    assert normalize_rut(f"{n}-k") == f"{n}-K"


def test_rut_invalido():
    with pytest.raises(ValueError):
        normalize_rut("12.345.678-9")
    with pytest.raises(ValueError):
        normalize_rut("abc")


# ---------- Login ----------
def test_login_incorrecto(client):
    r = client.post("/api/auth/login", json={"email": "admin@colegio.cl", "password": "mala"})
    assert r.status_code == 401


def test_sin_token_no_entra():
    with TestClient(app) as c:
        assert c.get("/api/students").status_code == 401


def test_me(client):
    assert client.get("/api/auth/me").json()["email"] == "admin@colegio.cl"


# ---------- Flujo completo ----------
def test_flujo_completo(client):
    teacher = client.post("/api/teachers", json={
        "rut": rut(10_000_000), "first_name": "Ana", "last_name": "Rojas", "specialty": "Lenguaje",
    })
    assert teacher.status_code == 201, teacher.text
    teacher_id = teacher.json()["id"]

    course = client.post("/api/courses", json={
        "name": "1° Básico A", "level": "Básica", "year": 2026, "head_teacher_id": teacher_id,
    })
    assert course.status_code == 201, course.text
    course_id = course.json()["id"]
    assert course.json()["head_teacher_name"] == "Ana Rojas"

    guardian = client.post("/api/guardians", json={
        "rut": rut(8_000_000), "first_name": "Pedro", "last_name": "Soto", "email": "pedro@mail.cl",
    })
    assert guardian.status_code == 201, guardian.text

    student = client.post("/api/students", json={
        "rut": "22.000.000-" + calc_dv("22000000"), "first_name": "Luis", "last_name": "Soto",
        "birth_date": "2019-05-10", "gender": "M", "course_id": course_id,
        "guardian_id": guardian.json()["id"],
    })
    assert student.status_code == 201, student.text
    body = student.json()
    assert body["rut"] == rut(22_000_000)
    assert body["course"]["name"] == "1° Básico A"
    assert body["guardian"]["full_name"] == "Pedro Soto"

    # búsqueda por nombre y por RUT con puntos
    assert client.get("/api/students?q=luis").json()["total"] == 1
    assert client.get(f"/api/students?q=22.000.000-{calc_dv('22000000')}").json()["total"] == 1
    assert client.get(f"/api/students?course_id={course_id}").json()["total"] == 1

    dash = client.get("/api/dashboard").json()
    assert dash["students"] == 1 and dash["teachers"] == 1 and dash["courses"] == 1
    assert dash["per_course"] == [{"course": "1° Básico A", "students": 1}]

    # editar
    upd = client.put(f"/api/students/{body['id']}", json={
        "rut": body["rut"], "first_name": "Luis", "last_name": "Soto Rojas",
        "birth_date": "2019-05-10", "course_id": None,
    })
    assert upd.status_code == 200 and upd.json()["course"] is None

    # retirar (borrado lógico)
    assert client.delete(f"/api/students/{body['id']}").status_code == 204
    assert client.get(f"/api/students/{body['id']}").status_code == 404
    assert client.get("/api/students").json()["total"] == 0


def test_validaciones(client):
    base = {"first_name": "A", "last_name": "B", "birth_date": "2019-01-01"}
    assert client.post("/api/students", json={**base, "rut": "11.111.111-9"}).status_code == 422
    assert client.post("/api/students", json={**base, "rut": "1-1", "birth_date": "2999-01-01"}).status_code == 422
    ok = {**base, "rut": rut(21_000_000)}
    assert client.post("/api/students", json=ok).status_code == 201
    assert client.post("/api/students", json=ok).status_code == 409  # RUT repetido
    assert client.post("/api/students", json={**ok, "rut": rut(21_000_001), "course_id": 999}).status_code == 422


def test_curso_duplicado(client):
    data = {"name": "2° Básico A", "level": "Básica", "year": 2026}
    assert client.post("/api/courses", json=data).status_code == 201
    assert client.post("/api/courses", json=data).status_code == 409


def test_borrar_profesor_deja_curso_sin_jefe(client):
    t = client.post("/api/teachers", json={"rut": rut(10_000_010), "first_name": "X", "last_name": "Y"}).json()
    c = client.post("/api/courses", json={
        "name": "3° A", "level": "Básica", "year": 2026, "head_teacher_id": t["id"],
    }).json()
    assert client.delete(f"/api/teachers/{t['id']}").status_code == 204
    assert client.get(f"/api/courses/{c['id']}").json()["head_teacher_id"] is None


# ---------- Asignaturas, asistencia y notas ----------
def crear_curso(client, name="4° Básico A", year=2026):
    r = client.post("/api/courses", json={"name": name, "level": "Básica", "year": year})
    assert r.status_code == 201, r.text
    return r.json()


def crear_estudiante(client, n, curso_id, nombre="Alumno"):
    r = client.post("/api/students", json={
        "rut": rut(23_000_000 + n), "first_name": f"{nombre}{n}", "last_name": "Prueba",
        "birth_date": "2015-03-01", "course_id": curso_id,
    })
    assert r.status_code == 201, r.text
    return r.json()


def crear_asignatura(client, name="Matemática", code="MAT"):
    r = client.post("/api/subjects", json={"name": name, "code": code})
    assert r.status_code == 201, r.text
    return r.json()


def test_asignaturas_crud_y_duplicado(client):
    s = crear_asignatura(client)
    assert s["code"] == "MAT"
    assert client.post("/api/subjects", json={"name": "Matemática"}).status_code == 409
    assert client.post("/api/subjects", json={"name": "matemática"}).status_code == 409
    assert client.get("/api/subjects?q=mate").json()["total"] == 1
    upd = client.put(f"/api/subjects/{s['id']}", json={"name": "Matemática y Física", "code": None})
    assert upd.status_code == 200 and upd.json()["code"] is None
    assert client.delete(f"/api/subjects/{s['id']}").status_code == 204
    assert client.get("/api/subjects").json()["total"] == 0


def test_asistencia_por_curso_y_dia(client):
    curso = crear_curso(client)
    otro = crear_curso(client, name="4° Básico B")
    a = crear_estudiante(client, 1, curso["id"])
    b = crear_estudiante(client, 2, curso["id"])
    ajeno = crear_estudiante(client, 3, otro["id"])
    dia = "2025-05-05"

    r = client.get(f"/api/attendance/day?course_id={curso['id']}&date={dia}")
    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) == 2
    assert r.json()["summary"]["sin_marcar"] == 2

    r = client.put("/api/attendance/day", json={
        "course_id": curso["id"], "date": dia,
        "items": [
            {"student_id": a["id"], "status": "presente"},
            {"student_id": b["id"], "status": "ausente", "note": "Sin aviso"},
        ],
    })
    assert r.status_code == 200, r.text
    assert r.json()["summary"] == {
        "presente": 1, "ausente": 1, "atrasado": 0, "justificado": 0, "sin_marcar": 0,
    }
    assert next(i for i in r.json()["items"] if i["student_id"] == b["id"])["note"] == "Sin aviso"

    # Guardar de nuevo corrige y permite borrar una marca enviando status nulo
    r = client.put("/api/attendance/day", json={
        "course_id": curso["id"], "date": dia,
        "items": [
            {"student_id": a["id"], "status": "atrasado"},
            {"student_id": b["id"], "status": None},
        ],
    })
    assert r.json()["summary"]["atrasado"] == 1
    assert r.json()["summary"]["sin_marcar"] == 1
    guardado = client.get(f"/api/attendance/day?course_id={curso['id']}&date={dia}").json()
    assert {i["student_id"]: i["status"] for i in guardado["items"]} == {a["id"]: "atrasado", b["id"]: None}

    r = client.get(f"/api/attendance/summary?course_id={curso['id']}&from={dia}&to={dia}")
    assert r.status_code == 200, r.text
    resumen = r.json()
    assert resumen["days"] == 1
    fila_a = next(i for i in resumen["items"] if i["student_id"] == a["id"])
    fila_b = next(i for i in resumen["items"] if i["student_id"] == b["id"])
    assert fila_a["atrasado"] == 1 and fila_a["rate"] == 100.0
    assert fila_b["total"] == 0 and fila_b["rate"] is None
    assert resumen["summary"]["total"] == 1
    assert resumen["summary"]["rate"] == 100.0

    # No se puede marcar a un estudiante de otro curso
    r = client.put("/api/attendance/day", json={
        "course_id": curso["id"], "date": dia,
        "items": [{"student_id": ajeno["id"], "status": "presente"}],
    })
    assert r.status_code == 422

    # No se puede registrar asistencia futura
    r = client.put("/api/attendance/day", json={
        "course_id": curso["id"], "date": "2999-01-01",
        "items": [{"student_id": a["id"], "status": "presente"}],
    })
    assert r.status_code == 422

    assert client.get("/api/attendance/day?course_id=999&date=" + dia).status_code == 404

    # Un curso con asistencia registrada no se puede eliminar
    assert client.delete(f"/api/courses/{curso['id']}").status_code == 409


def test_notas_promedios_y_escala(client):
    curso = crear_curso(client)
    matematica = crear_asignatura(client)
    lenguaje = crear_asignatura(client, name="Lenguaje", code="LEN")
    a = crear_estudiante(client, 1, curso["id"])
    b = crear_estudiante(client, 2, curso["id"])

    def nota(student, subject, score, title="Prueba", weight=1, dia="2025-05-05"):
        return client.post("/api/grades", json={
            "student_id": student["id"], "subject_id": subject["id"], "title": title,
            "score": score, "weight": weight, "date": dia,
        })

    assert nota(a, matematica, 6.0, "Prueba 1").status_code == 201
    assert nota(a, matematica, 5.0, "Prueba 2", weight=2).status_code == 201
    assert nota(b, matematica, 3.9, "Prueba 1").status_code == 201
    assert nota(a, lenguaje, 7.0).status_code == 201
    assert nota(a, matematica, 0.9).status_code == 422
    assert nota(a, matematica, 7.1).status_code == 422

    r = client.get(f"/api/grades/report?course_id={curso['id']}&subject_id={matematica['id']}")
    assert r.status_code == 200, r.text
    reporte = r.json()
    fila_a = next(i for i in reporte["items"] if i["student_id"] == a["id"])
    fila_b = next(i for i in reporte["items"] if i["student_id"] == b["id"])
    assert fila_a["count"] == 2 and fila_a["average"] == 5.3  # (6*1 + 5*2) / 3
    assert fila_b["average"] == 3.9
    assert reporte["summary"]["average"] == 4.6
    assert reporte["summary"]["approved"] == 1 and reporte["summary"]["failed"] == 1
    assert reporte["summary"]["grade_count"] == 3

    matriz = client.get(f"/api/grades/matrix?course_id={curso['id']}").json()
    assert [s["name"] for s in matriz["subjects"]] == ["Lenguaje", "Matemática"]
    fila_a = next(i for i in matriz["items"] if i["student_id"] == a["id"])
    assert fila_a["overall"] == 6.2  # promedio de sus promedios: (5.3 + 7.0) / 2
    promedios = {p["subject_id"]: p["average"] for p in matriz["subject_averages"]}
    assert promedios[matematica["id"]] == 4.6
    assert promedios[lenguaje["id"]] == 7.0

    informe = client.get(f"/api/grades/student/{a['id']}").json()
    assert [i["subject"]["name"] for i in informe["items"]] == ["Lenguaje", "Matemática"]
    assert informe["overall"] == 6.2

    # Editar y eliminar
    grade_id = fila_a["averages"][1]["subject_id"]  # solo para comprobar que existen datos
    assert grade_id == matematica["id"]
    lista = client.get(f"/api/grades?course_id={curso['id']}&subject_id={lenguaje['id']}").json()
    assert lista["total"] == 1
    assert client.delete(f"/api/grades/{lista['items'][0]['id']}").status_code == 204
    assert client.get(f"/api/grades?course_id={curso['id']}&subject_id={lenguaje['id']}").json()["total"] == 0


def test_notas_por_lote_y_validaciones(client):
    curso = crear_curso(client)
    otro = crear_curso(client, name="5° Básico A")
    materia = crear_asignatura(client)
    a = crear_estudiante(client, 1, curso["id"])
    b = crear_estudiante(client, 2, curso["id"])
    ajeno = crear_estudiante(client, 3, otro["id"])

    r = client.post("/api/grades/bulk", json={
        "course_id": curso["id"], "subject_id": materia["id"], "title": "Ensayo",
        "date": "2025-05-06", "weight": 2,
        "items": [{"student_id": a["id"], "score": 5.5}, {"student_id": b["id"], "score": 4.0}],
    })
    assert r.status_code == 201, r.text
    assert r.json()["created"] == 2

    reporte = client.get(f"/api/grades/report?course_id={curso['id']}&subject_id={materia['id']}").json()
    assert {i["average"] for i in reporte["items"]} == {5.5, 4.0}

    r = client.post("/api/grades/bulk", json={
        "course_id": curso["id"], "subject_id": materia["id"], "title": "Ensayo",
        "date": "2025-05-06",
        "items": [{"student_id": ajeno["id"], "score": 5.0}],
    })
    assert r.status_code == 422

    # Un estudiante sin curso no puede recibir notas
    sin_curso = crear_estudiante(client, 4, None)
    r = client.post("/api/grades", json={
        "student_id": sin_curso["id"], "subject_id": materia["id"], "title": "X",
        "score": 5.0, "date": "2025-05-06",
    })
    assert r.status_code == 422

    # Una asignatura o un curso con notas no se pueden borrar
    assert client.delete(f"/api/subjects/{materia['id']}").status_code == 409
    assert client.delete(f"/api/courses/{curso['id']}").status_code == 409
    assert client.delete(f"/api/courses/{otro['id']}").status_code == 204


def test_evaluaciones_formales(client):
    curso = crear_curso(client)
    otro = crear_curso(client, name="6° Básico A")
    materia = crear_asignatura(client)
    asignatura_curso = crear_asignatura_curso(client, curso["id"], materia["id"])
    asignatura_otro = crear_asignatura_curso(client, otro["id"], materia["id"])
    a = crear_estudiante(client, 21, curso["id"])
    b = crear_estudiante(client, 22, curso["id"])
    ajeno = crear_estudiante(client, 23, otro["id"])

    r = client.post("/api/evaluations", json={
        "course_subject_id": asignatura_curso["id"], "title": "Prueba 1",
        "kind": "prueba", "date": "2025-06-01", "weight": 2,
    })
    assert r.status_code == 201, r.text
    evaluacion = r.json()
    assert evaluacion["course_name"] == curso["name"]
    assert evaluacion["subject_name"] == materia["name"]
    assert evaluacion["grade_count"] == 0

    # El nombre no se repite dentro de la misma asignatura del curso
    r = client.post("/api/evaluations", json={
        "course_subject_id": asignatura_curso["id"], "title": "prueba 1",
        "date": "2025-06-02",
    })
    assert r.status_code == 409

    # La evaluación debe pertenecer al curso y asignatura de las notas
    r = client.post("/api/grades/bulk", json={
        "course_id": curso["id"], "subject_id": materia["id"],
        "evaluation_id": evaluacion["id"], "title": "Ignorado",
        "date": "2025-06-01",
        "items": [{"student_id": ajeno["id"], "score": 5.0}],
    })
    assert r.status_code == 422

    r = client.post("/api/evaluations", json={
        "course_subject_id": asignatura_otro["id"], "title": "Prueba 1",
        "date": "2025-06-01", "weight": 1,
    })
    evaluacion_otro = r.json()
    r = client.post("/api/grades/bulk", json={
        "course_id": curso["id"], "subject_id": materia["id"],
        "evaluation_id": evaluacion_otro["id"], "title": "X", "date": "2025-06-01",
        "items": [{"student_id": a["id"], "score": 5.0}],
    })
    assert r.status_code == 422

    # Las notas toman nombre, fecha y ponderación desde la evaluación
    r = client.post("/api/grades/bulk", json={
        "course_id": curso["id"], "subject_id": materia["id"],
        "evaluation_id": evaluacion["id"], "title": "Otro nombre",
        "date": "2030-01-01", "weight": 1,
        "items": [{"student_id": a["id"], "score": 6.0}, {"student_id": b["id"], "score": 4.0}],
    })
    assert r.status_code == 201, r.text

    notas = client.get(f"/api/grades?course_id={curso['id']}&subject_id={materia['id']}").json()
    assert notas["total"] == 2
    assert {n["evaluation_id"] for n in notas["items"]} == {evaluacion["id"]}
    assert {n["title"] for n in notas["items"]} == {"Prueba 1"}
    assert {n["weight"] for n in notas["items"]} == {2}
    assert {n["date"] for n in notas["items"]} == {"2025-06-01"}

    # No se pueden duplicar las notas de una misma evaluación
    r = client.post("/api/grades/bulk", json={
        "course_id": curso["id"], "subject_id": materia["id"],
        "evaluation_id": evaluacion["id"], "title": "Prueba 1", "date": "2025-06-01",
        "items": [{"student_id": a["id"], "score": 5.0}],
    })
    assert r.status_code == 409

    lista = client.get(
        f"/api/evaluations?course_id={curso['id']}&subject_id={materia['id']}"
    ).json()
    assert lista["total"] == 1
    assert lista["items"][0]["grade_count"] == 2

    # Editar la evaluación actualiza sus notas
    r = client.put(f"/api/evaluations/{evaluacion['id']}", json={
        "course_subject_id": asignatura_curso["id"], "title": "Prueba 1 bis",
        "kind": "control", "date": "2025-06-02", "weight": 3,
    })
    assert r.status_code == 200, r.text
    notas = client.get(f"/api/grades?course_id={curso['id']}&subject_id={materia['id']}").json()
    assert {n["title"] for n in notas["items"]} == {"Prueba 1 bis"}
    assert {n["weight"] for n in notas["items"]} == {3}
    assert {n["date"] for n in notas["items"]} == {"2025-06-02"}

    # No se puede mover de asignatura ni borrar con notas registradas
    r = client.put(f"/api/evaluations/{evaluacion['id']}", json={
        "course_subject_id": asignatura_otro["id"], "title": "Prueba 1 bis",
        "kind": "control", "date": "2025-06-02", "weight": 3,
    })
    assert r.status_code == 409
    assert client.delete(f"/api/evaluations/{evaluacion['id']}").status_code == 409

    for nota in notas["items"]:
        assert client.delete(f"/api/grades/{nota['id']}").status_code == 204
    assert client.delete(f"/api/evaluations/{evaluacion['id']}").status_code == 204


def crear_profesor(client, n, nombre="Ema", apellido="Paz"):
    r = client.post("/api/teachers", json={
        "rut": rut(10_000_000 + n), "first_name": nombre, "last_name": apellido,
    })
    assert r.status_code == 201, r.text
    return r.json()


def crear_asignatura_curso(client, curso_id, asignatura_id, teacher_id=None):
    r = client.post("/api/course-subjects", json={
        "course_id": curso_id, "subject_id": asignatura_id, "teacher_id": teacher_id,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_asignaturas_por_curso_y_profesor(client):
    curso = crear_curso(client)
    materia = crear_asignatura(client)
    teacher = crear_profesor(client, 200)

    r = client.post("/api/course-subjects", json={
        "course_id": curso["id"], "subject_id": materia["id"], "teacher_id": teacher["id"],
    })
    assert r.status_code == 201, r.text
    asignacion = r.json()
    assert asignacion["subject"]["name"] == "Matemática"
    assert asignacion["teacher"]["full_name"] == "Ema Paz"
    assert asignacion["schedule_count"] == 0

    # La misma asignatura no se puede repetir en el curso
    repetida = client.post("/api/course-subjects", json={
        "course_id": curso["id"], "subject_id": materia["id"], "teacher_id": teacher["id"],
    })
    assert repetida.status_code == 409
    assert client.post("/api/course-subjects", json={
        "course_id": curso["id"], "subject_id": 999,
    }).status_code == 404
    assert client.post("/api/course-subjects", json={
        "course_id": curso["id"], "subject_id": materia["id"], "teacher_id": 999,
    }).status_code == 422

    lista = client.get(f"/api/course-subjects?course_id={curso['id']}").json()
    assert lista["total"] == 1
    assert client.get(f"/api/course-subjects?teacher_id={teacher['id']}").json()["total"] == 1

    # Una asignatura asignada a un curso no se puede borrar
    assert client.delete(f"/api/subjects/{materia['id']}").status_code == 409

    # Quitar el profesor de la asignatura
    upd = client.put(f"/api/course-subjects/{asignacion['id']}", json={
        "course_id": curso["id"], "subject_id": materia["id"], "teacher_id": None,
    })
    assert upd.status_code == 200 and upd.json()["teacher"] is None

    # Al borrar un profesor, sus asignaturas quedan sin profesor
    client.put(f"/api/course-subjects/{asignacion['id']}", json={
        "course_id": curso["id"], "subject_id": materia["id"], "teacher_id": teacher["id"],
    })
    assert client.delete(f"/api/teachers/{teacher['id']}").status_code == 204
    sin_profesor = client.get(f"/api/course-subjects?course_id={curso['id']}").json()["items"][0]
    assert sin_profesor["teacher"] is None


def test_horario_bloques_y_choques(client):
    curso = crear_curso(client)
    otro = crear_curso(client, name="6° Básico A")
    materia = crear_asignatura(client)
    teacher = crear_profesor(client, 201)
    otro_teacher = crear_profesor(client, 202, "Juan", "Soto")

    cs = crear_asignatura_curso(client, curso["id"], materia["id"], teacher["id"])
    cs_otro = crear_asignatura_curso(client, otro["id"], materia["id"], teacher["id"])

    def bloque(course_subject_id, dia=1, inicio="08:00", fin="09:30", sala="Sala 1"):
        return client.post("/api/schedules", json={
            "course_subject_id": course_subject_id, "weekday": dia,
            "start_time": inicio, "end_time": fin, "room": sala,
        })

    r = bloque(cs["id"])
    assert r.status_code == 201, r.text
    horario = r.json()
    assert horario["course_name"] == "4° Básico A"
    assert horario["subject_name"] == "Matemática"
    assert horario["teacher_name"] == "Ema Paz"
    assert horario["start_time"] == "08:00:00" and horario["end_time"] == "09:30:00"
    assert horario["room"] == "Sala 1"

    # Choque dentro del mismo curso
    assert bloque(cs["id"], inicio="09:00", fin="10:00", sala="Sala 2").status_code == 409
    # Choque del profesor en otro curso
    assert bloque(cs_otro["id"], inicio="08:30", fin="09:00", sala="Sala 2").status_code == 409
    # Choque de sala con otro profesor
    cs_sala = crear_asignatura_curso(client, otro["id"], crear_asignatura(client, "Lenguaje", "LEN")["id"], otro_teacher["id"])
    assert bloque(cs_sala["id"], inicio="08:15", fin="09:00", sala="Sala 1").status_code == 409

    # Validaciones de formato y rango
    assert bloque(cs["id"], inicio="09:30", fin="09:30", sala="Sala 2").status_code == 422
    assert bloque(cs["id"], dia=6, sala="Sala 2").status_code == 422
    assert bloque(999).status_code == 404

    # Consultas por curso y por profesor
    por_curso = client.get(f"/api/schedules?course_id={curso['id']}").json()
    assert len(por_curso) == 1
    por_profesor = client.get(f"/api/schedules?teacher_id={teacher['id']}").json()
    assert len(por_profesor) == 1 and por_profesor[0]["course_id"] == curso["id"]

    # Editar el bloque a otro horario sin choques
    r = client.put(f"/api/schedules/{horario['id']}", json={
        "course_subject_id": cs["id"], "weekday": 2,
        "start_time": "10:00", "end_time": "11:30", "room": "Sala 3",
    })
    assert r.status_code == 200, r.text
    assert r.json()["weekday"] == 2 and r.json()["start_time"] == "10:00:00"

    # Al eliminar la asignatura del curso se eliminan sus bloques
    assert client.delete(f"/api/course-subjects/{cs['id']}").status_code == 204
    assert client.get(f"/api/schedules?course_id={curso['id']}").json() == []
    assert client.delete(f"/api/course-subjects/{cs_otro['id']}").status_code == 204
    assert client.delete(f"/api/course-subjects/{cs_sala['id']}").status_code == 204


def crear_postulacion(client, n, curso_id=None, status_="postulada", guardian_rut=None):
    r = client.post("/api/admissions", json={
        "applicant_rut": rut(25_000_000 + n),
        "first_name": f"Postulante{n}",
        "last_name": "Rojas",
        "birth_date": "2019-04-12",
        "gender": "F",
        "email": f"postulante{n}@mail.cl",
        "guardian_first_name": "Ana",
        "guardian_last_name": "Rojas",
        "guardian_rut": guardian_rut or rut(9_000_000 + n),
        "guardian_email": f"apoderado{n}@mail.cl",
        "course_id": curso_id,
        "year": 2026,
        "status": status_,
        "application_date": "2025-08-01",
        "notes": "Entrevista",
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_admisiones_crud_y_filtros(client):
    curso = crear_curso(client)
    postulacion = crear_postulacion(client, 0, curso["id"])
    assert postulacion["full_name"] == "Postulante0 Rojas"
    assert postulacion["course"]["name"] == "4° Básico A"
    assert postulacion["student_id"] is None

    # No se puede repetir el RUT del postulante
    assert client.post("/api/admissions", json={
        "applicant_rut": postulacion["applicant_rut"], "first_name": "Otro",
        "last_name": "Rojas", "birth_date": "2019-01-01", "year": 2026,
    }).status_code == 409

    assert client.get("/api/admissions?q=postulante0").json()["total"] == 1
    assert client.get("/api/admissions?status=postulada").json()["total"] == 1
    assert client.get("/api/admissions?status=inventado").status_code == 422
    assert client.get(f"/api/admissions?year=2026&course_id={curso['id']}").json()["total"] == 1
    assert client.get("/api/admissions?year=2025").json()["total"] == 0

    r = client.put(f"/api/admissions/{postulacion['id']}", json={
        "applicant_rut": postulacion["applicant_rut"],
        "first_name": postulacion["first_name"],
        "last_name": postulacion["last_name"],
        "birth_date": "2019-04-12",
        "guardian_first_name": "Ana", "guardian_last_name": "Rojas",
        "guardian_rut": postulacion["guardian_rut"],
        "course_id": None, "year": 2026, "status": "en_revision",
        "application_date": "2025-08-01", "notes": "Cambió de curso",
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "en_revision" and r.json()["course"] is None

    # No se puede crear ni editar directamente como matriculada
    assert client.post("/api/admissions", json={
        "applicant_rut": rut(25_000_200), "first_name": "X", "last_name": "Y",
        "birth_date": "2019-01-01", "year": 2026, "status": "matriculada",
    }).status_code == 409

    assert client.delete(f"/api/admissions/{postulacion['id']}").status_code == 204
    assert client.get(f"/api/admissions/{postulacion['id']}").status_code == 404


def test_matricular_postulacion_crea_estudiante(client):
    curso = crear_curso(client)
    guardian = client.post("/api/guardians", json={
        "rut": rut(9_000_050), "first_name": "Ana", "last_name": "Rojas",
        "email": "ana@mail.cl", "phone": "+56 9 1111 2222",
    }).json()
    postulacion = crear_postulacion(client, 1, curso["id"], guardian_rut=guardian["rut"])
    assert postulacion["status"] == "postulada"

    r = client.post(f"/api/admissions/{postulacion['id']}/enroll", json={})
    assert r.status_code == 200, r.text
    matriculada = r.json()
    assert matriculada["status"] == "matriculada"
    assert matriculada["student_id"] is not None
    assert matriculada["student_name"] == "Postulante1 Rojas"

    estudiante = client.get(f"/api/students/{matriculada['student_id']}").json()
    assert estudiante["rut"] == postulacion["applicant_rut"]
    assert estudiante["course"]["id"] == curso["id"]
    assert estudiante["guardian"]["id"] == guardian["id"]  # reutiliza el apoderado
    assert estudiante["status"] == "activo"

    # Ya matriculada no se puede volver a matricular, editar ni eliminar
    assert client.post(f"/api/admissions/{postulacion['id']}/enroll", json={}).status_code == 409
    assert client.put(f"/api/admissions/{postulacion['id']}", json={
        "applicant_rut": postulacion["applicant_rut"], "first_name": "Postulante1",
        "last_name": "Rojas", "birth_date": "2019-04-12", "year": 2026,
        "status": "aceptada", "application_date": "2025-08-01",
    }).status_code == 409
    assert client.delete(f"/api/admissions/{postulacion['id']}").status_code == 409

    # Y su RUT ya no se puede volver a postular
    assert client.post("/api/admissions", json={
        "applicant_rut": postulacion["applicant_rut"], "first_name": "Otra",
        "last_name": "Persona", "birth_date": "2019-01-01", "year": 2026,
    }).status_code == 409


def test_matricula_con_cupos_y_curso_requerido(client):
    curso = client.post("/api/courses", json={
        "name": "7° Básico A", "level": "Básica", "year": 2026, "capacity": 1,
    }).json()
    crear_estudiante(client, 1, curso["id"])
    postulacion = crear_postulacion(client, 2, curso["id"])

    r = client.post(f"/api/admissions/{postulacion['id']}/enroll", json={})
    assert r.status_code == 409
    assert "cupos" in r.json()["detail"]

    # Si la postulación no trae curso, hay que indicarlo al matricular
    otra = crear_postulacion(client, 3)
    assert client.post(f"/api/admissions/{otra['id']}/enroll", json={}).status_code == 422
    assert client.post(f"/api/admissions/{otra['id']}/enroll", json={"course_id": 999}).status_code == 422


def test_panel_cuenta_postulaciones_pendientes(client):
    crear_postulacion(client, 4, status_="postulada")
    crear_postulacion(client, 5, status_="en_revision")
    crear_postulacion(client, 6, status_="aceptada")
    panel = client.get("/api/dashboard").json()
    assert panel["pending_admissions"] == 2


def test_panel_incluye_asignaturas_y_asistencia_de_hoy(client):
    curso = crear_curso(client)
    crear_asignatura(client)
    a = crear_estudiante(client, 1, curso["id"])
    crear_estudiante(client, 2, curso["id"])
    hoy = date.today().isoformat()

    assert client.put("/api/attendance/day", json={
        "course_id": curso["id"], "date": hoy,
        "items": [{"student_id": a["id"], "status": "presente"}],
    }).status_code == 200

    panel = client.get("/api/dashboard").json()
    assert panel["subjects"] == 1
    assert panel["attendance_today"]["marked"] == 1
    assert panel["attendance_today"]["presente"] == 1
    assert panel["attendance_today"]["unmarked"] == 1
    assert panel["attendance_today"]["rate"] == 100.0


# ---------- Roles y usuarios ----------
def login_headers(client, email, password="clave12345"):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_roles_y_permisos(client):
    # Validaciones al crear usuarios
    assert client.post("/api/users", json={
        "email": "apoderado@colegio.cl", "full_name": "Sin vínculo",
        "password": "clave12345", "role": "apoderado",
    }).status_code == 422
    assert client.post("/api/users", json={
        "email": "estudiante@colegio.cl", "full_name": "Sin vínculo",
        "password": "clave12345", "role": "estudiante",
    }).status_code == 422

    r = client.post("/api/users", json={
        "email": "secretaria@colegio.cl", "full_name": "Sofía Secretaria",
        "password": "clave12345", "role": "secretaria",
    })
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "secretaria"
    assert client.post("/api/users", json={
        "email": "secretaria@colegio.cl", "full_name": "Otra",
        "password": "clave12345", "role": "secretaria",
    }).status_code == 409

    r = client.post("/api/users", json={
        "email": "profesor@colegio.cl", "full_name": "Pablo Profesor",
        "password": "clave12345", "role": "profesor",
    })
    assert r.status_code == 201, r.text

    # El admin no puede eliminarse ni quitarse el rol
    me = client.get("/api/auth/me").json()
    assert client.delete(f"/api/users/{me['id']}").status_code == 409
    assert client.put(f"/api/users/{me['id']}", json={"role": "profesor"}).status_code == 409

    # El login informa el rol
    r = client.post("/api/auth/login", json={
        "email": "secretaria@colegio.cl", "password": "clave12345",
    })
    assert r.json()["role"] == "secretaria" and r.json()["full_name"] == "Sofía Secretaria"

    sec = login_headers(client, "secretaria@colegio.cl")
    assert client.get("/api/students", headers=sec).status_code == 200
    assert client.get("/api/fees", headers=sec).status_code == 200
    assert client.get("/api/admissions", headers=sec).status_code == 200
    assert client.get("/api/users", headers=sec).status_code == 403
    assert client.post("/api/users", headers=sec, json={
        "email": "x@colegio.cl", "full_name": "X", "password": "clave12345",
    }).status_code == 403

    prof = login_headers(client, "profesor@colegio.cl")
    assert client.get("/api/students", headers=prof).status_code == 200
    assert client.get("/api/grades", headers=prof).status_code == 200
    assert client.get("/api/attendance/day?course_id=1&date=2025-05-05", headers=prof).status_code == 404
    assert client.post("/api/students", headers=prof, json={
        "rut": rut(23_100_000), "first_name": "No", "last_name": "Permitido",
        "birth_date": "2015-03-01",
    }).status_code == 403
    assert client.post("/api/courses", headers=prof, json={
        "name": "8° A", "level": "Básica", "year": 2026,
    }).status_code == 403
    assert client.get("/api/fees", headers=prof).status_code == 403
    assert client.get("/api/admissions", headers=prof).status_code == 403
    assert client.get("/api/users", headers=prof).status_code == 403

    # Al desactivar al profesor ya no puede entrar
    users = client.get("/api/users?q=profesor").json()["items"]
    profesor_id = users[0]["id"]
    assert client.put(f"/api/users/{profesor_id}", json={"is_active": False}).status_code == 200
    assert client.post("/api/auth/login", json={
        "email": "profesor@colegio.cl", "password": "clave12345",
    }).status_code == 401


# ---------- Pagos ----------
def test_cobros_pagos_y_resumen(client):
    curso = crear_curso(client)
    estudiante = crear_estudiante(client, 1, curso["id"])

    assert client.post("/api/fees", json={
        "student_id": 999, "concept": "mensualidad", "period": "2026-03",
        "amount": 65000, "due_date": "2026-03-05",
    }).status_code == 422

    r = client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "mensualidad",
        "description": "Mensualidad marzo", "period": "2020-03",
        "amount": 65000, "due_date": "2020-03-05",
    })
    assert r.status_code == 201, r.text
    cobro = r.json()
    assert cobro["status"] == "vencida"
    assert cobro["paid_amount"] == 0 and cobro["balance"] == 65000
    assert cobro["student_name"] == "Alumno1 Prueba"
    assert cobro["course_name"] == curso["name"]
    fee_id = cobro["id"]

    # Período y monto inválidos
    assert client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "mensualidad", "period": "2020-13",
        "amount": 65000, "due_date": "2020-03-05",
    }).status_code == 422
    assert client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "mensualidad", "period": "2020-04",
        "amount": 0, "due_date": "2020-04-05",
    }).status_code == 422

    # Editar mientras no haya pagos
    r = client.put(f"/api/fees/{fee_id}", json={
        "student_id": estudiante["id"], "concept": "mensualidad",
        "description": "Mensualidad marzo (ajustada)", "period": "2020-03",
        "amount": 70000, "due_date": "2020-03-05",
    })
    assert r.status_code == 200 and r.json()["amount"] == 70000

    # Pago parcial
    r = client.post(f"/api/fees/{fee_id}/payments", json={
        "amount": 20000, "method": "efectivo", "note": "Abono",
    })
    assert r.status_code == 201, r.text
    payment_id = r.json()["id"]
    detalle = client.get(f"/api/fees/{fee_id}").json()
    assert detalle["paid_amount"] == 20000 and detalle["balance"] == 50000
    assert detalle["status"] == "vencida"
    resumen = client.get("/api/fees/summary").json()
    assert resumen["charged"] == 70000 and resumen["collected"] == 20000
    assert resumen["overdue"] == 50000 and resumen["overdue_count"] == 1

    # No se puede pagar de más, con monto cero ni con fecha futura
    assert client.post(f"/api/fees/{fee_id}/payments", json={"amount": 60000}).status_code == 422
    assert client.post(f"/api/fees/{fee_id}/payments", json={"amount": 0}).status_code == 422
    assert client.post(f"/api/fees/{fee_id}/payments", json={
        "amount": 1000, "paid_on": "2999-01-01",
    }).status_code == 422

    # Pago final
    assert client.post(f"/api/fees/{fee_id}/payments", json={"amount": 50000}).status_code == 201
    detalle = client.get(f"/api/fees/{fee_id}").json()
    assert detalle["status"] == "pagada" and detalle["balance"] == 0
    assert client.post(f"/api/fees/{fee_id}/payments", json={"amount": 1000}).status_code == 409
    resumen = client.get("/api/fees/summary").json()
    assert resumen["collected"] == 70000 and resumen["paid_count"] == 1
    assert resumen["pending"] == 0 and resumen["overdue"] == 0

    # Con pagos no se puede editar ni borrar el cobro
    assert client.put(f"/api/fees/{fee_id}", json={
        "student_id": estudiante["id"], "concept": "mensualidad", "period": "2020-03",
        "amount": 80000, "due_date": "2020-03-05",
    }).status_code == 409
    assert client.delete(f"/api/fees/{fee_id}").status_code == 409

    # Se puede eliminar un pago (queda con saldo) y luego otro
    otro_pago = next(
        p["id"] for p in detalle["payments"] if p["id"] != payment_id
    )
    assert client.delete(f"/api/fees/{fee_id}/payments/{payment_id}").status_code == 204
    assert client.get(f"/api/fees/{fee_id}").json()["status"] == "vencida"
    assert client.delete(f"/api/fees/{fee_id}/payments/{otro_pago}").status_code == 204
    assert client.delete(f"/api/fees/{fee_id}").status_code == 204
    assert client.get(f"/api/fees/{fee_id}").status_code == 404

    # Filtros y búsqueda
    client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "matricula", "period": "2099-03",
        "amount": 120000, "due_date": "2099-03-05",
    })
    assert client.get("/api/fees?concept=matricula").json()["total"] == 1
    assert client.get("/api/fees?status=pendiente").json()["total"] == 1
    assert client.get("/api/fees?status=inventado").status_code == 422
    assert client.get("/api/fees?period=2099-03").json()["total"] == 1
    assert client.get(f"/api/fees?course_id={curso['id']}").json()["total"] == 1
    assert client.get("/api/fees?q=alumno1").json()["total"] == 1


def test_generar_cobros_por_curso(client):
    curso = crear_curso(client)
    crear_estudiante(client, 1, curso["id"])
    crear_estudiante(client, 2, curso["id"])

    payload = {
        "course_id": curso["id"], "concept": "mensualidad", "period": "2099-04",
        "amount": 65000, "due_date": "2099-04-05",
    }
    r = client.post("/api/fees/generate", json=payload)
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 2, "skipped": 0}

    r = client.post("/api/fees/generate", json=payload)
    assert r.json() == {"created": 0, "skipped": 2}

    lista = client.get(f"/api/fees?course_id={curso['id']}&period=2099-04").json()
    assert lista["total"] == 2
    assert all(item["status"] == "pendiente" for item in lista["items"])

    assert client.post("/api/fees/generate", json={
        "course_id": 999, "concept": "mensualidad", "period": "2099-04",
        "amount": 65000, "due_date": "2099-04-05",
    }).status_code == 422


# ---------- Portal ----------
def test_portal_apoderado_y_estudiante(client):
    curso = crear_curso(client)
    guardian = client.post("/api/guardians", json={
        "rut": rut(8_500_000), "first_name": "Pedro", "last_name": "Soto",
        "email": "pedro@mail.cl",
    }).json()
    r = client.post("/api/students", json={
        "rut": rut(24_000_000), "first_name": "Luis", "last_name": "Soto",
        "birth_date": "2015-03-01", "course_id": curso["id"],
        "guardian_id": guardian["id"],
    })
    assert r.status_code == 201, r.text
    estudiante = r.json()
    ajeno = crear_estudiante(client, 9, curso["id"])

    materia = crear_asignatura(client)
    hoy = date.today().isoformat()
    assert client.post("/api/grades", json={
        "student_id": estudiante["id"], "subject_id": materia["id"],
        "title": "Prueba 1", "score": 6.0, "weight": 1, "date": hoy,
    }).status_code == 201
    assert client.put("/api/attendance/day", json={
        "course_id": curso["id"], "date": hoy,
        "items": [
            {"student_id": estudiante["id"], "status": "presente"},
            {"student_id": ajeno["id"], "status": "ausente"},
        ],
    }).status_code == 200
    cobro = client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "mensualidad", "period": "2020-03",
        "amount": 65000, "due_date": "2020-03-05",
    }).json()
    assert cobro["status"] == "vencida"

    r = client.post("/api/users", json={
        "email": "apoderado@colegio.cl", "full_name": "Pedro Soto",
        "password": "apoderado1234", "role": "apoderado",
        "guardian_id": guardian["id"],
    })
    assert r.status_code == 201, r.text
    r = client.post("/api/users", json={
        "email": "estudiante@colegio.cl", "full_name": "Luis Soto",
        "password": "estudiante1234", "role": "estudiante",
        "student_id": estudiante["id"],
    })
    assert r.status_code == 201, r.text

    app_headers = login_headers(client, "apoderado@colegio.cl", "apoderado1234")
    me = client.get("/api/portal/me", headers=app_headers).json()
    assert me["role"] == "apoderado" and me["guardian"]["id"] == guardian["id"]
    hijos = client.get("/api/portal/children", headers=app_headers).json()
    assert [h["id"] for h in hijos] == [estudiante["id"]]
    assert hijos[0]["course"]["name"] == curso["name"]

    overview = client.get(
        f"/api/portal/students/{estudiante['id']}", headers=app_headers
    ).json()
    assert overview["student"]["id"] == estudiante["id"]
    assert overview["attendance"]["presente"] == 1
    assert overview["attendance"]["rate"] == 100.0
    assert overview["subjects"][0]["subject"]["name"] == "Matemática"
    assert overview["subjects"][0]["average"] == 6.0
    assert overview["overall"] == 6.0
    assert overview["fees"][0]["balance"] == 65000
    assert overview["pending_amount"] == 65000
    assert overview["overdue_amount"] == 65000

    # El apoderado no puede ver a un estudiante ajeno ni usar el panel
    assert client.get(
        f"/api/portal/students/{ajeno['id']}", headers=app_headers
    ).status_code == 403
    assert client.get("/api/portal/students/999", headers=app_headers).status_code == 404
    assert client.get("/api/students", headers=app_headers).status_code == 403
    assert client.get("/api/fees", headers=app_headers).status_code == 403

    est_headers = login_headers(client, "estudiante@colegio.cl", "estudiante1234")
    me = client.get("/api/portal/me", headers=est_headers).json()
    assert me["role"] == "estudiante" and me["student"]["id"] == estudiante["id"]
    propios = client.get("/api/portal/children", headers=est_headers).json()
    assert [h["id"] for h in propios] == [estudiante["id"]]
    assert client.get(
        f"/api/portal/students/{estudiante['id']}", headers=est_headers
    ).status_code == 200
    assert client.get(
        f"/api/portal/students/{ajeno['id']}", headers=est_headers
    ).status_code == 403


# ---------- Reportes ----------
def test_reportes_excel_y_certificado(client):
    from io import BytesIO

    from openpyxl import load_workbook

    teacher = client.post("/api/teachers", json={
        "rut": rut(10_500_000), "first_name": "Carla", "last_name": "Docente",
    }).json()
    curso = crear_curso(client, "5° Básico B")
    asignatura = crear_asignatura(client)
    r = client.post("/api/course-subjects", json={
        "course_id": curso["id"], "subject_id": asignatura["id"], "teacher_id": teacher["id"],
    })
    assert r.status_code == 201, r.text
    asignacion = r.json()
    lenguaje = crear_asignatura(client, "Lenguaje", "LEN")
    r = client.post("/api/course-subjects", json={
        "course_id": curso["id"], "subject_id": lenguaje["id"], "teacher_id": teacher["id"],
    })
    assert r.status_code == 201, r.text

    estudiante = crear_estudiante(client, 7, curso["id"], "Reportes")
    evaluacion = client.post("/api/evaluations", json={
        "course_subject_id": asignacion["id"], "title": "Prueba 1",
        "kind": "prueba", "date": "2026-11-17", "weight": 2,
    })
    assert evaluacion.status_code == 201, evaluacion.text
    evaluacion = evaluacion.json()
    assert client.post("/api/grades", json={
        "student_id": estudiante["id"], "subject_id": asignatura["id"],
        "title": "Prueba 1", "score": 6.0, "weight": 2, "date": "2026-11-17",
        "evaluation_id": evaluacion["id"],
    }).status_code == 201
    assert client.put("/api/attendance/day", json={
        "course_id": curso["id"], "date": "2026-11-17",
        "items": [{"student_id": estudiante["id"], "status": "presente"}],
    }).status_code == 200
    assert client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "mensualidad",
        "description": "Mensualidad 2026", "period": "2026-11",
        "amount": 65000, "due_date": "2026-11-05",
    }).status_code == 201

    # Planilla de notas: hoja resumen + una hoja por asignatura
    r = client.get(f"/api/reports/courses/{curso['id']}/grades.xlsx")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    wb = load_workbook(BytesIO(r.content))
    assert wb.sheetnames == ["Resumen", "Lenguaje", "Matemática"]
    resumen = [[c.value for c in row] for row in wb["Resumen"].iter_rows()]
    cabecera = next(row for row in resumen if "Estudiante" in row)
    assert "Promedio general" in cabecera
    fila = next(row for row in resumen if row[1] == estudiante["full_name"])
    assert fila[cabecera.index("Promedio general")] == 6.0

    hoja = [[c.value for c in row] for row in wb["Matemática"].iter_rows()]
    cabecera = next(row for row in hoja if "Estudiante" in row)
    assert "Prueba 1" in cabecera and "Promedio ponderado" in cabecera
    fila = next(row for row in hoja if row[1] == estudiante["full_name"])
    assert fila[cabecera.index("Prueba 1")] == 6.0
    assert fila[cabecera.index("Promedio ponderado")] == 6.0

    r = client.get(
        f"/api/reports/courses/{curso['id']}/grades.xlsx?subject_id={asignatura['id']}"
    )
    assert r.status_code == 200
    assert load_workbook(BytesIO(r.content)).sheetnames == ["Matemática"]
    assert client.get(
        f"/api/reports/courses/{curso['id']}/grades.xlsx?subject_id=999"
    ).status_code == 422

    # Libro de asistencia mensual
    r = client.get(f"/api/reports/courses/{curso['id']}/attendance.xlsx?month=2026-11")
    assert r.status_code == 200, r.text
    wb = load_workbook(BytesIO(r.content))
    ws = wb.active
    assert ws.title == "Asistencia 2026-11"
    valores = [c.value for row in ws.iter_rows() for c in row]
    assert "Libro de asistencia · 5° Básico B" in valores
    assert "P" in valores and 100.0 in valores
    assert client.get(
        f"/api/reports/courses/{curso['id']}/attendance.xlsx?month=2026-13"
    ).status_code == 422

    # Resumen del curso (incluye asistencia y deudas)
    r = client.get(f"/api/reports/courses/{curso['id']}/summary.xlsx")
    assert r.status_code == 200, r.text
    hoja = [[c.value for c in row] for row in load_workbook(BytesIO(r.content)).active.iter_rows()]
    cabecera = next(row for row in hoja if "Estudiante" in row)
    assert {"Matemática", "% Asistencia", "Deuda total", "Deuda vencida"} <= set(cabecera)
    fila = next(row for row in hoja if row[1] == estudiante["full_name"])
    assert fila[cabecera.index("Matemática")] == 6.0
    assert fila[cabecera.index("% Asistencia")] == 100.0
    assert fila[cabecera.index("Deuda total")] == 65000
    assert fila[cabecera.index("Deuda vencida")] == 65000

    # Certificado de alumno regular
    r = client.get(f"/api/reports/students/{estudiante['id']}/certificate")
    assert r.status_code == 200, r.text
    cert = r.json()
    assert cert["student"]["full_name"] == estudiante["full_name"]
    assert cert["student"]["rut"] == estudiante["rut"]
    assert cert["course"]["name"] == "5° Básico B"
    assert cert["course"]["year"] == 2026
    assert cert["attendance"]["rate"] == 100.0
    assert cert["grades"]["average"] == 6.0
    assert cert["certificate_number"] == f"CERT-2026-{estudiante['id']:04d}"
    assert client.get("/api/reports/students/999/certificate").status_code == 404

    # El profesor descarga planillas, pero no el resumen con deudas
    assert client.post("/api/users", json={
        "email": "docente@colegio.cl", "full_name": "Docente",
        "password": "clave12345", "role": "profesor",
    }).status_code == 201
    prof = login_headers(client, "docente@colegio.cl")
    assert client.get(
        f"/api/reports/courses/{curso['id']}/grades.xlsx", headers=prof
    ).status_code == 200
    assert client.get(
        f"/api/reports/courses/{curso['id']}/attendance.xlsx?month=2026-11", headers=prof
    ).status_code == 200
    assert client.get(
        f"/api/reports/courses/{curso['id']}/summary.xlsx", headers=prof
    ).status_code == 403

    # Un estudiante retirado no obtiene certificado de alumno regular
    assert client.delete(f"/api/students/{estudiante['id']}").status_code == 204
    assert client.get(
        f"/api/reports/students/{estudiante['id']}/certificate"
    ).status_code == 422


# ---------- Notificaciones ----------
def test_notificaciones(client):
    guardian = client.post("/api/guardians", json={
        "rut": rut(8_500_000), "first_name": "Marta", "last_name": "Apoderada",
        "email": "marta@mail.cl",
    }).json()
    curso = crear_curso(client, "6° Básico A")
    asignatura = crear_asignatura(client)
    asignacion = client.post("/api/course-subjects", json={
        "course_id": curso["id"], "subject_id": asignatura["id"],
    }).json()
    estudiante = client.post("/api/students", json={
        "rut": rut(23_200_000), "first_name": "Nico", "last_name": "Apoderado",
        "birth_date": "2014-04-01", "course_id": curso["id"],
        "guardian_id": guardian["id"],
    }).json()

    # Cinco inasistencias en el mes, una nota 2.0 y un cobro vencido
    for day in range(2, 7):
        assert client.put("/api/attendance/day", json={
            "course_id": curso["id"], "date": f"2026-11-{day:02d}",
            "items": [{"student_id": estudiante["id"], "status": "ausente"}],
        }).status_code == 200
    evaluacion = client.post("/api/evaluations", json={
        "course_subject_id": asignacion["id"], "title": "Prueba 1",
        "kind": "prueba", "date": "2026-11-10", "weight": 1,
    }).json()
    assert client.post("/api/grades", json={
        "student_id": estudiante["id"], "subject_id": asignatura["id"],
        "title": "Prueba 1", "score": 2.0, "weight": 1, "date": "2026-11-10",
        "evaluation_id": evaluacion["id"],
    }).status_code == 201
    assert client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "mensualidad",
        "period": "2020-03", "amount": 30000, "due_date": "2020-03-05",
    }).status_code == 201

    # Genera un aviso por cada tipo y no duplica al repetir
    r = client.post("/api/notifications/generate", json={"period": "2026-11"})
    assert r.status_code == 200, r.text
    assert r.json() == {
        "created": 3, "skipped": 0,
        "by_type": {"inasistencia": 1, "notas": 1, "deuda": 1},
    }
    r = client.post("/api/notifications/generate", json={"period": "2026-11"})
    assert r.json()["created"] == 0 and r.json()["skipped"] == 3

    assert client.post(
        "/api/notifications/generate", json={"period": "2026-99"}
    ).status_code == 422

    resumen = client.get("/api/notifications/summary").json()
    assert resumen["pending"] == 3 and resumen["sent"] == 0
    assert resumen["by_type"] == {"inasistencia": 1, "notas": 1, "deuda": 1}

    items = client.get("/api/notifications").json()
    assert items["total"] == 3
    assert items["items"][0]["student_name"] == "Nico Apoderado"
    assert items["items"][0]["guardian_name"] == "Marta Apoderada"
    assert items["items"][0]["course_name"] == "6° Básico A"
    deuda = client.get("/api/notifications?type=deuda").json()["items"]
    assert len(deuda) == 1 and "$30.000" in deuda[0]["message"]
    assert client.get("/api/notifications?type=otro").status_code == 422
    assert client.get("/api/notifications?q=nico").json()["total"] == 3
    assert client.get(
        f"/api/notifications?course_id={curso['id']}"
    ).json()["total"] == 3

    # Aviso manual
    r = client.post("/api/notifications", json={
        "student_id": estudiante["id"], "title": "Reunión de apoderados",
        "message": "La reunión será el viernes a las 18:00.",
    })
    assert r.status_code == 201, r.text
    manual = r.json()
    assert manual["type"] == "general" and manual["status"] == "pendiente"
    assert manual["guardian_email"] == "marta@mail.cl"
    assert client.post("/api/notifications", json={
        "student_id": 999, "title": "X", "message": "Y",
    }).status_code == 422

    # Publicar un aviso lo deja disponible en el portal de la familia
    r = client.put(f"/api/notifications/{deuda[0]['id']}", json={"status": "enviada"})
    assert r.status_code == 200, r.text
    assert r.json()["sent_at"] is not None
    assert client.put(
        f"/api/notifications/{deuda[0]['id']}", json={"status": "otro"}
    ).status_code == 422

    assert client.post("/api/users", json={
        "email": "marta@colegio.cl", "full_name": "Marta Apoderada",
        "password": "clave12345", "role": "apoderado",
        "guardian_id": guardian["id"],
    }).status_code == 201
    apoderado = login_headers(client, "marta@colegio.cl")
    visibles = client.get(
        f"/api/portal/notifications?student_id={estudiante['id']}", headers=apoderado
    ).json()
    assert [n["id"] for n in visibles] == [deuda[0]["id"]]
    assert len(client.get("/api/portal/notifications", headers=apoderado).json()) == 1
    with TestClient(app) as anonimo:
        assert anonimo.get("/api/portal/notifications").status_code == 401

    # Volver a pendiente lo oculta del portal
    assert client.put(
        f"/api/notifications/{deuda[0]['id']}", json={"status": "pendiente"}
    ).json()["sent_at"] is None
    assert client.get(
        "/api/portal/notifications", headers=apoderado
    ).json() == []

    # El profesor no administra avisos
    assert client.post("/api/users", json={
        "email": "docente@colegio.cl", "full_name": "Docente",
        "password": "clave12345", "role": "profesor",
    }).status_code == 201
    prof = login_headers(client, "docente@colegio.cl")
    assert client.get("/api/notifications", headers=prof).status_code == 403
    assert client.post(
        "/api/notifications/generate", headers=prof, json={"period": "2026-11"}
    ).status_code == 403

    assert client.delete(f"/api/notifications/{manual['id']}").status_code == 204
    assert client.delete(f"/api/notifications/{manual['id']}").status_code == 404




def test_expediente_admision(client):
    curso = crear_curso(client, "5° Básico A")
    postulacion = crear_postulacion(client, 1, curso["id"])
    base = f"/api/admissions/{postulacion['id']}"

    expediente = client.get(f"{base}/dossier").json()
    assert expediente == {
        "documents": [], "interviews": [], "scores": [], "weighted_score": None,
    }

    # Documentos: subir, listar y descargar
    r = client.post(f"{base}/documents", data={"name": "Certificado de nacimiento"}, files={
        "file": ("certificado.pdf", b"%PDF-1.4 certificado", "application/pdf"),
    })
    assert r.status_code == 201, r.text
    documento = r.json()
    assert documento["name"] == "Certificado de nacimiento"
    assert documento["filename"] == "certificado.pdf" and documento["size"] > 0
    descarga = client.get(f"/api/admission-documents/{documento['id']}/download")
    assert descarga.status_code == 200
    assert descarga.content == b"%PDF-1.4 certificado"
    assert descarga.headers["content-type"] == "application/pdf"
    assert "attachment" in descarga.headers["content-disposition"]
    assert client.post(f"{base}/documents", data={"name": "Malicioso"}, files={
        "file": ("virus.exe", b"MZ", "application/octet-stream"),
    }).status_code == 422
    assert client.post(f"{base}/documents", data={"name": "Vacío"}, files={
        "file": ("vacio.pdf", b"", "application/pdf"),
    }).status_code == 422
    assert client.post(f"{base}/documents", data={"name": "Grande"}, files={
        "file": ("grande.pdf", b"x" * (5 * 1024 * 1024 + 1), "application/pdf"),
    }).status_code == 422
    assert len(client.get(f"{base}/dossier").json()["documents"]) == 1

    # Entrevistas: agendar, editar estado y eliminar
    r = client.post(f"{base}/interviews", json={
        "scheduled_at": "2026-11-20T10:30:00", "interviewer": "Jefa de UTP",
        "mode": "online", "notes": "Entrevista con la familia",
    })
    assert r.status_code == 201, r.text
    entrevista = r.json()
    assert entrevista["status"] == "pendiente" and entrevista["mode"] == "online"
    assert client.post(f"{base}/interviews", json={
        "scheduled_at": "2026-11-21T09:00:00", "interviewer": "X", "mode": "video",
    }).status_code == 422
    r = client.put(f"/api/admission-interviews/{entrevista['id']}", json={
        "scheduled_at": "2026-11-20T10:30:00", "interviewer": "Dirección",
        "mode": "presencial", "status": "realizada", "notes": "Asistió la familia",
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "realizada" and r.json()["interviewer"] == "Dirección"
    assert len(client.get(f"{base}/interviews").json()) == 1

    # Puntajes: crear, duplicado, rango y promedio ponderado
    r = client.post(f"{base}/scores", json={
        "criterion": "Prueba de admisión", "score": 85, "weight": 2,
    })
    assert r.status_code == 201, r.text
    prueba = r.json()
    r = client.post(f"{base}/scores", json={
        "criterion": "Entrevista", "score": 70, "weight": 1,
    })
    assert r.status_code == 201, r.text
    entrevista_puntaje = r.json()
    assert client.post(f"{base}/scores", json={
        "criterion": "Prueba de admisión", "score": 60,
    }).status_code == 409
    assert client.post(f"{base}/scores", json={
        "criterion": "Otro", "score": 101,
    }).status_code == 422
    expediente = client.get(f"{base}/dossier").json()
    assert expediente["weighted_score"] == 80.0
    r = client.put(f"/api/admission-scores/{prueba['id']}", json={
        "criterion": "Prueba de admisión", "score": 90, "weight": 2,
    })
    assert r.status_code == 200, r.text
    assert client.get(f"{base}/dossier").json()["weighted_score"] == 83.3
    assert client.delete(
        f"/api/admission-scores/{entrevista_puntaje['id']}"
    ).status_code == 204
    assert client.get(f"{base}/dossier").json()["weighted_score"] == 90.0

    # El profesor no administra el expediente
    staff = client.post("/api/users", json={
        "email": "utp@colegio.cl", "full_name": "UTP", "password": "clave12345",
        "role": "profesor",
    })
    assert staff.status_code == 201, staff.text
    prof = login_headers(client, "utp@colegio.cl")
    assert client.get(f"{base}/dossier", headers=prof).status_code == 403
    assert client.get(
        f"/api/admission-documents/{documento['id']}/download", headers=prof
    ).status_code == 403

    # Al eliminar la postulación se elimina su expediente
    assert client.delete(f"/api/admission-documents/{documento['id']}").status_code == 204
    assert client.get(
        f"/api/admission-documents/{documento['id']}/download"
    ).status_code == 404
    r = client.post(f"{base}/documents", data={"name": "Copia"}, files={
        "file": ("copia.png", b"\x89PNGdata", "image/png"),
    })
    assert r.status_code == 201
    assert client.delete(base).status_code == 204
    assert client.get(f"/api/admission-documents/{r.json()['id']}/download").status_code == 404


# ---------- Pagos en línea ----------
def test_pagos_en_linea(client):
    curso = crear_curso(client)
    guardian = client.post("/api/guardians", json={
        "rut": rut(9_100_000), "first_name": "Marta", "last_name": "Rojas",
        "email": "marta@mail.cl",
    }).json()
    r = client.post("/api/students", json={
        "rut": rut(25_100_000), "first_name": "Ana", "last_name": "Rojas",
        "birth_date": "2015-03-01", "course_id": curso["id"],
        "guardian_id": guardian["id"],
    })
    assert r.status_code == 201, r.text
    estudiante = r.json()
    ajeno = crear_estudiante(client, 41, curso["id"])

    fee = client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "mensualidad",
        "period": "2020-03", "amount": 65000, "due_date": "2020-03-05",
    }).json()
    fee_ajeno = client.post("/api/fees", json={
        "student_id": ajeno["id"], "concept": "mensualidad",
        "period": "2020-03", "amount": 50000, "due_date": "2020-03-05",
    }).json()

    client.post("/api/users", json={
        "email": "apoderado@colegio.cl", "full_name": "Marta Rojas",
        "password": "apoderado1234", "role": "apoderado",
        "guardian_id": guardian["id"],
    })
    client.post("/api/users", json={
        "email": "estudiante@colegio.cl", "full_name": "Ana Rojas",
        "password": "estudiante1234", "role": "estudiante",
        "student_id": estudiante["id"],
    })
    app_headers = login_headers(client, "apoderado@colegio.cl", "apoderado1234")
    est_headers = login_headers(client, "estudiante@colegio.cl", "estudiante1234")

    with TestClient(app) as anonimo:
        r = anonimo.post("/api/payments/checkout", json={"fee_id": fee["id"]})
        assert r.status_code == 401
    assert client.post("/api/payments/checkout", json={"fee_id": fee["id"]}).status_code == 403

    r = client.post(
        "/api/payments/checkout", json={"fee_id": fee["id"]}, headers=app_headers
    )
    assert r.status_code == 200, r.text
    intent = r.json()["intent"]
    assert intent["status"] == "pendiente" and intent["amount"] == 65000
    assert intent["provider"] == "sandbox"
    assert intent["student_name"] == "Ana Rojas" and intent["fee_status"] == "vencida"
    assert r.json()["checkout_url"].endswith(intent["token"])
    token = intent["token"]

    # Se reutiliza el intento pendiente
    r = client.post(
        "/api/payments/checkout", json={"fee_id": fee["id"]}, headers=app_headers
    )
    assert r.json()["intent"]["token"] == token

    assert client.get(f"/api/payments/intents/{token}", headers=est_headers).status_code == 200
    r = client.post(
        "/api/payments/checkout", json={"fee_id": fee_ajeno["id"]}, headers=est_headers
    )
    assert r.status_code == 403
    assert client.get("/api/payments/intents/inexistente", headers=app_headers).status_code == 404

    r = client.post(f"/api/payments/intents/{token}/confirm", headers=app_headers)
    assert r.status_code == 200, r.text
    pagada = r.json()
    assert pagada["status"] == "pagada" and pagada["paid_at"]
    assert pagada["fee_balance"] == 0 and pagada["fee_status"] == "pagada"
    payment_id = pagada["payment_id"]

    # Confirmar de nuevo es idempotente
    r = client.post(f"/api/payments/intents/{token}/confirm", headers=app_headers)
    assert r.json()["payment_id"] == payment_id
    detalle = client.get(f"/api/fees/{fee['id']}").json()
    assert detalle["status"] == "pagada" and len(detalle["payments"]) == 1
    assert detalle["payments"][0]["method"] == "tarjeta"
    assert detalle["payments"][0]["reference"].startswith("ONLINE-")
    assert client.post(
        "/api/payments/checkout", json={"fee_id": fee["id"]}, headers=app_headers
    ).status_code == 409
    assert client.post(
        f"/api/payments/intents/{token}/cancel", headers=app_headers
    ).status_code == 409

    # Cancelar y reiniciar el pago
    fee2 = client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "cuota",
        "period": "2020-04", "amount": 30000, "due_date": "2020-04-05",
    }).json()
    token2 = client.post(
        "/api/payments/checkout", json={"fee_id": fee2["id"]}, headers=est_headers
    ).json()["intent"]["token"]
    r = client.post(f"/api/payments/intents/{token2}/cancel", headers=est_headers)
    assert r.json()["status"] == "cancelada"
    assert client.post(
        f"/api/payments/intents/{token2}/confirm", headers=est_headers
    ).status_code == 409
    nuevotoken = client.post(
        "/api/payments/checkout", json={"fee_id": fee2["id"]}, headers=est_headers
    ).json()["intent"]["token"]
    assert nuevotoken != token2

    # Conciliación
    lista = client.get("/api/payments/intents").json()
    assert lista["total"] == 3
    assert client.get("/api/payments/intents?status=pagada").json()["total"] == 1
    assert client.get("/api/payments/intents?status=inventado").status_code == 422
    assert client.get("/api/payments/intents?q=ana").json()["total"] == 3
    assert client.get("/api/payments/intents?q=alumno41").json()["total"] == 0
    assert client.get("/api/payments/intents", headers=app_headers).status_code == 403


# ---------- Avisos por correo ----------
def test_envio_de_aviso_por_correo(client, monkeypatch):
    import app.routers.notifications as notifications_module

    curso = crear_curso(client)
    guardian = client.post("/api/guardians", json={
        "rut": rut(9_200_000), "first_name": "Carla", "last_name": "Mena",
        "email": "carla@mail.cl",
    }).json()
    estudiante = client.post("/api/students", json={
        "rut": rut(25_200_000), "first_name": "Tomás", "last_name": "Mena",
        "birth_date": "2015-03-01", "course_id": curso["id"],
        "guardian_id": guardian["id"],
    }).json()

    aviso = client.post("/api/notifications", json={
        "student_id": estudiante["id"], "type": "general",
        "title": "Reunión de apoderados",
        "message": "La reunión será el viernes a las 18:00.",
    }).json()
    assert aviso["channel"] == "manual" and aviso["status"] == "pendiente"

    enviados = []
    monkeypatch.setattr(
        notifications_module,
        "send_email",
        lambda to, subject, body: enviados.append((to, subject, body)),
    )
    r = client.post(f"/api/notifications/{aviso['id']}/email")
    assert r.status_code == 200, r.text
    enviado = r.json()
    assert enviado["status"] == "enviada" and enviado["channel"] == "email"
    assert enviado["sent_at"] and enviado["guardian_email"] == "carla@mail.cl"
    assert enviados == [(
        "carla@mail.cl",
        "Reunión de apoderados",
        enviados[0][2],
    )]
    assert "Tomás" not in enviados[0][2] and "18:00" in enviados[0][2]
    assert client.post(f"/api/notifications/{aviso['id']}/email").status_code == 409

    # Sin configuración SMTP
    otro = client.post("/api/notifications", json={
        "student_id": estudiante["id"], "type": "general",
        "title": "Citación", "message": "Ven a secretaría.",
    }).json()

    def sin_configuracion(*args, **kwargs):
        raise notifications_module.EmailNotConfigured("SMTP no configurado")

    monkeypatch.setattr(notifications_module, "send_email", sin_configuracion)
    assert client.post(f"/api/notifications/{otro['id']}/email").status_code == 503

    # Apoderado sin correo
    guardian2 = client.post("/api/guardians", json={
        "rut": rut(9_300_000), "first_name": "Raúl", "last_name": "Pino",
    }).json()
    estudiante2 = client.post("/api/students", json={
        "rut": rut(25_300_000), "first_name": "Ema", "last_name": "Pino",
        "birth_date": "2015-03-01", "course_id": curso["id"],
        "guardian_id": guardian2["id"],
    }).json()
    aviso3 = client.post("/api/notifications", json={
        "student_id": estudiante2["id"], "type": "general",
        "title": "Aviso", "message": "Sin correo.",
    }).json()
    assert client.post(f"/api/notifications/{aviso3['id']}/email").status_code == 422

    with TestClient(app) as anonimo:
        assert anonimo.post(f"/api/notifications/{aviso['id']}/email").status_code == 401


# ---------- Postulación en línea ----------
def test_postulacion_en_linea(client):
    curso = crear_curso(client, name="1° Medio A", year=date.today().year)

    cursos = client.get("/api/public/courses")
    assert cursos.status_code == 200
    assert cursos.json()[0]["id"] == curso["id"]
    assert cursos.json()[0]["vacancies"] == curso["capacity"]

    base = {
        "applicant_rut": rut(26_100_000),
        "first_name": "Emilia", "last_name": "Vergara",
        "birth_date": "2012-05-04",
        "guardian_first_name": "Paula", "guardian_last_name": "Vergara",
        "guardian_email": "paula@mail.cl", "guardian_phone": "+56911111111",
        "course_id": curso["id"],
    }
    r = client.post("/api/public/admissions", json=base)
    assert r.status_code == 201, r.text
    creada = r.json()
    assert creada["status"] == "postulada"
    assert creada["applicant_name"] == "Emilia Vergara"
    assert creada["course_name"] == curso["name"]
    assert creada["year"] == curso["year"]
    assert creada["documents"] == []
    assert len(creada["token"]) >= 24
    assert creada["tracking_url"] == f"/postular/{creada['token']}"

    # La postulación aparece en el panel de admisiones
    lista = client.get("/api/admissions?q=emilia").json()
    assert lista["total"] == 1
    assert "access_token" not in lista["items"][0]

    # No se puede postular dos veces con el mismo RUT ni forzar estado/año
    assert client.post("/api/public/admissions", json=base).status_code == 409
    assert client.post("/api/public/admissions", json={
        **base, "applicant_rut": rut(26_200_000), "status": "matriculada",
    }).status_code == 422
    sin_apoderado = {**base, "applicant_rut": rut(26_200_000)}
    sin_apoderado.pop("guardian_first_name")
    assert client.post("/api/public/admissions", json=sin_apoderado).status_code == 422
    sin_contacto = {
        **base, "applicant_rut": rut(26_200_000),
        "guardian_email": None, "guardian_phone": None,
    }
    assert client.post("/api/public/admissions", json=sin_contacto).status_code == 422
    assert client.post("/api/public/admissions", json={
        **base, "applicant_rut": rut(26_200_000), "course_id": 999,
    }).status_code == 422

    # Seguimiento y carga de documentos con el token
    token = creada["token"]
    seguimiento = client.get(f"/api/public/admissions/{token}")
    assert seguimiento.status_code == 200
    assert seguimiento.json()["applicant_name"] == "Emilia Vergara"
    r = client.post(
        f"/api/public/admissions/{token}/documents",
        data={"name": "Certificado de nacimiento"},
        files={"file": ("nacimiento.pdf", b"%PDF-1.4 demo", "application/pdf")},
    )
    assert r.status_code == 201, r.text
    assert client.get(f"/api/public/admissions/{token}").json()["documents"][0][
        "name"
    ] == "Certificado de nacimiento"
    assert client.post(
        f"/api/public/admissions/{token}/documents",
        data={"name": "Ejecutable"},
        files={"file": ("x.exe", b"MZ", "application/x-msdownload")},
    ).status_code == 422
    assert client.get("/api/public/admissions/no-existe").status_code == 404
    assert client.post(
        "/api/public/admissions/no-existe/documents",
        data={"name": "Carta"},
        files={"file": ("carta.pdf", b"%PDF", "application/pdf")},
    ).status_code == 404

    # Administración puede matricular la postulación en línea
    admission_id = lista["items"][0]["id"]
    assert client.post(
        f"/api/admissions/{admission_id}/enroll", json={}
    ).status_code == 200
    assert client.get(f"/api/public/admissions/{token}").json()["status"] == "matriculada"


# ---------- Avisos por WhatsApp ----------
def test_envio_de_aviso_por_whatsapp(client, monkeypatch):
    import app.routers.notifications as notifications_module

    curso = crear_curso(client)
    guardian = client.post("/api/guardians", json={
        "rut": rut(9_400_000), "first_name": "Nora", "last_name": "Silva",
        "phone": "+56 9 8765 4321",
    }).json()
    estudiante = client.post("/api/students", json={
        "rut": rut(25_400_000), "first_name": "Julián", "last_name": "Silva",
        "birth_date": "2015-03-01", "course_id": curso["id"],
        "guardian_id": guardian["id"],
    }).json()
    aviso = client.post("/api/notifications", json={
        "student_id": estudiante["id"], "type": "general",
        "title": "Reunión de apoderados", "message": "Viernes a las 18:00.",
    }).json()

    enviados = []
    monkeypatch.setattr(
        notifications_module,
        "send_whatsapp",
        lambda phone, text: enviados.append((phone, text)),
    )
    r = client.post(f"/api/notifications/{aviso['id']}/whatsapp")
    assert r.status_code == 200, r.text
    enviado = r.json()
    assert enviado["status"] == "enviada" and enviado["channel"] == "whatsapp"
    assert enviado["guardian_phone"] == "+56 9 8765 4321" and enviado["sent_at"]
    assert enviados[0][0] == "56987654321"
    assert "Reunión de apoderados" in enviados[0][1]
    assert "18:00" in enviados[0][1]
    assert client.post(f"/api/notifications/{aviso['id']}/whatsapp").status_code == 409

    # Apoderado sin teléfono
    guardian2 = client.post("/api/guardians", json={
        "rut": rut(9_500_000), "first_name": "Iván", "last_name": "Lara",
    }).json()
    estudiante2 = client.post("/api/students", json={
        "rut": rut(25_500_000), "first_name": "Noa", "last_name": "Lara",
        "birth_date": "2015-03-01", "course_id": curso["id"],
        "guardian_id": guardian2["id"],
    }).json()
    aviso2 = client.post("/api/notifications", json={
        "student_id": estudiante2["id"], "type": "general",
        "title": "Aviso", "message": "Sin teléfono.",
    }).json()
    assert client.post(f"/api/notifications/{aviso2['id']}/whatsapp").status_code == 422

    # Teléfono sin código de país
    guardian3 = client.post("/api/guardians", json={
        "rut": rut(9_600_000), "first_name": "Paz", "last_name": "Mora",
        "phone": "123",
    }).json()
    estudiante3 = client.post("/api/students", json={
        "rut": rut(25_600_000), "first_name": "Lía", "last_name": "Mora",
        "birth_date": "2015-03-01", "course_id": curso["id"],
        "guardian_id": guardian3["id"],
    }).json()
    aviso3 = client.post("/api/notifications", json={
        "student_id": estudiante3["id"], "type": "general",
        "title": "Aviso", "message": "Teléfono inválido.",
    }).json()
    assert client.post(f"/api/notifications/{aviso3['id']}/whatsapp").status_code == 422

    # Sin configuración del proveedor
    otro = client.post("/api/notifications", json={
        "student_id": estudiante["id"], "type": "general",
        "title": "Citación", "message": "Ven a secretaría.",
    }).json()

    def sin_configuracion(*args, **kwargs):
        raise notifications_module.WhatsAppNotConfigured("WhatsApp no configurado")

    monkeypatch.setattr(notifications_module, "send_whatsapp", sin_configuracion)
    assert client.post(f"/api/notifications/{otro['id']}/whatsapp").status_code == 503


def test_checkout_con_webpay_y_retorno(client, monkeypatch):
    import app.routers.payments as payments_module
    from app.config import settings

    curso = crear_curso(client)
    guardian = client.post("/api/guardians", json={
        "rut": rut(9_400_000), "first_name": "Inés", "last_name": "Soto",
        "email": "ines@mail.cl",
    }).json()
    estudiante = client.post("/api/students", json={
        "rut": rut(25_400_000), "first_name": "Lucas", "last_name": "Soto",
        "birth_date": "2015-03-01", "course_id": curso["id"],
        "guardian_id": guardian["id"],
    }).json()
    fee = client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "mensualidad",
        "period": "2020-03", "amount": 70000, "due_date": "2020-03-05",
    }).json()
    client.post("/api/users", json={
        "email": "ines@colegio.cl", "full_name": "Inés Soto",
        "password": "apoderado1234", "role": "apoderado",
        "guardian_id": guardian["id"],
    })
    headers = login_headers(client, "ines@colegio.cl", "apoderado1234")

    monkeypatch.setattr(settings, "webpay_commerce_code", "597000000001")
    monkeypatch.setattr(settings, "webpay_api_key", "clave-secreta")
    pedidos = []

    def crear(buy_order, session_id, amount, return_url):
        pedidos.append((buy_order, session_id, amount, return_url))
        return {"token": f"WS-{len(pedidos)}", "url": "https://webpay.test/pagar"}

    def confirmar(token):
        return {
            "status": "AUTHORIZED", "response_code": 0, "amount": 70000,
            "buy_order": "INT00000001",
        }

    monkeypatch.setattr(payments_module.webpay, "create_transaction", crear)
    monkeypatch.setattr(payments_module.webpay, "commit_transaction", confirmar)

    r = client.post("/api/payments/checkout", json={"fee_id": fee["id"]}, headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["provider"] == "webpay"
    assert data["webpay_url"] == "https://webpay.test/pagar"
    assert data["webpay_token"] == "WS-1"
    intent = data["intent"]
    assert intent["provider"] == "webpay" and intent["status"] == "pendiente"
    assert pedidos[0][2] == 70000
    assert pedidos[0][3].endswith("/payments/webpay/return")

    # El sandbox no puede confirmar una transacción de Webpay
    r = client.post(f"/api/payments/intents/{intent['token']}/confirm", headers=headers)
    assert r.status_code == 409

    r = client.post(
        "/api/payments/webpay/return", data={"token_ws": "WS-1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "webpay=ok" in r.headers["location"]
    pagado = client.get(
        f"/api/payments/intents/{intent['token']}", headers=headers
    ).json()
    assert pagado["status"] == "pagada" and pagado["payment_id"]

    cobro = client.get(f"/api/fees/{fee['id']}").json()
    assert cobro["balance"] == 0
    assert cobro["payments"][0]["reference"] == "WEBPAY-INT00000001"
    assert cobro["payments"][0]["method"] == "tarjeta"

    # Segundo retorno: idempotente
    r = client.post(
        "/api/payments/webpay/return", data={"token_ws": "WS-1"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and "webpay=ok" in r.headers["location"]
    assert len(client.get(f"/api/fees/{fee['id']}").json()["payments"]) == 1

    # Cancelación desde Webpay (TBK_TOKEN)
    fee2 = client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "mensualidad",
        "period": "2020-04", "amount": 70000, "due_date": "2020-04-05",
    }).json()
    r = client.post("/api/payments/checkout", json={"fee_id": fee2["id"]}, headers=headers)
    intent2 = r.json()["intent"]
    r = client.post(
        "/api/payments/webpay/return", data={"TBK_TOKEN": "WS-2"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and "webpay=cancelado" in r.headers["location"]
    assert client.get(
        f"/api/payments/intents/{intent2['token']}", headers=headers
    ).json()["status"] == "cancelada"


def test_conciliacion_bancaria(client):
    curso = crear_curso(client)
    guardian = client.post("/api/guardians", json={
        "rut": rut(9_500_000), "first_name": "Elsa", "last_name": "Vera",
    }).json()
    estudiante = client.post("/api/students", json={
        "rut": rut(25_500_000), "first_name": "Diego", "last_name": "Vera",
        "birth_date": "2015-03-01", "course_id": curso["id"],
        "guardian_id": guardian["id"],
    }).json()
    fee = client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "mensualidad",
        "period": "2020-03", "amount": 40000, "due_date": "2020-03-05",
    }).json()

    cartola = (
        "fecha,descripcion,monto\n"
        f"2020-03-10,TRANSFERENCIA {estudiante['rut']} PAGO MENSUALIDAD,40000\n"
    )
    r = client.post(
        "/api/payments/bank/import",
        files={"file": ("cartola.csv", cartola.encode(), "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"imported": 1, "matched": 1, "pending": 0, "skipped": 0}

    cobro = client.get(f"/api/fees/{fee['id']}").json()
    assert cobro["balance"] == 0
    assert cobro["payments"][0]["method"] == "transferencia"
    assert cobro["payments"][0]["reference"].startswith("CARTOLA-")

    movimientos = client.get("/api/payments/bank").json()
    assert movimientos["total"] == 1
    assert movimientos["items"][0]["status"] == "conciliado"
    assert movimientos["items"][0]["student_name"] == "Diego Vera"

    # Reimportar la misma cartola no duplica movimientos
    r = client.post(
        "/api/payments/bank/import",
        files={"file": ("cartola.csv", cartola.encode(), "text/csv")},
    )
    assert r.json()["imported"] == 0 and r.json()["skipped"] == 1

    # Movimiento sin RUT queda pendiente y se concilia a mano
    fee2 = client.post("/api/fees", json={
        "student_id": estudiante["id"], "concept": "cuota",
        "period": "2020-03", "amount": 45000, "due_date": "2020-03-20",
    }).json()
    cartola2 = "fecha;descripcion;monto\n15-03-2020;PAGO CUOTA;45.000\n"
    r = client.post(
        "/api/payments/bank/import",
        files={"file": ("cartola2.csv", cartola2.encode(), "text/csv")},
    )
    assert r.json() == {"imported": 1, "matched": 0, "pending": 1, "skipped": 0}
    pendiente = client.get("/api/payments/bank?status=pendiente").json()["items"][0]
    assert pendiente["amount"] == 45000 and pendiente["fee_id"] is None

    r = client.post(
        f"/api/payments/bank/{pendiente['id']}/match", json={"fee_id": fee2["id"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "conciliado" and r.json()["fee_id"] == fee2["id"]
    assert client.get(f"/api/fees/{fee2['id']}").json()["balance"] == 0
    assert client.post(
        f"/api/payments/bank/{pendiente['id']}/match", json={"fee_id": fee2["id"]}
    ).status_code == 409


def test_firma_y_verificacion_de_certificado(client):
    curso = crear_curso(client)
    estudiante = crear_estudiante(client, 77, curso["id"], nombre="Firma")

    r = client.get(f"/api/reports/students/{estudiante['id']}/certificate")
    assert r.status_code == 200, r.text
    certificado = r.json()
    firma = certificado["signature"]
    assert firma["code"].startswith("FE-") and len(firma["code"]) == 15
    assert firma["algorithm"] == "HMAC-SHA256"
    assert firma["verification_url"] == f"/verificar/{firma['code']}"

    with TestClient(app) as anonimo:
        r = anonimo.get(f"/api/public/certificates/{firma['code']}")
        assert r.status_code == 200, r.text
        datos = r.json()
        assert datos["valid"] is True
        assert datos["certificate_number"] == certificado["certificate_number"]
        assert datos["student_name"] == certificado["student"]["full_name"]
        assert datos["student_rut"] == estudiante["rut"]
        assert datos["course_name"] == curso["name"]
        assert r.json()["signed_on"]

        # El código no distingue mayúsculas y uno inexistente da 404
        assert anonimo.get(
            f"/api/public/certificates/{firma['code'].lower()}"
        ).status_code == 200
        assert anonimo.get("/api/public/certificates/FE-000000000000").status_code == 404


# ---------- UTP ----------
def _plan_docx() -> bytes:
    import io

    import docx

    doc = docx.Document()
    table = doc.add_table(rows=0, cols=4)

    def row(*values):
        cells = table.add_row().cells
        for i, value in enumerate(values):
            cells[i].text = value

    row("Planificación de Unidad 4")
    row("Asignatura", "LENGUA Y LITERATURA 7° BÁSICO")
    row("Docente", "Pedro Perez")
    row("Fecha de inicio", "05 DE OCTUBRE", "Fecha de cierre", "16 DE DICIEMBRE")
    row("Cantidad de clases", "2")
    row("Eje / OA", "Objetivo de la clase")
    row("OA1", "Leer y comprender textos narrativos")
    row("OA2", "Escribir textos narrativos")
    row("Estrategias")
    row("Tipo de evaluación", "OA", "Instrumento", "Procedimiento")
    row("Formativa", "OA1", "Guía de lectura", "Lectura comprensiva")
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_utp_bases_y_analisis(client):
    r = client.get("/api/utp/bases")
    assert r.status_code == 200, r.text
    bases = r.json()
    assert bases["loaded"] is True and bases["size"] > 0
    assert bases["engine_version"]

    r = client.post(
        "/api/utp/analyze",
        files=[("planificaciones", ("plan.docx", _plan_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))],
        data={"anio": "2026"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["bases"]["oa"] == {"7": 25, "8": 26}
    assert len(data["resumen"]) == 1
    resumen = data["resumen"][0]
    assert resumen["docente"] == "Pedro Perez"
    assert resumen["asignatura"].startswith("LENGUA")
    assert resumen["clases"] == 2 and resumen["evaluaciones"] == 1
    assert resumen["unidad"] == "UNIDAD 4"
    assert data["fecha_revision"] == date.today().isoformat()
    assert len(data["clases"]) == 2 and len(data["evaluaciones"]) == 1
    assert data["clases"][0]["oa_citado"]

    r = client.get(f"/api{data['download_url']}")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Un archivo que no es Word se rechaza
    r = client.post(
        "/api/utp/analyze",
        files=[("planificaciones", ("plan.txt", b"hola", "text/plain"))],
    )
    assert r.status_code == 422


def test_utp_solo_personal(client):
    guardian = client.post("/api/guardians", json={
        "rut": rut(8_600_000), "first_name": "Sin", "last_name": "Acceso",
        "email": "sinacceso@mail.cl",
    }).json()
    r = client.post("/api/users", json={
        "email": "sinacceso@colegio.cl", "full_name": "Sin Acceso",
        "password": "clave12345", "role": "apoderado",
        "guardian_id": guardian["id"],
    })
    assert r.status_code == 201, r.text
    headers = login_headers(client, "sinacceso@colegio.cl")
    assert client.get("/api/utp/bases", headers=headers).status_code == 403
    assert client.post(
        "/api/utp/analyze",
        files=[("planificaciones", ("plan.docx", _plan_docx()))],
        headers=headers,
    ).status_code == 403


def test_utp_excel_anterior_invalido(client):
    r = client.post(
        "/api/utp/analyze",
        files=[
            ("planificaciones", ("plan.docx", _plan_docx())),
            ("previo", ("control.xlsx", b"no es un excel")),
        ],
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["resumen"]) == 1
    assert client.get(f"/api{r.json()['download_url']}").status_code == 200
