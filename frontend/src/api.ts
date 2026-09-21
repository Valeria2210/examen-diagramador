import axios from "axios";
import type { ImportedParameter } from "./importParameters";
import type {
  Attribute,
  DiagramFull,
  DiagramSummary,
  Method,
  Project,
  Relation,
  UMLClass,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api";

const http = axios.create({ baseURL: BASE_URL });

export type BackendGeneration = {
  avisos?: string[];
  sha256: string; tamano_bytes: number; expira_en: string;
  mensaje: string; estado: string; backend_ejecutable: boolean;
  compilacion: string;
  metricas: { alcance: string; entidades: number; relaciones: number; relaciones_por_tipo: Record<string, number>; archivos_java: number; lineas_java: number;
    duracion_generacion_ms: number; entidades_por_segundo: number; ir_validado: boolean;
    duracion_total_ms: number;
    compilacion: string; endpoints_documentados: number };
  generacion_id: string; zip_url: string; entidades_generadas: string[];
};

export async function validateBackend(diagrama_id: number, completar_pk = true, autocorregir = true): Promise<unknown> {
  const { data } = await http.post("/generador/validar/", { diagrama_id, completar_pk, autocorregir });
  return data.ir;
}

export async function prepareBackend(diagrama_id: number, incluir_swagger: boolean, incluir_docker: boolean, alcance: "entidades" | "completo" = "completo", completar_pk = true, autocorregir = true): Promise<BackendGeneration> {
  const { data } = await http.post<BackendGeneration>("/generar-backend/", { diagrama_id, incluir_swagger, incluir_docker, alcance, completar_pk, autocorregir }, { timeout: 120000 });
  return data;
}

export type FlutterGeneration = {
  sha256: string; tamano_bytes: number; expira_en: string;
  mensaje: string; estado: "FLUTTER_GENERADO"; compilacion: string;
  generacion_id: string; backend_generacion_id: string; zip_url: string;
  entidades_generadas: string[];
  metricas: { producto: "flutter"; entidades: number; archivos_flutter: number;
    ia_local: boolean; backend_generacion_id: string; ir_validado: boolean;
    compilacion: string; duracion_total_ms: number };
};

export async function prepareFlutter(diagrama_id: number, api_base_url: string, incluir_ia_local = true): Promise<FlutterGeneration> {
  const { data } = await http.post<FlutterGeneration>("/generador/generar-flutter/",
    { diagrama_id, api_base_url, incluir_ia_local }, { timeout: 120000 });
  return data;
}

export async function downloadFlutter(generation: FlutterGeneration): Promise<void> {
  return downloadBackend(generation as unknown as BackendGeneration);
}

export async function downloadBackend(generation: BackendGeneration): Promise<void> {
  // Use our API origin and Token interceptor rather than navigating to an unauthenticated URL.
  const segments = new URL(generation.zip_url).pathname.split("/").filter(Boolean);
  const filename = segments[segments.length - 1];
  if (!filename || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\.zip$/.test(filename)) throw new Error("Nombre de descarga inválido.");
  let data: Blob;
  try {
    const response = await http.get<Blob>(`/generador/descargar/${filename}/`, { responseType: "blob", timeout: 120000 });
    data = response.data;
  } catch (cause: unknown) {
    if (axios.isAxiosError(cause) && cause.response?.data instanceof Blob) {
      try { cause.response.data = JSON.parse(await cause.response.data.text()); } catch { /* Keep the safe fallback. */ }
    }
    throw cause;
  }
  if (data.size !== generation.tamano_bytes) throw new Error("El ZIP está incompleto. Reintenta la descarga.");
  const digest = await crypto.subtle.digest("SHA-256", await data.arrayBuffer());
  const hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  if (hash !== generation.sha256) throw new Error("La integridad del ZIP no coincide. Genera el backend nuevamente.");
  const url = URL.createObjectURL(data);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = filename;
  document.body.appendChild(anchor); anchor.click(); anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export type AuthUser = {
  id: number;
  username: string;
  email: string;
  is_staff?: boolean;
  is_superuser?: boolean;
};
export type AuthResponse = { token: string; user: AuthUser };
export const AUTH_EXPIRED_EVENT = "uml-auth-expired";

export type AdminUserData = {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  is_superuser: boolean;
  date_joined: string | null;
  projects_count: number;
};

export type AdminStatsData = {
  stats: {
    total_users: number;
    total_projects: number;
    total_diagrams: number;
    total_classes: number;
    gemini_model: string;
  };
  users: AdminUserData[];
};

export async function fetchAdminStats(): Promise<AdminStatsData> {
  const { data } = await http.get<AdminStatsData>("/admin/stats/");
  return data;
}

export async function createAdminUser(payload: {
  username: string;
  email?: string;
  password: string;
  is_staff?: boolean;
}): Promise<AdminUserData> {
  const { data } = await http.post<AdminUserData>("/admin/users/", payload);
  return data;
}

export async function deleteAdminUser(userId: number): Promise<void> {
  await http.delete(`/admin/users/${userId}/`);
}

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("uml-auth-token");
  if (token) config.headers.Authorization = `Token ${token}`;
  return config;
});

