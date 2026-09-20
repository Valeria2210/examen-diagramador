import { ChangeEvent, FormEvent, useEffect, useState } from "react";
import * as api from "../api";
import { normalizeMethodParameters } from "../importParameters";
import type { ImportedParameter } from "../importParameters";

type Message = {
  role: "assistant" | "user";
  text: string;
};

type AiClassSpec = {
  name: string;
  kind?: "CLASS" | "ABSTRACT" | "INTERFACE" | "ENUM";
  attributes?: Array<{ name: string; type?: string; visibility?: string; is_static?: boolean }>;
  methods?: Array<{ name: string; returnType?: string; visibility?: string; parameters?: ImportedParameter[]; is_static?: boolean }>;
};

type AiRelationSpec = {
  from: string;
  to: string;
  type?: string;
  sourceMultiplicity?: string;
  targetMultiplicity?: string;
  label?: string;
};

type AiDiagramSpec = {
  classes: AiClassSpec[];
  relations: AiRelationSpec[];
};

const quickActions = [
  "¿Cómo empiezo?",
  "Diseña un sistema de ventas",
  "Haz un diagrama de biblioteca",
  "Crea un sistema de ecommerce",
  "Relación Cliente con Pedido",
  "Crear diagrama desde voz",
];

function normalizeName(name: string): string {
  return name
    .trim()
    .toLocaleLowerCase()
    .replace(/\s+/g, " ")
    .replace(/[.,;:]+$/g, "");
}

function relationKey(sourceId: number, targetId: number, relationType: string): string {
  const endpoints = relationType === "ASSOCIATION"
    ? [sourceId, targetId].sort((a, b) => a - b)
    : [sourceId, targetId];
  return `${relationType}:${endpoints[0]}:${endpoints[1]}`;
}

function normalizeMultiplicity(value?: string): string {
  const normalized = (value ?? "1").trim().toLowerCase();
  if (["muchos", "muchas", "varios", "varias", "n", "m", "*"].includes(normalized)) return "*";
  if (["uno", "una"].includes(normalized)) return "1";
  return value?.trim() || "1";
}

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  }
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

function buildAssistantReply(input: string): string {
  const prompt = input.toLowerCase();

  if (prompt.includes("empiez") || prompt.includes("inicio") || prompt.includes("usar") || prompt.includes("ayuda")) {
    return "Claro. Primero creamos un proyecto y un diagrama; luego te ayudo a definir las clases y las relaciones. Cuando lo tengas listo, lo pulimos juntos en el canvas.";
  }

  if (prompt.includes("diagrama") || prompt.includes("crear diagrama") || prompt.includes("nuevo diagrama")) {
    return "Perfecto. Hacemos esto juntos: creás el proyecto, eliges el diagrama, y después te ayudo a diseñar cada clase con sus atributos y sus relaciones.";
  }

  if (prompt.includes("clase") || prompt.includes("agregar clase") || prompt.includes("nueva clase")) {
    return "Vamos con la clase. Se crea desde el botón + Clase y luego la personalizamos: nombre, tipo, atributos y métodos. Yo puedo ayudarte a decidir la estructura si me lo pides.";
  }

  if (prompt.includes("relaci") || prompt.includes("conectar") || prompt.includes("flecha")) {
    return "Sí, ese es el momento de conectar la idea. Arrastrás desde la clase origen hasta la destino y luego ajustamos la multiplicidad y el tipo de relación para que quede correcto.";
  }

  if (prompt.includes("guardar") || prompt.includes("export") || prompt.includes("xmi")) {
    return "Cuando estés satisfecho con el diseño, guardamos y exportamos. Si querés, te ayudo a dejarlo listo para compartir o para la siguiente etapa del proyecto.";
  }

  if (prompt.includes("atributo") || prompt.includes("método") || prompt.includes("metodo")) {
    return "Eso se hace dentro de cada clase: agregás atributos y métodos, definís visibilidad y tipos, y luego ajustás el detalle. Es muy rápido y queda ordenado.";
  }

  if (prompt.includes("arrastr") || prompt.includes("mover") || prompt.includes("drag")) {
    return "No pasa nada: arrastrás la clase por su encabezado y la dejamos en el lugar correcto. La app guarda la posición automáticamente para que no pierdas el trabajo.";
  }

  if (prompt.includes("voz") || prompt.includes("voice") || prompt.includes("dicta")) {
    return "Perfecto. Decime algo así: 'Diseña un sistema de ventas con Cliente, Pedido y Producto. Cliente realiza muchos pedidos. Pedido pertenece a un cliente. Producto está en muchos pedidos.'";
  }

  return "Claro, te ayudo. Si me describís el sistema en lenguaje natural, yo te lo convierto en un diagrama UML con clases y relaciones, y te dejo una propuesta lista para revisar.";
}

