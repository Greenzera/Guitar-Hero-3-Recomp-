// Processo principal do launcher do Guitar Hero 3 Recomp.
//
// Tudo o que a interface mostra sai daqui: estado do jogo, DLCs, mods, idioma
// e as opcoes de video lidas do gh3recomp.toml que fica ao lado do executavel.

const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const { spawn, fork } = require('child_process');
const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const zlib = require('zlib');
const crypto = require('crypto');

const xiso = require('./xiso.js');
const modsmod = require('./mods.js');

// Empacotado, o codigo vive em resources/app e a raiz e' a pasta do executavel.
// Em desenvolvimento, e' a pasta acima do launcher/.
const RAIZ = app.isPackaged
  ? path.dirname(app.getPath('exe'))
  : path.resolve(__dirname, '..');
// Onde ficam os 3,4 GB do jogo. Por omissao e' game/ ao lado do launcher, mas
// o utilizador escolhe outra pasta no primeiro arranque -- por isso isto e'
// variavel, e tudo o que depende dela recalcula-se em derivar().
let JOGO = path.join(RAIZ, 'game');
let EXE, TOML, TOML_PADRAO, DLCS, MODS, LOGS, DESLIGADAS, PAB;

function derivar() {
  EXE = path.join(JOGO, 'Guitar Hero 3 Recomp.exe');
  TOML = path.join(JOGO, 'gh3recomp.toml');
  TOML_PADRAO = path.join(JOGO, 'gh3recomp.default.toml');
  DLCS = path.join(JOGO, 'DLCs');
  MODS = path.join(JOGO, 'MODS');
  LOGS = path.join(JOGO, 'logs');
  DESLIGADAS = path.join(DLCS, 'dlc_disabled.txt');
  PAB = path.join(JOGO, 'DATA', 'COMPRESSED', 'PAK', 'qb.pab.xen');
}
derivar();

// A escolha fica ao lado das definicoes do utilizador, e nao ao lado do
// executavel: instalado em Program Files, a pasta do executavel nao e' gravavel.
function ficheiroEscolha() {
  return path.join(app.getPath('userData'), 'launcher.json');
}

function carregarEscolha() {
  try {
    const d = JSON.parse(fs.readFileSync(ficheiroEscolha(), 'utf8'));
    if (d.jogo && fs.existsSync(path.dirname(d.jogo))) {
      JOGO = d.jogo;
      derivar();
    }
  } catch {
    /* primeira vez, ou ficheiro estragado: fica o valor por omissao */
  }
}

function gravarEscolha() {
  try {
    fs.mkdirSync(path.dirname(ficheiroEscolha()), { recursive: true });
    fs.writeFileSync(ficheiroEscolha(), JSON.stringify({ jogo: JOGO }, null, 2));
  } catch {}
}
// No pacote as ferramentas vao em tools/; no projeto vivem em gh3recomp/tools.
const FERRAMENTAS = fs.existsSync(path.join(RAIZ, 'tools', 'traduzir_ptbr.py'))
  ? path.join(RAIZ, 'tools')
  : path.join(RAIZ, 'gh3recomp', 'tools');
// Builds alternativos: um por cada xex de mod de codigo ja recompilado.
const BUILDS_PACOTE = path.join(RAIZ, 'bin');
const BUILDS_PROJETO = path.join(RAIZ, 'gh3recomp', 'out', 'build');
const TRADUTOR = path.join(FERRAMENTAS, 'traduzir_ptbr.py');

// Frase que so' existe no arquivo depois de a traducao entrar. Serve de
// sonda: e' mais honesto do que guardar um sinalizador que pode dessincronizar.
const MARCA_PT = Buffer.from('Verso 1', 'utf16le').swap16();

let janela = null;
let processoJogo = null;
let extracao = null;

// ---------------------------------------------------------------- utilitarios

async function existe(p) {
  try {
    await fsp.access(p);
    return true;
  } catch {
    return false;
  }
}

