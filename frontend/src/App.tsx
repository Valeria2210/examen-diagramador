import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  Connection,
  ConnectionMode,
  Controls,
  Edge,
  EdgeChange,
  Node,
  NodeChange,
  OnConnectStart,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  useEdgesState,
  useNodesState,
} from "reactflow";
import "reactflow/dist/style.css";

import * as api from "./api";
import { ClassNode, ClassNodeActions, ClassNodeData } from "./components/ClassNode";
import { RelationEdge, RelationEdgeData, UMLMarkerDefs } from "./components/RelationEdge";
import { RelationPanel } from "./components/RelationPanel";
import { Toolbar } from "./components/Toolbar";
import { AIAssistant } from "./components/AIAssistant";
import { AuthPage } from "./components/AuthPage";
import { ShareProjectDialog } from "./components/ShareProjectDialog";
import { VersionHistoryDialog } from "./components/VersionHistoryDialog";
import { BackendDiagramDialog } from "./components/BackendDiagramDialog";
import { canEditDiagram, canShareProject } from "./permissions";
import { exportDiagram } from "./exportDiagram";
import { normalizeMethodParameters } from "./importParameters";
import type { Attribute, ClassKind, DiagramSummary, Method, Relation, UMLClass } from "./types";

const nodeTypes = { umlClass: ClassNode };
const edgeTypes = { umlRelation: RelationEdge };

function classToNode(umlClass: UMLClass, actions: ClassNodeActions, readOnly = false): Node<ClassNodeData> {
  return {
    id: String(umlClass.id),
    type: "umlClass",
    position: { x: umlClass.pos_x, y: umlClass.pos_y },
    style: { width: umlClass.width, height: umlClass.height },
    data: { umlClass, actions, readOnly },
  };
}

function getRelationHandles(relation: Relation, classes: UMLClass[]): { sourceHandle: string; targetHandle: string } {
  const source = classes.find((umlClass) => umlClass.id === relation.source);
  const target = classes.find((umlClass) => umlClass.id === relation.target);
  if (!source || !target) return { sourceHandle: "source-right", targetHandle: "source-left" };

  const horizontal = Math.abs(target.pos_x - source.pos_x) >= Math.abs(target.pos_y - source.pos_y);
  if (horizontal && target.pos_x >= source.pos_x) return { sourceHandle: "source-right", targetHandle: "source-left" };
  if (horizontal) return { sourceHandle: "source-left", targetHandle: "source-right" };
  if (target.pos_y >= source.pos_y) return { sourceHandle: "source-bottom", targetHandle: "source-top" };
  return { sourceHandle: "source-top", targetHandle: "source-bottom" };
}

function relationToEdge(
  relation: Relation,
  onSelectRelation: (r: Relation) => void,
  handles: { sourceHandle: string; targetHandle: string } = { sourceHandle: "source-right", targetHandle: "source-left" }
): Edge<RelationEdgeData> {
  return {
    id: `rel-${relation.id}`,
    source: String(relation.source),
    target: String(relation.target),
    sourceHandle: handles.sourceHandle.replace(/^target-/, "source-"),
    targetHandle: handles.targetHandle.replace(/^target-/, "source-"),
    type: "umlRelation",
    data: { relation, onSelectRelation },
  };
}

function normalizeImportedVisibility(value?: string): Attribute["visibility"] {
  const normalized = (value ?? "PRIVATE").toUpperCase();
  if (normalized === "PUBLIC" || normalized === "+") return "PUBLIC";
  if (normalized === "PROTECTED" || normalized === "#") return "PROTECTED";
  if (normalized === "PACKAGE" || normalized === "~") return "PACKAGE";
  return "PRIVATE";
}

function normalizeImportedRelationType(value?: string): Relation["relation_type"] {
  const normalized = (value ?? "ASSOCIATION").toUpperCase();
  if (normalized.includes("INHERIT")) return "INHERITANCE";
  if (normalized.includes("REALIZ")) return "REALIZATION";
  if (normalized.includes("AGGR")) return "AGGREGATION";
  if (normalized.includes("COMPOS")) return "COMPOSITION";
  if (normalized.includes("DEPEND")) return "DEPENDENCY";
  return "ASSOCIATION";
}

