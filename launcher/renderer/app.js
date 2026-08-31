// Interface do launcher. Tudo o que muda estado passa pelo processo principal
// e volta com o valor real lido do disco -- a interface nunca adivinha.

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

let estado = null;
let ocupado = false;

// -------------------------------------------------------------------- brinde

let temporizador = null;
function brinde(texto) {
  const el = $('#brinde');
  el.textContent = texto;
  el.classList.add('visivel');
  clearTimeout(temporizador);
  temporizador = setTimeout(() => el.classList.remove('visivel'), 3600);
}

function recado(texto, tipo) {
  const el = $('#recado');
  el.textContent = texto;
  el.className = 'recado' + (tipo ? ' ' + tipo : '');
}

// ------------------------------------------------------------------ desenhar

const NOMES_BACKEND = { d3d12: 'Direct3D 12', vulkan: 'Vulkan' };

function tamanhoLegivel(bytes) {
  if (!bytes) return null;
  const mb = bytes / (1024 * 1024);
  return mb >= 1024 ? (mb / 1024).toFixed(1) + ' GB' : Math.round(mb) + ' MB';
}

function desenharMarcadores() {
  const c = estado.config;
  $('#m-backend').textContent = NOMES_BACKEND[c.gpu_backend] || c.gpu_backend;
  $('#m-idioma').textContent =
    estado.traducao === null ? '—' : estado.traducao ? 'Português' : 'Inglês';
  $('#m-dlcs').textContent = `${estado.dlcs.filter((d) => d.ativa).length}/${estado.dlcs.length}`;
  $('#m-mods').textContent = `${estado.mods.filter((m) => m.ativo).length}/${estado.mods.length}`;
}

function desenharTraducao() {
  const sw = $('#sw-traducao');
  const nota = $('#nota-traducao');
  if (!estado.tradutorPresente) {
    sw.disabled = true;
    nota.textContent = 'instalador não encontrado';
    return;
  }
  if (estado.traducao === null) {
    sw.disabled = true;
    nota.textContent = 'não consegui ler o arquivo do jogo';
    return;
  }
  sw.disabled = ocupado;
  sw.setAttribute('aria-checked', String(estado.traducao));
  nota.textContent = estado.traducao
    ? '712 frases traduzidas sobre o inglês'
    : 'o jogo está em inglês';
}

function desenharVideo() {
  const c = estado.config;
  const seg = $('#seg-backend');
  seg.querySelectorAll('button').forEach((b) => {
    const ligado = b.dataset.valor === c.gpu_backend;
    b.setAttribute('aria-checked', String(ligado));
  });
  const indice = c.gpu_backend === 'vulkan' ? 1 : 0;
  seg.querySelector('.polegar').style.transform = `translateX(${indice * 74}px)`;

  $$('.interruptor[data-config]').forEach((sw) => {
    sw.setAttribute('aria-checked', String(c[sw.dataset.config] === true));
  });
}

function desenharDlcs() {
  const alvo = $('#lista-dlcs');
  alvo.innerHTML = '';
  if (!estado.dlcs.length) {
    alvo.innerHTML = '<p class="vazio">Nenhum pacote em <b>game\\DLCs</b>.</p>';
    return;
  }
  for (const d of estado.dlcs) {
    const tam = tamanhoLegivel(d.tamanho);
    const linha = document.createElement('div');
    linha.className = 'linha';
    linha.innerHTML = `
      <div class="texto">
        <span class="nome"></span>
        <span class="nota">${d.pasta ? 'pasta' : tam ? 'pacote · ' + tam : 'pacote'}</span>
      </div>
      <button class="interruptor" role="switch" aria-checked="${d.ativa}" aria-label="Ativar DLC"><span></span></button>`;
    linha.querySelector('.nome').textContent = d.nome;
    linha.querySelector('.interruptor').addEventListener('click', async (ev) => {
      const btn = ev.currentTarget;
      const novo = btn.getAttribute('aria-checked') !== 'true';
      btn.setAttribute('aria-checked', String(novo));
      estado.dlcs = await window.gh3.dlc(d.nome, novo);
      desenharMarcadores();
      brinde(`${d.nome} ${novo ? 'ativada' : 'desativada'}. Vale no próximo arranque.`);
    });
    alvo.appendChild(linha);
  }
}