async function lerToml() {
  const valores = {};
  const origem = (await existe(TOML)) ? TOML : TOML_PADRAO;
  if (!(await existe(origem))) return valores;
  const texto = await fsp.readFile(origem, 'utf8');
  for (const linha of texto.split(/\r?\n/)) {
    const m = linha.match(/^([a-z0-9_]+)\s*=\s*(.+?)\s*$/i);
    if (!m) continue;
    let v = m[2];
    if (v.startsWith("'") && v.endsWith("'")) v = v.slice(1, -1);
    else if (v === 'true') v = true;
    else if (v === 'false') v = false;
    else if (/^-?\d+(\.\d+)?$/.test(v)) v = Number(v);
    valores[m[1]] = v;
  }
  return valores;
}

// Reescreve uma chave sem tocar no resto do ficheiro: o jogo tambem grava aqui,
// e reconstruir o toml inteiro apagaria comentarios e chaves que nao conheco.
async function gravarToml(chave, valor) {
  if (!(await existe(TOML)) && (await existe(TOML_PADRAO))) {
    await fsp.copyFile(TOML_PADRAO, TOML);
  }
  const texto = await fsp.readFile(TOML, 'utf8');
  const bruto = typeof valor === 'string' ? `'${valor}'` : String(valor);
  const alvo = new RegExp(`^${chave}\\s*=.*$`, 'm');
  const novo = alvo.test(texto)
    ? texto.replace(alvo, `${chave} = ${bruto}`)
    : `${texto.replace(/\s*$/, '')}\n${chave} = ${bruto}\n`;
  await fsp.writeFile(TOML, novo, 'utf8');
}

// Depois de instalar, as pastas passam a existir e os caminhos gravados no toml
// tem de apontar para onde o jogo esta mesmo -- senao herdava-se os caminhos da
// maquina onde o pacote foi feito e o jogo nao achava os dados.
async function prepararConfig() {
  if (!(await existe(TOML)) && (await existe(TOML_PADRAO))) {
    await fsp.copyFile(TOML_PADRAO, TOML);
  }
  await fsp.mkdir(DLCS, { recursive: true });
  await fsp.mkdir(MODS, { recursive: true });
  await fsp.mkdir(path.join(JOGO, 'userdata'), { recursive: true });
  if (!(await existe(TOML))) return;
  await gravarToml('game_data_root', JOGO);
  await gravarToml('user_data_root', path.join(JOGO, 'userdata'));
  await gravarToml('mods_root', MODS);
  await gravarToml('dlc_root', DLCS);
}

async function traducaoInstalada() {
  try {
    const cru = await fsp.readFile(PAB);
    return zlib.inflateRawSync(cru).includes(MARCA_PT);
  } catch {
    return null; // arquivo em falta ou ilegivel: melhor dizer que nao se sabe
  }
}

async function listarDlcs() {
  if (!(await existe(DLCS))) return [];
  let desligadas = new Set();
  if (await existe(DESLIGADAS)) {
    const t = await fsp.readFile(DESLIGADAS, 'utf8');
    desligadas = new Set(t.split(/\r?\n/).map((l) => l.trim()).filter(Boolean));
  }
  const entradas = await fsp.readdir(DLCS, { withFileTypes: true });
  const fora = [];
  for (const e of entradas) {
    if (e.name.toLowerCase().endsWith('.txt')) continue;
    let tamanho = 0;
    try {
      const st = await fsp.stat(path.join(DLCS, e.name));
      tamanho = st.isDirectory() ? 0 : st.size;
    } catch {}
    fora.push({ nome: e.name, pasta: e.isDirectory(), tamanho, ativa: !desligadas.has(e.name) });
  }
  return fora.sort((a, b) => a.nome.localeCompare(b.nome, 'pt'));
}

