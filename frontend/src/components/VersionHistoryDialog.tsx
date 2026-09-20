import { useEffect, useState } from "react";
import * as api from "../api";

export function VersionHistoryDialog({ diagramId, readOnly, withSaving, onClose, onRestored }: {
  diagramId: number;
  readOnly: boolean;
  withSaving: (operation: () => Promise<unknown>) => Promise<boolean>;
  onClose: () => void;
  onRestored: () => void;
}) {
  const [versions, setVersions] = useState<api.DiagramVersion[]>([]);
  const [label, setLabel] = useState("");
  const [loading, setLoading] = useState(true);
  const [restoring, setRestoring] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadVersions = async () => {
    try {
      setVersions(await api.listDiagramVersions(diagramId));
    } catch {
      setError("No se pudo cargar el historial.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadVersions(); }, [diagramId]);

  const saveVersion = async () => {
    if (readOnly || saving || restoring !== null) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await withSaving(() => api.createDiagramVersion(diagramId, label || "Punto guardado"));
      if (!saved) { setError("No se pudo guardar la versión."); return; }
      setLabel("");
      await loadVersions();
    } catch {
      setError("No se pudo guardar la versión.");
    } finally {
      setSaving(false);
    }
  };

  const restore = async (version: api.DiagramVersion) => {
    if (readOnly || saving || restoring !== null) return;
    if (!window.confirm(`¿Restaurar la versión ${version.version_number}?`)) return;
    setRestoring(version.id);
    setError(null);
    try {
      const restored = await withSaving(() => api.restoreDiagramVersion(diagramId, version.id));
      if (!restored) { setError("No se pudo restaurar la versión."); return; }
      onRestored();
      onClose();
    } catch {
      setError("No se pudo restaurar la versión.");
    } finally {
      setRestoring(null);
    }
  };

  return (
    <div className="share-backdrop" role="dialog" aria-modal="true" aria-label="Historial de versiones">
      <div className="share-dialog version-dialog">
        <div className="share-header">
          <div><span className="share-kicker">Historial</span><h2>Versiones del diagrama</h2></div>
          <button disabled={saving || restoring !== null} className="share-close" onClick={onClose} aria-label="Cerrar historial">×</button>
        </div>
        {!readOnly && <div className="version-create">
          <input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Nombre de la versión" aria-label="Nombre de la versión" />
          <button disabled={saving || restoring !== null || loading} className="toolbar-btn toolbar-btn-primary" onClick={() => void saveVersion()}>Guardar versión</button>
        </div>}
        {error && <div className="share-error">{error}</div>}
        <div className="version-list">
          {loading && <p className="share-empty">Cargando historial...</p>}
          {!loading && versions.length === 0 && <p className="share-empty">Todavía no hay versiones guardadas.</p>}
          {versions.map((version) => <div className="version-item" key={version.id}><div><strong>Versión {version.version_number}</strong><span>{version.label} · {new Date(version.created_at).toLocaleString()}</span><small>{version.created_by ?? "Sistema"}</small></div>{!readOnly && <button className="toolbar-btn" disabled={saving || restoring !== null} onClick={() => void restore(version)}>{restoring === version.id ? "Restaurando..." : "Restaurar"}</button>}</div>)}
        </div>
      </div>
    </div>
  );
}
