import { useEffect, useState } from "react";
import * as api from "../api";
import type { AccessRole } from "../types";
import { canGrantRole } from "../permissions";

export function ShareProjectDialog({ projectId, projectName, accessRole, onClose }: { projectId: number; projectName: string; accessRole: AccessRole | null | undefined; onClose: () => void }) {
  const [role, setRole] = useState<api.ProjectShare["role"]>("VIEWER");
  const [shares, setShares] = useState<api.ProjectShare[]>([]);
  const [newLink, setNewLink] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadShares = async () => {
    try {
      setShares(await api.listProjectShares(projectId));
    } catch {
      setError("No se pudieron cargar los enlaces compartidos.");
    }
  };

  useEffect(() => { void loadShares(); }, [projectId]);

  const createLink = async () => {
    if (loading || !canGrantRole(accessRole, role)) return;
    setLoading(true);
    setError(null);
    try {
      const share = await api.createProjectShare(projectId, role);
      const url = new URL(window.location.href);
      url.searchParams.set("share", share.token);
      setNewLink(url.toString());
      await loadShares();
    } catch (err) {
      setError(axiosMessage(err, "No se pudo crear el enlace."));
    } finally {
      setLoading(false);
    }
  };

  const revokeLink = async (token: string) => {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      await api.revokeProjectShare(projectId, token);
      await loadShares();
      if (newLink?.includes(token)) setNewLink(null);
    } catch (err) {
      setError(axiosMessage(err, "No se pudo revocar el enlace."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="share-backdrop" role="dialog" aria-modal="true" aria-label="Compartir proyecto">
      <div className="share-dialog">
        <div className="share-header">
          <div>
            <span className="share-kicker">Proyecto</span>
            <h2>{projectName}</h2>
          </div>
          <button className="share-close" onClick={onClose} aria-label="Cerrar compartir">×</button>
        </div>
        <p className="share-copy">Crea un enlace y decide si podrán ver o editar este proyecto.</p>
        <div className="share-create-row">
          <label>Permiso<select value={role} onChange={(event) => setRole(event.target.value as api.ProjectShare["role"])}>
            {(["VIEWER", "EDITOR", "SHARER", "ADMIN"] as const).filter((option) => canGrantRole(accessRole, option)).map((option) => <option key={option} value={option}>{roleLabel(option)}</option>)}
          </select></label>
          <button className="toolbar-btn toolbar-btn-primary" onClick={() => void createLink()} disabled={loading}>Crear enlace</button>
        </div>
        {newLink && <div className="share-new-link"><input value={newLink} readOnly aria-label="Enlace para compartir" /><button className="toolbar-btn" onClick={() => {
          if (!navigator.clipboard) { setError("Selecciona y copia el enlace manualmente."); return; }
          void navigator.clipboard.writeText(newLink).catch(() => setError("No se pudo copiar. Selecciona y copia el enlace manualmente."));
        }}>Copiar</button></div>}
        {error && <div className="share-error">{error}</div>}
        <div className="share-list">
          <span className="share-kicker">Enlaces creados</span>
          {shares.filter((share) => share.active).length === 0 && <p className="share-empty">Todavía no hay enlaces activos.</p>}
          {shares.filter((share) => share.active).map((share) => <div className="share-item" key={share.token}><span>{roleLabel(share.role)}</span><button disabled={loading} className="toolbar-btn toolbar-btn-quiet" onClick={() => void revokeLink(share.token)}>Revocar</button></div>)}
        </div>
      </div>
    </div>
  );
}

function axiosMessage(error: unknown, fallback: string) {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    return response?.data?.detail ?? fallback;
  }
  return fallback;
}

function roleLabel(role: api.ProjectShare["role"]) {
  return { VIEWER: "Solo lectura", EDITOR: "Puede editar", SHARER: "Puede compartir", ADMIN: "Administrador" }[role];
}
