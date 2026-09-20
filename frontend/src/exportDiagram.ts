import { toCanvas } from "html-to-image";
import { getRectOfNodes, type Node } from "reactflow";

export async function exportDiagram(canvas: HTMLElement, nodes: Node[], name: string, format: "png" | "jpg") {
  const viewport = canvas.querySelector<HTMLElement>(".react-flow__viewport");
  if (!viewport || nodes.length === 0) throw new Error("Agrega una clase antes de exportar el diagrama.");
  await document.fonts.ready;
  const bounds = getRectOfNodes(nodes);
  for (const path of viewport.querySelectorAll<SVGGraphicsElement>(".react-flow__edge-path")) {
    const box = path.getBBox();
    const right = Math.max(bounds.x + bounds.width, box.x + box.width);
    const bottom = Math.max(bounds.y + bounds.height, box.y + box.height);
    bounds.x = Math.min(bounds.x, box.x); bounds.y = Math.min(bounds.y, box.y);
    bounds.width = right - bounds.x; bounds.height = bottom - bounds.y;
  }
  const padding = 80;
  const scale = Math.min(1, 4000 / (bounds.width + padding * 2), 4000 / (bounds.height + padding * 2));
  const width = Math.ceil((bounds.width + padding * 2) * scale);
  const height = Math.ceil((bounds.height + padding * 2) * scale);
  // Render edges as a standalone SVG: nested SVGs inside a foreignObject can
  // lose their percentage dimensions, inherited colors and marker references.
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.setAttribute("viewBox", `${bounds.x - padding} ${bounds.y - padding} ${width / scale} ${height / scale}`);
  const defs = canvas.querySelector("svg[data-uml-markers] defs");
  if (defs) svg.appendChild(defs.cloneNode(true));
  for (const path of viewport.querySelectorAll<SVGPathElement>(".react-flow__edge-path")) {
    const clone = path.cloneNode(true) as SVGPathElement;
    const style = getComputedStyle(path);
    clone.removeAttribute("class");
    clone.removeAttribute("style");
    clone.setAttribute("stroke", "#171717");
    clone.setAttribute("stroke-width", style.strokeWidth || "1.5");
    clone.setAttribute("stroke-dasharray", style.strokeDasharray || "none");
    clone.setAttribute("fill", "none");
    clone.setAttribute("opacity", "1");
    for (const attr of ["marker-start", "marker-end"]) {
      const reference = path.getAttribute(attr)?.match(/#([^)'"\s]+)/)?.[1];
      if (reference) clone.setAttribute(attr, `url(#${reference})`);
    }
    svg.appendChild(clone);
  }
    const options = { backgroundColor: "transparent", width, height, pixelRatio: 1,
      style: { width: `${width}px`, height: `${height}px`, transformOrigin: "0 0",
        transform: `translate(${(-bounds.x + padding) * scale}px, ${(-bounds.y + padding) * scale}px) scale(${scale})` },
      filter: (node: HTMLElement) => !node.classList?.contains("react-flow__handle")
        && !node.classList?.contains("react-flow__resize-control")
        && !node.classList?.contains("react-flow__edges") && node.tagName !== "BUTTON",
    };
    const nodesCanvas = await toCanvas(viewport, options);
    const output = document.createElement("canvas");
    output.width = width; output.height = height;
    const context = output.getContext("2d");
    if (!context) throw new Error("No se pudo crear la imagen del diagrama.");
    const edgesImage = new Image();
    await new Promise<void>((resolve, reject) => {
      edgesImage.onload = () => resolve();
      edgesImage.onerror = () => reject(new Error("No se pudieron exportar las relaciones."));
      edgesImage.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(svg))}`;
    });
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, width, height);
    context.drawImage(edgesImage, 0, 0, width, height);
    context.drawImage(nodesCanvas, 0, 0);
    const url = output.toDataURL(format === "png" ? "image/png" : "image/jpeg", 0.95);
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `${name.replace(/[^a-zA-Z0-9_-]/g, "_") || "diagrama"}.${format}`;
    document.body.appendChild(anchor); anchor.click(); anchor.remove();
}
