import { ChangeEvent, useEffect, useRef, useState } from "react";
import type { DiagramSummary } from "../types";
import type { AuthUser } from "../api";

interface ToolbarProps {
  collapsed: boolean;
  onTogglePanel: () => void;
  onExportImage: (format: "png" | "jpg") => void;
  exportingImage: boolean;
  diagrams: DiagramSummary[];
  currentDiagramId: number | null;
  onSelectDiagram: (id: number) => void;
  onCreateDiagram: () => void;
  onShareProject: () => void;
  onHistory: () => void;
  onBackend: () => void;
  readOnly: boolean;
  canShare: boolean;
  loading: boolean;
  saveError: boolean;
  onAddClass: () => void;
  onSaveAs: () => void;
  onExportXmi: () => void;
  onExportEnterpriseArchitect: () => void;
  onImportImage: (file: File) => void;
  onImportXmi: (file: File) => void;
  saving: boolean;
  assistantOpen: boolean;
  onToggleAssistant: () => void;
  user: AuthUser | null;
  onLogout: () => void;
}

export function Toolbar({
  collapsed, onTogglePanel, onExportImage, exportingImage,
  diagrams,
  currentDiagramId,
  onSelectDiagram,
  onCreateDiagram,
    onShareProject,
    onHistory,
  onBackend,
  readOnly,
  canShare,
  loading,
  saveError,
  onAddClass,
  onSaveAs,
  onExportXmi,
  onExportEnterpriseArchitect,
  onImportImage,
  onImportXmi,
  saving,
  assistantOpen,
  onToggleAssistant,
  user,
  onLogout,
}: ToolbarProps) {
  const imageInputRef = useRef<HTMLInputElement>(null);
  const xmiInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [selectedImage, setSelectedImage] = useState<{ file: File; url: string } | null>(null);

  useEffect(() => {
    if (!cameraOpen) return;
    let cancelled = false;
    setCameraError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError("Este navegador no permite capturar desde la cámara.");
      return;
    }
    void navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          void videoRef.current.play();
        }
      })
      .catch(() => setCameraError("No se pudo acceder a la cámara. Comprueba los permisos del navegador."));

    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    };
  }, [cameraOpen]);

  const closeCamera = () => {
    setCameraOpen(false);
    setCapturedImage(null);
  };

  const captureImage = () => {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    setCapturedImage(canvas.toDataURL("image/jpeg", 0.92));
  };

  const confirmCapturedImage = async () => {
    if (!capturedImage) return;
    const response = await fetch(capturedImage);
    const blob = await response.blob();
    onImportImage(new File([blob], `captura-uml-${Date.now()}.jpg`, { type: "image/jpeg" }));
    closeCamera();
  };

  const handleImageSelected = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setSelectedImage({ file, url: String(reader.result) });
    reader.readAsDataURL(file);
  };

  const confirmSelectedImage = () => {
    if (!selectedImage) return;
    onImportImage(selectedImage.file);
    setSelectedImage(null);
  };

  const handleXmiSelected = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) onImportXmi(file);
  };

  return (
    <aside id="diagram-controls" className={`toolbar ${collapsed ? "toolbar-collapsed" : ""}`} aria-label="Panel de control del diagrama">
      <button className="toolbar-btn toolbar-panel-toggle" onClick={onTogglePanel} aria-expanded={!collapsed} aria-controls="diagram-control-content">
        {collapsed ? "Mostrar controles" : "Ocultar controles"}
      </button>
      <div id="diagram-control-content" className="toolbar-content" hidden={collapsed}>
      <div className="toolbar-brand">
        <strong className="toolbar-title">Diagramador UML</strong>
        <span className="toolbar-status">{saving ? "Guardando..." : saveError ? "Revisa el error" : loading ? "Cargando..." : "Guardado"}</span>
      </div>

      <div className="toolbar-group toolbar-diagram-group">
        <span className="toolbar-group-label">Diagrama</span>
        <select
          className="toolbar-select"
          value={currentDiagramId ?? ""}
          onChange={(e) => onSelectDiagram(Number(e.target.value))}
          aria-label="Seleccionar diagrama"
          disabled={saving || loading}
        >
          {diagrams.length === 0 && <option value="">Sin diagramas</option>}
          {diagrams.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <button className="toolbar-btn toolbar-btn-primary" onClick={onCreateDiagram} disabled={saving}>
          + Nuevo
        </button>
        <button className="toolbar-btn" onClick={onShareProject} disabled={currentDiagramId === null || !canShare || loading}>
          Compartir
        </button>
      </div>

      <div className="toolbar-group">
        <span className="toolbar-group-label">Edición</span>
        <button className="toolbar-btn toolbar-btn-primary" onClick={onAddClass} disabled={currentDiagramId === null || readOnly}>
          + Clase
        </button>
        <button className="toolbar-btn" onClick={onSaveAs} disabled={currentDiagramId === null || readOnly}>
          Guardar copia
        </button>
        <button className="toolbar-btn" onClick={onHistory} disabled={currentDiagramId === null}>
          Historial
        </button>
      </div>

      <div className="toolbar-group">
        <span className="toolbar-group-label">Intercambio</span>
        <button className="toolbar-btn" onClick={() => onExportImage("png")} disabled={currentDiagramId === null || loading || exportingImage}>Descargar PNG</button>
        <button className="toolbar-btn" onClick={() => onExportImage("jpg")} disabled={currentDiagramId === null || loading || exportingImage}>Descargar JPG</button>
        <button className="toolbar-btn toolbar-btn-backend" onClick={onBackend} disabled={currentDiagramId === null || saving || loading || saveError}>
          Generar backend
        </button>
        <button className="toolbar-btn" onClick={onExportXmi} disabled={currentDiagramId === null}>
          Exportar XMI
        </button>
        <button className="toolbar-btn" onClick={onExportEnterpriseArchitect} disabled={currentDiagramId === null}>
          Exportar EA (JSON)
        </button>
        <button className="toolbar-btn" onClick={() => xmiInputRef.current?.click()} disabled={currentDiagramId === null || readOnly}>
          Importar XMI
        </button>
      </div>

      <div className="toolbar-group">
        <span className="toolbar-group-label">Imagen</span>
        <button className="toolbar-btn" onClick={() => imageInputRef.current?.click()} disabled={currentDiagramId === null || readOnly}>
          Subir imagen
        </button>
        <button className="toolbar-btn" onClick={() => setCameraOpen(true)} disabled={currentDiagramId === null || readOnly}>
          Cámara
        </button>
      </div>

      <div className="toolbar-group toolbar-ai-group">
        <span className="toolbar-group-label">Asistente</span>
        <button className="toolbar-btn toolbar-btn-ai" onClick={onToggleAssistant}>
          {assistantOpen ? "Ocultar IA" : "Mostrar IA"}
        </button>
      </div>

      <div className="toolbar-account">
        <span className="toolbar-user">{user?.username ?? "Cuenta"}</span>
        <button className="toolbar-btn toolbar-btn-quiet" onClick={onLogout}>Salir</button>
      </div>

      </div>
      <input
        ref={imageInputRef}
        className="toolbar-file-input"
        type="file"
        accept="image/png,image/jpeg,image/webp,image/bmp"
        onChange={handleImageSelected}
        aria-label="Importar diagrama UML desde una imagen"
      />
      <input
        ref={xmiInputRef}
        className="toolbar-file-input"
        type="file"
        accept=".xmi,.xml,.zip,application/xml,text/xml,application/zip"
        onChange={handleXmiSelected}
        aria-label="Importar diagrama UML desde XMI"
      />

      {cameraOpen && (
        <div className="camera-backdrop" role="dialog" aria-modal="true" aria-label="Capturar diagrama UML">
          <div className="camera-dialog">
            <div className="camera-header">
              <strong>Capturar diagrama</strong>
              <button className="camera-close" onClick={closeCamera} aria-label="Cerrar cámara">×</button>
            </div>
            {cameraError && <p className="camera-error">{cameraError}</p>}
            {capturedImage ? (
              <img className="camera-preview" src={capturedImage} alt="Vista previa del diagrama capturado" />
            ) : (
              <video ref={videoRef} className="camera-preview" autoPlay muted playsInline />
            )}
            <div className="camera-actions">
              {capturedImage ? (
                <>
                  <button className="toolbar-btn" onClick={() => setCapturedImage(null)}>Repetir</button>
                  <button className="toolbar-btn toolbar-btn-primary" onClick={() => void confirmCapturedImage()}>Usar fotografía</button>
                </>
              ) : (
                <button className="toolbar-btn toolbar-btn-primary" onClick={captureImage} disabled={Boolean(cameraError)}>Capturar</button>
              )}
            </div>
          </div>
        </div>
      )}

      {selectedImage && (
        <div className="camera-backdrop" role="dialog" aria-modal="true" aria-label="Confirmar imagen UML">
          <div className="camera-dialog">
            <div className="camera-header">
              <strong>Confirmar imagen</strong>
              <button className="camera-close" onClick={() => setSelectedImage(null)} aria-label="Cerrar vista previa">×</button>
            </div>
            <img className="camera-preview" src={selectedImage.url} alt="Vista previa del diagrama UML seleccionado" />
            <div className="camera-actions">
              <button className="toolbar-btn" onClick={() => setSelectedImage(null)}>Cancelar</button>
              <button className="toolbar-btn toolbar-btn-primary" onClick={confirmSelectedImage}>Analizar imagen</button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
