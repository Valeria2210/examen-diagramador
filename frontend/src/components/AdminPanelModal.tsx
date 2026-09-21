import { useState, useEffect } from "react";
import * as api from "../api";

interface AdminPanelModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser: api.AuthUser;
}

export function AdminPanelModal({ isOpen, onClose, currentUser }: AdminPanelModalProps) {
  const [data, setData] = useState<api.AdminStatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"overview" | "users" | "create">("overview");

  // Form for new user
  const [newUsername, setNewUsername] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newIsStaff, setNewIsStaff] = useState(false);
  const [formBusy, setFormBusy] = useState(false);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const stats = await api.fetchAdminStats();
      setData(stats);
    } catch (err) {
      setError(api.errorMessage(err, "No se pudo cargar la información del panel de administración."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      void loadData();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormBusy(true);
    setFormError(null);
    setFormSuccess(null);

    try {
      await api.createAdminUser({
        username: newUsername.trim(),
        email: newEmail.trim(),
        password: newPassword,
        is_staff: newIsStaff,
      });
      setFormSuccess(`¡Usuario "${newUsername}" creado con éxito!`);
      setNewUsername("");
      setNewEmail("");
      setNewPassword("");
      setNewIsStaff(false);
      void loadData();
    } catch (err) {
      setFormError(api.errorMessage(err, "Error al crear el usuario."));
    } finally {
      setFormBusy(false);
    }
  };

  const handleDeleteUser = async (userId: number, username: string) => {
    if (userId === currentUser.id) {
      alert("No puedes eliminar tu propio usuario en sesión.");
      return;
    }
    if (!window.confirm(`¿Estás segura de eliminar al usuario "${username}"? Sus proyectos y diagramas también se eliminarán.`)) {
      return;
    }

    try {
      await api.deleteAdminUser(userId);
      void loadData();
    } catch (err) {
      alert(api.errorMessage(err, "Error al eliminar usuario."));
    }
  };

  return (
    <div className="admin-modal-backdrop" role="dialog" aria-modal="true" aria-label="Panel de Administración">
      <div className="admin-modal-card">
        {/* Header con estilo elegante y moderno */}
        <div className="admin-modal-header">
          <div className="admin-modal-title-group">
            <div className="admin-badge-icon">👑</div>
            <div>
              <h2 className="admin-modal-title">Panel de Control de Administración</h2>
              <p className="admin-modal-subtitle">
                Bienvenida, <strong>{currentUser.username}</strong> • Gestión integral de usuarios, métricas y sistema
              </p>
            </div>
          </div>
          <button className="admin-modal-close-btn" onClick={onClose} aria-label="Cerrar panel">
            ✕
          </button>
        </div>

        {/* Barra de Navegación de Pestañas */}
        <div className="admin-nav-tabs">
          <button
            className={`admin-nav-tab ${tab === "overview" ? "active" : ""}`}
            onClick={() => setTab("overview")}
          >
            📊 Resumen y Métricas
          </button>
          <button
            className={`admin-nav-tab ${tab === "users" ? "active" : ""}`}
            onClick={() => setTab("users")}
          >
            👥 Gestión de Usuarios ({data?.users.length ?? 0})
          </button>
          <button
            className={`admin-nav-tab ${tab === "create" ? "active" : ""}`}
            onClick={() => setTab("create")}
          >
            ➕ Crear Nuevo Usuario
          </button>
          <button
            className="admin-nav-tab admin-nav-tab-refresh"
            onClick={() => void loadData()}
            title="Refrescar datos"
          >
            🔄 Recargar
          </button>
        </div>

        {/* Contenido Principal */}
        <div className="admin-modal-body">
          {error && <div className="admin-alert admin-alert-danger">{error}</div>}

          {loading ? (
            <div className="admin-loading-state">
              <div className="admin-spinner"></div>
              <p>Cargando información administrativa...</p>
            </div>
          ) : (
            <>
              {/* Pestaña: Resumen General */}
              {tab === "overview" && data && (
                <div className="admin-tab-content">
                  <div className="admin-stats-grid">
                    <div className="admin-stat-card">
                      <div className="admin-stat-icon-wrapper user-theme">👤</div>
                      <div>
                        <span className="admin-stat-label">Usuarios Registrados</span>
                        <strong className="admin-stat-value">{data.stats.total_users}</strong>
                      </div>
                    </div>

                    <div className="admin-stat-card">
                      <div className="admin-stat-icon-wrapper project-theme">📁</div>
                      <div>
                        <span className="admin-stat-label">Proyectos Activos</span>
                        <strong className="admin-stat-value">{data.stats.total_projects}</strong>
                      </div>
                    </div>

                    <div className="admin-stat-card">
                      <div className="admin-stat-icon-wrapper diagram-theme">📐</div>
                      <div>
                        <span className="admin-stat-label">Diagramas Modelados</span>
                        <strong className="admin-stat-value">{data.stats.total_diagrams}</strong>
                      </div>
                    </div>

                    <div className="admin-stat-card">
                      <div className="admin-stat-icon-wrapper class-theme">🧱</div>
                      <div>
                        <span className="admin-stat-label">Clases UML Creadas</span>
                        <strong className="admin-stat-value">{data.stats.total_classes}</strong>
                      </div>
                    </div>
                  </div>

                  <div className="admin-card-section">
                    <h3 className="admin-section-title">⚡ Estado del Motor de IA y Servidor</h3>
                    <div className="admin-status-banner">
                      <div className="admin-status-item">
                        <span className="admin-status-dot online"></span>
                        <div>
                          <strong>Servicio de IA (Google Gemini)</strong>
                          <p>Modelo activo: <code>{data.stats.gemini_model}</code> (Structured JSON Output activo)</p>
                        </div>
                      </div>
                      <div className="admin-status-item">
                        <span className="admin-status-dot online"></span>
                        <div>
                          <strong>Base de Datos Relacional</strong>
                          <p>PostgreSQL 17 sincronizado con esquemas de diagramas y Flyway</p>
                        </div>
                      </div>
                      <div className="admin-status-item">
                        <span className="admin-status-dot online"></span>
                        <div>
                          <strong>Generadores de Código</strong>
                          <p>Spring Boot 3.x (Java 17) &amp; Flutter Mobile (MediaPipe IA Local)</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Pestaña: Lista de Usuarios */}
              {tab === "users" && data && (
                <div className="admin-tab-content">
                  <div className="admin-table-container">
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th>ID</th>
                          <th>Usuario</th>
                          <th>Email</th>
                          <th>Rol / Privilegio</th>
                          <th>Proyectos</th>
                          <th>Fecha de Registro</th>
                          <th style={{ textAlign: "right" }}>Acciones</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.users.map((u) => (
                          <tr key={u.id} className={u.id === currentUser.id ? "current-user-row" : ""}>
                            <td>#{u.id}</td>
                            <td>
                              <div className="admin-user-cell">
                                <span className="admin-avatar">
                                  {u.username.substring(0, 2).toUpperCase()}
                                </span>
                                <div>
                                  <strong>{u.username}</strong>
                                  {u.id === currentUser.id && (
                                    <span className="admin-badge-self">Tú (en sesión)</span>
                                  )}
                                </div>
                              </div>
                            </td>
                            <td>{u.email || <em style={{ color: "#999" }}>Sin email</em>}</td>
                            <td>
                              {u.is_superuser ? (
                                <span className="admin-role-badge superuser">Super Admin</span>
                              ) : u.is_staff ? (
                                <span className="admin-role-badge staff">Staff Admin</span>
                              ) : (
                                <span className="admin-role-badge user">Usuario Regular</span>
                              )}
                            </td>
                            <td>
                              <span className="admin-count-pill">{u.projects_count}</span>
                            </td>
                            <td>
                              {u.date_joined
                                ? new Date(u.date_joined).toLocaleDateString("es-ES", {
                                    year: "numeric",
                                    month: "short",
                                    day: "numeric",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  })
                                : "-"}
                            </td>
                            <td style={{ textAlign: "right" }}>
                              {u.id !== currentUser.id ? (
                                <button
                                  className="admin-action-btn delete"
                                  onClick={() => void handleDeleteUser(u.id, u.username)}
                                  title={`Eliminar usuario ${u.username}`}
                                >
                                  🗑️ Eliminar
                                </button>
                              ) : (
                                <span style={{ color: "#888", fontSize: "12px" }}>Protegido</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Pestaña: Crear Nuevo Usuario */}
              {tab === "create" && (
                <div className="admin-tab-content">
                  <div className="admin-form-container">
                    <form className="admin-create-form" onSubmit={handleCreateUser}>
                      <h3 className="admin-section-title">Nuevo Usuario para el Sistema</h3>
                      <p className="admin-section-desc">
                        Crea cuentas para colaboradores, alumnos o administradores adicionales con acceso directo al diagramador.
                      </p>

                      {formSuccess && <div className="admin-alert admin-alert-success">{formSuccess}</div>}
                      {formError && <div className="admin-alert admin-alert-danger">{formError}</div>}

                      <div className="admin-form-group">
                        <label>Nombre de Usuario *</label>
                        <input
                          type="text"
                          required
                          value={newUsername}
                          onChange={(e) => setNewUsername(e.target.value)}
                          placeholder="Ej. carlos_diagramador"
                        />
                      </div>

                      <div className="admin-form-group">
                        <label>Correo Electrónico (Opcional)</label>
                        <input
                          type="email"
                          value={newEmail}
                          onChange={(e) => setNewEmail(e.target.value)}
                          placeholder="carlos@example.com"
                        />
                      </div>

                      <div className="admin-form-group">
                        <label>Contraseña *</label>
                        <input
                          type="password"
                          required
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          placeholder="Mínimo 6 caracteres"
                        />
                      </div>

                      <div className="admin-form-group checkbox-group">
                        <label className="admin-checkbox-label">
                          <input
                            type="checkbox"
                            checked={newIsStaff}
                            onChange={(e) => setNewIsStaff(e.target.checked)}
                          />
                          <span>
                            <strong>Dar privilegios de Administrador (Staff)</strong>
                            <small>Permite gestionar otros usuarios y ver este panel de administración.</small>
                          </span>
                        </label>
                      </div>

                      <div className="admin-form-actions">
                        <button type="button" className="admin-btn secondary" onClick={() => setTab("users")}>
                          Cancelar
                        </button>
                        <button type="submit" className="admin-btn primary" disabled={formBusy}>
                          {formBusy ? "Creando usuario..." : "✨ Guardar y Registrar Usuario"}
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
