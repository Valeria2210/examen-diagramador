import type { MethodParam } from "./types";

export type ImportedParameter = string | MethodParam;

export function normalizeMethodParameters(parameters: ImportedParameter[] = []): MethodParam[] {
  return parameters.map((parameter) => {
    if (typeof parameter !== "string") {
      return { name: parameter.name.trim() || "param", type: parameter.type?.trim() || "String" };
    }
    const separator = parameter.indexOf(":");
    if (separator >= 0) {
      return { name: parameter.slice(0, separator).trim() || "param", type: parameter.slice(separator + 1).trim() || "String" };
    }
    // Older imports use "Type name"; preserve the complete type, including spaces.
    const legacy = parameter.trim().match(/^(.*?)\s+([\w$]+)$/);
    return legacy ? { name: legacy[2], type: legacy[1] } : { name: parameter.trim() || "param", type: "String" };
  });
}