function desenharMods() {
  const alvo = $('#lista-mods');
  alvo.innerHTML = '';
  if (!estado.mods.length) {
    alvo.innerHTML = '<p class="vazio">Nenhum mod em <b>game\\MODS</b>.</p>';
    return;
  }
  for (const m of estado.mods) {
    const linha = document.createElement('div');
    linha.className = 'linha';
    linha.innerHTML = `
      <div class="texto">
        <span class="nome"></span>
        <span class="nota">${m.codigo ? 'altera o executável · ' : ''}${m.ativo ? 'a ser carregado' : 'desligado'}</span>
      </div>
      <button class="interruptor" role="switch" aria-checked="${m.ativo}" aria-label="Ativar mod"><span></span></button>`;
    linha.querySelector('.nome').textContent = m.nome;
    linha.querySelector('.interruptor').addEventListener('click', async (ev) => {
      const novo = ev.currentTarget.getAttribute('aria-checked') !== 'true';
      estado.mods = await window.gh3.mod(m.nome, novo);
      desenharMods();
      desenharMarcadores();
      brinde(novo
        ? `${m.nome} ligado. Se o jogo abrir em tela preta, é este mod — desligue-o aqui.`
        : `${m.nome} desligado.`);
    });
    alvo.appendChild(linha);
  }
}

function desenharJogar() {
  const b = $('#jogar');
  b.disabled = ocupado || !estado.build || estado.aCorrer;
  b.classList.toggle('ocupado', estado.aCorrer);
  b.querySelector('.rotulo').textContent = estado.aCorrer ? 'Em execução' : 'Jogar';
  if (estado.aCorrer) return;

  // Um mod que traga o proprio default.xex precisa do executavel recompilado
  // desse xex -- e e' isso que o utilizador tem de saber antes de carregar.
  if (estado.buildAviso) recado(estado.buildAviso, 'alerta');
  else if (estado.buildNota && estado.buildNota !== 'jogo base') {
    recado('Vai abrir com ' + estado.buildNota + '.', 'bom');
  } else recado('Recompilado do Xbox 360 · nativo em PC');
}

function desenhar() {
  // Sem o jogo instalado nao ha nada para configurar: mostra-se o instalador.
  $('#vista-instalar').hidden = estado.instalado;
  $('#vista-jogar').hidden = !estado.instalado;
  if (!estado.instalado) return;
  desenharMarcadores();
  desenharTraducao();
  desenharVideo();
  desenharDlcs();
  desenharMods();
  desenharJogar();
}

async function recarregar() {
  estado = await window.gh3.estado();
  desenhar();
}

// -------------------------------------------------------------------- acções

$$('[data-janela]').forEach((b) =>
  b.addEventListener('click', () => window.gh3.janela(b.dataset.janela))
);

$$('[data-abrir]').forEach((b) =>
  b.addEventListener('click', () => window.gh3.abrir(b.dataset.abrir))
);

$('#btn-importar-mod').addEventListener('click', async () => {
  const r = await window.gh3.importarMod();
  if (r.cancelado) return;
  if (!r.ok) {
    brinde('Nao deu: ' + r.erro);
    return;
  }
  estado.mods = r.mods;
  desenharMods();
  desenharMarcadores();
  brinde(`${r.nome} importado${r.codigo ? ' (altera o executavel)' : ''}. Ligue-o na lista.`);
});

