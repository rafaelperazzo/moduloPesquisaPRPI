import io
import os
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Canvas com duas passagens para calcular o total real de páginas (Página X de Y)."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))
        # Rodapé inferior
        page_text = f"Página {self._pageNumber} de {page_count}"
        self.drawRightString(landscape(A4)[0] - 15 * mm, 10 * mm, page_text)
        self.drawString(15 * mm, 10 * mm, "Sistema de Gestão de Pesquisa - UFCA")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(15 * mm, 14 * mm, landscape(A4)[0] - 15 * mm, 14 * mm)
        self.restoreState()


def gerar_pdf_resultado_edital(descricao, mensagem, lista_projetos, total, brasao_path=None):
    """
    Gera o relatório de resultado de edital em formato A4 Paisagem,
    com repetição de cabeçalho de tabela e quebra de página automática.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=18 * mm
    )

    styles = getSampleStyleSheet()

    # Estilos de texto
    style_inst = ParagraphStyle('Inst', fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#1E293B"))
    style_subinst = ParagraphStyle('SubInst', fontName='Helvetica', fontSize=7, leading=9, alignment=TA_CENTER, textColor=colors.HexColor("#334155"))
    style_titulo = ParagraphStyle('Tit', fontName='Helvetica-Bold', fontSize=14, leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#0F172A"))
    style_desc = ParagraphStyle('Desc', fontName='Helvetica', fontSize=10, leading=12, alignment=TA_CENTER, textColor=colors.HexColor("#475569"))
    style_msg = ParagraphStyle('Msg', fontName='Helvetica-Bold', fontSize=11, leading=14, alignment=TA_CENTER, textColor=colors.HexColor("#047857"))
    
    # Estilos das Células
    th_style = ParagraphStyle('TH', fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=TA_CENTER, textColor=colors.white)
    cell_center = ParagraphStyle('CC', fontName='Helvetica', fontSize=7, leading=8.5, alignment=TA_CENTER, textColor=colors.HexColor("#1E293B"))
    cell_left = ParagraphStyle('CL', fontName='Helvetica', fontSize=7, leading=8.5, alignment=TA_LEFT, textColor=colors.HexColor("#1E293B"))
    cell_left_bold = ParagraphStyle('CLB', fontName='Helvetica-Bold', fontSize=7, leading=8.5, alignment=TA_LEFT, textColor=colors.HexColor("#1E293B"))

    story = []

    # 1. Cabeçalho Institucional
    story.append(Paragraph("MINISTÉRIO DA EDUCAÇÃO", style_subinst))
    story.append(Paragraph("UNIVERSIDADE FEDERAL DO CARIRI", style_inst))
    story.append(Paragraph("PRÓ-REITORIA DE PESQUISA, INOVAÇÃO E PÓS-GRADUAÇÃO — COORDENADORIA DE PESQUISA", style_subinst))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Propostas Submetidas a Edital", style_titulo))
    story.append(Paragraph(str(descricao), style_desc))
    if mensagem:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(str(mensagem), style_msg))
    story.append(Spacer(1, 4 * mm))

    # 2. Montagem da Tabela de Projetos
    # Largura disponível: 297mm - 24mm = 273mm
    col_widths = [
        12 * mm,  # Id
        28 * mm,  # Categoria
        52 * mm,  # Proponente
        14 * mm,  # UA
        20 * mm,  # Prioridade
        15 * mm,  # Score
        72 * mm,  # Título
        18 * mm,  # Solicitadas
        18 * mm,  # Concedidas
        24 * mm   # OBS
    ]

    table_data = [[
        Paragraph("ID", th_style),
        Paragraph("Categoria", th_style),
        Paragraph("Proponente", th_style),
        Paragraph("UA", th_style),
        Paragraph("Prioridade", th_style),
        Paragraph("Score", th_style),
        Paragraph("Título do Projeto", th_style),
        Paragraph("Bolsas Solicit.", th_style),
        Paragraph("Bolsas Conced.", th_style),
        Paragraph("OBS", th_style),
    ]]

    for linha in lista_projetos:
        # Categoria (linha[2])
        cat = "PROJETO NOVO" if linha[2] == 1 else ("PROJETO EM ANDAMENTO" if linha[2] == 0 else str(linha[2]))
        
        # Limpeza simples de tags em OBS
        obs_texto = str(linha[19] or "").replace("<BR>", " ").replace("<br>", " ")
        
        table_data.append([
            Paragraph(str(linha[0]), cell_center),
            Paragraph(cat, cell_center),
            Paragraph(str(linha[3] or ""), cell_left_bold),
            Paragraph(str(linha[5] or ""), cell_center),
            Paragraph(str(linha[16] or ""), cell_center),
            Paragraph(str(linha[6] or "0"), cell_center),
            Paragraph(str(linha[7] or ""), cell_left),
            Paragraph(str(linha[17] or "0"), cell_center),
            Paragraph(str(linha[18] or "0"), cell_center),
            Paragraph(obs_texto, cell_left),
        ])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    # Estilização da Tabela
    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ]

    # Alternância de cores nas linhas (Zebra striping)
    for i in range(1, len(table_data)):
        bg = colors.HexColor("#F8FAFC") if i % 2 == 0 else colors.white
        t_style.append(('BACKGROUND', (0, i), (-1, i), bg))

    table.setStyle(TableStyle(t_style))
    story.append(table)
    
    # 3. Rodapé do Relatório
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>Total de propostas submetidas:</b> {total}", ParagraphStyle('Total', fontName='Helvetica', fontSize=8, textColor=colors.HexColor("#1E293B"))))

    # Constroi o documento
    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()