function normalizeClassKind(kind?: string): "CLASS" | "ABSTRACT" | "INTERFACE" | "ENUM" {
  const value = (kind ?? "CLASS").toUpperCase();
  if (value === "ABSTRACT") return "ABSTRACT";
  if (value === "INTERFACE") return "INTERFACE";
  if (value === "ENUM") return "ENUM";
  return "CLASS";
}

function normalizeVisibility(value?: string): "PUBLIC" | "PRIVATE" | "PROTECTED" | "PACKAGE" {
  const v = (value ?? "PRIVATE").toUpperCase();
  if (v === "PUBLIC" || v === "+" || v === "PUB") return "PUBLIC";
  if (v === "PROTECTED" || v === "#" || v === "PROT") return "PROTECTED";
  if (v === "PACKAGE" || v === "~" || v === "PACK") return "PACKAGE";
  return "PRIVATE";
}

function normalizeRelationType(type?: string): "ASSOCIATION" | "AGGREGATION" | "COMPOSITION" | "INHERITANCE" | "REALIZATION" | "DEPENDENCY" {
  const value = (type ?? "ASSOCIATION").toUpperCase();
  if (value.includes("HERIT")) return "INHERITANCE";
  if (value.includes("REALIZ")) return "REALIZATION";
  if (value.includes("AGGR")) return "AGGREGATION";
  if (value.includes("COMPOS")) return "COMPOSITION";
  if (value.includes("DEPEND")) return "DEPENDENCY";
  return "ASSOCIATION";
}

function extractClassNamesFromText(input: string): string[] {
  const ignoredNames = new Set(["Crea", "Crear", "Agrega", "Añade", "Haz", "Una", "Un", "La", "El", "Entre", "Relación", "Relacion", "Clase"]);
  const directMatches = (input.match(/\b[A-Z][A-Za-z0-9_]*\b/g) ?? []).filter((name) => !ignoredNames.has(name));
  const lowercaseSeeds = [
    "cliente",
    "pedido",
    "producto",
    "usuario",
    "cuenta",
    "factura",
    "orden",
    "detalle",
    "libro",
    "autor",
    "categoria",
    "carrito",
    "pago",
    "transaccion",
    "empleado",
    "departamento",
  ];

  const inferred = lowercaseSeeds.filter((seed) => input.toLowerCase().includes(seed));
  const combined = [...directMatches, ...inferred.map((value) => value.charAt(0).toUpperCase() + value.slice(1))];
  const unique = combined.filter((name, index, arr) => name && arr.indexOf(name) === index);
  return unique.slice(0, 8);
}

