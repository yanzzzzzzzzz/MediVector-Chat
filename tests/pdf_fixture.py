"""Tiny deterministic PDFs with real selectable text; no external assets or API calls."""
from io import BytesIO
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


def pdf_bytes(pages):
    writer = PdfWriter()
    for lines in pages:
        page = writer.add_blank_page(width=595, height=842)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        text = 'BT /F1 12 Tf 40 790 Td 18 TL\n'
        for line in lines:
            escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            text += f'({escaped}) Tj T*\n'
        stream.set_data((text + 'ET').encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
