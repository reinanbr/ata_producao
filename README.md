# ata_producao

Gera a ata mensal da reunião do Colegiado do PPGCTA a partir de três arquivos:

- o **vídeo** da reunião (gravação do Google Meet);
- a **pauta** do mês (`.docx`, `.md` ou `.txt`);
- a **ata do mês anterior** (`.docx`), usada como modelo de estilo e formatação.

O áudio é transcrito localmente com [faster-whisper](https://github.com/SYSTRAN/faster-whisper).
A redação é feita pelo Claude (`claude -p`). O resultado é um `.docx` com o mesmo
cabeçalho, rodapé e assinatura do modelo.

## Uso

Coloque esta pasta (`gerador_ata/`) dentro da pasta onde ficam os vídeos, as pautas e as atas:

```
ata/
├── gerador_ata/                                  ← este repositório
├── Reunião ... 2026_11_06 09_53 GMT-03_00 - Recording.mp4
├── 11 - Pauta PPGCTA - Novembro 2026.md
└── 10 - ATA REUNIÃO PPGCTA - OUTUBRO 2026.docx
```

```bash
./gerador_ata/gerar_ata.sh --verificar   # só mostra o que detectou (vídeo, pauta, modelo, saída)
./gerador_ata/gerar_ata.sh               # gera a ata
./gerador_ata/gerar_ata.sh --help        # todas as opções
```

Para acompanhar o andamento (quanto falta), rode em outra janela do terminal
(Ctrl+C fecha só a tela, sem interromper a geração):

```bash
./gerador_ata/acompanhar.sh
```

O programa detecta os arquivos sozinho:

- **vídeo:** o de data mais recente no nome;
- **pauta:** a do mês do vídeo;
- **modelo:** a ata mais recente de um mês anterior;
- **saída:** `NN - ATA REUNIÃO PPGCTA - <MÊS> <ANO>.docx`.

Ele também avisa sobre erros comuns da pauta, como o mês errado no título ou na ata em
apreciação quando a pauta foi copiada da do mês anterior.

Ao lado da ata, são gerados dois arquivos:

- `*.ATENCAO.md`: pontos para o secretário revisar;
- `*.transcricao.txt`: a transcrição com horários.

A transcrição (~35 min) e o rascunho ficam em cache em `cache/`. Se você corrigir a pauta e
rodar de novo, ele não transcreve outra vez.

## Instalação

```bash
python3 -m venv ~/.local/tools/ataenv
~/.local/tools/ataenv/bin/pip install -r requirements.txt
cp roster.exemplo.json roster.json   # e preencha com os nomes do colegiado
```

Também é preciso:

- o `ffmpeg`;
- o [Claude Code](https://claude.com/claude-code) (`claude`) no `PATH`, já autenticado.

Os caminhos do ambiente Python e do `ffmpeg` estão fixos em `gerar_ata.sh` e em
`transcribe.py` (`FFMPEG`). Ajuste-os se instalar em outro lugar.

`roster.json` lista os docentes e discentes e serve para corrigir os nomes mal
transcritos. Ele **não é versionado** porque tem dados pessoais.

## Arquivos

| Arquivo | Função |
|---|---|
| `gerar_ata.sh` | atalho que ativa o ambiente e grava o log em `cache/ultimo_log.txt` |
| `acompanhar.sh` | mostra o andamento (etapa, % da transcrição, tempo restante), atualizando sozinho |
| `gerar_ata.py` | fluxo principal: transcrição → redação → `.docx` |
| `entradas.py` | detecção automática dos arquivos e verificações da pauta |
| `transcribe.py` | extração de áudio + transcrição em blocos de 10 min, com checkpoint |
| `prompt_template.py` | prompt e JSON Schema da redação |
| `docx_utils.py` | leitura de `.docx`/`.md` e montagem da nova ata a partir do modelo |
| `roster.exemplo.json` | modelo da lista de nomes (`roster.json`) |