function buildLocalPrototype(input: string): AiDiagramSpec | null {
  const names = extractClassNamesFromText(input);
  if (names.length === 0) return null;
  const declaration = input.match(/(?:clase|interfaz|enum)\s+([A-Za-zÁÉÍÓÚÑáéíóúñ][\wÁÉÍÓÚÑáéíóúñ]*)(?:\s+con\s+(.+?))?(?:\.|$)/i);
  const declaredName = declaration?.[1];
  const attributeText = declaration?.[2];
  const declaredAttributes = attributeText
    ? attributeText.split(/,|\s+y\s+/i).map((part) => part.trim()).filter(Boolean).map((part) => {
        const [name, type = "String"] = part.split(/\s*:\s*/);
        return { name: name.trim(), type: type.trim(), visibility: "PRIVATE" };
      })
    : [];
  const normalizedNames = declaredName ? [declaredName, ...names.filter((name) => name !== declaredName)] : names;
  return {
    classes: normalizedNames.map((name, index) => ({ name, kind: "CLASS", attributes: index === 0 ? declaredAttributes : [], methods: [] })),
    relations: normalizedNames.slice(1).map((name, index) => ({
      from: normalizedNames[index],
      to: name,
      type: "ASSOCIATION",
      sourceMultiplicity: "1",
      targetMultiplicity: /muchos|muchas|varios|varias| muchos /i.test(input) ? "*" : "1",
      label: "relaciona",
    })),
  };
}

async function askClaudeForUml(description: string): Promise<AiDiagramSpec> {
  const payload = await api.interpretUml<AiDiagramSpec>(description);
  return {
    classes: Array.isArray(payload.classes) ? payload.classes : [],
    relations: Array.isArray(payload.relations) ? payload.relations : [],
  };
}

async function askBackendForXmi(file: File): Promise<AiDiagramSpec> {
  const payload = await api.interpretXmi<AiDiagramSpec>(file);
  const classes: unknown[] = Array.isArray(payload.classes) ? payload.classes : [];
  const relations: unknown[] = Array.isArray(payload.relations) ? payload.relations : [];
  return {
    classes: classes.map((raw) => {
      const item = raw as AiClassSpec;
      return {
        name: String(item?.name ?? "NuevaClase"),
        kind: normalizeClassKind(item?.kind),
        attributes: Array.isArray(item?.attributes) ? item.attributes : [],
        methods: Array.isArray(item?.methods) ? item.methods : [],
      };
    }),
    relations: relations.map((raw) => {
      const item = raw as AiRelationSpec;
      return ({
      from: String(item?.from ?? ""),
      to: String(item?.to ?? ""),
      type: normalizeRelationType(item?.type),
        sourceMultiplicity: item?.sourceMultiplicity ?? "1",
        targetMultiplicity: item?.targetMultiplicity ?? "1",
        label: item?.label ?? "",
      });
    }),
  };
}

function summarizeSpec(spec: AiDiagramSpec): string {
  const classesCount = spec.classes.length;
  const relationsCount = spec.relations.length;
  const names = spec.classes.map((cls) => cls.name).join(", ");
  return `He interpretado ${classesCount} clase(s) y ${relationsCount} relación(es): ${names || "sin clases"}.`;
}

