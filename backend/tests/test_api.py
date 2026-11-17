import os

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
