import { CommitInput } from "./CommitInput";
import { memo } from "react";
import { Handle, NodeResizer, Position } from "reactflow";
import type { Attribute, ClassKind, Method, UMLClass, Visibility } from "../types";
import { VISIBILITY_SYMBOL } from "../types";

export interface ClassNodeActions {
  onChangeName: (classId: number, name: string) => Promise<boolean>;
  onChangeKind: (classId: number, kind: ClassKind) => void;
  onDeleteClass: (classId: number) => void;
  onResizeClass: (classId: number, width: number, height: number, x: number, y: number) => void;
  onAddAttribute: (classId: number) => void;
  onUpdateAttribute: (classId: number, attributeId: number, patch: Partial<Attribute>) => Promise<boolean>;
  onDeleteAttribute: (classId: number, attributeId: number) => void;
  onAddMethod: (classId: number) => void;
  onUpdateMethod: (classId: number, methodId: number, patch: Partial<Method>) => Promise<boolean>;
  onDeleteMethod: (classId: number, methodId: number) => void;
}

export interface ClassNodeData {
  umlClass: UMLClass;
  actions: ClassNodeActions;
  readOnly?: boolean;
}

const VISIBILITY_OPTIONS: Visibility[] = ["PUBLIC", "PRIVATE", "PROTECTED", "PACKAGE"];
const KIND_OPTIONS: ClassKind[] = ["CLASS", "ABSTRACT", "INTERFACE", "ENUM"];
const ATTRIBUTE_TYPES = ["String", "Integer", "Long", "BigDecimal", "Double", "Float", "Boolean", "LocalDate", "LocalDateTime", "UUID", "texto_largo"];

