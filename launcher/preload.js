// Ponte estreita entre a interface e o processo principal: a janela nao tem
// acesso ao Node, so' a estas funcoes.

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('gh3', {
  estado: () => ipcRenderer.invoke('estado'),
  jogar: () => ipcRenderer.invoke('jogar'),
  traducao: (instalar) => ipcRenderer.invoke('traducao', instalar),
  dlc: (nome, ativa) => ipcRenderer.invoke('dlc', nome, ativa),
  mod: (nome, ativo) => ipcRenderer.invoke('mod', nome, ativo),
  importarMod: (caminho) => ipcRenderer.invoke('importar-mod', caminho),
  config: (chave, valor) => ipcRenderer.invoke('config', chave, valor),
  abrir: (qual) => ipcRenderer.invoke('abrir', qual),
  abrirLog: () => ipcRenderer.invoke('abrir-log'),
  janela: (acao) => ipcRenderer.send('janela', acao),
  aoFecharJogo: (fn) => ipcRenderer.on('jogo-fechou', (_e, d) => fn(d)),

  escolherIso: () => ipcRenderer.invoke('escolher-iso'),
  escolherPasta: () => ipcRenderer.invoke('escolher-pasta'),
  inspecionar: (caminho) => ipcRenderer.invoke('inspecionar', caminho),
  instalar: (caminho) => ipcRenderer.invoke('instalar', caminho),
  cancelar: () => ipcRenderer.invoke('cancelar'),
  aoProgresso: (fn) => ipcRenderer.on('progresso', (_e, d) => fn(d)),
});
