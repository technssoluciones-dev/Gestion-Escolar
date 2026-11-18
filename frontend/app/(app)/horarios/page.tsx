"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

type Course = { id: number; name: string; year: number };
type Subject = { id: number; name: string; code: string | null };
type Teacher = { id: number; full_name: string; is_active: boolean };

type CourseSubject = {
  id: number;
  course_id: number;
  subject_id: number;
  teacher_id: number | null;
  subject: Subject;
  teacher: { id: number; full_name: string } | null;
  schedule_count: number;
};

type Schedule = {
  id: number;
  course_subject_id: number;
  course_id: number;
  course_name: string;
  subject_id: number;
  subject_name: string;
  teacher_id: number | null;
  teacher_name: string | null;
  weekday: number;
  start_time: string;
  end_time: string;
  room: string | null;
};

const DAYS = [
  { value: 1, label: "Lunes" },
  { value: 2, label: "Martes" },
  { value: 3, label: "Miércoles" },
  { value: 4, label: "Jueves" },
  { value: 5, label: "Viernes" },
];

function timeLabel(value: string): string {
  return value.slice(0, 5);
}

function dayLabel(value: number): string {
  return DAYS.find((day) => day.value === value)?.label ?? "";
}

function ScheduleCard({
  block,
  showCourse,
  onEdit,
  onDelete,
}: {
  block: Schedule;
  showCourse: boolean;
  onEdit?: (block: Schedule) => void;
  onDelete?: (block: Schedule) => void;
}) {
  return (
    <div className="week-block">
      <div className="week-time">
        {timeLabel(block.start_time)} – {timeLabel(block.end_time)}
      </div>
      <strong>{block.subject_name}</strong>
      {showCourse ? (
        <div className="muted small-text">{block.course_name}</div>
      ) : (
        <div className="muted small-text">{block.teacher_name ?? "Sin profesor asignado"}</div>
      )}
      {showCourse && block.teacher_name && (
        <div className="muted small-text">{block.teacher_name}</div>
      )}
      {block.room && <div className="muted small-text">{block.room}</div>}
      {onEdit && onDelete && (
        <div className="week-actions">
          <button className="btn small secondary" onClick={() => onEdit(block)}>
            Editar
          </button>
          <button className="btn small danger" onClick={() => onDelete(block)}>
            Quitar
          </button>
        </div>
      )}
    </div>
  );
}

function WeekGrid({
  blocks,
  showCourse = false,
  onEdit,
  onDelete,
}: {
  blocks: Schedule[];
  showCourse?: boolean;
  onEdit?: (block: Schedule) => void;
  onDelete?: (block: Schedule) => void;
}) {
  return (
    <div className="week-grid">
      {DAYS.map((day) => {
        const items = blocks
          .filter((block) => block.weekday === day.value)
          .sort((a, b) => a.start_time.localeCompare(b.start_time));
        return (
          <div className="week-col" key={day.value}>
            <div className="week-col-head">{day.label}</div>
            {items.map((block) => (
              <ScheduleCard
                key={block.id}
                block={block}
                showCourse={showCourse}
                onEdit={onEdit}
                onDelete={onDelete}
              />
            ))}
            {items.length === 0 && <div className="week-empty">Sin clases</div>}
          </div>
        );
      })}
    </div>
  );
}