export function AIAssistant({
  isOpen,
  onClose,
  currentDiagramId,
  onRefresh,
  readOnly,
  withSaving,
}: {
  isOpen: boolean;
  onClose: () => void;
  currentDiagramId: number | null;
  onRefresh: () => void;
  readOnly: boolean;
  withSaving: (operation: () => Promise<unknown>) => Promise<boolean>;
}) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Hola. Soy tu asistente para usar este diagramador UML. Puedo guiarte paso a paso o ayudarte a crear un diagrama a partir de voz o texto.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingSpec, setPendingSpec] = useState<AiDiagramSpec | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [xmiInputKey, setXmiInputKey] = useState(0);
  const [analysisLoading, setAnalysisLoading] = useState(false);

  const reviewDiagram = async () => {
    if (!currentDiagramId || analysisLoading) return;
    setAnalysisLoading(true);
    try {
      const analysis = await api.analyzeDiagram(currentDiagramId);
      const message = analysis.summary.total === 0
        ? "La revisión UML no encontró problemas en el diagrama."
        : `La revisión UML encontró ${analysis.summary.errors} error(es) y ${analysis.summary.warnings} advertencia(s): ${analysis.findings.map((item) => item.message).join(" ")}`;
      setMessages((current) => [...current, { role: "assistant", text: message }]);
    } catch (error) {
      const reason = error instanceof Error ? error.message : "No se pudo revisar el diagrama.";
      setMessages((current) => [...current, { role: "assistant", text: reason }]);
    } finally {
      setAnalysisLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && currentDiagramId) void reviewDiagram();
  }, [currentDiagramId, isOpen]);

  const parseNaturalCommand = (text: string): AiDiagramSpec | null => {
    const normalized = text.trim();
    if (!normalized) return null;

    const attributeCommand = normalized.match(/(?:agrega|añade|adiciona)\s+(?:el\s+)?(?:atributo\s+)?([\wáéíóúñ]+)(?:\s+de\s+tipo\s+([\w.[\]<>]+))?\s+a\s+(?:la\s+)?clase\s+([\wáéíóúñ]+)/i);
    if (attributeCommand) {
      const [, attributeName, attributeType, className] = attributeCommand;
      return {
        classes: [{
          name: className,
          kind: "CLASS",
          attributes: [{ name: attributeName, type: attributeType || "String", visibility: "PRIVATE" }],
          methods: [],
        }],
        relations: [],
      };
    }

    const classNames = extractClassNamesFromText(normalized);
    if (classNames.length === 0) return null;

    const declaration = normalized.match(/(?:clase|interfaz|enum)\s+([A-Za-zÁÉÍÓÚÑáéíóúñ][\wÁÉÍÓÚÑáéíóúñ]*)(?:\s+con\s+(.+?))?(?:\.|$)/i);
    const declarationAttributes = declaration?.[2]
      ? declaration[2].split(/,|\s+y\s+/i).map((part) => part.trim()).filter(Boolean).map((part) => {
          const [name, type = "String"] = part.split(/\s*:\s*/);
          return { name: name.trim(), type: type.trim(), visibility: "PRIVATE" };
        })
      : [];

    const relations: AiRelationSpec[] = [];
    const lower = normalized.toLowerCase();

    if (lower.includes(" tenga ") || lower.includes(" tiene ")) {
      const relationNames = extractClassNamesFromText(normalized);
      if (relationNames.length >= 2) {
        const hasMany = /muchos|muchas|varios|varias|\*/i.test(normalized);
        relations.push({
          from: relationNames[0],
          to: relationNames[1],
          type: "composition",
          sourceMultiplicity: "1",
          targetMultiplicity: hasMany ? "*" : "1",
          label: "tiene",
        });
      }
    }

    if (lower.includes("herencia") || lower.includes("hereda") || lower.includes("relaciona") || lower.includes("relación") || lower.includes("conecta") || lower.includes("tiene") || lower.includes("tenga") || lower.includes("pertenece") || lower.includes("realiza")) {
      const parts = normalized.split(/(?:herencia|hereda|entre|relaciona|relación|conecta|tiene|tenga|pertenece|realiza)/i);
      const lastPart = parts[parts.length - 1] ?? normalized;
      const relationNames = extractClassNamesFromText(lastPart).length >= 2
        ? extractClassNamesFromText(lastPart)
        : classNames;
      if (relationNames.length >= 2 && relations.length === 0) {
        const hasMany = /muchos|muchas|varios|varias|\*/i.test(lastPart);
        relations.push({
          from: relationNames[0],
          to: relationNames[1],
          type: lower.includes("herencia") || lower.includes("hereda") ? "inheritance" : "association",
          sourceMultiplicity: "1",
          targetMultiplicity: hasMany ? "*" : "1",
          label: lower.includes("tiene") || lower.includes("tenga") ? "tiene" : "relaciona",
        });
      }
    }

    if (classNames.length > 1 && relations.length === 0) {
      for (let index = 1; index < classNames.length; index += 1) {
        relations.push({ from: classNames[index - 1], to: classNames[index], type: "association", label: "relaciona" });
      }
    }

    return {
      classes: classNames.map((name) => ({
        name,
        kind: "CLASS",
        attributes: declaration?.[1] === name ? declarationAttributes : [],
        methods: [],
      })),
      relations,
    };
  };

  const isIncrementalCommand = (text: string): boolean => {
    const lower = text.trim().toLowerCase();
    return /^(agrega|añade|crea|crear|elimina|borra|relaciona|conecta|haz que|hace que)\b/.test(lower);
  };

  const applyGeneratedSpec = async (spec: AiDiagramSpec) => {
    if (loading) return;
    if (readOnly) {
      setMessages((current) => [...current, { role: "assistant", text: "Este proyecto está en modo solo lectura. Solicita permiso de edición para aplicar cambios." }]);
      setPendingSpec(null);
      return;
    }
    if (!currentDiagramId) {
      setMessages((current) => [...current, { role: "assistant", text: "Primero creá o seleccioná un diagrama para poder generar clases y relaciones." }]);
      return;
    }

    setLoading(true);
    const applied = await withSaving(async () => {
    const current = await api.getDiagramFull(currentDiagramId);
    const classesByName = new Map<string, typeof current.classes[number]>();
    for (const umlClass of current.classes) {
      const key = normalizeName(umlClass.name);
      if (!classesByName.has(key)) classesByName.set(key, umlClass);
    }
    const classesByRequestedName = new Map<string, number>();
    const existingRelationKeys = new Set(
      current.relations.map((relation) => relationKey(relation.source, relation.target, relation.relation_type))
    );
    let createdClasses = 0;
    let createdRelations = 0;

    for (const [classIndex, classItem] of spec.classes.entries()) {
      const className = classItem.name || "NuevaClase";
      const classKey = normalizeName(className);
      const existingClass = classesByName.get(classKey);
      const diagramClass = existingClass ?? await api.createClass({
          diagram: currentDiagramId,
          name: className,
          kind: normalizeClassKind(classItem.kind),
          pos_x: 80 + (classIndex % 4) * 300,
          pos_y: 80 + Math.floor(classIndex / 4) * 240,
        });

      if (!existingClass) {
        classesByName.set(classKey, diagramClass);
        createdClasses += 1;
      }
      classesByRequestedName.set(classKey, diagramClass.id);

      for (const attribute of classItem.attributes ?? []) {
        const attributeName = normalizeName(attribute.name || "atributo");
        const alreadyExists = diagramClass.attributes.some((item) => normalizeName(item.name) === attributeName);
        if (alreadyExists) continue;
        const createdAttribute = await api.createAttribute({
          uml_class: diagramClass.id,
          name: attribute.name || "atributo",
          data_type: attribute.type || "String",
          visibility: normalizeVisibility(attribute.visibility),
          is_static: attribute.is_static ?? false,
          order: diagramClass.attributes.length,
        });
        diagramClass.attributes.push(createdAttribute);
      }

      for (const method of classItem.methods ?? []) {
        const methodName = normalizeName(method.name || "metodo");
        const alreadyExists = diagramClass.methods.some((item) => normalizeName(item.name) === methodName);
        if (alreadyExists) continue;
        const createdMethod = await api.createMethod({
          uml_class: diagramClass.id,
          name: method.name || "metodo",
          return_type: method.returnType || "void",
          visibility: normalizeVisibility(method.visibility),
          parameters: normalizeMethodParameters(method.parameters),
          is_static: method.is_static ?? false,
          order: diagramClass.methods.length,
        });
        diagramClass.methods.push(createdMethod);
      }
    }

    for (const relation of spec.relations) {
      const sourceId = classesByRequestedName.get(normalizeName(relation.from)) ?? classesByName.get(normalizeName(relation.from))?.id;
      const targetId = classesByRequestedName.get(normalizeName(relation.to)) ?? classesByName.get(normalizeName(relation.to))?.id;
      if (!sourceId || !targetId) continue;

      const relationType = normalizeRelationType(relation.type);
      const key = relationKey(sourceId, targetId, relationType);
      if (existingRelationKeys.has(key)) continue;

      await api.createRelation({
        diagram: currentDiagramId,
        source: sourceId,
        target: targetId,
        relation_type: relationType,
        multiplicity_source: normalizeMultiplicity(relation.sourceMultiplicity),
        multiplicity_target: normalizeMultiplicity(relation.targetMultiplicity),
        label: relation.label || "",
      });
      existingRelationKeys.add(key);
      createdRelations += 1;
    }

    onRefresh();
    setPendingSpec(null);
    setMessages((current) => [...current, { role: "assistant", text: `Listo. Agregué ${createdClasses} clase(s) y ${createdRelations} relación(es), sin duplicar lo que ya existía.` }]);
    });
    if (!applied) setMessages((current) => [...current, { role: "assistant", text: "No se pudieron aplicar todos los cambios. Revisa el diagrama y el mensaje de error antes de reintentar." }]);
    setLoading(false);
  };

  const generateFromText = async (text: string) => {
    const cleanText = text.trim();
    if (!cleanText || loading) return;

    const nextUserMessage = { role: "user" as const, text: cleanText };
    setMessages((current) => [...current, nextUserMessage]);
    setInput("");
    setLoading(true);

    try {
      let spec: AiDiagramSpec | null = null;
      if (isIncrementalCommand(cleanText)) {
        spec = parseNaturalCommand(cleanText);
      }

      if (spec && spec.classes.length > 0) {
        setPendingSpec(spec);
        setMessages((current) => [
          ...current,
          { role: "assistant", text: `Perfecto, te lo preparo así: ${summarizeSpec(spec)}. ¿Te lo dejo en el diagrama?` },
        ]);
      } else {
        const claudeSpec = await askClaudeForUml(cleanText);
        setPendingSpec(claudeSpec);
        setMessages((current) => [...current, { role: "assistant", text: `${summarizeSpec(claudeSpec)} ¿Te lo dejo en el diagrama?` }]);
      }
    } catch (error) {
      const reason = api.errorMessage(error, "No se pudo interpretar la descripción.");
      const localPrototype = buildLocalPrototype(cleanText);
      if (localPrototype) {
        setPendingSpec(localPrototype);
        setMessages((current) => [...current, {
          role: "assistant",
          text: `Claude no está disponible: ${reason} Generé un prototipo local con las clases detectadas para que puedas revisarlo.`,
        }]);
      } else {
        setMessages((current) => [...current, { role: "assistant", text: `${reason} ${buildAssistantReply(cleanText)}` }]);
      }
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleXmiSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    setXmiInputKey((value) => value + 1);
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".xmi") && !file.name.toLowerCase().endsWith(".xml") && !file.name.toLowerCase().endsWith(".zip")) {
      setMessages((current) => [...current, { role: "assistant", text: "Elegí un archivo .xmi, .xml o .zip con XMI exportado desde Enterprise Architect." }]);
      return;
    }

    setMessages((current) => [...current, { role: "user", text: `Importar desde Enterprise Architect: ${file.name}` }]);
    setLoading(true);
    try {
      const spec = await askBackendForXmi(file);
      setPendingSpec(spec);
      setMessages((current) => [...current, { role: "assistant", text: `Leí el XMI de Enterprise Architect. ${summarizeSpec(spec)} Revisá la propuesta y confirmá si querés incorporarla al lienzo.` }]);
    } catch (error) {
      console.error(error);
      const reason = api.errorMessage(error, "No se pudo importar el archivo.");
      setMessages((current) => [...current, { role: "assistant", text: `No pude importar ese archivo. ${reason}` }]);
    } finally {
      setLoading(false);
    }
  };

  const startVoiceCapture = () => {
    const SpeechRecognitionCtor = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      setMessages((current) => [...current, { role: "assistant", text: "Tu navegador no soporta reconocimiento de voz. Podés escribir el texto manualmente en el campo." }]);
      return;
    }

    const recognition = new SpeechRecognitionCtor();
    recognition.lang = "es-ES";
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((entry) => entry[0]?.transcript ?? "")
        .join(" ")
        .trim();

      if (transcript) {
        setInput(transcript);
        void generateFromText(transcript);
      }
    };

    recognition.onerror = () => {
      setIsListening(false);
      setMessages((current) => [...current, { role: "assistant", text: "No pude entender el audio. Probá escribir la descripción o repetirla con más claridad." }]);
    };

    recognition.onend = () => setIsListening(false);

    setIsListening(true);
    recognition.start();
  };

  const handleSend = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void generateFromText(input);
  };

  if (!isOpen) return null;

  return (
    <aside className="ai-assistant">
      <div className="ai-assistant-header">
        <div>
          <div className="ai-assistant-title">Asistente IA</div>
          <div className="ai-assistant-subtitle">Diseña tu diagrama junto a mí</div>
        </div>
        <button className="ai-assistant-close" onClick={onClose} aria-label="Cerrar asistente">✕</button>
      </div>

      <div className="ai-assistant-actions">
        <label className="ai-assistant-chip ai-assistant-upload">
          📂 Importar desde Enterprise Architect
          <input
            key={xmiInputKey}
            type="file"
            accept=".xmi,.xml,.zip,application/xml,text/xml,application/zip"
            onChange={handleXmiSelected}
            disabled={loading || readOnly}
            aria-label="Importar diagrama desde archivo XMI de Enterprise Architect"
          />
        </label>
        {quickActions.map((action) => (
          <button key={action} className="ai-assistant-chip" onClick={() => {
            if (action === "Crear diagrama desde voz") {
              startVoiceCapture();
              return;
            }
            void generateFromText(action);
          }}>
            {action}
          </button>
        ))}
        <button className="ai-assistant-chip ai-assistant-mic" onClick={startVoiceCapture} disabled={loading}>
          {isListening ? "🎙️ Escuchando..." : "🎙️ Voz"}
        </button>
        <button className="ai-assistant-chip" onClick={() => void reviewDiagram()} disabled={analysisLoading || !currentDiagramId}>
          {analysisLoading ? "Revisando..." : "Revisar UML"}
        </button>
      </div>

      <div className="ai-assistant-chat">
        {messages.map((message, index) => (
          <div key={`${message.role}-${index}`} className={`ai-message ${message.role}`}>
            {message.text}
          </div>
        ))}
        {pendingSpec && (
          <div className="ai-confirm-box">
            <strong>Vista previa del diseño</strong>
            <div>{pendingSpec.classes.length} clases propuestas</div>
            <div>{pendingSpec.relations.length} relaciones sugeridas</div>
            <button disabled={loading || readOnly || currentDiagramId === null} className="ai-confirm-button" onClick={() => void applyGeneratedSpec(pendingSpec)}>
              Sí, créalo
            </button>
            <button className="ai-cancel-button" onClick={() => setPendingSpec(null)}>
              Ajustarlo
            </button>
          </div>
        )}
        {loading && <div className="ai-message assistant">Estoy interpretando tu idea para convertirla en clases y relaciones...</div>}
      </div>

      <form className="ai-assistant-form" onSubmit={handleSend}>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ej: Crea un sistema de ventas con Cliente y Pedido..."
          aria-label="Pregunta al asistente"
          disabled={loading}
        />
        <button type="submit" disabled={loading}>
          {loading ? "..." : "Enviar"}
        </button>
      </form>
    </aside>
  );
}