export default function App() {
  const [authToken, setAuthToken] = useState(() => localStorage.getItem("uml-auth-token"));
  const [authUser, setAuthUser] = useState<api.AuthUser | null>(null);
  const [sessionError, setSessionError] = useState<string | null>(null);

  useEffect(() => {
    const expired = () => {
      setAuthToken(null);
      setAuthUser(null);
      setSessionError("Tu sesión venció. Inicia sesión nuevamente.");
    };
    const syncSession = (event: StorageEvent) => {
      if (event.key === "uml-auth-token" || event.key === null) {
        setAuthUser(null);
        setAuthToken(localStorage.getItem("uml-auth-token"));
      }
    };
    window.addEventListener(api.AUTH_EXPIRED_EVENT, expired);
    window.addEventListener("storage", syncSession);
    return () => {
      window.removeEventListener(api.AUTH_EXPIRED_EVENT, expired);
      window.removeEventListener("storage", syncSession);
    };
  }, []);

  useEffect(() => {
    if (!authToken) return;
    let cancelled = false;
    void api.getCurrentUser().then((user) => {
      if (!cancelled) setAuthUser(user);
    }).catch(() => {
      // The API interceptor handles invalid credentials. Network failures are
      // reported by the editor and must not erase an otherwise valid session.
    });
    return () => { cancelled = true; };
  }, [authToken]);

  const handleLogout = useCallback(async () => {
    try {
      await api.logout();
    } catch (err) {
      console.error(err);
    } finally {
      localStorage.removeItem("uml-auth-token");
      setAuthToken(null);
      setAuthUser(null);
      setSessionError(null);
    }
  }, []);

  if (!authToken) {
    return <AuthPage sessionError={sessionError} onAuthenticated={(response) => {
      localStorage.setItem("uml-auth-token", response.token);
      setAuthToken(response.token);
      setAuthUser(response.user);
      setSessionError(null);
    }} />;
  }

  return <DiagramEditor key={authToken} authUser={authUser} onLogout={handleLogout} />;
}

