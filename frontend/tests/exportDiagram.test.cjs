const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');

function fixture(fail = false) {
  let options, clicked, mime, serialized;
  const draws = [];
  function element() {
    return { attrs: {}, children: [], setAttribute(k,v) { this.attrs[k]=v; }, getAttribute(k) { return this.attrs[k]; }, removeAttribute(k) { delete this.attrs[k]; }, appendChild(n) { this.children.push(n); }, cloneNode() { const n=element(); n.attrs={...this.attrs}; return n; } };
  }
  const path = element();
  path.attrs = { d: 'M -300 -200 C 0 0 900 400 900 400', 'marker-end': 'url(#arrow-open)' };
  path.getBBox = () => ({ x:-300, y:-200, width:1200, height:600 });
  const viewport = { querySelectorAll: () => [path] };
  const canvas = { querySelector: s => s.includes('viewport') ? viewport : element() };
  const context = { fillRect() { draws.push('background'); }, drawImage(n) { draws.push(n.kind); } };
  const document = { fonts:{ ready:Promise.resolve() }, body:{ appendChild(){} }, createElementNS:()=>element(), createElement(tag) {
    if(tag==='canvas') return { getContext:()=>context, toDataURL(type) { mime=type; return 'data:'+type; } };
    return { click() { clicked=this.download; }, remove(){} };
  } };
  class Image { kind='edges'; set src(v) { this.onload(); } }
  class XMLSerializer { serializeToString(svg) { serialized=svg; return '<svg/>'; } }
  const imports = { 'html-to-image': { toCanvas:async(n,o)=> { options=o; if(fail) throw Error('render failed'); return {kind:'nodes'}; } }, reactflow:{getRectOfNodes:()=>({x:-100,y:-50,width:1000,height:700})} };
  const code=ts.transpileModule(fs.readFileSync('src/exportDiagram.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const module={exports:{}};
  new Function('require','exports','document','Image','XMLSerializer','getComputedStyle',code)(n=>imports[n],module.exports,document,Image,XMLSerializer,()=>({strokeWidth:'1.5',strokeDasharray:'6 4'}));
  return { run:(nodes=[{}],format='png')=>module.exports.exportDiagram(canvas,nodes,'Modelo',format), options:()=>options, clicked:()=>clicked, mime:()=>mime, svg:()=>serialized, draws };
}

test('export preserves offscreen bounds and paints opaque edges behind nodes',async()=>{
  const s=fixture(); await s.run();
  assert.equal(s.options().width,1360); assert.equal(s.options().height,1010);
  assert.equal(s.options().style.transform,'translate(380px, 280px) scale(1)');
  const path=s.svg().children[1];
  assert.equal(path.attrs.stroke,'#171717'); assert.equal(path.attrs.opacity,'1');
  assert.equal(path.attrs['marker-end'],'url(#arrow-open)'); assert.equal(path.attrs['stroke-dasharray'],'6 4');
  assert.deepEqual(s.draws,['background','edges','nodes']); assert.equal(s.clicked(),'Modelo.png');
});
test('JPG uses JPEG encoding and omits duplicate DOM edges and editing controls',async()=>{
  const s=fixture(); await s.run([{}],'jpg'); assert.equal(s.mime(),'image/jpeg');
  assert.equal(s.options().backgroundColor,'transparent');
  for(const name of ['react-flow__edges','react-flow__handle','react-flow__resize-control']) assert.equal(s.options().filter({classList:{contains:n=>n===name}}),false);
  assert.equal(s.options().filter({tagName:'BUTTON'}),false); assert.equal(s.clicked(),'Modelo.jpg');
});
test('empty diagrams and renderer errors do not download',async()=>{
  const s=fixture(true); await assert.rejects(s.run([]),/Agrega una clase/); await assert.rejects(s.run(),/render failed/); assert.equal(s.clicked(),undefined);
});