const RAIZES_BUILD = [BUILDS_PACOTE, BUILDS_PROJETO];
const listarMods = () => modsmod.listarMods(MODS);
const listarBuilds = () => modsmod.listarBuilds(EXE, JOGO, RAIZES_BUILD);

async function escolherBuild() {
  return modsmod.escolherBuild(await listarBuilds(), await listarMods());
}

async function ultimoLog() {
  if (!(await existe(LOGS))) return null;
  const ficheiros = (await fsp.readdir(LOGS)).filter((f) => f.endsWith('.log'));
  if (!ficheiros.length) return null;
  let melhor = null;
  for (const f of ficheiros) {
    const st = await fsp.stat(path.join(LOGS, f));
    if (!melhor || st.mtimeMs > melhor.mtime) melhor = { nome: f, mtime: st.mtimeMs };
  }
  return melhor;
}

async function estado() {
  const cfg = await lerToml();
  const dlcs = await listarDlcs();
  const v = xiso.verificarJogoExtraido(JOGO);
  const escolha = await escolherBuild();
  return {
    instalado: v.ok,
    pastaJogo: JOGO,
    build: escolha.build ? escolha.build.nome : null,
    buildNota: escolha.nota,
    buildAviso: escolha.aviso,
    motivo: v.motivo || '',
    jogoPresente: await existe(EXE),
    aCorrer: processoJogo !== null,
    traducao: await traducaoInstalada(),
    tradutorPresente: await existe(TRADUTOR),
    dlcs,
    mods: await listarMods(),
    log: await ultimoLog(),
    config: {
      gpu_backend: cfg.gpu_backend || 'd3d12',
      present_effect: cfg.present_effect || 'bilinear',
      fullscreen: cfg.fullscreen === true,
      vsync: cfg.vsync === true,
      show_fps_counter: cfg.show_fps_counter === true,
      window_width: cfg.window_width || 1280,
      window_height: cfg.window_height || 720,
    },
  };
}

function avisar(canal, dados) {
  if (janela && !janela.isDestroyed()) janela.webContents.send(canal, dados);
}

// ------------------------------------------------------------------- processos

async function jogar() {
  if (processoJogo) return { ok: false, erro: 'O jogo já está aberto.' };
  // Confere a cada arranque, e nao so' quando se instala: entre uma coisa e
  // outra a pasta pode ter sido mexida.
  const v = xiso.verificarJogoExtraido(JOGO);
  if (!v.ok) return { ok: false, erro: v.motivo };

  const escolha = await escolherBuild();
  if (!escolha.build) return { ok: false, erro: escolha.aviso || 'Nao ha nenhum build para lancar.' };

  // O build base corre como sempre, da pasta dele. Um build de variante vive
  // noutro sitio, por isso recebe os caminhos por argumento -- e um perfil so'
  // dele, senao as duas variantes pisavam as definicoes uma da outra.
  let args = [];
  let pasta = JOGO;
  if (!escolha.build.proprio) {
    const perfil = path.join(JOGO, 'userdata', escolha.build.nome);
    fs.mkdirSync(perfil, { recursive: true });
    args = ['--game_data_root', JOGO, '--user_data_root', perfil];
    pasta = path.dirname(escolha.build.exe);
  }
  processoJogo = spawn(escolha.build.exe, args, { cwd: pasta, detached: false });
  processoJogo.on('exit', (codigo) => {
    processoJogo = null;
    avisar('jogo-fechou', { codigo });
  });
  processoJogo.on('error', (e) => {
    processoJogo = null;
    avisar('jogo-fechou', { erro: e.message });
  });
  return { ok: true };
}

