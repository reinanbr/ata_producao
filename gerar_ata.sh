#!/bin/bash
# Atalho: gera a ata usando o ambiente Python já instalado.
#
# Uso (de dentro da pasta ata), depois de colocar o vídeo e a pauta do mês na pasta:
#   ./gerador_ata/gerar_ata.sh               # detecta vídeo, pauta, ata anterior e nome da saída
#   ./gerador_ata/gerar_ata.sh --verificar   # só mostra o que detectou, sem processar
#   ./gerador_ata/gerar_ata.sh --help        # todas as opções
#
# O andamento também fica registrado em gerador_ata/cache/ultimo_log.txt
export TMPDIR=/home/secretaria/.local/tools/tmp
export HF_HOME=/home/secretaria/.local/tools/hf_cache
AQUI="$(dirname "$(readlink -f "$0")")"
mkdir -p "$AQUI/cache" "$TMPDIR"
/home/secretaria/.local/tools/ataenv/bin/python3 -u "$AQUI/gerar_ata.py" "$@" 2>&1 \
  | grep --line-buffered -vE "UserWarning|warnings.warn" | tee "$AQUI/cache/ultimo_log.txt"
exit "${PIPESTATUS[0]}"
