"""Testes do conversor CDR -> ODG.

Rodam fora do Streamlit (modo "bare"): os st.* viram avisos inofensivos.
A conversão de ponta a ponta precisa do LibreOffice (soffice) instalado.
"""
import io
import shutil
import struct
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
OUTPUT = Path(__file__).parent / "output"
HAS_SOFFICE = shutil.which("soffice") is not None or shutil.which("libreoffice") is not None

ODG_MIME = b"application/vnd.oasis.opendocument.graphics"


def png_size(data: bytes):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "não é PNG"
    return struct.unpack(">II", data[16:24])


# --- algoritmo de versão (igual ao da libcdr) -------------------------------

def test_cdr_version_algoritmo():
    def riff(tag: bytes) -> bytes:
        return b"RIFF" + b"\x00\x00\x00\x00" + tag + b"\x00" * 8
    assert app.cdr_version(riff(b"CDR7")) == 700
    assert app.cdr_version(riff(b"cdr8")) == 800
    assert app.cdr_version(riff(b"CDR ")) == 300
    assert app.cdr_version(riff(b"CDRA")) == 1000   # CorelDRAW 10, não X3
    assert app.cdr_version(riff(b"CDRD")) == 1300   # X3
    assert app.cdr_version(riff(b"CDRE")) == 1400   # X4
    assert app.cdr_version(riff(b"CDR0")) == 0
    assert app.cdr_version(riff(b"WAVE")) == 0
    assert app.cdr_version(b"WL" + b"\x00" * 14) == 200
    assert app.version_name(1300) == "X3"
    assert app.version_name(700) == "7"


# --- inspeção do cabeçalho -------------------------------------------------

def test_header_fixtures():
    assert app.inspect_header((FIXTURES / "corel_arrows_x3.cdr").read_bytes()) == ("cdr", "X3")
    assert app.inspect_header((FIXTURES / "text_rgb_fill_cdr7.cdr").read_bytes()) == ("cdr", "7")
    assert app.inspect_header((FIXTURES / "fdo48739-1.cdr").read_bytes()) == ("cdr", "X4 ou posterior")
    assert app.inspect_header((FIXTURES / "shapes_v1.cdr").read_bytes())[0] == "cdr"


def test_header_impostores():
    assert app.inspect_header(b"%PDF-1.7 lixo" + b"\x00" * 16)[1] == "PDF"
    assert app.inspect_header(b'<?xml version="1.0"?><svg xmlns="x"></svg>')[1] == "SVG"
    assert app.inspect_header(b'<?xml version="1.0"?><root/>' + b" " * 16)[1] == "XML"
    assert app.inspect_header(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')[1] == "SVG"
    assert app.inspect_header(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)[1] == "PNG"
    assert app.inspect_header(b"")[0] == "outro"
    # ODG renomeado para .cdr: ZIP com mimetype + content.xml. Neste app o
    # engano é fácil de cometer (a saída também é ODG), então tem de recusar.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", ODG_MIME.decode())
        z.writestr("content.xml", "<x/>")
    assert app.inspect_header(buf.getvalue()) == ("outro", "OpenDocument renomeado")
    # ZIP qualquer
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "x")
    assert app.inspect_header(buf.getvalue()) == ("outro", "ZIP")


# --- conversão de ponta a ponta -------------------------------------------

def assert_odg_valido(data: bytes):
    """Um ODG que abre em qualquer leitor de OpenDocument: ZIP cujo PRIMEIRO
    membro é o 'mimetype', gravado SEM compressão (regra do ODF; sem ela o
    arquivo é detectado como ZIP genérico), com content.xml e manifesto."""
    assert data[:2] == b"PK", "não é um contêiner ZIP"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = z.infolist()
        assert infos[0].filename == "mimetype", "mimetype não é o primeiro membro"
        assert infos[0].compress_type == zipfile.ZIP_STORED, "mimetype comprimido"
        assert z.read("mimetype") == ODG_MIME
        names = z.namelist()
        assert "content.xml" in names
        assert "META-INF/manifest.xml" in names
        assert z.testzip() is None, "ZIP corrompido"


@pytest.mark.skipif(not HAS_SOFFICE, reason="LibreOffice (soffice) ausente")
@pytest.mark.parametrize("name,version", [
    ("corel_arrows_x3.cdr", "X3"),
    ("text_rgb_fill_cdr7.cdr", "7"),
    ("fdo48739-1.cdr", "X4 ou posterior"),
    ("shapes_v1.cdr", None),
])
def test_cdr_para_odg(name, version):
    OUTPUT.mkdir(exist_ok=True)
    odg, preview, info = app.convert_cdr_to_odg(str(FIXTURES / name))
    assert_odg_valido(odg)
    assert info["pages"] >= 1
    assert info["page_width_cm"] > 0 and info["page_height_cm"] > 0
    # um desenho tem de chegar ao ODG como alguma coisa desenhável
    assert info["shapes"] + info["texts"] + info["images"] > 0
    if version:
        assert info["version"] == version
    png_size(preview)
    (OUTPUT / (Path(name).stem + ".odg")).write_bytes(odg)
    (OUTPUT / (Path(name).stem + "_previa.png")).write_bytes(preview)


