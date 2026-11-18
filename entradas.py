"""Detecção automática dos arquivos do mês na pasta da ata (vídeo, pauta,
ata-modelo do mês anterior e nome da ata de saída) + verificações da pauta.

Convenções de nome esperadas (as mesmas usadas até hoje):
  vídeo : "... 2026_11_06 09_53 GMT-03_00 - Recording.mp4"  (data/hora do Meet)
  pauta : "11 - Pauta PPGCTA - Novembro 2026.docx" (ou .md/.txt)
  ata   : "10 - ATA REUNIÃO PPGCTA - OUTUBRO 2026.docx"
"""
import datetime as dt
import os
import re
import unicodedata

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".wav"}
PAUTA_EXT = {".docx", ".md", ".txt"}


def _norm(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


_MESES_NORM = [_norm(m) for m in MESES]


def meses_citados(texto):
    """Números (1-12) dos meses citados por extenso no texto, na ordem do calendário."""
    t = _norm(texto)
    return [i + 1 for i, m in enumerate(_MESES_NORM) if re.search(rf"\b{m}\b", t)]


def data_por_extenso(d):
    return f"{d.day:02d} de {MESES[d.month - 1]} de {d.year}"


def dia_da_semana(d):
    return DIAS_SEMANA[d.weekday()]


def data_hora_da_gravacao(nome_arquivo):
    """(date, time|None) a partir de '... 2026_11_06 09_53 ...'; (None, None) se não houver."""
    m = re.search(r"(20\d\d)[_-](\d\d)[_-](\d\d)(?:[ _T]+(\d\d)[_:h](\d\d))?", nome_arquivo)
    if not m:
        return None, None
    data = dt.date(int(m[1]), int(m[2]), int(m[3]))
    hora = dt.time(int(m[4]), int(m[5])) if m[4] else None
    return data, hora


def _ano_mes_do_nome(nome):
    meses = meses_citados(nome)
    anos = re.findall(r"\b(20\d\d)\b", nome)
    if len(meses) == 1 and anos:
        return int(anos[-1]), meses[0]
    return None


def _listar(pasta, exts):
    out = []
    for f in sorted(os.listdir(pasta)):
        p = os.path.join(pasta, f)
        if f.startswith(("~$", ".")) or not os.path.isfile(p):
            continue
        if os.path.splitext(f)[1].lower() in exts:
            out.append(p)
    return out


def achar_video(pasta):
    """O vídeo com a data mais recente no nome (empate/sem data: o mais novo no disco)."""
    videos = _listar(pasta, VIDEO_EXT)
    if not videos:
        raise FileNotFoundError(f"Nenhum vídeo/áudio encontrado em {pasta}")

    def chave(p):
        d, h = data_hora_da_gravacao(os.path.basename(p))
        return (d or dt.date.min, h or dt.time.min, os.path.getmtime(p))

    return max(videos, key=chave)


def achar_pauta(pasta, data):
    candidatas = [p for p in _listar(pasta, PAUTA_EXT) if "pauta" in _norm(os.path.basename(p))]
    nome_mes = _MESES_NORM[data.month - 1]
    boas = [p for p in candidatas
            if re.search(rf"\b{nome_mes}\b", _norm(os.path.basename(p)))
            and str(data.year) in os.path.basename(p)]
    if not boas:  # fallback: número do mês no início do nome ("11 - Pauta ...")
        boas = [p for p in candidatas if re.match(rf"0?{data.month}\b", os.path.basename(p))]
    if not boas:
        raise FileNotFoundError(
            f"Pauta de {MESES[data.month - 1]}/{data.year} não encontrada em {pasta} "
            "(esperado algo como '11 - Pauta PPGCTA - Novembro 2026.docx'); use --pauta.")
    return max(boas, key=os.path.getmtime)


def achar_modelo(pasta, data, excluir=None):
    """A ata (.docx) mais recente ANTERIOR ao mês da reunião."""
    candidatas = []
    for p in _listar(pasta, {".docx"}):
        nome = os.path.basename(p)
        if excluir and os.path.abspath(p) == os.path.abspath(excluir):
            continue
        if not re.search(r"\bata\b", _norm(nome)):
            continue
        am = _ano_mes_do_nome(nome)
        if am and am < (data.year, data.month):
            candidatas.append((am, os.path.getmtime(p), p))
    if not candidatas:
        raise FileNotFoundError(f"Nenhuma ata anterior a {MESES[data.month - 1]}/{data.year} em {pasta}; use --template.")
    return max(candidatas)[2]


def nome_saida(pasta, data):
    return os.path.join(
        pasta, f"{data.month:02d} - ATA REUNIÃO PPGCTA - {MESES[data.month - 1].upper()} {data.year}.docx")


def verificar_pauta(texto_pauta, data):
    """Avisos sobre erros de cópia comuns na pauta (mês do título, mês da ata em apreciação)."""
    avisos = []
    linhas = [l.strip(" *\t") for l in texto_pauta.splitlines() if l.strip(" *\t")]
    titulo = " ".join(linhas[:2])
    errados = [m for m in meses_citados(titulo) if m != data.month]
    if errados:
        avisos.append(
            f"O título da pauta cita {', '.join(MESES[m - 1].upper() for m in errados)}, mas a reunião foi em "
            f"{data_por_extenso(data)} (provável erro de cópia da pauta anterior).")

    mes_anterior = 12 if data.month == 1 else data.month - 1
    m = re.search(r"aprecia[cç][aã]o da ata[^\n]*", texto_pauta, re.IGNORECASE)
    if m:
        citados = meses_citados(m.group(0))
        if citados and mes_anterior not in citados:
            avisos.append(
                f"A pauta diz \"{m.group(0).strip(' *')}\", mas a ata a ser apreciada deveria ser a de "
                f"{MESES[mes_anterior - 1]} (reunião anterior).")
    return avisos