$('#btn-log').addEventListener('click', async () => {
  const r = await window.gh3.abrirLog();
  if (!r.ok) brinde('Ainda não há nenhum log — o jogo nunca foi aberto.');
});

$('#jogar').addEventListener('click', async () => {
  const r = await window.gh3.jogar();
  if (!r.ok) {
    recado(r.erro, 'alerta');
    return;
  }
  estado.aCorrer = true;
  desenharJogar();
  recado('O jogo está a carregar…');
});

window.gh3.aoFecharJogo(({ codigo, erro }) => {
  estado.aCorrer = false;
  desenharJogar();
  if (erro) recado('Não consegui abrir o jogo: ' + erro, 'alerta');
  else if (codigo === 0 || codigo === null) recado('Recompilado do Xbox 360 · nativo em PC');
  else recado(`O jogo terminou com código ${codigo}.`, 'alerta');
});

$('#sw-traducao').addEventListener('click', async () => {
  if (ocupado) return;
  const instalar = $('#sw-traducao').getAttribute('aria-checked') !== 'true';
  ocupado = true;
  $('#sw-traducao').setAttribute('aria-checked', String(instalar));
  $('#nota-traducao').textContent = instalar ? 'a instalar…' : 'a repor o inglês…';
  desenharJogar();

  const r = await window.gh3.traducao(instalar);
  estado.traducao = r.traducao;
  ocupado = false;
  desenhar();

  if (!r.ok) brinde('Não deu: ' + (r.erro || 'erro desconhecido'));
  else brinde(instalar ? 'Tradução instalada.' : 'O jogo voltou ao inglês.');
});

$$('.interruptor[data-config]').forEach((sw) =>
  sw.addEventListener('click', async () => {
    const chave = sw.dataset.config;
    const novo = sw.getAttribute('aria-checked') !== 'true';
    sw.setAttribute('aria-checked', String(novo));
    estado.config = await window.gh3.config(chave, novo);
    desenharVideo();
  })
);

$('#seg-backend').querySelectorAll('button').forEach((b) =>
  b.addEventListener('click', async () => {
    if (b.dataset.valor === estado.config.gpu_backend) return;
    estado.config = await window.gh3.config('gpu_backend', b.dataset.valor);
    desenharVideo();
    desenharMarcadores();
    brinde(`Renderizador: ${NOMES_BACKEND[estado.config.gpu_backend]}.`);
  })
);

// ---------------------------------------------------------------- instalador

const PASSOS = ['iso', 'verificar', 'confirmar', 'extrair', 'erro'];
let isoEscolhido = null;
let inicioExtracao = 0;

function passo(qual) {
  for (const p of PASSOS) $('#passo-' + p).hidden = p !== qual;
}

function gb(bytes) {
  return (bytes / 1073741824).toLocaleString('pt-BR', {
    minimumFractionDigits: 1, maximumFractionDigits: 1,
  }) + ' GB';
}

function duracao(segundos) {
  if (!isFinite(segundos) || segundos <= 0) return '';
  const m = Math.floor(segundos / 60);
  const s = Math.round(segundos % 60);
  return m > 0 ? `faltam ${m} min ${s}s` : `faltam ${s}s`;
}

function falhar(texto) {
  $('#texto-erro').textContent = texto;
  passo('erro');
}