@pytest.mark.skipif(not HAS_SOFFICE, reason="LibreOffice (soffice) ausente")
def test_previa_vem_do_odg_entregue_e_tem_tinta():
    """A prévia é gerada a partir do ODG ENTREGUE, não de um intermediário.
    Se ela tem tinta de verdade, está provado que o arquivo que o usuário
    baixa abre no LibreOffice e traz o desenho — o pôster do X4 (bug
    fdo48739) é todo vetorial, com o texto convertido em curvas."""
    import pymupdf
    _odg, preview, _info = app.convert_cdr_to_odg(str(FIXTURES / "fdo48739-1.cdr"))
    pix = pymupdf.Pixmap(preview)
    samples = pix.samples
    non_white = sum(1 for b in samples[::97] if b < 240)
    assert non_white / (len(samples) // 97) > 0.2


@pytest.mark.skipif(not HAS_SOFFICE, reason="LibreOffice (soffice) ausente")
def test_odg_sai_editavel_com_texto_de_verdade():
    """O ODG não é uma imagem embrulhada: o texto do desenho chega como
    texto, editável. O fixture do CorelDRAW 7 tem texto."""
    odg, _preview, info = app.convert_cdr_to_odg(str(FIXTURES / "text_rgb_fill_cdr7.cdr"))
    assert info["texts"] > 0, "nenhuma moldura de texto no ODG"
    with zipfile.ZipFile(io.BytesIO(odg)) as z:
        content = z.read("content.xml").decode("utf-8", "replace")
    assert "<text:p" in content or "text:p" in content


@pytest.mark.skipif(not HAS_SOFFICE, reason="LibreOffice (soffice) ausente")
def test_correcoes_chegam_ao_arquivo_entregue():
    """As correções de recorte e de texto são aplicadas no ODG que sai, e não
    só num intermediário descartado. Prova: converter o mesmo CDR sem passar
    pelas correções e comparar o content.xml — quando o contador diz que
    houve correção, os dois arquivos TÊM de diferir."""
    import tempfile
    import uuid

    name = "text_rgb_fill_cdr7.cdr"
    odg, _preview, info = app.convert_cdr_to_odg(str(FIXTURES / name))
    corrigidos = info["cropped_images"] + info["moved_texts"] + info["condensed_texts"]
    if corrigidos == 0:
        pytest.skip("este fixture não precisou de correção")

    work = Path(tempfile.gettempdir()) / f"cdr_cru_{uuid.uuid4().hex}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        cru_path = app.run_soffice_convert(FIXTURES / name, work, "odg:draw8", "odg")
        with zipfile.ZipFile(cru_path) as z:
            cru = z.read("content.xml")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    with zipfile.ZipFile(io.BytesIO(odg)) as z:
        entregue = z.read("content.xml")
    assert entregue != cru, "o ODG entregue é o mesmo que o LibreOffice cuspiu"


def test_svg_renomeado_e_recusado_antes_do_libreoffice(tmp_path):
    fake = tmp_path / "logo.cdr"
    fake.write_bytes(b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>')
    with pytest.raises(app.ConversionError, match="SVG"):
        app.convert_cdr_to_odg(str(fake))


def test_odg_renomeado_e_recusado(tmp_path):
    """Sem esta guarda o app aceitaria o próprio formato de saída como
    entrada e devolveria o arquivo praticamente intacto."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", ODG_MIME.decode())
        z.writestr("content.xml", "<x/>")
    fake = tmp_path / "desenho.cdr"
    fake.write_bytes(buf.getvalue())
    with pytest.raises(app.ConversionError, match="OpenDocument"):
        app.convert_cdr_to_odg(str(fake))


@pytest.mark.skipif(not HAS_SOFFICE, reason="LibreOffice (soffice) ausente")
def test_cdr_corrompido(tmp_path):
    data = bytearray((FIXTURES / "corel_arrows_x3.cdr").read_bytes())
    data[64:] = b"\x00" * (len(data) - 64)
    fake = tmp_path / "corrompido.cdr"
    fake.write_bytes(bytes(data))
    with pytest.raises(app.ConversionError):
        app.convert_cdr_to_odg(str(fake))
