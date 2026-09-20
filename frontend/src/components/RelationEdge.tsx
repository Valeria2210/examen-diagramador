import { BaseEdge, EdgeLabelRenderer, EdgeProps, getBezierPath } from "reactflow";
import type { Relation } from "../types";

export interface RelationEdgeData {
  relation: Relation;
  onSelectRelation: (relation: Relation) => void;
}

const MARKER_BY_TYPE: Record<Relation["relation_type"], string> = {
  ASSOCIATION: "url(#arrow-open)",
  AGGREGATION: "url(#diamond-open)",
  COMPOSITION: "url(#diamond-filled)",
  INHERITANCE: "url(#triangle-hollow)",
  REALIZATION: "url(#triangle-hollow)",
  DEPENDENCY: "url(#arrow-open)",
};

const DASHED_TYPES: Relation["relation_type"][] = ["REALIZATION", "DEPENDENCY"];

export function RelationEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<RelationEdgeData>) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  if (!data) return null;
  const { relation, onSelectRelation } = data;
  const isDashed = DASHED_TYPES.includes(relation.relation_type);

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={MARKER_BY_TYPE[relation.relation_type]}
        style={{ strokeWidth: 1.5, strokeDasharray: isDashed ? "6 4" : undefined, cursor: "pointer" }}
        interactionWidth={20}
      />
      <EdgeLabelRenderer>
        <div
          className="uml-edge-label nodrag nopan"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
          }}
          onClick={() => onSelectRelation(relation)}
        >
          <span className="uml-edge-mult">{relation.multiplicity_source}</span>
          <span className="uml-edge-type">{relation.label || relation.relation_type}</span>
          <span className="uml-edge-mult">{relation.multiplicity_target}</span>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

/** Definiciones SVG de marcadores UML, se montan una sola vez en App */
export function UMLMarkerDefs() {
  return (
    <svg data-uml-markers style={{ position: "absolute", width: 0, height: 0 }}>
      <defs>
        <marker id="arrow-open" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10" fill="none" stroke="#171717" strokeWidth="1.5" />
        </marker>
        <marker id="triangle-hollow" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" orient="auto-start-reverse">
          <path d="M 0 0 L 12 6 L 0 12 Z" fill="white" stroke="#171717" strokeWidth="1.5" />
        </marker>
        <marker id="diamond-open" viewBox="0 0 14 10" refX="13" refY="5" markerWidth="14" markerHeight="10" orient="auto-start-reverse">
          <path d="M 0 5 L 7 0 L 14 5 L 7 10 Z" fill="white" stroke="#171717" strokeWidth="1.5" />
        </marker>
        <marker id="diamond-filled" viewBox="0 0 14 10" refX="13" refY="5" markerWidth="14" markerHeight="10" orient="auto-start-reverse">
          <path d="M 0 5 L 7 0 L 14 5 L 7 10 Z" fill="#171717" stroke="#171717" strokeWidth="1.5" />
        </marker>
      </defs>
    </svg>
  );
}
