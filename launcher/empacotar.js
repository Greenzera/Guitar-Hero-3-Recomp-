// Monta a pasta distribuivel do launcher.
//
//     node empacotar.js [destino]
//
// O Electron ja' esta' em node_modules/electron/dist; empacotar e' copia-lo,
// renomear o executavel e por o codigo em resources/app. Nao precisa de rede
// nem de electron-builder.
//
// O que NAO entra: o default.xex do jogo e os dados. O executavel do jogo vem
// do disco de quem joga, extraido pelo proprio instalador; o do GH3 Deluxe vem
// dentro do mod, e a camada de mods poe-no por cima na altura de correr.

'use strict';

const fs = require('fs');
const path = require('path');

const AQUI = __dirname;
const RAIZ = path.resolve(AQUI, '..');
const ELECTRON = path.join(AQUI, 'node_modules', 'electron', 'dist');
const DESTINO = process.argv[2] || path.join(RAIZ, 'dist', 'Guitar Hero 3 Recomp');
const NOME_EXE = 'Guitar Hero 3 Recomp.exe';

// Ficheiros do launcher que vao para resources/app.
const APP = ['main.js', 'preload.js', 'xiso.js', 'mods.js', 'extrator.js', 'package.json'];
const APP_PASTAS = ['renderer', 'assets'];
const ICONE = path.join(AQUI, 'assets', 'icone.ico');

function copiar(origem, destino) {
  fs.mkdirSync(path.dirname(destino), { recursive: true });
  fs.copyFileSync(origem, destino);
}

function copiarPasta(origem, destino, filtro) {
  fs.mkdirSync(destino, { recursive: true });
  for (const e of fs.readdirSync(origem, { withFileTypes: true })) {
    const de = path.join(origem, e.name);
    const para = path.join(destino, e.name);
    if (filtro && !filtro(de, e)) continue;
    if (e.isDirectory()) copiarPasta(de, para, filtro);
    else fs.copyFileSync(de, para);
  }
}

function tamanho(pasta) {
  let total = 0;
  const andar = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const f = path.join(d, e.name);
      if (e.isDirectory()) andar(f);
      else total += fs.statSync(f).size;
    }
  };
  andar(pasta);
  return total;
}

if (!fs.existsSync(ELECTRON)) {
  console.error('Falta node_modules/electron/dist -- corre npm install primeiro.');
  process.exit(1);
}

console.log('destino:', DESTINO);
fs.rmSync(DESTINO, { recursive: true, force: true });

// 1. o runtime do Electron
copiarPasta(ELECTRON, DESTINO);
fs.renameSync(path.join(DESTINO, 'electron.exe'), path.join(DESTINO, NOME_EXE));
// o app de exemplo do Electron nao serve para nada aqui
fs.rmSync(path.join(DESTINO, 'resources', 'default_app.asar'), { force: true });
console.log('  runtime do Electron copiado');

// 2. o codigo do launcher
const APP_DIR = path.join(DESTINO, 'resources', 'app');
for (const f of APP) copiar(path.join(AQUI, f), path.join(APP_DIR, f));
for (const d of APP_PASTAS) copiarPasta(path.join(AQUI, d), path.join(APP_DIR, d));
console.log('  launcher em resources/app');

// 3. o jogo base: o executavel recompilado e as bibliotecas, sem dados
const BASE = path.join(RAIZ, 'game');
const JOGO = path.join(DESTINO, 'game');
fs.mkdirSync(JOGO, { recursive: true });
let base = 0;
for (const f of fs.readdirSync(BASE)) {
  if (/\.(exe|dll)$/i.test(f) || f === 'source-xex.sha256' || f === 'gh3recomp.default.toml') {
    copiar(path.join(BASE, f), path.join(JOGO, f));
    base++;
  }
}
console.log(`  jogo base: ${base} ficheiros (sem dados, sem default.xex)`);

// 4. builds de variante, um por cada mod de codigo ja recompilado
const ORIGEM_BUILDS = path.join(RAIZ, 'gh3recomp', 'out', 'build');
const BIN = path.join(DESTINO, 'bin');
let variantes = 0;
if (fs.existsSync(ORIGEM_BUILDS)) {
  for (const e of fs.readdirSync(ORIGEM_BUILDS, { withFileTypes: true })) {
    if (!e.isDirectory()) continue;
    const de = path.join(ORIGEM_BUILDS, e.name);
    if (!fs.existsSync(path.join(de, 'source-xex.sha256'))) continue;
    if (!fs.existsSync(path.join(de, 'gh3.exe'))) continue;
    // o build base ja' foi para game/; aqui vao so' as variantes
    const h = fs.readFileSync(path.join(de, 'source-xex.sha256'), 'utf8').trim().toUpperCase();
    const hBase = fs.readFileSync(path.join(BASE, 'source-xex.sha256'), 'utf8').trim().toUpperCase();
    if (h === hBase) continue;
    copiarPasta(de, path.join(BIN, e.name), (f) => /\.(exe|dll)$|source-xex\.sha256$|\.toml$/i.test(f));
    variantes++;
    console.log(`  variante: ${e.name}  (xex ${h.slice(0, 12)}…)`);
  }
}
if (!variantes) console.log('  variantes: nenhuma');

// 5. as ferramentas que o launcher chama
const TOOLS = path.join(DESTINO, 'tools');
for (const f of ['traduzir_ptbr.py', '_arquivo_qb.py']) {
  const de = path.join(RAIZ, 'gh3recomp', 'tools', f);
  if (fs.existsSync(de)) copiar(de, path.join(TOOLS, f));
}
console.log('  ferramentas da traducao');

// 6. leia-me
const leiame = path.join(AQUI, 'LEIA-ME.txt');
if (fs.existsSync(leiame)) copiar(leiame, path.join(DESTINO, 'LEIA-ME.txt'));


// 7. icone e dados de versao no executavel.
// O rcedit e' opcional: sem ele o pacote fica bom na mesma, so' herda o icone
// do Electron.
async function marcar() {
  let rcedit;
  try {
    // o rcedit 5 e' modulo ESM e exporta { rcedit }
    const m = require('rcedit');
    rcedit = typeof m === 'function' ? m : m.rcedit;
    if (typeof rcedit !== 'function') throw new Error('formato inesperado');
  } catch {
    console.log('  (sem rcedit: o executavel fica com o icone do Electron)');
    return;
  }
  await rcedit(path.join(DESTINO, NOME_EXE), {
    icon: fs.existsSync(ICONE) ? ICONE : undefined,
    'file-version': '1.0.0.0',
    'product-version': '1.0.0.0',
    'version-string': {
      ProductName: 'Guitar Hero 3 Recomp',
      FileDescription: 'Guitar Hero 3 Recomp',
      CompanyName: 'luisxl15',
      OriginalFilename: NOME_EXE,
    },
  });
  console.log('  icone e versao aplicados ao executavel');
}

marcar().then(() => {
  console.log('');
  console.log('pronto: ' + (tamanho(DESTINO) / 1048576).toFixed(0) + ' MB');
  console.log('abre com: "' + path.join(DESTINO, NOME_EXE) + '"');
});