http.interceptors.response.use(undefined, (error: unknown) => {
  if (axios.isAxiosError(error) && error.response?.status === 401) {
    const token = localStorage.getItem("uml-auth-token");
    if (token && error.config?.headers.Authorization === `Token ${token}`) {
      localStorage.removeItem("uml-auth-token");
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
  }
  return Promise.reject(error);
});

export function errorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) return error instanceof Error ? error.message : fallback;
  const messages = (value: unknown): string[] => {
    if (typeof value === "string") return [value];
    if (Array.isArray(value)) return value.flatMap(messages);
    if (value && typeof value === "object") return Object.values(value).flatMap(messages);
    return [];
  };
  // An HTML server error must never replace the user-facing message.
  const data: unknown = error.response?.data;
  return data && typeof data === "object" ? messages(data).join(" ") || fallback : fallback;
}

export function getAuthHeaders(): HeadersInit {
  const token = localStorage.getItem("uml-auth-token");
  return token ? { Authorization: `Token ${token}` } : {};
}

export async function interpretUml<T>(description: string): Promise<T> {
  const { data } = await http.post<T>("/ai/interpret-uml/", { description });
  return data;
}

export async function interpretXmi<T>(file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await http.post<T>("/ai/import-xmi/", formData);
  return data;
}

export async function register(username: string, email: string, password: string): Promise<AuthResponse> {
  const { data } = await http.post<AuthResponse>("/auth/register/", { username, email, password });
  return data;
}

export async function login(username: string, password: string): Promise<AuthResponse> {
  const { data } = await http.post<AuthResponse>("/auth/login/", { username, password });
  return data;
}

export async function logout(): Promise<void> {
  await http.post("/auth/logout/");
}

export async function getCurrentUser(): Promise<AuthUser> {
  const { data } = await http.get<AuthUser>("/auth/me/");
  return data;
}

// ---- Proyectos y diagramas ----
export async function listDiagrams(): Promise<DiagramSummary[]> {
  const diagrams: DiagramSummary[] = [];
  let next: string | null = "/diagrams/";
  const visited = new Set<string>();
  while (next) {
    if (visited.has(next)) throw new Error("La paginación de diagramas contiene un ciclo.");
    visited.add(next);
    const { data }: { data: { results: DiagramSummary[]; next?: string | null } | DiagramSummary[] } = await http.get(next);
    diagrams.push(...(Array.isArray(data) ? data : data.results));
    // Retain our configured API origin; only use the server's next-page query.
    const nextPage: string | null = Array.isArray(data) ? null : data.next ?? null;
    next = nextPage ? `/diagrams/${new URL(nextPage, window.location.origin).search}` : null;
  }
  return diagrams;
}

export async function getDiagramFull(id: number): Promise<DiagramFull> {
  const { data } = await http.get<DiagramFull>(`/diagrams/${id}/full/`);
  return data;
}

export type DiagramVersion = {
  id: number;
  version_number: number;
  label: string;
  created_at: string;
  created_by: string | null;
};

export async function listDiagramVersions(id: number): Promise<DiagramVersion[]> {
  const { data } = await http.get<DiagramVersion[]>(`/diagrams/${id}/versions/`);
  return data;
}

export async function createDiagramVersion(id: number, label: string): Promise<DiagramVersion> {
  const { data } = await http.post<DiagramVersion>(`/diagrams/${id}/versions/`, { label });
  return data;
}

export async function restoreDiagramVersion(id: number, versionId: number): Promise<void> {
  await http.post(`/diagrams/${id}/restore_version/`, { version_id: versionId });
}

export type DiagramFinding = {
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  class_id?: number;
  class_ids?: number[];
  attribute_id?: number;
  relation_id?: number;
};

export type DiagramAnalysis = {
  diagram_id: number;
  findings: DiagramFinding[];
  summary: { errors: number; warnings: number; total: number };
};

export async function analyzeDiagram(id: number): Promise<DiagramAnalysis> {
  const { data } = await http.get<DiagramAnalysis>(`/diagrams/${id}/analyze/`);
  return data;
}

export async function createProject(name: string): Promise<Project> {
  const { data } = await http.post<Project>("/projects/", { name, description: "" });
  return data;
}

export async function createDiagram(projectId: number, name: string): Promise<DiagramSummary> {
  const { data } = await http.post<DiagramSummary>("/diagrams/", { project: projectId, name });
  return data;
}

export type ProjectShare = {
  token: string;
  role: "VIEWER" | "EDITOR" | "SHARER" | "ADMIN";
  active: boolean;
  created_at?: string;
  project?: number;
};

export async function createProjectShare(projectId: number, role: ProjectShare["role"]): Promise<ProjectShare> {
  const { data } = await http.post<ProjectShare>(`/projects/${projectId}/share/`, { role });
  return data;
}

