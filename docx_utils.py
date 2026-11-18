"""Utilidades para ler o texto de um .docx e para montar uma nova ata a partir
de um .docx-modelo, preservando cabeçalho/rodapé/logos/estilos do modelo.

Técnica: edição direta do XML (zipfile + regex) em vez de python-docx, porque
o modelo usa customXML/headers/footers/fonts embutidas que python-docx não
reproduz com fidelidade ao reescrever o documento.
"""
import html
import os
import re
import shutil
import zipfile

RUN_PLAIN = (
    '<w:r w:rsidDel="00000000" w:rsidR="00000000" w:rsidRPr="00000000">'
    '<w:rPr><w:rFonts w:ascii="Arial" w:cs="Arial" w:eastAsia="Arial" w:hAnsi="Arial"/>'
    '<w:rtl w:val="0"/></w:rPr><w:t xml:space="preserve">{}</w:t></w:r>'
)
RUN_BOLD = (
    '<w:r w:rsidDel="00000000" w:rsidR="00000000" w:rsidRPr="00000000">'
    '<w:rPr><w:rFonts w:ascii="Arial" w:cs="Arial" w:eastAsia="Arial" w:hAnsi="Arial"/>'
    '<w:b w:val="1"/><w:bCs w:val="1"/><w:rtl w:val="0"/></w:rPr>'
    '<w:t xml:space="preserve">{}</w:t></w:r>'
)


def read_text(docx_path):
    """Extrai o texto visível de um .docx (parágrafos concatenados, \\n entre eles)."""
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    xml = re.sub(r"<w:br/>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    return html.unescape(text)


def _clean_markdown(text):
    """Limpa um .md exportado do Google Docs: remove imagens embutidas em base64,
    troca links [texto](url) pelo texto e desfaz escapes como '\\-'."""
    # definições de imagem embutida: [image1]: <data:image/png;base64,....>
    text = re.sub(r"^\[[^\]]+\]:\s*<data:[^>]*>\s*$", "", text, flags=re.MULTILINE)
    # referências a imagens: ![][image1] ou ![alt](url)
    text = re.sub(r"!\[[^\]]*\](\[[^\]]*\]|\([^)]*\))", "", text)
    text = re.sub(r"\*\*[ \t]*\*\*", "", text)  # negrito que só envolvia imagens
    # links [texto](url) -> texto
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    # escapes do Markdown: \- \. \* etc.
    text = re.sub(r"\\([\\`*_{}\[\]()#+\-.!>|~])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_any_text(path):
    """Lê o texto de uma pauta/ata em .docx, .md ou .txt."""
    if os.path.splitext(path)[1].lower() == ".docx":
        return read_text(path)
    with open(path, encoding="utf-8") as f:
        return _clean_markdown(f.read())


def _markdown_bold_to_runs(markdown_text):
    """Converte '**a)** texto **b)** texto' em uma lista de runs XML (negrito/normal)."""
    parts = re.split(r"\*\*(.*?)\*\*", markdown_text)
    runs = []
    for i, seg in enumerate(parts):
        if seg == "":
            continue
        template = RUN_BOLD if i % 2 == 1 else RUN_PLAIN
        runs.append(template.format(html.escape(seg, quote=False)))
    return "".join(runs)


def build_docx(template_path, body_markdown, out_path):
    """Clona template_path para out_path, substituindo o 1º parágrafo do corpo
    (word/document.xml) pelo texto em body_markdown (** marca negrito).
    Mantém cabeçalho/rodapé/imagens/fontes/bloco de assinatura do modelo.
    """
    with zipfile.ZipFile(template_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")

    paras = re.findall(r"<w:p .*?</w:p>", xml, re.DOTALL)
    if not paras:
        raise ValueError(f"Nenhum parágrafo encontrado em {template_path}")
    p0 = paras[0]
    m = re.match(r"(<w:p [^>]*>)(<w:pPr>.*?</w:pPr>)", p0, re.DOTALL)
    if not m:
        raise ValueError("Não foi possível localizar <w:pPr> do 1º parágrafo do modelo")
    open_tag, ppr = m.group(1), m.group(2)

    new_p0 = open_tag + ppr + _markdown_bold_to_runs(body_markdown) + "</w:p>"
    new_xml = xml.replace(p0, new_p0, 1)
    if new_xml == xml:
        raise ValueError("Substituição do corpo da ata falhou (XML não mudou)")

    tmp_out = out_path + ".tmp"
    with zipfile.ZipFile(template_path) as zin, zipfile.ZipFile(
        tmp_out, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = new_xml.encode("utf-8")
            zout.writestr(item, data)
    os.replace(tmp_out, out_path)
    return out_path
