"""Extração de áudio (ffmpeg estático) + transcrição (faster-whisper, CPU).

A transcrição é feita em blocos de ~10 min, cortados em pontos de silêncio:
  - usa pouca RAM (só um bloco de áudio na memória por vez);
  - grava um checkpoint a cada bloco: se o processo cair, a próxima execução
    retoma do último bloco concluído em vez de recomeçar do zero;
  - mostra progresso e tempo restante estimado.
"""
import datetime as dt
import json
import os
import subprocess
import time
import wave

import numpy as np

FFMPEG = os.path.abspath("/home/secretaria/.local/tools/bin/ffmpeg")
SR = 16000

# Configuração padrão (escolhida por benchmark nesta máquina: 4 núcleos, ~3 GB livres).
PADRAO = {
    "modelo": "medium",
    "beam_size": 1,
    "batch_size": 4,  # 0 = modo sequencial (sem lote)
    "bloco_s": 600,
}


def extract_audio(video_path, wav_path):
    cmd = [FFMPEG, "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", wav_path]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return wav_path


def _blocos(wav_path, bloco_s, busca_s=15):
    """Gera (inicio_s, fim_s) cobrindo o áudio, cortando no trecho de menor
    energia a até ±busca_s de cada fronteira nominal (evita cortar palavras)."""
    with wave.open(wav_path, "rb") as wf:
        assert wf.getsampwidth() == 2 and wf.getnchannels() == 1 and wf.getframerate() == SR
        n = wf.getnframes()
        cortes = [0]
        alvo = bloco_s * SR
        while alvo < n - busca_s * SR:
            ini = max(alvo - busca_s * SR, cortes[-1] + SR)
            wf.setpos(ini)
            x = np.frombuffer(wf.readframes(2 * busca_s * SR), dtype=np.int16).astype(np.float32)
            quadro = SR // 10  # janelas de 100 ms
            k = len(x) // quadro
            energia = (x[: k * quadro].reshape(k, quadro) ** 2).mean(axis=1)
            cortes.append(ini + int(np.argmin(energia)) * quadro)
            alvo = cortes[-1] + bloco_s * SR
        cortes.append(n)
    return [(a / SR, b / SR) for a, b in zip(cortes, cortes[1:])]


def _ler_trecho(wav_path, ini_s, fim_s):
    with wave.open(wav_path, "rb") as wf:
        wf.setpos(int(ini_s * SR))
        raw = wf.readframes(int((fim_s - ini_s) * SR))
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _fmt_min(seg):
    seg = int(seg)
    return f"{seg // 3600}h{seg % 3600 // 60:02d}" if seg >= 3600 else f"{seg // 60} min"


def transcribe(wav_path, checkpoint_path, modelo=PADRAO["modelo"], beam_size=PADRAO["beam_size"],
               batch_size=PADRAO["batch_size"], bloco_s=PADRAO["bloco_s"], language="pt"):
    """Retorna lista de segmentos [(start, end, text)] com tempos absolutos (s).
    Retoma de checkpoint_path se existir um checkpoint compatível."""
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    blocos = _blocos(wav_path, bloco_s)
    total = blocos[-1][1]
    config = {"modelo": modelo, "beam_size": beam_size, "batch_size": batch_size, "blocos": blocos}

    estado = {"config": config, "blocos_feitos": 0, "segmentos": []}
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path, encoding="utf-8") as f:
            salvo = json.load(f)
        if salvo.get("config") == json.loads(json.dumps(config)):
            estado = salvo
            print(f"      Retomando checkpoint: {estado['blocos_feitos']}/{len(blocos)} blocos já transcritos.", flush=True)

    model = WhisperModel(modelo, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    pipe = BatchedInferencePipeline(model) if batch_size else None

    t0 = time.time()
    feito_nesta_execucao = 0.0
    for i in range(estado["blocos_feitos"], len(blocos)):
        ini, fim = blocos[i]
        audio = _ler_trecho(wav_path, ini, fim)
        if pipe:
            it, _ = pipe.transcribe(audio, language=language, beam_size=beam_size, batch_size=batch_size)
        else:
            it, _ = model.transcribe(audio, language=language, beam_size=beam_size, vad_filter=True)
        for s in it:
            texto = s.text.strip()
            if texto:
                estado["segmentos"].append((round(ini + s.start, 2), round(ini + s.end, 2), texto))
        estado["blocos_feitos"] = i + 1

        tmp = checkpoint_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False)
        os.replace(tmp, checkpoint_path)

        feito_nesta_execucao += fim - ini
        decorrido = time.time() - t0
        restante = (total - fim) * decorrido / feito_nesta_execucao
        print(f"      {100 * fim / total:3.0f}%  ({_fmt_min(fim)} de {_fmt_min(total)} de áudio)  "
              f"decorrido {_fmt_min(decorrido)}, faltam ~{_fmt_min(restante)}", flush=True)

    return [tuple(s) for s in estado["segmentos"]]


def segments_to_text(segments, inicio_gravacao=None, agrupar_s=30):
    """Texto compacto para o prompt: uma marca de tempo a cada ~agrupar_s segundos.
    Com inicio_gravacao (datetime), as marcas viram horário de relógio [10:02:15];
    sem ele, tempo decorrido da gravação [0:07:15]."""
    def marca(t):
        if inicio_gravacao:
            return (inicio_gravacao + dt.timedelta(seconds=t)).strftime("%H:%M:%S")
        t = int(t)
        return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"

    linhas, atual, inicio_linha = [], [], None
    for s, _e, txt in segments:
        if inicio_linha is None or s - inicio_linha >= agrupar_s:
            if atual:
                linhas.append(f"[{marca(inicio_linha)}] " + " ".join(atual))
            atual, inicio_linha = [], s
        atual.append(txt.strip())
    if atual:
        linhas.append(f"[{marca(inicio_linha)}] " + " ".join(atual))
    return "\n".join(linhas)
