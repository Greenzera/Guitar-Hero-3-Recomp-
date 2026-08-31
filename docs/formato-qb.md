# O arquivo de scripts do GH3 (`qb.pak` + `qb.pab`)

Notas do que foi preciso descobrir para traduzir o jogo. Vale para a versão
Xbox 360; a de PC é parecida mas o índice e os dados nem sempre batem certo
entre si.

## Onde vive

```
DATA/COMPRESSED/PAK/qb.pak.xen    índice
DATA/COMPRESSED/PAK/qb.pab.xen    dados
DATA/COMPRESSED/compress.toc.xen  índice do arquivo comprimido
```

Os três estão comprimidos com **deflate cru** (`wbits=-15`, sem cabeçalho
zlib). O jogo lê daqui e ignora os equivalentes soltos em `DATA/PAK`.

## `compress.toc.xen`

Cabeçalho de 16 bytes: magic `TOC1`, número de entradas, offset do início da
tabela. Depois, 16 bytes por ficheiro, big-endian:

| offset | campo |
|---|---|
| +0 | hash do nome |
| +4 | tamanho descomprimido |
| +8 | tamanho comprimido (em disco) |
| +12 | flags |

O `compress.toc.lst.xen` ao lado é a mesma lista em texto, com o nome e o
tamanho comprimido. As duas têm de ser atualizadas juntas.

Todos os tamanhos descomprimidos originais são múltiplos de 2048 — o jogo lê
por setores.

## `qb.pak` — o índice

Registos de 32 bytes, big-endian, terminados por um registo a zeros:

| offset | campo |
|---|---|
| +0x00 | checksum da extensão |
| +0x04 | offset |
| +0x08 | tamanho |
| +0x10 | checksum do nome |

Duas coisas que não são óbvias:

**Os offsets são relativos ao início do pak**, não ao pab. O jogo carrega o
índice e põe o pab logo a seguir, num só buffer — por isso o primeiro offset é
sempre igual ao tamanho do pak.

**Os bytes guardados no pab são `arredondar_para_cima(tamanho − 32, 32)`.** O
tamanho declarado conta 32 bytes que não estão no pab, e é por isso que dois
registos consecutivos parecem sobrepor-se se olhar só para offset + tamanho.

A base é livre: dá para deslocar tudo (encher o índice com zeros e somar o
mesmo valor a todos os offsets) que o jogo continua a funcionar.

**O pab tem uma cauda que nenhum registo referencia** — 16 960 bytes no
original. Deitá-la fora mata o jogo. Tem de ir sempre atrás, intacta.

## As entradas de texto

Dentro de cada ficheiro, uma string fica assim:

```
[cabeçalho 12] [texto UTF-16BE] [NUL NUL] [enchimento até múltiplo de 4] [rodapé]
```

O cabeçalho traz o checksum do ficheiro (ou o marcador de tipo `00 84 00 00`
quatro bytes antes) e o offset da entrada dentro do ficheiro, relativo a uma
base própria de cada ficheiro.

## A regra que manda em tudo

O jogo percorre as entradas **em sequência**, lendo cada texto até ao NUL.
Consequências, todas verificadas em execução:

| edição | resultado |
|---|---|
| trocar bytes mantendo o tamanho | funciona |
| encurtar o texto | o NUL aparece cedo, o resto é lido no sítio errado, crash em ~2 s |
| alongar, corrigindo os offsets de todas as entradas seguintes e o índice | também morre |

O caso de alongar foi tentado a sério: reconstruir o ficheiro inteiro, deslocar
as entradas, recalcular os offsets e o tamanho no índice. Só 1 ficheiro em 12
sobreviveu — há outras referências dentro do ficheiro a apontar para os textos
que não se conseguem localizar.

Daí a tradução encher o português com espaços até ao tamanho exato do inglês, e
deixar em inglês tudo o que não caiba.

## Como se verifica que o arquivo continua bom

Reconstruir com o conteúdo original e comparar byte a byte com o ficheiro em
disco. Se a reconstrução não der igual, o modelo do formato está errado algures
— e vale mais descobrir isso ali do que a olhar para um ecrã preto.