export default function HorariosPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [courseId, setCourseId] = useState("");
  const [tab, setTab] = useState<"horario" | "asignaturas" | "profesor">("horario");

  const [assignments, setAssignments] = useState<CourseSubject[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [teacherId, setTeacherId] = useState("");
  const [teacherSchedules, setTeacherSchedules] = useState<Schedule[]>([]);

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [assignmentModal, setAssignmentModal] = useState<{
    mode: "new" | "edit";
    item?: CourseSubject;
  } | null>(null);
  const [assignmentForm, setAssignmentForm] = useState({ subjectId: "", teacherId: "" });

  const [scheduleModal, setScheduleModal] = useState<{
    mode: "new" | "edit";
    item?: Schedule;
  } | null>(null);
  const [scheduleForm, setScheduleForm] = useState({
    courseSubjectId: "",
    weekday: "1",
    start: "08:00",
    end: "09:30",
    room: "",
  });

  useEffect(() => {
    Promise.all([
      api<{ items: Course[] }>("/courses?limit=200"),
      api<{ items: Subject[] }>("/subjects?limit=200"),
      api<{ items: Teacher[] }>("/teachers?limit=200"),
    ])
      .then(([courseResult, subjectResult, teacherResult]) => {
        setCourses(courseResult.items);
        setSubjects(subjectResult.items);
        setTeachers(teacherResult.items);
        if (courseResult.items.length) {
          setCourseId((prev) => prev || String(courseResult.items[0].id));
        }
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "No se pudieron cargar los datos"),
      );
  }, []);

  const loadCourse = useCallback(async (cid: string) => {
    setLoading(true);
    setError("");
    try {
      const [assignmentResult, scheduleResult] = await Promise.all([
        api<{ items: CourseSubject[] }>(`/course-subjects?course_id=${cid}`),
        api<Schedule[]>(`/schedules?course_id=${cid}`),
      ]);
      setAssignments(assignmentResult.items);
      setSchedules(scheduleResult);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el curso");
      setAssignments([]);
      setSchedules([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (courseId) {
      loadCourse(courseId);
    } else {
      setAssignments([]);
      setSchedules([]);
    }
  }, [courseId, loadCourse]);

  const loadTeacher = useCallback(async (tid: string) => {
    setLoading(true);
    setError("");
    try {
      setTeacherSchedules(await api<Schedule[]>(`/schedules?teacher_id=${tid}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el horario del profesor");
      setTeacherSchedules([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab !== "profesor") return;
    if (!teacherId && teachers.length) {
      setTeacherId(String(teachers[0].id));
      return;
    }
    if (teacherId) loadTeacher(teacherId);
  }, [tab, teacherId, teachers, loadTeacher]);

  const course = courses.find((item) => String(item.id) === courseId);

  function openNewAssignment() {
    const used = new Set(assignments.map((item) => item.subject_id));
    const available = subjects.filter((subject) => !used.has(subject.id));
    if (available.length === 0) {
      setError("Todas las asignaturas ya están asignadas a este curso.");
      return;
    }
    setError("");
    setAssignmentForm({ subjectId: String(available[0].id), teacherId: "" });
    setAssignmentModal({ mode: "new" });
  }

  function openEditAssignment(item: CourseSubject) {
    setError("");
    setAssignmentForm({
      subjectId: String(item.subject_id),
      teacherId: item.teacher_id ? String(item.teacher_id) : "",
    });
    setAssignmentModal({ mode: "edit", item });
  }

  async function saveAssignment(event: React.FormEvent) {
    event.preventDefault();
    if (!courseId) return;
    const subjectId = Number(assignmentForm.subjectId);
    if (!subjectId) {
      setError("Selecciona una asignatura.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const body = {
        course_id: Number(courseId),
        subject_id: subjectId,
        teacher_id: assignmentForm.teacherId ? Number(assignmentForm.teacherId) : null,
      };
      if (assignmentModal?.mode === "edit" && assignmentModal.item) {
        await api(`/course-subjects/${assignmentModal.item.id}`, { method: "PUT", body });
        setNotice("Asignatura del curso actualizada.");
      } else {
        await api("/course-subjects", { method: "POST", body });
        setNotice("Asignatura agregada al curso.");
      }
      setAssignmentModal(null);
      await loadCourse(courseId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar la asignatura");
    } finally {
      setSaving(false);
    }
  }

  async function deleteAssignment(item: CourseSubject) {
    const extra = item.schedule_count
      ? ` También se eliminarán ${item.schedule_count} bloque(s) de horario.`
      : "";
    if (!window.confirm(`¿Quitar ${item.subject.name} de este curso?${extra}`)) return;
    setError("");
    setNotice("");
    try {
      await api(`/course-subjects/${item.id}`, { method: "DELETE" });
      setNotice("Asignatura quitada del curso.");
      if (courseId) await loadCourse(courseId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo quitar la asignatura");
    }
  }

  function openNewSchedule() {
    if (assignments.length === 0) {
      setError("Primero agrega asignaturas al curso.");
      return;
    }
    setError("");
    setScheduleForm({
      courseSubjectId: String(assignments[0].id),
      weekday: "1",
      start: "08:00",
      end: "09:30",
      room: "",
    });
    setScheduleModal({ mode: "new" });
  }

  function openEditSchedule(block: Schedule) {
    setError("");
    setScheduleForm({
      courseSubjectId: String(block.course_subject_id),
      weekday: String(block.weekday),
      start: timeLabel(block.start_time),
      end: timeLabel(block.end_time),
      room: block.room ?? "",
    });
    setScheduleModal({ mode: "edit", item: block });
  }

  async function saveSchedule(event: React.FormEvent) {
    event.preventDefault();
    if (!scheduleForm.courseSubjectId) {
      setError("Selecciona una asignatura del curso.");
      return;
    }
    if (scheduleForm.end <= scheduleForm.start) {
      setError("La hora de término debe ser posterior a la de inicio.");
      return;
    }
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const body = {
        course_subject_id: Number(scheduleForm.courseSubjectId),
        weekday: Number(scheduleForm.weekday),
        start_time: scheduleForm.start,
        end_time: scheduleForm.end,
        room: scheduleForm.room.trim() || null,
      };
      if (scheduleModal?.mode === "edit" && scheduleModal.item) {
        await api(`/schedules/${scheduleModal.item.id}`, { method: "PUT", body });
        setNotice("Bloque de horario actualizado.");
      } else {
        await api("/schedules", { method: "POST", body });
        setNotice("Bloque de horario agregado.");
      }
      setScheduleModal(null);
      if (courseId) await loadCourse(courseId);
      if (teacherId && tab === "profesor") await loadTeacher(teacherId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar el bloque");
    } finally {
      setSaving(false);
    }
  }

  async function deleteSchedule(block: Schedule) {
    if (
      !window.confirm(
        `¿Quitar ${block.subject_name} del ${dayLabel(block.weekday).toLowerCase()} a las ${timeLabel(
          block.start_time,
        )}?`,
      )
    ) {
      return;
    }
    setError("");
    setNotice("");
    try {
      await api(`/schedules/${block.id}`, { method: "DELETE" });
      setNotice("Bloque de horario quitado.");
      if (courseId) await loadCourse(courseId);
      if (teacherId && tab === "profesor") await loadTeacher(teacherId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo quitar el bloque");
    }
  }

  const usedSubjects = new Set(
    assignments
      .filter((item) => item.id !== assignmentModal?.item?.id)
      .map((item) => item.subject_id),
  );
  const availableSubjects = subjects.filter((subject) => !usedSubjects.has(subject.id));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Horarios</h1>
          <p>Asignaturas por curso y profesor, y el horario semanal de cada curso.</p>
        </div>
        {tab === "horario" && (
          <button className="btn" onClick={openNewSchedule} disabled={!courseId || !assignments.length}>
            Agregar bloque
          </button>
        )}
        {tab === "asignaturas" && (
          <button className="btn" onClick={openNewAssignment} disabled={!courseId}>
            Agregar asignatura
          </button>
        )}
      </div>

      <div className="filters">
        {tab === "profesor" ? (
          <div>
            <label htmlFor="teacher">Profesor</label>
            <select id="teacher" value={teacherId} onChange={(e) => setTeacherId(e.target.value)}>
              <option value="">Selecciona un profesor</option>
              {teachers.map((teacher) => (
                <option key={teacher.id} value={teacher.id}>
                  {teacher.full_name}
                  {teacher.is_active ? "" : " (inactivo)"}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div>
            <label htmlFor="course">Curso</label>
            <select
              id="course"
              value={courseId}
              onChange={(e) => {
                setCourseId(e.target.value);
                setNotice("");
              }}
            >
              <option value="">Selecciona un curso</option>
              {courses.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.year})
                </option>
              ))}
            </select>
          </div>
        )}
        {tab === "profesor" && teacherSchedules.length > 0 && (
          <div className="filters-actions">
            <span className="muted small-text">
              {teacherSchedules.length} bloque(s) en la semana
            </span>
          </div>
        )}
      </div>

      <div className="tabs">
        <button className={`tab ${tab === "horario" ? "active" : ""}`} onClick={() => setTab("horario")}>
          Horario semanal
        </button>
        <button
          className={`tab ${tab === "asignaturas" ? "active" : ""}`}
          onClick={() => setTab("asignaturas")}
        >
          Asignaturas y profesores
        </button>
        <button className={`tab ${tab === "profesor" ? "active" : ""}`} onClick={() => setTab("profesor")}>
          Por profesor
        </button>
      </div>

      {error && <div className="alert">{error}</div>}
      {notice && <div className="notice">{notice}</div>}

      {courses.length === 0 && (
        <div className="empty-state">
          Aún no hay cursos. <Link href="/cursos">Crea un curso</Link> para armar su horario.
        </div>
      )}

      {tab === "horario" && courseId && (
        <>
          {assignments.length === 0 && !loading && (
            <div className="empty-state">
              {course?.name} todavía no tiene asignaturas asignadas.{" "}
              <button className="btn small" onClick={() => setTab("asignaturas")}>
                Agregar asignaturas
              </button>
            </div>
          )}

          {assignments.length > 0 && (
            <WeekGrid
              blocks={schedules}
              onEdit={openEditSchedule}
              onDelete={deleteSchedule}
            />
          )}

          {loading && <div className="empty">Cargando horario...</div>}
          {!loading && assignments.length > 0 && schedules.length === 0 && (
            <p className="muted small-text">
              Aún no hay bloques en la semana. Usa &quot;Agregar bloque&quot; para crear el primero.
            </p>
          )}
          {!loading && assignments.length > 0 && schedules.length > 0 && (
            <p className="muted small-text">
              El horario es semanal. No se permiten dos clases del mismo curso, del mismo profesor
              ni en la misma sala a la vez.
            </p>
          )}
        </>
      )}

      {tab === "asignaturas" && courseId && (
        <>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Asignatura</th>
                  <th>Profesor a cargo</th>
                  <th>Bloques</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {assignments.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>{item.subject.name}</strong>
                      {item.subject.code && (
                        <div className="muted small-text">{item.subject.code}</div>
                      )}
                    </td>
                    <td>
                      {item.teacher ? (
                        item.teacher.full_name
                      ) : (
                        <span className="muted">Sin asignar</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge ${item.schedule_count ? "ok" : "none"}`}>
                        {item.schedule_count}
                      </span>
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          className="btn small secondary"
                          onClick={() => openEditAssignment(item)}
                        >
                          Editar
                        </button>
                        <button className="btn small danger" onClick={() => deleteAssignment(item)}>
                          Quitar
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {loading && <div className="empty">Cargando asignaturas...</div>}
            {!loading && assignments.length === 0 && (
              <div className="empty">
                Este curso no tiene asignaturas.{" "}
                <button className="btn small" onClick={openNewAssignment}>
                  Agregar la primera
                </button>
              </div>
            )}
          </div>
          <p className="muted small-text" style={{ marginTop: 10 }}>
            Si necesitas crear una asignatura nueva, hazlo en{" "}
            <Link href="/asignaturas">Asignaturas</Link>. Aquí solo se asignan al curso y a su profesor.
          </p>
        </>
      )}

      {tab === "profesor" && (
        <>
          {!teacherId && teachers.length > 0 && (
            <div className="empty-state">Selecciona un profesor para ver su horario.</div>
          )}
          {teachers.length === 0 && (
            <div className="empty-state">
              Aún no hay profesores. <Link href="/profesores">Crea un profesor</Link> para asignarle
              asignaturas.
            </div>
          )}
          {teacherId && <WeekGrid blocks={teacherSchedules} showCourse />}
          {loading && <div className="empty">Cargando horario...</div>}
          {!loading && teacherId && teacherSchedules.length === 0 && (
            <div className="empty-state">
              Este profesor no tiene bloques de horario asignados.
            </div>
          )}
        </>
      )}

      {assignmentModal && (
        <div className="overlay">
          <div className="modal">
            <div className="modal-head">
              <h2>
                {assignmentModal.mode === "edit" ? "Editar asignatura del curso" : "Agregar asignatura"}
              </h2>
              <button className="btn secondary small" onClick={() => setAssignmentModal(null)}>
                Cerrar
              </button>
            </div>
            <form onSubmit={saveAssignment}>
              <div className="form-grid">
                <div className="full">
                  <label htmlFor="subject">
                    Asignatura <span className="req">*</span>
                  </label>
                  <select
                    id="subject"
                    value={assignmentForm.subjectId}
                    onChange={(e) =>
                      setAssignmentForm((prev) => ({ ...prev, subjectId: e.target.value }))
                    }
                    required
                  >
                    <option value="">Selecciona una asignatura</option>
                    {availableSubjects.map((subject) => (
                      <option key={subject.id} value={subject.id}>
                        {subject.name}
                        {subject.code ? ` (${subject.code})` : ""}
                      </option>
                    ))}
                  </select>
                  {availableSubjects.length === 0 && (
                    <p className="muted small-text" style={{ marginBottom: 0 }}>
                      Todas las asignaturas ya están asignadas. Crea una nueva en{" "}
                      <Link href="/asignaturas">Asignaturas</Link>.
                    </p>
                  )}
                </div>
                <div className="full">
                  <label htmlFor="assignment-teacher">Profesor a cargo</label>
                  <select
                    id="assignment-teacher"
                    value={assignmentForm.teacherId}
                    onChange={(e) =>
                      setAssignmentForm((prev) => ({ ...prev, teacherId: e.target.value }))
                    }
                  >
                    <option value="">Sin asignar</option>
                    {teachers.map((teacher) => (
                      <option key={teacher.id} value={teacher.id}>
                        {teacher.full_name}
                        {teacher.is_active ? "" : " (inactivo)"}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="modal-foot">
                <button type="button" className="btn secondary" onClick={() => setAssignmentModal(null)}>
                  Cancelar
                </button>
                <button className="btn" disabled={saving || availableSubjects.length === 0}>
                  {saving ? "Guardando..." : "Guardar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {scheduleModal && (
        <div className="overlay">
          <div className="modal">
            <div className="modal-head">
              <h2>{scheduleModal.mode === "edit" ? "Editar bloque" : "Agregar bloque al horario"}</h2>
              <button className="btn secondary small" onClick={() => setScheduleModal(null)}>
                Cerrar
              </button>
            </div>
            <form onSubmit={saveSchedule}>
              <div className="form-grid">
                <div className="full">
                  <label htmlFor="schedule-subject">
                    Asignatura del curso <span className="req">*</span>
                  </label>
                  <select
                    id="schedule-subject"
                    value={scheduleForm.courseSubjectId}
                    onChange={(e) =>
                      setScheduleForm((prev) => ({ ...prev, courseSubjectId: e.target.value }))
                    }
                    required
                  >
                    <option value="">Selecciona una asignatura</option>
                    {assignments.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.subject.name}
                        {item.teacher ? ` — ${item.teacher.full_name}` : " — sin profesor"}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="schedule-day">
                    Día <span className="req">*</span>
                  </label>
                  <select
                    id="schedule-day"
                    value={scheduleForm.weekday}
                    onChange={(e) =>
                      setScheduleForm((prev) => ({ ...prev, weekday: e.target.value }))
                    }
                  >
                    {DAYS.map((day) => (
                      <option key={day.value} value={day.value}>
                        {day.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="schedule-room">Sala</label>
                  <input
                    id="schedule-room"
                    type="text"
                    value={scheduleForm.room}
                    placeholder="Ej: Sala 1"
                    onChange={(e) => setScheduleForm((prev) => ({ ...prev, room: e.target.value }))}
                  />
                </div>
                <div>
                  <label htmlFor="schedule-start">
                    Hora de inicio <span className="req">*</span>
                  </label>
                  <input
                    id="schedule-start"
                    type="time"
                    step="300"
                    value={scheduleForm.start}
                    onChange={(e) => setScheduleForm((prev) => ({ ...prev, start: e.target.value }))}
                    required
                  />
                </div>
                <div>
                  <label htmlFor="schedule-end">
                    Hora de término <span className="req">*</span>
                  </label>
                  <input
                    id="schedule-end"
                    type="time"
                    step="300"
                    value={scheduleForm.end}
                    onChange={(e) => setScheduleForm((prev) => ({ ...prev, end: e.target.value }))}
                    required
                  />
                </div>
              </div>
              <div className="modal-foot">
                <button type="button" className="btn secondary" onClick={() => setScheduleModal(null)}>
                  Cancelar
                </button>
                <button className="btn" disabled={saving}>
                  {saving ? "Guardando..." : "Guardar bloque"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
