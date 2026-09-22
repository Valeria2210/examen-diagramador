import { useState } from "react";
import { downloadFlutter, errorMessage, prepareFlutter } from "../api";
import type { FlutterGeneration } from "../api";

export function FlutterDiagramDialog({ diagramId, onClose }: { diagramId: number; onClose: () => void }) {
  const [apiUrl, setApiUrl] = useState("http://10.0.2.2:8080");
  const [localAi, setLocalAi] = useState(true);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [generation, setGeneration] = useState<FlutterGeneration | null>(null);

  const generate = async () => {
    if (busy) return;
    setBusy(true); setError(null); setGeneration(null); setProgress("Buscando el último backend completo…");
    try {
      const result = await prepareFlutter(diagramId, apiUrl.trim(), localAi);
      setGeneration(result); setProgress("Verificando y descargando el ZIP…");
      await downloadFlutter(result);
      setProgress("Frontend Flutter generado. Descarga iniciada.");
    } catch (cause: unknown) {
      setProgress(""); setError(errorMessage(cause, "No se pudo generar el frontend Flutter."));
    } finally { setBusy(false); }
  };

  return <div className="camera-backdrop" role="dialog" aria-modal="true" aria-label="Generar frontend Flutter">
    <div className="camera-dialog backend-diagram-dialog">
      <div className="camera-header">
        <strong>Generar frontend Flutter</strong>
        <button className="camera-close" onClick={onClose} disabled={busy} aria-label="Cerrar">×</button>
      </div>
      <p>Usará exactamente el IR del último backend completo generado para este diagrama.</p>
      <label htmlFor="flutter-api-url">URL del backend para el móvil</label>
      <input id="flutter-api-url" value={apiUrl} disabled={busy}
        onChange={(event) => setApiUrl(event.target.value)} placeholder="http://10.0.2.2:8080" />
      <p><small>Android Emulator: 10.0.2.2. Teléfono físico: usa la IP LAN de tu PC. Producción: HTTPS.</small></p>
      <label><input type="checkbox" checked={localAi} disabled={busy}
        onChange={(event) => setLocalAi(event.target.checked)} /> Incluir asistente de IA local en el teléfono</label>
      <p>La IA usa un modelo MediaPipe instalado en el dispositivo. El modelo no se incluye por tamaño y licencia.</p>
      {error && <p role="alert">{error}</p>}
      {progress && <p role="status" aria-live="polite">{progress}</p>}
      <button className="toolbar-btn toolbar-btn-primary" disabled={busy || !apiUrl.trim()} onClick={() => void generate()}>
        {busy ? "Generando…" : "Generar app Flutter"}
      </button>
      {generation && <>
        <p>{generation.mensaje}: {generation.metricas.entidades} entidades, {generation.metricas.archivos_flutter} archivos.</p>
        <button className="toolbar-btn" disabled={busy} onClick={() => void downloadFlutter(generation)}>Volver a descargar ZIP</button>
      </>}
    </div>
  </div>;
}
