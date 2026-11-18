#!/usr/bin/env python3
"""Gera a ata do colegiado do PPGCTA a partir do vídeo da reunião, da pauta e
da ata do mês anterior (usada como modelo de estilo/formatação).

Uso mais simples (de dentro da pasta ata) — detecta tudo sozinho:
    ./gerador_ata/gerar_ata.sh

  -> vídeo  : o de data mais recente no nome (".. 2026_11_06 09_53 .. .mp4")
  -> pauta  : "NN - Pauta PPGCTA - <Mês> <Ano>" (.docx, .md ou .txt) do mês do vídeo
  -> modelo : a ata .docx mais recente de um mês anterior
  -> saída  : "NN - ATA REUNIÃO PPGCTA - <MÊS> <ANO>.docx"

Só conferir o que foi detectado, sem processar nada:
    ./gerador_ata/gerar_ata.sh --verificar

Qualquer item pode ser informado à mão (--video, --pauta, --template, --out).
Transcrição e rascunho ficam em gerador_ata/cache/: rodar de novo depois de
corrigir a pauta NÃO refaz a transcrição (~35 min) — só a redação.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import docx_utils  # noqa: E402
import entradas  # noqa: E402
import prompt_template  # noqa: E402
import transcribe  # noqa: E402

ROSTER_DEFAULT = os.path.join(AQUI, "roster.json")
CACHE = os.path.join(AQUI, "cache")


def call_claude(prompt, schema, max_budget_usd=5.0, tentativas=2):
    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--json-schema", json.dumps(schema),
        "--restricted",
        "--max-budget-usd", str(max_budget_usd),
    ]
    erro = None
    for n in range(1, tentativas + 1):
        # prompt via stdin: evita o limite de tamanho de argumento da linha de comando
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=1800)
        if result.returncode == 0:
            outer = json.loads(result.stdout)
            if "structured_output" in outer:
                return outer["structured_output"]
            payload_text = outer.get("result") or outer.get("response") or outer.get("content")
            if payload_text is not None:
                return json.loads(payload_text)
            erro = f"Não encontrei o payload na resposta da CLI: {outer!r}"[:2000]
        else:
            erro = f"claude -p falhou (code={result.returncode}): {(result.stderr or result.stdout)[-2000:]}"
        if n < tentativas:
            print(f"      Tentativa {n} falhou, tentando de novo em 30 s ...\n      {erro[:300]}", flush=True)
            time.sleep(30)
    raise RuntimeError(erro)


def _hash_arquivo_rapido(path):
    """Identifica o vídeo por nome + tamanho + 1 MB do meio (rápido mesmo para 500 MB)."""
    h = hashlib.sha1()
    tam = os.path.getsize(path)
    h.update(f"{os.path.basename(path)}|{tam}".encode())
    with open(path, "rb") as f:
        f.seek(tam // 2)
        h.update(f.read(1 << 20))
    return h.hexdigest()[:16]


def _resolver_entradas(args):
    pasta = os.path.abspath(args.pasta)
    video = args.video or entradas.achar_video(pasta)
    data, hora = entradas.data_hora_da_gravacao(os.path.basename(video))
    if args.data:
        data = dt.date.fromisoformat(args.data)
    if data is None:
        raise SystemExit("Não consegui ler a data da reunião no nome do vídeo; informe --data AAAA-MM-DD.")
    out = args.out or entradas.nome_saida(pasta, data)
    pauta = args.pauta or entradas.achar_pauta(pasta, data)
    template = args.template or entradas.achar_modelo(pasta, data, excluir=out)
    return pasta, video, data, hora, pauta, template, out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pasta", default=os.path.dirname(AQUI), help="Pasta com vídeo/pauta/atas (padrão: a pasta ata)")
    ap.add_argument("--video")
    ap.add_argument("--pauta", help="Pauta em .docx, .md ou .txt")
    ap.add_argument("--template", help="Ata do mês anterior (modelo)")
    ap.add_argument("--out", help="Arquivo .docx da nova ata")
    ap.add_argument("--data", help="Data da reunião AAAA-MM-DD (se não der para ler do nome do vídeo)")
    ap.add_argument("--roster", default=ROSTER_DEFAULT)
    ap.add_argument("--model", "--modelo-whisper", dest="modelo", default=transcribe.PADRAO["modelo"],
                    help="Modelo faster-whisper (medium, large-v3, ...)")
    ap.add_argument("--transcript", help="transcript.json já pronto (pula a transcrição)")
    ap.add_argument("--verificar", action="store_true", help="Só mostra o que foi detectado e sai")
    ap.add_argument("--sobrescrever", action="store_true", help="Permite substituir uma ata .docx já existente")
    ap.add_argument("--refazer-transcricao", action="store_true", help="Ignora a transcrição em cache")
    ap.add_argument("--refazer-redacao", action="store_true", help="Ignora o rascunho em cache e chama o Claude de novo")
    ap.add_argument("--orcamento-usd", type=float, default=5.0, help="Teto de gasto da chamada ao Claude")
    args = ap.parse_args()

    t_total = time.time()
    pasta, video, data, hora, pauta, template, out = _resolver_entradas(args)
    base_out = os.path.splitext(out)[0]
    pauta_text = docx_utils.read_any_text(pauta)
    avisos = entradas.verificar_pauta(pauta_text, data)

    print("Reunião :", entradas.data_por_extenso(data), f"({entradas.dia_da_semana(data)})",
          f"— gravação iniciada às {hora:%H:%M}" if hora else "")
    print("Vídeo   :", os.path.basename(video))
    print("Pauta   :", os.path.basename(pauta))
    print("Modelo  :", os.path.basename(template))
    print("Saída   :", os.path.basename(out))
    for a in avisos:
        print("ATENÇÃO :", a)

    problemas = [f"não encontrado: {p}" for p in (video, pauta, template) if not os.path.isfile(p)]
    if not os.path.isfile(args.roster):
        problemas.append(f"lista de nomes não encontrada: {args.roster} "
                         "(copie roster.exemplo.json para roster.json e preencha)")
    if os.path.exists(out) and not args.sobrescrever:
        problemas.append(f"a ata de saída já existe (use --sobrescrever ou --out outro_nome.docx): {out}")
    if not shutil.which("claude"):
        problemas.append("comando `claude` não encontrado no PATH")
    if problemas:
        raise SystemExit("\nNão dá para continuar:\n  - " + "\n  - ".join(problemas))
    if args.verificar:
        print("\n(--verificar: nada foi processado)")
        return

    with open(args.roster, encoding="utf-8") as f:
        roster = json.load(f)
    os.makedirs(CACHE, exist_ok=True)

    # ---- 1-2. Transcrição (com cache e checkpoint) ----
    if args.transcript:
        with open(args.transcript, encoding="utf-8") as f:
            segments = [(x["start"], x["end"], x["text"]) if isinstance(x, dict) else tuple(x)
                        for x in json.load(f)["segments"]]
        print(f"\n[1-2/5] Transcrição informada: {len(segments)} segmentos.", flush=True)
    else:
        chave = f"{_hash_arquivo_rapido(video)}_{args.modelo}"
        cache_transcr = os.path.join(CACHE, f"transcricao_{chave}.json")
        checkpoint = os.path.join(CACHE, f"transcricao_{chave}.parcial.json")
        if args.refazer_transcricao:
            for p in (cache_transcr, checkpoint):
                if os.path.exists(p):
                    os.remove(p)
        if os.path.exists(cache_transcr):
            with open(cache_transcr, encoding="utf-8") as f:
                segments = [tuple(s) for s in json.load(f)["segments"]]
            print(f"\n[1-2/5] Transcrição já feita antes (cache): {len(segments)} segmentos.", flush=True)
        else:
            t0 = time.time()
            print("\n[1/5] Extraindo áudio ...", flush=True)
            tmpdir = os.environ.get("TMPDIR") or tempfile.gettempdir()
            wav_path = os.path.join(tmpdir, f"ata_audio_{chave}.wav")
            transcribe.extract_audio(video, wav_path)
            print(f"[2/5] Transcrevendo (faster-whisper {args.modelo}, em blocos de 10 min) ...", flush=True)
            segments = transcribe.transcribe(wav_path, checkpoint, modelo=args.modelo)
            with open(cache_transcr, "w", encoding="utf-8") as f:
                json.dump({"video": os.path.basename(video), "segments": segments}, f, ensure_ascii=False)
            os.remove(checkpoint)
            os.remove(wav_path)
            print(f"      {len(segments)} segmentos em {transcribe._fmt_min(time.time() - t0)}.", flush=True)

    inicio_gravacao = dt.datetime.combine(data, hora) if hora else None
    transcript_for_prompt = transcribe.segments_to_text(segments, inicio_gravacao)
    with open(base_out + ".transcricao.txt", "w", encoding="utf-8") as f:
        f.write(transcript_for_prompt + "\n")

    # ---- 3. Pauta + modelo ----
    print("[3/5] Lendo pauta e ata-modelo ...", flush=True)
    template_text = docx_utils.read_text(template)
    am = entradas._ano_mes_do_nome(os.path.basename(template))
    contexto = {
        "data_reuniao": f"{entradas.data_por_extenso(data)} ({entradas.dia_da_semana(data)})",
        "inicio_gravacao": f"{hora:%H:%M}" if hora else None,
        "ata_anterior": f"{entradas.MESES[am[1] - 1]} de {am[0]}" if am else None,
        "avisos": avisos,
    }

    # ---- 4. Redação (com cache por conteúdo do prompt) ----
    prompt = prompt_template.build_prompt(pauta_text, transcript_for_prompt, roster, template_text, contexto)
    chave_r = hashlib.sha256((prompt + json.dumps(prompt_template.SCHEMA)).encode()).hexdigest()[:16]
    cache_rasc = os.path.join(CACHE, f"rascunho_{chave_r}.json")
    if os.path.exists(cache_rasc) and not args.refazer_redacao:
        with open(cache_rasc, encoding="utf-8") as f:
            draft = json.load(f)
        print("[4/5] Mesmas entradas de antes: reaproveitando o rascunho em cache (sem nova chamada).", flush=True)
    else:
        print(f"[4/5] Chamando `claude -p` para redigir a ata (prompt ~{len(prompt) // 4000}k tokens) ...", flush=True)
        t0 = time.time()
        draft = call_claude(prompt, prompt_template.SCHEMA, max_budget_usd=args.orcamento_usd)
        with open(cache_rasc, "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False, indent=1)
        print(f"      Redação pronta em {transcribe._fmt_min(time.time() - t0)}.", flush=True)

    # ---- 5. .docx final + pontos de atenção ----
    print("[5/5] Montando o .docx final ...", flush=True)
    docx_utils.build_docx(template, draft["corpo_ata_markdown"], out)

    attention_path = base_out + ".ATENCAO.md"
    with open(attention_path, "w", encoding="utf-8") as f:
        f.write(f"# Pontos de atenção — {draft.get('data_reuniao', '')}\n\n")
        f.write(f"Horário de início estimado: {draft.get('hora_inicio_estimada', '?')}\n\n")
        if avisos:
            f.write("## Avisos automáticos sobre a pauta\n\n")
            for a in avisos:
                f.write(f"- {a}\n")
            f.write("\n## Revisar na ata\n\n")
        for item in draft.get("pontos_de_atencao", []):
            f.write(f"- {item}\n")
        f.write(f"\nPara conferir trechos, veja a transcrição com horários: "
                f"{os.path.basename(base_out)}.transcricao.txt\n")

    print(f"\nPronto em {transcribe._fmt_min(time.time() - t_total)}:\n  {out}\n  {attention_path}\n"
          f"  {base_out}.transcricao.txt")


if __name__ == "__main__":
    main()
