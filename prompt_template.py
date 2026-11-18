"""Monta o prompt e o JSON Schema usados na chamada `claude -p` que redige o
corpo da nova ata, no mesmo estilo/estrutura da ata-modelo do mês anterior.
"""
import json

SCHEMA = {
    "type": "object",
    "properties": {
        "hora_inicio_estimada": {
            "type": "string",
            "description": "Horário estimado de início da reunião, formato HH:MMh",
        },
        "data_reuniao": {
            "type": "string",
            "description": "Data da reunião, formato DD de mês de AAAA",
        },
        "corpo_ata_markdown": {
            "type": "string",
            "description": (
                "Texto integral do corpo da ata, em um único parágrafo corrido, "
                "no estilo formal da ata-modelo fornecida. Use **a)**, **b)** etc. "
                "para marcar em negrito apenas as letras dos subitens de II e III, "
                "exatamente como no modelo. Não inclua o bloco de assinatura."
            ),
        },
        "pontos_de_atencao": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Lista curta de ressalvas para o secretário revisar antes de "
                "finalizar: nomes incertos na transcrição, horário estimado por "
                "não ter sido dito explicitamente, presença não confirmada de "
                "docentes/discentes que não falaram na gravação, etc."
            ),
        },
    },
    "required": ["hora_inicio_estimada", "data_reuniao", "corpo_ata_markdown", "pontos_de_atencao"],
}


def build_prompt(pauta_text, transcript_text, roster, template_body_text, contexto=None):
    """contexto: dict opcional com dados confiáveis extraídos dos nomes dos arquivos
    (data da reunião, início da gravação, avisos automáticos sobre a pauta)."""
    roster_json = json.dumps(roster, ensure_ascii=False, indent=2)
    contexto = contexto or {}
    dados = []
    if contexto.get("data_reuniao"):
        dados.append(f"- Data da reunião: {contexto['data_reuniao']}.")
    if contexto.get("inicio_gravacao"):
        dados.append(
            f"- A gravação começou às {contexto['inicio_gravacao']}; as marcas [HH:MM:SS] da transcrição "
            "já são horários de relógio (hora local).")
    if contexto.get("ata_anterior"):
        dados.append(f"- A ata-modelo abaixo é a da reunião anterior ({contexto['ata_anterior']}).")
    for aviso in contexto.get("avisos", []):
        dados.append(f"- Aviso automático sobre a pauta: {aviso}")
    bloco_dados = ""
    if dados:
        bloco_dados = ("=== DADOS CONFIÁVEIS DA REUNIÃO (extraídos dos arquivos; prevalecem sobre a pauta "
                       "em caso de divergência) ===\n" + "\n".join(dados) + "\n\n")
    return f"""Você é o secretário do Programa de Pós-Graduação em Ciência e Tecnologia \
Ambiental (PPGCTA) e precisa redigir a ata oficial da reunião ordinária do Colegiado, \
seguindo EXATAMENTE o mesmo estilo e estrutura narrativa da ata-modelo abaixo (parágrafo \
único corrido, com seções numeradas em romano I/II/III/IV e subitens em letras a), b), c)...).

{bloco_dados}=== ATA-MODELO (mês anterior, use como referência de estilo/estrutura, NÃO repita o conteúdo dela) ===
{template_body_text}

=== PAUTA DA REUNIÃO ATUAL (fonte primária dos pontos e decisões já registradas) ===
{pauta_text}

=== LISTA DE DOCENTES/DISCENTES CONHECIDOS DO PROGRAMA (use para corrigir nomes mal \
transcritos pelo reconhecimento de voz — a transcrição abaixo é de voz e tem erros \
fonéticos, especialmente em nomes próprios) ===
{roster_json}

=== TRANSCRIÇÃO DA GRAVAÇÃO DA REUNIÃO (com erros de reconhecimento de voz; use o \
roster acima para corrigir nomes) ===
{transcript_text}

Instruções:
1. Siga a pauta para a estrutura dos itens II (informes) e III (ordem do dia) e para as \
   decisões já indicadas nela (aprovado/aprovada etc.).
2. Sempre que a pauta pedir explicitamente para "extrair os pontos mais relevantes da \
   discussão para registro em ata" (ou pedido equivalente feito durante a reunião), releia \
   o trecho correspondente da transcrição e escreva um resumo fiel e conciso dos principais \
   argumentos e da decisão final — não apenas "foi discutido e aprovado".
3. Reconstrua a lista de presença a partir de quem efetivamente fala na transcrição, \
   cruzando com o roster; quem não aparece falando e não está na lista de ausências \
   justificadas da pauta deve ir para pontos_de_atencao, não para a lista de presentes.
4. Estime o horário de início pelo momento em que a reunião é formalmente aberta na \
   transcrição (use as marcas de horário de relógio, se houver; senão o horário convocado na \
   pauta), e explique a estimativa em pontos_de_atencao.
5. Não invente nomes completos que não constem do roster nem da pauta nem da transcrição — \
   quando incerto, mantenha a forma como aparece no roster/pauta e registre a incerteza em \
   pontos_de_atencao.
6. Feche o corpo da ata com a frase de encerramento no mesmo padrão do modelo (menção ao \
   secretário Reinan Bezerra redigindo a ata, submissão à aprovação do colegiado, assinatura \
   do coordenador) — mas NÃO inclua o bloco de assinatura separado, só o parágrafo corrido.
7. A pauta costuma ser copiada da do mês anterior e pode conter erros (mês errado no título, \
   mês errado da ata em apreciação, datas). Redija a ata com a informação correta (os DADOS \
   CONFIÁVEIS acima prevalecem) e registre cada correção feita em pontos_de_atencao.
"""