// Corre o instalador da traducao. Tenta 'python' e depois 'py', que e' o
// lancador do Windows -- numa maquina so' um deles costuma existir.
function correrTradutor(instalar) {
  const args = instalar ? [TRADUTOR] : [TRADUTOR, '--restaurar'];
  return new Promise((resolve) => {
    const tentar = (comando, alternativa) => {
      const p = spawn(comando, args, { cwd: FERRAMENTAS });
      let saida = '';
      let falhouAoArrancar = false;
      p.stdout.on('data', (d) => (saida += d));
      p.stderr.on('data', (d) => (saida += d));
      p.on('error', () => {
        falhouAoArrancar = true;
        if (alternativa) tentar(alternativa, null);
        else resolve({ ok: false, erro: 'Python nao encontrado no sistema.' });
      });
      p.on('exit', (codigo) => {
        if (falhouAoArrancar) return;
        resolve(codigo === 0
          ? { ok: true, saida: saida.trim() }
          : { ok: false, erro: saida.trim() || `O instalador saiu com codigo ${codigo}.` });
      });
    };
    tentar('python', 'py');
  });
}

async function gravarDlcs(lista) {
  const desligadas = lista.filter((d) => !d.ativa).map((d) => d.nome);
  if (!desligadas.length) {
    if (await existe(DESLIGADAS)) await fsp.unlink(DESLIGADAS);
    return;
  }
  const cabecalho = '# Uma DLC por linha: as que estao aqui nao sao carregadas.\n';
  await fsp.writeFile(DESLIGADAS, cabecalho + desligadas.join('\r\n') + '\r\n', 'utf8');
}

// ------------------------------------------------------------------------ IPC

ipcMain.handle('estado', estado);
ipcMain.handle('jogar', jogar);

ipcMain.handle('escolher-iso', async () => {
  const r = await dialog.showOpenDialog(janela, {
    title: 'Escolha o ISO do Guitar Hero III',
    filters: [{ name: 'Imagem de disco', extensions: ['iso'] }],
    properties: ['openFile'],
  });
  return r.canceled ? null : r.filePaths[0];
});

ipcMain.handle('escolher-pasta', async () => {
  const r = await dialog.showOpenDialog(janela, {
    title: 'Onde quer instalar o jogo',
    defaultPath: path.dirname(JOGO),
    properties: ['openDirectory', 'createDirectory'],
  });
  if (r.canceled) return { ok: false, cancelado: true };
  // Se a pasta escolhida ja' se chama "game", usa-se tal e qual; senao cria-se
  // uma subpasta, para nao espalhar 3,4 GB no meio das coisas do utilizador.
  const escolhida = r.filePaths[0];
  JOGO = path.basename(escolhida).toLowerCase() === 'game'
    ? escolhida
    : path.join(escolhida, 'Guitar Hero 3 Recomp', 'game');
  derivar();
  gravarEscolha();
  return { ok: true, pasta: JOGO };
});

ipcMain.handle('inspecionar', (_e, caminho) => {
  const info = xiso.inspecionar(caminho);
  let livre = Number.MAX_SAFE_INTEGER;
  try {
    const st = fs.statfsSync(RAIZ);
    livre = Number(st.bavail) * Number(st.bsize);
  } catch {}
  return { ...info, espacoLivre: livre, espacoChega: livre >= (info.bytesTotais || 0) * 1.05 };
});