async function verificarIso(caminho) {
  isoEscolhido = caminho;
  passo('verificar');
  const info = await window.gh3.inspecionar(caminho);
  if (!info.valido) {
    falhar(info.erro);
    return;
  }

  const linhas = [
    ['Tipo de disco', info.tipoDisco, null],
    ['Conteúdo', `${info.ficheiros} ficheiros · ${gb(info.bytesTotais)}`, null],
    ['Versão do disco', info.mesmaVersao ? 'confere' : 'não é esta', info.mesmaVersao],
    ['Espaço livre', gb(info.espacoLivre), info.espacoChega],
  ];
  $('#ficha').innerHTML = linhas
    .map(([k, v, bom]) => {
      const classe = bom === null ? '' : bom ? ' class="certo"' : ' class="errado"';
      return `<div class="par"><b>${k}</b><span${classe}>${v}</span></div>`;
    })
    .join('');

  const podeInstalar = info.mesmaVersao && info.espacoChega;
  $('#btn-instalar').disabled = !podeInstalar;
  $('#passo-confirmar').querySelector('.passo-titulo').textContent = info.mesmaVersao
    ? 'Disco reconhecido'
    : 'Este disco não serve';
  passo('confirmar');

  if (!info.mesmaVersao) {
    brinde('O jogo foi recompilado da versão USA Rev 1. Com outra, não arranca.');
  } else if (!info.espacoChega) {
    brinde('Não há espaço em disco suficiente para a instalação.');
  }
}

async function instalar() {
  if (!isoEscolhido) return;
  inicioExtracao = Date.now();
  $('#barra-cheia').style.width = '0%';
  $('#progresso-pct').textContent = '0%';
  $('#progresso-eta').textContent = '';
  $('#ficheiro-atual').textContent = '\u00a0';
  passo('extrair');

  const r = await window.gh3.instalar(isoEscolhido);
  if (!r.ok) {
    falhar(r.erro || 'A instalação parou sem dizer porquê.');
    return;
  }
  $('#titulo-extrair').textContent = 'Pronto';
  await recarregar();
  brinde(`Instalado: ${r.ficheiros} ficheiros, ${gb(r.bytes)}.`);
}

window.gh3.aoProgresso((p) => {
  const fracao = p.totais ? p.feitos / p.totais : 0;
  $('#barra-cheia').style.width = (fracao * 100).toFixed(1) + '%';
  $('#progresso-pct').textContent = Math.floor(fracao * 100) + '%';
  $('#progresso-gb').textContent = `${gb(p.feitos)} / ${gb(p.totais)}`;
  if (p.ficheiro) $('#ficheiro-atual').textContent = p.ficheiro;

  const decorrido = (Date.now() - inicioExtracao) / 1000;
  if (decorrido > 2 && p.feitos > 0) {
    const porSegundo = p.feitos / decorrido;
    $('#progresso-eta').textContent = duracao((p.totais - p.feitos) / porSegundo);
  }
});

$('#btn-escolher').addEventListener('click', async () => {
  const c = await window.gh3.escolherIso();
  if (c) verificarIso(c);
});
$('#btn-outro').addEventListener('click', async () => {
  const c = await window.gh3.escolherIso();
  if (c) verificarIso(c);
  else passo('iso');
});
$('#btn-instalar').addEventListener('click', instalar);
$('#btn-recomecar').addEventListener('click', () => passo('iso'));
$('#btn-cancelar').addEventListener('click', async () => {
  await window.gh3.cancelar();
  falhar('Instalação cancelada. A pasta do jogo ficou pela metade — recomece quando quiser.');
});

// Arrastar o ISO para a janela.
const alvo = $('#alvo');
const vista = $('#vista-instalar');
for (const evento of ['dragenter', 'dragover']) {
  vista.addEventListener(evento, (e) => {
    e.preventDefault();
    alvo.classList.add('sobre');
  });
}
for (const evento of ['dragleave', 'drop']) {
  vista.addEventListener(evento, () => alvo.classList.remove('sobre'));
}
vista.addEventListener('drop', (e) => {
  e.preventDefault();
  const f = e.dataTransfer.files[0];
  if (!f) return;
  if (!f.name.toLowerCase().endsWith('.iso')) {
    falhar('Isso não é um ficheiro .iso.');
    return;
  }
  verificarIso(f.path);
});

// ------------------------------------------------------------------ arranque

recarregar().then(() => {
  if (estado.instalado && !estado.jogoPresente) {
    recado('Nao encontrei o executavel na pasta do jogo.', 'alerta');
  }
});