function DiagramEditor({ authUser, onLogout }: { authUser: api.AuthUser | null; onLogout: () => void }) {
  const [diagrams, setDiagrams] = useState<DiagramSummary[]>([]);
  const [currentDiagramId, setCurrentDiagramId] = useState<number | null>(null);
  const [nodes, setNodes] = useNodesState<ClassNodeData>([]);
  const [edges, setEdges] = useEdgesState<RelationEdgeData>([]);
  const [selectedRelation, setSelectedRelation] = useState<Relation | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [controlsCollapsed, setControlsCollapsed] = useState(false);
  const [exportingImage, setExportingImage] = useState(false);
  const [backendOpen, setBackendOpen] = useState(false);
  const refreshRequestId = useRef(0);
  const pendingConnectionSource = useRef<string | null>(null);
  const pendingSaves = useRef(0);
  const mutationRevision = useRef(0);
  const interacting = useRef(false);
  const recoverDiagram = useRef<() => Promise<void>>(async () => {});

  const currentDiagram = diagrams.find((diagram) => diagram.id === currentDiagramId);
  const readOnly = !canEditDiagram(currentDiagram?.access_role);
  const canShare = canShareProject(currentDiagram?.access_role);

  const withSaving = useCallback(async (fn: () => Promise<unknown>): Promise<boolean> => {
    pendingSaves.current += 1;
    mutationRevision.current += 1;
    setSaving(true);
    setError(null);
    try {
      await fn();
      return true;
    } catch (err) {
      console.error(err);
      setError(api.errorMessage(err, "No se pudieron guardar los cambios. Comprueba tu conexión e inténtalo nuevamente."));
      void recoverDiagram.current();
      return false;
    } finally {
      pendingSaves.current -= 1;
      mutationRevision.current += 1;
      setSaving(pendingSaves.current > 0);
    }
  }, []);

  const handleSelectRelation = useCallback((relation: Relation) => {
    setSelectedRelation(relation);
    setNodes((current) => current.map((node) => node.selected ? { ...node, selected: false } : node));
    setEdges((current) => current.map((edge) => ({ ...edge, selected: edge.id === `rel-${relation.id}` })));
    canvasRef.current?.focus({ preventScroll: true });
  }, [setNodes, setEdges]);

  // ---- Cargar lista de diagramas al iniciar ----
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const shareToken = new URLSearchParams(window.location.search).get("share");
        let sharedProjectId: number | null = null;
        if (shareToken) {
          try {
            const shared = await api.acceptProjectShare(shareToken);
            sharedProjectId = shared.project;
            if (cancelled) return;
            const url = new URL(window.location.href);
            url.searchParams.delete("share");
            window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
          } catch (err) {
            console.error(err);
            if (cancelled) return;
            setError(api.errorMessage(err, "No se pudo aceptar el enlace de invitación."));
          }
        }
        const list = await api.listDiagrams();
        if (cancelled) return;

        setDiagrams(list);
        if (list.length > 0) {
          setCurrentDiagramId(list.find((diagram) => diagram.project === sharedProjectId)?.id ?? list[0].id);
        } else {
          setLoading(false);
        }
      } catch (err) {
        if (cancelled) return;
        console.error(err);
        setError("No se pudo conectar con el backend. ¿Está corriendo en http://127.0.0.1:8000?");
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  // ---- Acciones sobre clases/atributos/métodos (definidas antes de cargar, para inyectarlas en cada nodo) ----
  const actions = useMemo<ClassNodeActions>(() => {
    const changeClass = (classId: number, update: (umlClass: UMLClass) => UMLClass) => {
      setNodes((current) => current.map((node) => node.id === String(classId)
        ? { ...node, data: { ...node.data, umlClass: update(node.data.umlClass) } }
        : node));
    };
    const saveEdit = (operation: () => Promise<unknown>) => readOnly ? Promise.resolve(false) : withSaving(operation);
    return {
      onChangeName: (classId, name) => saveEdit(async () => {
        const updated = await api.updateClass(classId, { name });
        changeClass(classId, (item) => ({ ...item, name: updated.name }));
      }),
      onChangeKind: (classId, kind: ClassKind) => { void saveEdit(async () => {
        const updated = await api.updateClass(classId, { kind });
        changeClass(classId, (item) => ({ ...item, kind: updated.kind }));
      }); },
      onDeleteClass: (classId) => { void saveEdit(async () => {
        await api.deleteClass(classId);
        setNodes((current) => current.filter((node) => node.id !== String(classId)));
        setEdges((current) => current.filter((edge) => edge.source !== String(classId) && edge.target !== String(classId)));
        setSelectedRelation((current) => current?.source === classId || current?.target === classId ? null : current);
      }); },
      onResizeClass: (classId, width, height, x, y) => { void saveEdit(async () => {
        const updated = await api.updateClass(classId, { width, height, pos_x: x, pos_y: y });
        setNodes((current) => current.map((node) => node.id === String(classId)
          ? { ...node, position: { x: updated.pos_x, y: updated.pos_y }, style: { ...node.style, width: updated.width, height: updated.height },
            data: { ...node.data, umlClass: { ...node.data.umlClass, width: updated.width, height: updated.height, pos_x: updated.pos_x, pos_y: updated.pos_y } } }
          : node));
      }); },
      onAddAttribute: (classId) => { void saveEdit(async () => {
        const attribute = await api.createAttribute({ uml_class: classId });
        changeClass(classId, (item) => ({ ...item, attributes: [...item.attributes, attribute] }));
      }); },
      onUpdateAttribute: (classId, attributeId, patch: Partial<Attribute>) => { return saveEdit(async () => {
        const attribute = await api.updateAttribute(attributeId, patch);
        changeClass(classId, (item) => ({ ...item, attributes: item.attributes.map((value) => value.id === attributeId ? attribute : value) }));
      }); },
      onDeleteAttribute: (classId, attributeId) => { void saveEdit(async () => {
        await api.deleteAttribute(attributeId);
        changeClass(classId, (item) => ({ ...item, attributes: item.attributes.filter((value) => value.id !== attributeId) }));
      }); },
      onAddMethod: (classId) => { void saveEdit(async () => {
        const method = await api.createMethod({ uml_class: classId });
        changeClass(classId, (item) => ({ ...item, methods: [...item.methods, method] }));
      }); },
      onUpdateMethod: (classId, methodId, patch: Partial<Method>) => { return saveEdit(async () => {
        const method = await api.updateMethod(methodId, patch);
        changeClass(classId, (item) => ({ ...item, methods: item.methods.map((value) => value.id === methodId ? method : value) }));
      }); },
      onDeleteMethod: (classId, methodId) => { void saveEdit(async () => {
        await api.deleteMethod(methodId);
        changeClass(classId, (item) => ({ ...item, methods: item.methods.filter((value) => value.id !== methodId) }));
      }); },
    };
  }, [readOnly, setEdges, setNodes, withSaving]);

  const isEditing = () => interacting.current || Boolean(document.activeElement?.closest("input, textarea, select, [contenteditable='true']"));

  const refreshDiagram = useCallback(async (background = false) => {
    if (currentDiagramId === null) return;
    const requestId = ++refreshRequestId.current;
    const revision = mutationRevision.current;
    try {
      const full = await api.getDiagramFull(currentDiagramId);
      if (requestId !== refreshRequestId.current || (background && (pendingSaves.current > 0 || revision !== mutationRevision.current || isEditing()))) return;
      const nextReadOnly = !canEditDiagram(full.access_role);
      setDiagrams((current) => current.map((diagram) => diagram.id === full.id ? {
        ...diagram, name: full.name, project: full.project, access_role: full.access_role, updated_at: full.updated_at,
      } : diagram));
      setNodes((previous) => full.classes.map((item) => {
        const previousNode = previous.find((node) => node.id === String(item.id));
        return { ...previousNode, ...classToNode(item, actions, nextReadOnly), selected: previousNode?.selected };
      }));
      setEdges((previous) => full.relations.map((relation) => {
        const previousEdge = previous.find((edge) => edge.id === 'rel-' + relation.id);
        return { ...relationToEdge(relation, handleSelectRelation, { sourceHandle: previousEdge?.sourceHandle ?? getRelationHandles(relation, full.classes).sourceHandle, targetHandle: previousEdge?.targetHandle ?? getRelationHandles(relation, full.classes).targetHandle }), selected: previousEdge?.selected };
      }));
      setSelectedRelation((selected) => full.relations.find((relation) => relation.id === selected?.id) ?? null);
    } catch (err) {
      if (requestId !== refreshRequestId.current) return;
      console.error(err);
      setError(api.errorMessage(err, "No se pudo actualizar el diagrama. Comprueba tu conexi?n."));
    } finally {
      if (requestId === refreshRequestId.current) setLoading(false);
    }
  }, [currentDiagramId, setEdges, setNodes, handleSelectRelation, actions]);

  useEffect(() => {
    recoverDiagram.current = () => refreshDiagram();
  }, [refreshDiagram]);

  // A diagram change invalidates requests immediately, including on unmount.
  useEffect(() => {
    setLoading(currentDiagramId !== null);
    setSelectedRelation(null);
    setShareOpen(false);
    setHistoryOpen(false);
    void refreshDiagram();
    return () => { refreshRequestId.current += 1; };
  }, [currentDiagramId, refreshDiagram]);

  useEffect(() => {
    if (currentDiagramId === null) return;
    const timer = window.setInterval(() => {
      if (pendingSaves.current === 0 && !document.hidden && !isEditing()) void refreshDiagram(true);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [currentDiagramId, refreshDiagram]);

  const onNodesChangeHandler = useCallback(
    (changes: NodeChange[]) => {
      const allowedChanges = changes.filter((change) => change.type !== "remove" && (!readOnly || change.type === "select" || change.type === "dimensions"));
      for (const change of changes) {
        if (!readOnly && change.type === "remove") actions.onDeleteClass(Number(change.id));
      }
      if (changes.some((change) => change.type === "position" && change.dragging)) interacting.current = true;
      if (changes.some((change) => change.type === "dimensions" && change.resizing !== undefined)) {
        interacting.current = changes.some((change) => change.type === "dimensions" && change.resizing);
      }
      setNodes((nds) => applyNodeChanges(allowedChanges, nds));
    },
    [actions, readOnly, setNodes]
  );

  const onEdgesChangeHandler = useCallback(
    (changes: EdgeChange[]) => {
      const allowedChanges = readOnly ? changes.filter((change) => change.type === "select") : changes;
      setEdges((eds) => applyEdgeChanges(allowedChanges, eds));
    },
    [readOnly, setEdges]
  );

  const onNodeDragStop = useCallback(
    (_: unknown, node: Node<ClassNodeData>) => {
      interacting.current = false;
      if (readOnly) return;
      withSaving(() => api.updateClass(Number(node.id), { pos_x: node.position.x, pos_y: node.position.y }));
    },
    [readOnly, withSaving]
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (readOnly) return;
      pendingConnectionSource.current = null;
      if (!connection.source || !connection.target || !/^source-(top|right|bottom|left)$/.test(connection.sourceHandle ?? "") || !/^source-(top|right|bottom|left)$/.test(connection.targetHandle ?? "") || currentDiagramId === null) return;
      withSaving(async () => {
        const relation = await api.createRelation({
          diagram: currentDiagramId,
          source: Number(connection.source),
          target: Number(connection.target),
          relation_type: "ASSOCIATION",
        });
        setEdges((eds) => addEdge(relationToEdge(relation, handleSelectRelation, {
          sourceHandle: connection.sourceHandle ?? "source-right",
          targetHandle: connection.targetHandle ?? "source-left",
        }), eds));
      });
    },
    [currentDiagramId, readOnly, withSaving, setEdges, handleSelectRelation]
  );

  const onConnectStart = useCallback<OnConnectStart>(
    (_event, params) => {
      interacting.current = true;
      pendingConnectionSource.current = params.handleType === "source" ? params.nodeId : null;
    },
    []
  );

  const onConnectEnd = useCallback(() => {
    interacting.current = false;
    pendingConnectionSource.current = null;
  }, []);

  const handleAddClass = useCallback(() => {
    if (readOnly || currentDiagramId === null) return;
    const existingNames = new Set(nodes.map((node) => node.data.umlClass.name.toLowerCase()));
    let name = "NuevaClase";
    let suffix = 2;
    while (existingNames.has(name.toLowerCase())) name = `NuevaClase${suffix++}`;
    withSaving(async () => {
      const umlClass = await api.createClass({
        diagram: currentDiagramId,
        name,
        kind: "CLASS",
        pos_x: 120 + Math.random() * 200,
        pos_y: 120 + Math.random() * 200,
      });
      setNodes((nds) => [...nds, classToNode(umlClass, actions, readOnly)]);
    });
  }, [actions, currentDiagramId, nodes, readOnly, setNodes, withSaving]);

  const handleCreateDiagram = useCallback(() => {
    const projectName = window.prompt("Nombre del proyecto:");
    if (!projectName) return;
    const diagramName = window.prompt("Nombre del diagrama:", "Diagrama principal") ?? "Diagrama principal";
    withSaving(async () => {
      const project = await api.createProject(projectName);
      const diagram = await api.createDiagram(project.id, diagramName);
      setDiagrams((ds) => [...ds, diagram]);
      setCurrentDiagramId(diagram.id);
    });
  }, [withSaving]);

  const handleShareProject = useCallback(() => {
    if (currentDiagramId === null || !canShare) return;
    setShareOpen(true);
  }, [canShare, currentDiagramId]);

  const handleRelationChange = useCallback(
    (patch: Partial<Relation>) => {
      if (readOnly || !selectedRelation) return Promise.resolve(false);
      return withSaving(async () => {
        const updated = await api.updateRelation(selectedRelation.id, patch);
        setSelectedRelation((current) => current?.id === updated.id ? updated : current);
        setEdges((eds) => eds.map((edge) => edge.id === `rel-${updated.id}`
          ? { ...edge, data: { ...edge.data!, relation: updated } } : edge));
      });
    },
    [readOnly, selectedRelation, setEdges, withSaving]
  );

  const handleRelationDelete = useCallback(() => {
    if (readOnly || !selectedRelation) return;
    const relationId = selectedRelation.id;
    void withSaving(async () => {
      await api.deleteRelation(relationId);
      setEdges((eds) => eds.filter((e) => e.id !== `rel-${relationId}`));
      setSelectedRelation((current) => current?.id === relationId ? null : current);
    });
  }, [readOnly, selectedRelation, setEdges, withSaving]);

  const handleSaveAs = useCallback(() => {
    if (readOnly || currentDiagramId === null) return;
    const currentName = diagrams.find((d) => d.id === currentDiagramId)?.name ?? "Diagrama";
    const newName = window.prompt("Guardar como (nuevo nombre del diagrama):", `${currentName} (copia)`);
    if (!newName) return;
    withSaving(async () => {
      const newDiagram = await api.saveDiagramAs(currentDiagramId, newName);
      setDiagrams((ds) => [...ds, newDiagram]);
      setCurrentDiagramId(newDiagram.id);
    });
  }, [currentDiagramId, diagrams, readOnly, withSaving]);

  const handleExportXmi = useCallback(async () => {
    if (currentDiagramId === null) return;
    try {
    const blob = await api.downloadDiagramXmi(currentDiagramId);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    const diagramName = diagrams.find((diagram) => diagram.id === currentDiagramId)?.name ?? "diagrama";
    const safeName = diagramName.replace(/[^\p{L}\p{N}\-_ ]/gu, "_").trim() || "diagrama";
    link.download = `${safeName}.xmi`;
    link.click();
    URL.revokeObjectURL(url);
    } catch (err) {
      setError(api.errorMessage(err, "No se pudo exportar el diagrama XMI."));
    }
  }, [currentDiagramId, diagrams]);

  const handleExportEnterpriseArchitect = useCallback(async () => {
    if (currentDiagramId === null) return;
    try {
    const blob = await api.downloadDiagramEnterpriseArchitectJson(currentDiagramId);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "diagrama_enterprise_architect.json";
    link.click();
    URL.revokeObjectURL(url);
    } catch (err) {
      setError(api.errorMessage(err, "No se pudo exportar el diagrama para Enterprise Architect."));
    }
  }, [currentDiagramId]);

  const handleImportImage = useCallback(async (file: File) => {
    if (readOnly || currentDiagramId === null) return;
    if (!file.type.startsWith("image/")) {
      setError("Seleccioná un archivo de imagen PNG, JPG, WEBP o BMP.");
      return;
    }

    await withSaving(async () => {
      const detected = await api.importDiagramImage(currentDiagramId, file);
      const current = await api.getDiagramFull(currentDiagramId);
      const classesByName = new Map(current.classes.map((item) => [item.name.trim().toLowerCase(), item]));
      const importedClasses = new Map<string, UMLClass>();

      for (const [index, classSpec] of detected.classes.entries()) {
        const name = classSpec.name.trim() || `Clase${index + 1}`;
        const key = name.toLowerCase();
        let umlClass = classesByName.get(key);
        if (!umlClass) {
          umlClass = await api.createClass({
            diagram: currentDiagramId,
            name,
            kind: classSpec.kind ?? "CLASS",
            pos_x: classSpec.pos_x ?? 80 + (index % 4) * 300,
            pos_y: classSpec.pos_y ?? 80 + Math.floor(index / 4) * 240,
          });
          classesByName.set(key, umlClass);
          for (const attribute of classSpec.attributes ?? []) {
            await api.createAttribute({
              uml_class: umlClass.id,
              name: attribute.name || "atributo",
              data_type: attribute.type || "String",
              visibility: normalizeImportedVisibility(attribute.visibility),
              is_static: attribute.is_static ?? false,
              order: 0,
            });
          }
          for (const method of classSpec.methods ?? []) {
            await api.createMethod({
              uml_class: umlClass.id,
              name: method.name || "metodo",
              return_type: method.returnType || "void",
              visibility: normalizeImportedVisibility(method.visibility),
              parameters: normalizeMethodParameters(method.parameters),
              is_static: method.is_static ?? false,
              order: 0,
            });
          }
        }
        importedClasses.set(key, umlClass);
      }

      const existingRelations = new Set(current.relations.map((relation) => `${relation.source}:${relation.target}:${relation.relation_type}`));
      for (const relation of detected.relations) {
        const source = importedClasses.get(relation.from.trim().toLowerCase()) ?? classesByName.get(relation.from.trim().toLowerCase());
        const target = importedClasses.get(relation.to.trim().toLowerCase()) ?? classesByName.get(relation.to.trim().toLowerCase());
        if (!source || !target) continue;
        const relationType = normalizeImportedRelationType(relation.type);
        const relationKey = `${source.id}:${target.id}:${relationType}`;
        if (existingRelations.has(relationKey)) continue;
        await api.createRelation({
          diagram: currentDiagramId,
          source: source.id,
          target: target.id,
          relation_type: relationType,
          multiplicity_source: relation.sourceMultiplicity || "1",
          multiplicity_target: relation.targetMultiplicity || "1",
          label: relation.label || "",
        });
        existingRelations.add(relationKey);
      }

      const updated = await api.getDiagramFull(currentDiagramId);
      setNodes(updated.classes.map((item) => classToNode(item, actions, readOnly)));
      setEdges(updated.relations.map((item) => relationToEdge(item, handleSelectRelation, getRelationHandles(item, updated.classes))));
      setError(null);
    });
  }, [actions, currentDiagramId, handleSelectRelation, readOnly, setEdges, setNodes, withSaving]);

  const handleImportXmi = useCallback(async (file: File) => {
    if (readOnly || currentDiagramId === null) return;
    const lowerName = file.name.toLowerCase();
    if (!lowerName.endsWith(".xmi") && !lowerName.endsWith(".xml") && !lowerName.endsWith(".zip")) {
      setError("Seleccioná un archivo .xmi, .xml o .zip con XMI.");
      return;
    }

    await withSaving(async () => {
      const imported = await api.importDiagramXmi(currentDiagramId, file);
      setNodes(imported.classes.map((item) => classToNode(item, actions, readOnly)));
      setEdges(imported.relations.map((item) => relationToEdge(item, handleSelectRelation, getRelationHandles(item, imported.classes))));
      setError(null);
    });
  }, [actions, currentDiagramId, handleSelectRelation, readOnly, setEdges, setNodes, withSaving]);

  return (
    <div className="app-container">
      <Toolbar
        collapsed={controlsCollapsed}
        onTogglePanel={() => setControlsCollapsed((value) => !value)}
        exportingImage={exportingImage}
        onExportImage={(format) => {
          if (!canvasRef.current || exportingImage) return;
          setExportingImage(true); setError(null);
          void exportDiagram(canvasRef.current, nodes, currentDiagram?.name ?? "diagrama", format)
            .catch((cause: unknown) => setError(api.errorMessage(cause, "No se pudo exportar el diagrama.")))
            .finally(() => setExportingImage(false));
        }}
        diagrams={diagrams}
        currentDiagramId={currentDiagramId}
        onSelectDiagram={(id) => { if (pendingSaves.current === 0) setCurrentDiagramId(id); }}
        onCreateDiagram={handleCreateDiagram}
          onShareProject={handleShareProject}
          onHistory={() => setHistoryOpen(true)}
        onBackend={() => {
          if (currentDiagramId === null || loading) return;
          if (pendingSaves.current > 0) { setError("Espera a que termine el guardado antes de generar el backend."); return; }
          setBackendOpen(true);
        }}
        readOnly={readOnly || loading || saving}
        canShare={canShare}
        loading={loading}
        saveError={error !== null}
        onAddClass={handleAddClass}
        onSaveAs={handleSaveAs}
        onExportXmi={handleExportXmi}
        onExportEnterpriseArchitect={handleExportEnterpriseArchitect}
        onImportImage={handleImportImage}
        onImportXmi={handleImportXmi}
        saving={saving}
        assistantOpen={assistantOpen}
        onToggleAssistant={() => setAssistantOpen((value) => !value)}
        user={authUser}
        onLogout={onLogout}
      />

      {shareOpen && canShare && currentDiagram && (
        <ShareProjectDialog
          key={currentDiagram.project}
          projectId={currentDiagram.project}
          projectName={currentDiagram.name}
          accessRole={currentDiagram.access_role}
          onClose={() => setShareOpen(false)}
        />
      )}

      {backendOpen && <BackendDiagramDialog key={currentDiagramId} initialDiagramId={currentDiagramId} autoGenerate onClose={() => setBackendOpen(false)} />}

      {historyOpen && currentDiagramId !== null && (
        <VersionHistoryDialog
          key={currentDiagramId}
          diagramId={currentDiagramId}
          readOnly={readOnly}
          withSaving={withSaving}
          onClose={() => setHistoryOpen(false)}
          onRestored={() => void refreshDiagram()}
        />
      )}

      {error && <div className="app-error">{error}</div>}

      <div className="workspace-shell">
        <div className="canvas-wrapper" ref={canvasRef} tabIndex={0} aria-label="Lienzo UML. Enter elimina la clase o relación seleccionada."
          onKeyDown={(event) => {
            if (event.key !== "Enter" || event.repeat || event.nativeEvent.isComposing || readOnly || loading || pendingSaves.current > 0) return;
            if ((event.target as HTMLElement).closest("input, textarea, select, button, summary, [contenteditable='true']") || document.querySelector(".camera-backdrop, .share-backdrop")) return;
            if (selectedRelation) {
              event.preventDefault();
              event.stopPropagation();
              handleRelationDelete();
              return;
            }
            const selected = nodes.filter((node) => node.selected);
            if (selected.length !== 1) return;
            event.preventDefault(); actions.onDeleteClass(Number(selected[0].id));
          }}>
          <UMLMarkerDefs />
          {loading && (
            <div className="app-loading">Cargando diagrama...</div>
          )}
            <ReactFlow
              key={currentDiagramId}
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              onNodesChange={onNodesChangeHandler}
              onEdgesChange={onEdgesChangeHandler}
              onNodeDragStop={onNodeDragStop}
              onConnect={onConnect}
              onConnectStart={onConnectStart}
              onConnectEnd={onConnectEnd}
              onEdgeClick={(_event, edge) => {
                if (edge.data?.relation) handleSelectRelation(edge.data.relation);
              }}
              onPaneClick={() => setSelectedRelation(null)}
              nodesDraggable={!readOnly && !loading}
              nodesConnectable={!readOnly && !loading}
              deleteKeyCode={null}
              connectionMode={ConnectionMode.Loose}
              connectionRadius={20}
              connectOnClick={true}
              onNodeClick={(event) => {
                setSelectedRelation(null);
                if (!(event.target as HTMLElement).closest("input, textarea, select, button, summary")) canvasRef.current?.focus({ preventScroll: true });
              }}
              fitView
            >
              <Background />
              <Controls />
            </ReactFlow>

          {selectedRelation && (
            <RelationPanel
              key={selectedRelation.id}
              relation={selectedRelation}
              onChange={handleRelationChange}
              onDelete={handleRelationDelete}
              onClose={() => setSelectedRelation(null)}
              readOnly={readOnly}
            />
          )}
        </div>

        <AIAssistant
          key={currentDiagramId}
          isOpen={assistantOpen}
          onClose={() => setAssistantOpen(false)}
          currentDiagramId={currentDiagramId}
          onRefresh={() => { void refreshDiagram(); }}
          readOnly={readOnly || loading}
          withSaving={withSaving}
        />
      </div>
    </div>
  );
}