ipcMain.handle('instalar', (_e, caminho) => {
  if (extracao) return Promise.resolve({ ok: false, erro: 'Já há uma instalação a decorrer.' });

  // A tranca. Esta e a versao do disco de que o jogo foi recompilado, e nenhuma
  // outra serve -- recusa-se aqui, antes de gastar minutos a copiar 3,4 GB que
  // nao iam funcionar.
  const info = xiso.inspecionar(caminho);
  if (!info.valido) return Promise.resolve({ ok: false, erro: info.erro });
  if (!info.mesmaVersao) {
    return Promise.resolve({
      ok: false,
      erro: [
        'Este ISO não é a versão de que o jogo foi recompilado, por isso não iria funcionar.',
        `Esperado: default.xex com ${xiso.XEX_TAMANHO} bytes, SHA-256 ${xiso.XEX_HASH.slice(0, 16)}…`,
        `Neste ISO: ${info.tamanhoXex} bytes, SHA-256 ${info.hashXex.slice(0, 16)}…`,
      ].join('\n'),
    });
  }

  return new Promise((resolve) => {
    extracao = fork(path.join(__dirname, 'extrator.js'), [caminho, JOGO], {
      stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
    });
    extracao.on('message', async (m) => {
      if (m.tipo === 'progresso') {
        avisar('progresso', m);
      } else if (m.tipo === 'fim') {
        extracao = null;
        if (m.ok) await prepararConfig();
        resolve(m);
      }
    });
    extracao.on('error', (e) => {
      extracao = null;
      resolve({ ok: false, erro: e.message });
    });
    extracao.on('exit', (codigo) => {
      if (extracao) {
        extracao = null;
        resolve({ ok: false, erro: `A instalação terminou de repente (código ${codigo}).` });
      }
    });
  });
});

ipcMain.handle('cancelar', () => {
  if (!extracao) return false;
  extracao.kill();
  extracao = null;
  return true;
});
ipcMain.handle('traducao', async (_e, instalar) => {
  const r = await correrTradutor(instalar);
  return { ...r, traducao: await traducaoInstalada() };
});
ipcMain.handle('dlc', async (_e, nome, ativa) => {
  const lista = await listarDlcs();
  const alvo = lista.find((d) => d.nome === nome);
  if (alvo) alvo.ativa = ativa;
  await gravarDlcs(lista);
  return listarDlcs();
});
ipcMain.handle('mod', async (_e, nome, ativo) => {
  await modsmod.ligarMod(MODS, nome, ativo);
  return listarMods();
});
ipcMain.handle('importar-mod', async (_e, caminho) => {
  try {
    let origem = caminho;
    if (!origem) {
      const r = await dialog.showOpenDialog(janela, {
        title: 'Escolha a pasta do mod, ou o .zip dele',
        properties: ['openFile', 'openDirectory'],
        filters: [{ name: 'Mod', extensions: ['zip'] }],
      });
      if (r.canceled) return { ok: false, cancelado: true };
      origem = r.filePaths[0];
    }
    const info = await modsmod.importarMod(MODS, origem);
    return { ok: true, ...info, mods: await listarMods() };
  } catch (e) {
    return { ok: false, erro: e.message };
  }
});

ipcMain.handle('config', async (_e, chave, valor) => {
  await gravarToml(chave, valor);
  return (await estado()).config;
});
ipcMain.handle('abrir', async (_e, qual) => {
  const destinos = { jogo: JOGO, dlcs: DLCS, mods: MODS, logs: LOGS, raiz: RAIZ };
  const alvo = destinos[qual];
  if (!alvo) return { ok: false };
  await shell.openPath(alvo);
  return { ok: true };
});
ipcMain.handle('abrir-log', async () => {
  const l = await ultimoLog();
  if (!l) return { ok: false };
  await shell.openPath(path.join(LOGS, l.nome));
  return { ok: true };
});
ipcMain.on('janela', (_e, acao) => {
  if (!janela) return;
  if (acao === 'minimizar') janela.minimize();
  else if (acao === 'maximizar') janela.isMaximized() ? janela.unmaximize() : janela.maximize();
  else if (acao === 'fechar') janela.close();
});

// --------------------------------------------------------------------- janela

function criarJanela() {
  janela = new BrowserWindow({
    width: 1180,
    height: 760,
    minWidth: 1000,
    minHeight: 680,
    frame: false,
    show: false,
    backgroundColor: '#08080a',
    icon: path.join(__dirname, 'assets', 'logo.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  janela.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  janela.once('ready-to-show', () => janela.show());
  janela.on('closed', () => (janela = null));
}

app.whenReady().then(() => {
  carregarEscolha();
  criarJanela();
});
app.on('window-all-closed', () => app.quit());
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) criarJanela();
});
