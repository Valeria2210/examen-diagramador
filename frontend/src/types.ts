export type Visibility = "PUBLIC" | "PRIVATE" | "PROTECTED" | "PACKAGE";
export type AccessRole = "OWNER" | "ADMIN" | "EDITOR" | "SHARER" | "VIEWER";
export type ClassKind = "CLASS" | "ABSTRACT" | "INTERFACE" | "ENUM";
export type RelationType =
  | "ASSOCIATION"
  | "AGGREGATION"
  | "COMPOSITION"
  | "INHERITANCE"
  | "REALIZATION"
  | "DEPENDENCY";

export const VISIBILITY_SYMBOL: Record<Visibility, string> = {
  PUBLIC: "+",
  PRIVATE: "-",
  PROTECTED: "#",
  PACKAGE: "~",
};

export interface Attribute {
  es_pk?: boolean;
  es_unico?: boolean;
  nullable?: boolean;
  longitud?: number | null;
  id: number;
  uml_class: number;
  name: string;
  data_type: string;
  visibility: Visibility;
  is_static: boolean;
  order: number;
}

export interface MethodParam {
  name: string;
  type: string;
}

export interface Method {
  id: number;
  uml_class: number;
  name: string;
  return_type: string;
  visibility: Visibility;
  parameters: MethodParam[];
  is_static: boolean;
  order: number;
}

export interface UMLClass {
  id: number;
  diagram: number;
  name: string;
  kind: ClassKind;
  pos_x: number;
  pos_y: number;
  width: number;
  height: number;
  attributes: Attribute[];
  methods: Method[];
}

export interface Relation {
  nombre_campo_origen?: string;
  nombre_campo_destino?: string;
  id: number;
  diagram: number;
  source: number;
  target: number;
  relation_type: RelationType;
  multiplicity_source: string;
  multiplicity_target: string;
  label: string;
}

export interface DiagramSummary {
  id: number;
  project: number;
  name: string;
  created_at: string;
  updated_at: string;
  access_role?: AccessRole | null;
}

export interface DiagramFull extends DiagramSummary {
  classes: UMLClass[];
  relations: Relation[];
}

export interface Project {
  id: number;
  name: string;
  description: string;
  owner: number | null;
  created_at: string;
  updated_at: string;
}