export async function listProjectShares(projectId: number): Promise<ProjectShare[]> {
  const { data } = await http.get<ProjectShare[]>(`/projects/${projectId}/shares/`);
  return data;
}

export async function revokeProjectShare(projectId: number, token: string): Promise<void> {
  await http.post(`/projects/${projectId}/revoke_share/`, { token });
}

export async function acceptProjectShare(token: string): Promise<{ project: number; project_name: string; role: ProjectShare["role"] }> {
  const { data } = await http.post(`/shares/${token}/accept/`);
  return data;
}

// ---- Clases ----
export async function createClass(payload: {
  diagram: number;
  name: string;
  kind: UMLClass["kind"];
  pos_x: number;
  pos_y: number;
}): Promise<UMLClass> {
  const { data } = await http.post<UMLClass>("/classes/", payload);
  return { ...data, attributes: data.attributes ?? [], methods: data.methods ?? [] };
}

export async function updateClass(id: number, patch: Partial<UMLClass>): Promise<UMLClass> {
  const { data } = await http.patch<UMLClass>(`/classes/${id}/`, patch);
  return data;
}

export async function deleteClass(id: number): Promise<void> {
  await http.delete(`/classes/${id}/`);
}

// ---- Atributos ----
export async function createAttribute(payload: Partial<Attribute> & { uml_class: number }): Promise<Attribute> {
  const { data } = await http.post<Attribute>("/attributes/", {
    name: "atributo",
    data_type: "String",
    visibility: "PRIVATE",
    is_static: false,
    order: 0,
    ...payload,
  });
  return data;
}

export async function updateAttribute(id: number, patch: Partial<Attribute>): Promise<Attribute> {
  const { data } = await http.patch<Attribute>(`/attributes/${id}/`, patch);
  return data;
}

export async function deleteAttribute(id: number): Promise<void> {
  await http.delete(`/attributes/${id}/`);
}

// ---- Métodos ----
export async function createMethod(payload: Partial<Method> & { uml_class: number }): Promise<Method> {
  const { data } = await http.post<Method>("/methods/", {
    name: "metodo",
    return_type: "void",
    visibility: "PUBLIC",
    parameters: [],
    is_static: false,
    order: 0,
    ...payload,
  });
  return data;
}

export async function updateMethod(id: number, patch: Partial<Method>): Promise<Method> {
  const { data } = await http.patch<Method>(`/methods/${id}/`, patch);
  return data;
}

export async function deleteMethod(id: number): Promise<void> {
  await http.delete(`/methods/${id}/`);
}

export async function saveDiagramAs(id: number, name: string): Promise<DiagramFull> {
  const { data } = await http.post<DiagramFull>(`/diagrams/${id}/save_as/`, { name });
  return data;
}

export async function downloadDiagramXmi(id: number): Promise<Blob> {
  const { data } = await http.get<Blob>(`/diagrams/${id}/export_xmi/`, { responseType: "blob" });
  return data;
}

export async function downloadDiagramEnterpriseArchitectJson(id: number): Promise<Blob> {
  const { data } = await http.get<Blob>(`/diagrams/${id}/export_ea_json/`, { responseType: "blob" });
  return data;
}

export type ImageImportClass = {
  name: string;
  kind?: UMLClass["kind"];
  attributes?: Array<{ name: string; type?: string; visibility?: string; is_static?: boolean }>;
  methods?: Array<{ name: string; returnType?: string; visibility?: string; parameters?: ImportedParameter[]; is_static?: boolean }>;
  pos_x?: number;
  pos_y?: number;
};

export type ImageImportSpec = {
  classes: ImageImportClass[];
  relations: Array<{
    from: string;
    to: string;
    type?: string;
    sourceMultiplicity?: string;
    targetMultiplicity?: string;
    label?: string;
  }>;
};

export async function importDiagramImage(id: number, file: File): Promise<ImageImportSpec> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await http.post<ImageImportSpec>(`/diagrams/${id}/import_image/`, formData);
  return data;
}

export async function importDiagramXmi(id: number, file: File): Promise<DiagramFull> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await http.post<DiagramFull>(`/diagrams/${id}/import_xmi/`, formData);
  return data;
}

export async function createRelation(payload: {
  diagram: number;
  source: number;
  target: number;
  relation_type: Relation["relation_type"];
  multiplicity_source?: string;
  multiplicity_target?: string;
  label?: string;
}): Promise<Relation> {
  const { data } = await http.post<Relation>("/relations/", {
    multiplicity_source: "1",
    multiplicity_target: "1",
    label: "",
    ...payload,
  });
  return data;
}

export async function updateRelation(id: number, patch: Partial<Relation>): Promise<Relation> {
  const { data } = await http.patch<Relation>(`/relations/${id}/`, patch);
  return data;
}

export async function deleteRelation(id: number): Promise<void> {
  await http.delete(`/relations/${id}/`);
}