function ClassNodeComponent({ data, selected }: { data: ClassNodeData; selected: boolean }) {
  const { umlClass, actions, readOnly = false } = data;

  return (
    <div className="uml-class-node">
      <NodeResizer
        isVisible={selected && !readOnly}
        minWidth={180}
        minHeight={100}
        lineClassName="uml-resize-border"
        handleClassName="uml-resize-handle"
        onResizeEnd={(_, params) => actions.onResizeClass(umlClass.id, params.width, params.height, params.x, params.y)}
        lineStyle={{ borderColor: "var(--accent)", borderWidth: 2 }}
        handleStyle={{ width: 12, height: 12, borderRadius: 2, backgroundColor: "var(--accent)", border: "2px solid white", zIndex: 10 }}
      />
      {([Position.Top, Position.Right, Position.Bottom, Position.Left] as Position[]).map((position) => (
        <Handle
          key={`source-${position}`}
          type="source"
          isConnectable={!readOnly}
          title="Iniciar relación"
          position={position}
          id={`source-${position.toLowerCase()}`}
          className={`uml-handle uml-handle-source uml-handle-${position.toLowerCase()}`}
        />
      ))}

      <div className="uml-class-header">
        <select
          className="uml-kind-select"
          value={umlClass.kind}
          disabled={readOnly}
          onChange={(e) => actions.onChangeKind(umlClass.id, e.target.value as ClassKind)}
        >
          {KIND_OPTIONS.map((k) => (
            <option key={k} value={k}>
              {k === "CLASS" ? "Clase" : k === "ABSTRACT" ? "Abstracta" : k === "INTERFACE" ? "Interfaz" : "Enum"}
            </option>
          ))}
        </select>
        <CommitInput
          className="uml-class-name nodrag"
          value={umlClass.name}
          readOnly={readOnly}
          onCommit={(value) => actions.onChangeName(umlClass.id, value)}
        />
        <button className="uml-icon-btn nodrag" title="Eliminar clase" disabled={readOnly} onClick={() => actions.onDeleteClass(umlClass.id)}>
          ✕
        </button>
      </div>

      <div className="uml-class-body">
        <div className="uml-section">
          {umlClass.attributes.map((attr) => (
            <div className="uml-row nodrag" key={attr.id}>
              <select
                value={attr.visibility}
                disabled={readOnly}
                onChange={(e) =>
                  actions.onUpdateAttribute(umlClass.id, attr.id, { visibility: e.target.value as Visibility })
                }
              >
                {VISIBILITY_OPTIONS.map((v) => (
                  <option key={v} value={v}>
                    {VISIBILITY_SYMBOL[v]}
                  </option>
                ))}
              </select>
              <CommitInput
                className="uml-input-name"
                value={attr.name}
                readOnly={readOnly}
                onCommit={(value) => actions.onUpdateAttribute(umlClass.id, attr.id, { name: value })}
              />
              <span>:</span>
              <select className="uml-attribute-type" aria-label={`Tipo de dato de ${attr.name}`}
                value={attr.data_type} disabled={readOnly}
                onChange={(event) => void actions.onUpdateAttribute(umlClass.id, attr.id, { data_type: event.target.value })}>
                {!ATTRIBUTE_TYPES.includes(attr.data_type) && <option value={attr.data_type}>{attr.data_type}</option>}
                {ATTRIBUTE_TYPES.map((type) => <option key={type} value={type}>{type === "texto_largo" ? "Texto largo" : type}</option>)}
              </select>
              <button className="uml-icon-btn" disabled={readOnly} onClick={() => actions.onDeleteAttribute(umlClass.id, attr.id)}>✕</button>
              <details className="uml-persistence-options">
              <summary>Persistencia{attr.es_pk ? " · PK" : ""}</summary>
              <CommitInput className="uml-input-type" value={attr.longitud?.toString() ?? ""} readOnly={readOnly}
                placeholder="Longitud" onCommit={(value) => {
                  if (value !== "" && (!/^\d+$/.test(value) || Number(value) < 1)) return Promise.resolve(false);
                  return actions.onUpdateAttribute(umlClass.id, attr.id, { longitud: value === "" ? null : Number(value) });
                }} />
              <label title="Clave primaria"><input type="checkbox" checked={attr.es_pk ?? false} disabled={readOnly}
                onChange={(e) => void actions.onUpdateAttribute(umlClass.id, attr.id, { es_pk: e.target.checked })} />PK</label>
              <label title="Valor único"><input type="checkbox" checked={attr.es_unico ?? false} disabled={readOnly}
                onChange={(e) => void actions.onUpdateAttribute(umlClass.id, attr.id, { es_unico: e.target.checked })} />Único</label>
              <label title="Permitir nulos"><input type="checkbox" checked={attr.nullable ?? true} disabled={readOnly}
                onChange={(e) => void actions.onUpdateAttribute(umlClass.id, attr.id, { nullable: e.target.checked })} />Nulo</label>
              </details>
            </div>
          ))}
          <button className="uml-add-btn nodrag" disabled={readOnly} onClick={() => actions.onAddAttribute(umlClass.id)}>
            + atributo
          </button>
        </div>

        <div className="uml-section">
          {umlClass.methods.map((m) => (
            <div className="uml-row nodrag" key={m.id}>
              <select
                value={m.visibility}
                disabled={readOnly}
                onChange={(e) => actions.onUpdateMethod(umlClass.id, m.id, { visibility: e.target.value as Visibility })}
              >
                {VISIBILITY_OPTIONS.map((v) => (
                  <option key={v} value={v}>
                    {VISIBILITY_SYMBOL[v]}
                  </option>
                ))}
              </select>
              <CommitInput
                className="uml-input-name"
                value={m.name}
                readOnly={readOnly}
                onCommit={(value) => actions.onUpdateMethod(umlClass.id, m.id, { name: value })}
              />
              <span>():</span>
              <CommitInput
                className="uml-input-type"
                value={m.return_type}
                readOnly={readOnly}
                onCommit={(value) => actions.onUpdateMethod(umlClass.id, m.id, { return_type: value })}
              />
              <button className="uml-icon-btn" disabled={readOnly} onClick={() => actions.onDeleteMethod(umlClass.id, m.id)}>
                ✕
              </button>
            </div>
          ))}
          <button className="uml-add-btn nodrag" disabled={readOnly} onClick={() => actions.onAddMethod(umlClass.id)}>
            + método
          </button>
        </div>
      </div>
    </div>
  );
}

export const ClassNode = memo(ClassNodeComponent);
