"""Extract plain text from knowledge uploads. No OCR."""
import io
import re
import zipfile
from xml.etree import ElementTree

# Keep multipart requests below the 20 MiB reverse-proxy limit.
MAX_UPLOAD_MB = 20
MAX_BYTES = MAX_UPLOAD_MB * 1_000_000
MAX_CHARS = 20000


def extract_upload(upload) -> str:
    if upload.size > MAX_BYTES:
        raise ValueError(f'文件超过 {MAX_UPLOAD_MB} MB，请压缩或拆分后再上传。')
    raw = upload.read()
    if not raw:
        raise ValueError('文件是空的')
    ext = upload.name.rsplit('.', 1)[-1].lower()
    if ext in ('txt', 'md', 'markdown'):
        text = raw.decode('utf-8', errors='replace')
    elif ext == 'docx':
        text = _office_xml(raw, 'word/document.xml')
    elif ext == 'pptx':
        text = _office_xml(raw, 'ppt/slides/slide')
    elif ext == 'pdf':
        text = _pdf_text(raw)
    else:
        raise ValueError('只支持 TXT、Markdown、DOCX、PPTX 和 PDF')
    text = re.sub(r'\n{3,}', '\n\n', (text or '').strip())
    if len(text) < 2:
        raise ValueError('没有提取到文字。扫描件需要先做成可复制的文本。')
    return text[:MAX_CHARS]


def _office_xml(raw: bytes, prefix: str) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError('文档无法打开') from exc
    names = [item for item in archive.namelist() if item.startswith(prefix) and item.endswith('.xml')]
    if not names:
        raise ValueError('文档里没有正文')
    pieces = []
    for name in sorted(names):
        try:
            root = ElementTree.fromstring(archive.read(name))
        except ElementTree.ParseError as exc:
            raise ValueError('文档正文无法读取') from exc
        pieces.append(''.join(root.itertext()))
    return '\n'.join(piece.strip() for piece in pieces if piece and piece.strip())


def _pdf_text(raw: bytes) -> str:
    pieces = []
    for match in re.findall(br'\((?:\\.|[^\\)]){2,}\)', raw):
        try:
            pieces.append(match[1:-1].decode('utf-8', errors='ignore'))
        except UnicodeDecodeError:
            continue
    text = '\n'.join(pieces).strip()
    if len(text) >= 8:
        return text
    visible = re.findall(br'[\x20-\x7e\u4e00-\u9fff]{4,}', raw)
    return '\n'.join(part.decode('utf-8', errors='ignore') for part in visible[:200])
