import { CommitInput } from "./CommitInput";
import type { Relation, RelationType } from "../types";

interface RelationPanelProps {
  relation: Relation;
  onChange: (patch: Partial<Relation>) => Promise<boolean>;
  onDelete: () => void;
  onClose: () => void;
  readOnly?: boolean;
}

const RELATION_LABELS: Record<RelationType, string> = {
  ASSOCIATION: "Asociación",
  AGGREGATION: "Agregación",
  COMPOSITION: "Composición",
  INHERITANCE: "Herencia",
  REALIZATION: "Realización",
  DEPENDENCY: "Dependencia",
};

export function RelationPanel({ relation, onChange, onDelete, onClose, readOnly = false }: RelationPanelProps) {
  return (
    <div className="relation-panel">
      <div className="relation-panel-header">
        <strong>{readOnly ? "Detalle de relación" : "Editar relación"}</strong>
        <button className="uml-icon-btn" aria-label="Cerrar panel de relación" onClick={onClose}>
          ✕
        </button>
      </div>

      <label>
        Tipo
        <select
          value={relation.relation_type}
          disabled={readOnly}
          onChange={(e) => onChange({ relation_type: e.target.value as RelationType })}
        >
          {Object.entries(RELATION_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

      <label>
        Multiplicidad origen
        <CommitInput
          value={relation.multiplicity_source}
          readOnly={readOnly}
          onCommit={(value) => onChange({ multiplicity_source: value })}
        />
      </label>

      <label>
        Multiplicidad destino
        <CommitInput
          value={relation.multiplicity_target}
          readOnly={readOnly}
          onCommit={(value) => onChange({ multiplicity_target: value })}
        />
      </label>

      <label>
        Campo en la clase origen
        <CommitInput readOnly={readOnly} value={relation.nombre_campo_origen ?? ""} onCommit={(value) => onChange({ nombre_campo_origen: value })} />
      </label>
      <label>
        Campo en la clase destino
        <CommitInput readOnly={readOnly} value={relation.nombre_campo_destino ?? ""} onCommit={(value) => onChange({ nombre_campo_destino: value })} />
      </label>
      <label>
        Etiqueta
        <CommitInput readOnly={readOnly} value={relation.label} onCommit={(value) => onChange({ label: value })} />
      </label>

      {relation.source === relation.target && relation.nombre_campo_origen === relation.nombre_campo_destino && <p role="alert">La autorrelación necesita campos distintos: jefe y subordinados, por ejemplo.</p>}

      <button className="uml-delete-btn" disabled={readOnly} onClick={onDelete}>
        Eliminar relación
      </button>
    </div>
  );
}
