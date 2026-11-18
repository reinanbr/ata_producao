#!/bin/bash
# Mostra o andamento da geração da ata, atualizando sozinho.
# Rode em outra janela do terminal enquanto o gerar_ata.sh trabalha:
#
#   ./gerador_ata/acompanhar.sh        # atualiza a cada 5 s
#   ./gerador_ata/acompanhar.sh 30     # atualiza a cada 30 s
#
# Ctrl+C fecha só esta tela — NÃO interrompe a geração da ata.
AQUI="$(dirname "$(readlink -f "$0")")"
LOG="$AQUI/cache/ultimo_log.txt"
INTERVALO="${1:-5}"

barra() {  # $1 = porcentagem (0-100)
  local largura=40 cheio=$(( $1 * 40 / 100 ))
  printf '  ['
  printf '%*s' "$cheio" '' | tr ' ' '#'
  printf '%*s' $(( largura - cheio )) '' | tr ' ' '.'
  printf '] %3d%%\n' "$1"
}

while true; do
  clear 2>/dev/null || printf '\n\n'
  echo "=== Geração da ata — $(date +%H:%M:%S) ==="
  echo
  if [ ! -f "$LOG" ]; then
    echo "Ainda não há log em $LOG."
    sleep "$INTERVALO"
    continue
  fi

  grep -E '^(Reunião|Saída) ' "$LOG"
  echo

  etapa=$(grep -E '^\[[0-9-]+/5\]' "$LOG" | tail -1)
  echo "Etapa: ${etapa:-iniciando ...}"

  case "$etapa" in
    "[2/5]"*)
      progresso=$(grep -E '^[[:space:]]+[0-9]+%' "$LOG" | tail -1)
      if [ -n "$progresso" ]; then
        barra "$(echo "$progresso" | grep -oE '[0-9]+%' | head -1 | tr -d %)"
        echo "  $(echo "$progresso" | sed 's/^[[:space:]]*//')"
        echo "  (depois da transcrição: + ~5-10 min para redigir e montar o .docx)"
      else
        echo "  Carregando o modelo / primeiro bloco de 10 min ainda em andamento ..."
      fi
      ;;
    "[4/5]"*)
      echo "  A redação pelo Claude costuma levar 5-10 min."
      ;;
  esac

  parado=$(( ( $(date +%s) - $(stat -c %Y "$LOG") ) / 60 ))
  echo
  echo "Última novidade no log: há $parado min (a transcrição atualiza a cada bloco, ~7 min)"

  pid=$(pgrep -f "gerar_ata.py" | head -1)
  if [ -n "$pid" ]; then
    echo "Processo: rodando (PID $pid)"
    echo
    echo "(Ctrl+C fecha esta tela sem interromper a geração)"
  else
    echo "Processo: terminou / não está rodando."
    echo
    if grep -q '^Pronto em' "$LOG"; then
      sed -n '/^Pronto em/,$p' "$LOG"
    else
      echo "Últimas linhas do log:"
      tail -5 "$LOG"
    fi
    exit 0
  fi
  sleep "$INTERVALO"
done
