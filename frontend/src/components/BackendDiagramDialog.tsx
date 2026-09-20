import { useCallback, useEffect, useRef, useState } from "react";
import { downloadBackend, errorMessage, getDiagramFull, listDiagrams, prepareBackend, validateBackend } from "../api";
import type { BackendGeneration } from "../api";
import type { DiagramFull, DiagramSummary } from "../types";

export function BackendDiagramDialog({ initialDiagramId, onClose, autoGenerate = false }: {
  initialDiagramId: number | null;
  onClose: () => void;
  autoGenerate?: boolean;
}) {
  const [diagrams, setDiagrams] = useState<DiagramSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(initialDiagramId);
  const [diagram, setDiagram] = useState<DiagramFull | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDiagram, setLoadingDiagram] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [ir, setIr] = useState<unknown>(null);
  const [generation, setGeneration] = useState<BackendGeneration | null>(null);
  const [swagger, setSwagger] = useState(true);
  const [scope, setScope] = useState<"entidades" | "completo">("completo");
  const actionRunning = useRef(false);
  const [progress, setProgress] = useState("");
  const [docker, setDocker] = useState(true);
  const [completePk, setCompletePk] = useState(true);
  const autoStarted = useRef(false);

  const run = useCallback(async (action: () => Promise<void>) => {
    if (actionRunning.current) return;
    actionRunning.current = true;
    setBusy(true); setError(null);
    try { await action(); }
    catch (cause: unknown) { setProgress(""); setError(errorMessage(cause, "No se pudo completar la solicitud del generador.")); }
    finally { actionRunning.current = false; setBusy(false); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void listDiagrams().then((items) => {
      if (cancelled) return;
      items = items.filter((item) => item.access_role === "OWNER" && item.id === initialDiagramId);
      setDiagrams(items);
      setSelectedId(items[0]?.id ?? null);
      if (items.length === 0) setError("Selecciona un diagrama del lienzo del que seas propietario para generar el backend.");
    }).catch((cause: unknown) => {
      if (!cancelled) setError(errorMessage(cause, "No se pudieron consultar los diagramas guardados."));
    }).finally(() => { if (!cancelled) setLoadingList(false); });
    return () => { cancelled = true; };
  }, [initialDiagramId]);

  useEffect(() => {
    if (loadingList || selectedId === null) return;
    let cancelled = false;
    setDiagram(null);
    setIr(null);
    setGeneration(null);
    setError(null); setProgress("");
    setLoadingDiagram(true);
    void getDiagramFull(selectedId).then((item) => {
      if (!cancelled) setDiagram(item);
    }).catch((cause: unknown) => {
      if (!cancelled) setError(errorMessage(cause, "No se pudo cargar el diagrama seleccionado."));
    }).finally(() => { if (!cancelled) setLoadingDiagram(false); });
    return () => { cancelled = true; };
  }, [selectedId, loadingList]);

  const generate = useCallback(async () => {
    if (!diagram) return;
    setGeneration(null); setProgress("Validando, corrigiendo y generando el backend…");
    const result = await prepareBackend(diagram.id, scope === "completo" && swagger, docker, scope, completePk, completePk);
    setGeneration(result); setProgress("Verificando y descargando el ZIP…");
    await downloadBackend(result); setProgress("Backend generado. Descarga del ZIP iniciada.");
  }, [diagram, scope, swagger, docker, completePk]);

  useEffect(() => {
    if (!autoGenerate || !diagram || autoStarted.current) return;
    autoStarted.current = true;
    if (diagram.classes.length > 0) void run(generate);
    // One generation per dialog opening; retries are explicit after an error.
  }, [autoGenerate, diagram, run, generate]);

  const download = () => {
    if (!diagram) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(diagram, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `diagrama-${diagram.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return <div className="camera-backdrop" role="dialog" aria-modal="true" aria-label="Seleccionar diagrama para backend">
    <div className="camera-dialog backend-diagram-dialog">
      <div className="camera-header">
        <strong>Generar backend · Fase 2</strong>
        <button className="camera-close" onClick={onClose} disabled={busy} aria-label="Cerrar">×</button>
      </div>
      <p>Se generará el diagrama actual del lienzo en Spring Boot con PostgreSQL.</p>
      <label htmlFor="backend-diagram-select">Diagrama de origen</label>
      <select id="backend-diagram-select" value={selectedId ?? ""} disabled
        onChange={(event) => setSelectedId(Number(event.target.value))}>
        {diagrams.length === 0 && <option value="">Sin diagramas disponibles</option>}
        {diagrams.map((item) => <option key={item.id} value={item.id}>{item.name} (#{item.id})</option>)}
      </select>
      {(loadingList || loadingDiagram) && <p role="status">Consultando la base de datos…</p>}
      {error && <p role="alert">{error}</p>}
      {!loadingList && !error && diagrams.length === 0 && <p>Crea y guarda un diagrama para comenzar.</p>}
      {diagram && <>
        <p><strong>{diagram.name}</strong>: {diagram.classes.length} clases y {diagram.relations.length} relaciones.</p>
        {diagram.classes.length === 0 && <p>Este diagrama está vacío. Agrega clases antes de preparar el backend.</p>}
        <details><summary>Ver modelo del diagrama</summary>
          <pre className="backend-diagram-preview">{JSON.stringify(diagram, null, 2)}</pre>
          <button className="toolbar-btn" onClick={download}>Descargar modelo JSON</button>
        </details>
        <label><input type="checkbox" checked={completePk} disabled={busy} onChange={(e) => { setCompletePk(e.target.checked); setGeneration(null); setIr(null); }} /> Corregir automáticamente al generar</label>
        <p>Completa PK faltantes y corrige nombres, tipos equivalentes y campos en conflicto. El ZIP incluye un informe; el diagrama original se conserva. Los errores ambiguos se muestran para que puedas resolverlos.</p>
        <label htmlFor="backend-scope">Alcance de generación</label>
        <select id="backend-scope" value={scope} disabled={busy} onChange={(e) => {
          setScope(e.target.value as "entidades" | "completo"); setGeneration(null);
        }}>
          <option value="entidades">Paso 4 · Solo entidades de prueba</option>
          <option value="completo">Backend completo con CRUD y documentación offline</option>
        </select>
        {scope === "entidades" && <p>Descarga el proyecto de prueba y ejecuta mvn compile con Java 17+ antes de continuar con Repository.</p>}
        <label><input type="checkbox" checked={swagger} disabled={busy || scope === "entidades"} onChange={(e) => { setGeneration(null); setSwagger(e.target.checked); }} /> Incluir Swagger</label>
        <label><input type="checkbox" checked={docker} disabled={busy} onChange={(e) => { setGeneration(null); setDocker(e.target.checked); }} /> Incluir Docker</label>
        <div>
          <button className="toolbar-btn" disabled={busy || diagram.classes.length === 0} onClick={() => void run(async () => {
            setProgress("Validando el modelo…");
            setIr(null); setGeneration(null); setIr(await validateBackend(diagram.id, completePk, completePk));
          })}>Validar modelo</button>
          <button className="toolbar-btn toolbar-btn-primary" disabled={busy || diagram.classes.length === 0} onClick={() => void run(generate)}>{busy ? "Generando…" : scope === "entidades" ? "Generar entidades de prueba" : "Generar backend Spring Boot"}</button>
        </div>
        {progress && <p role="status" aria-live="polite">{progress}</p>}
        {ir !== null && <details><summary>Resultado de validación</summary>
          <pre className="backend-diagram-preview">{JSON.stringify(ir, null, 2)}</pre>
        </details>}
        {generation && <><p role="status">{generation.mensaje}</p>
          {!!generation.avisos?.length && <details><summary>Correcciones aplicadas ({generation.avisos.length})</summary><ul>{generation.avisos.map((notice, index) => <li key={index}>{notice}</li>)}</ul></details>}
          <details><summary>Detalles de generación y métricas</summary><dl>
            <dt>Entidades / archivos Java / líneas Java</dt>
            <dd>{generation.metricas.entidades} / {generation.metricas.archivos_java} / {generation.metricas.lineas_java}</dd>
            <dt>Tiempo de generación</dt><dd>{generation.metricas.duracion_generacion_ms} ms</dd>
            <dt>Tiempo total del servidor</dt><dd>{generation.metricas.duracion_total_ms} ms</dd>
            <dt>ZIP / caducidad</dt><dd>{(generation.tamano_bytes / 1024).toFixed(1)} KB / {new Date(generation.expira_en).toLocaleString()}</dd>
            <dt>Relaciones validadas</dt><dd>{generation.metricas.relaciones} ({Object.entries(generation.metricas.relaciones_por_tipo).filter(([, count]) => count > 0).map(([type, count]) => `${type}: ${count}`).join(", ") || "sin relaciones"})</dd>
            <dt>Productividad del generador</dt><dd>{generation.metricas.entidades_por_segundo} entidades/s</dd>
            <dt>Calidad</dt><dd>IR validado. Compilación: {generation.compilacion}. Endpoints documentados: {generation.metricas.endpoints_documentados}.</dd>
          </dl></details>
          <button className="toolbar-btn" disabled={busy} onClick={() => void run(async () => {
            setProgress("Verificando y descargando el ZIP…"); await downloadBackend(generation); setProgress("Descarga iniciada.");
          })}>Volver a descargar ZIP</button></>}
        <p>El ZIP incluye el alcance elegido, README, métricas y un manifiesto de integridad. El backend completo añade OpenAPI y Postman offline. La descarga se inicia automáticamente al terminar.</p>
        <p className="backend-next-phase"><strong>Fase 3 · Flutter pendiente.</strong> La aplicación móvil se conectará a la API del backend generado. Esta fase aún no se ha iniciado.</p>
      </>}
    </div>
  </div>;
}
