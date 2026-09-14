# 🖍️ Conversor de CDR para ODG

Aplicação web em Python/Streamlit que converte desenhos **CDR (CorelDRAW) para ODG (LibreOffice Draw)**, sem CorelDRAW.

## 🎯 O que faz

| Entrada | Saída |
| --- | --- |
| `.cdr` (CorelDRAW 7 a X7; versões mais antigas e mais novas dependem do arquivo) | **`.odg`** editável, com todas as páginas do desenho, as formas, os textos e as imagens separados |

Escopo único e fixo — este app não lida com nenhum outro formato de entrada ou saída.

- Interface de tela única (upload → converter → prévia → baixar)
- O ODG sai **editável**: o texto continua texto, as formas continuam formas. Não é uma imagem embrulhada num arquivo de desenho.
- Abre no [LibreOffice Draw](https://www.libreoffice.org/discover/draw/), no [Inkscape](https://inkscape.org/) e no Google Drive
- Mostra a versão do CorelDRAW, o tamanho da página e quantas formas, textos e imagens vieram
- Processamento em diretórios temporários — nenhum arquivo é armazenado

## ⚙️ Como converte

1. **LibreOffice Draw** (headless) lê o CDR com a biblioteca **libcdr** e grava um ODG.
2. **odg_crop.py** reaplica os recortes de imagem que a libcdr perde: no Corel, uma foto recortada (PowerClip ou ferramenta de corte) chega ao ODG como um polígono invisível com o retângulo do recorte seguido da imagem inteira, que cobre o resto do desenho. O módulo corta os pixels na proporção do polígono e encolhe a moldura. Recortes não retangulares viram o retângulo envolvente.
3. **odg_text.py** corrige a posição e a largura do texto artístico. A libcdr dobra a largura da caixa do texto antes de entregá-la, e o topo dessa caixa é a altura de maiúscula, não o topo da ascendente da fonte. O módulo devolve o texto à largura que o CorelDRAW registrou (condensando quando a fonte do servidor é mais larga) e sobe a moldura a diferença entre ascendente e maiúscula.
4. O ODG corrigido é **o arquivo entregue**. As correções ficam gravadas nele, não num intermediário descartado.
5. Para a **prévia** na tela, e só para ela, o LibreOffice exporta esse mesmo ODG para PDF e o **PyMuPDF** rasteriza a primeira página. A prévia mostra a página inteira, que é o que você vê ao abrir o arquivo no LibreOffice Draw.

As fontes de `static/fonts/` (181 arquivos) são o que permite ao LibreOffice medir o texto com a fonte que o CorelDRAW usou. Sem elas, uma fonte ausente no servidor vira outra de largura diferente e o texto estoura a arte.

Limites honestos, medidos num corpus de 84 CDR reais (do CorelDRAW 7 ao X4+): cores CMYK e Pantone saem em RGB; efeitos exclusivos do Corel (envelope, lente, extrusão) podem não aparecer; texto cirílico de alguns arquivos das versões 8 e 9 sai como "?????" (limitação da libcdr). Um SVG, PDF ou ODG renomeado para `.cdr` é recusado antes de chegar ao LibreOffice — no caso do ODG isso importa duas vezes, porque ele é também o formato de saída e seria devolvido quase intacto. Se a libcdr abrir o arquivo mas devolver página vazia, o app avisa em vez de entregar um desenho em branco.

## 🚀 Rodar localmente

Pré-requisitos: Python 3.10+ e LibreOffice instalado (com o componente Draw).

```bash
pip install -r requirements.txt
streamlit run app.py
```

Abre em `http://localhost:8501`.

## 🧪 Testes

```bash
pip install pytest
pytest -q
```

Os testes cobrem o algoritmo de versão (igual ao da libcdr), a detecção de impostores, os dois módulos de correção e a conversão de ponta a ponta com CDR reais de `tests/fixtures/` (corpus público de testes do LibreOffice). Há um teste que compara o ODG entregue com o que o LibreOffice cospe sem as correções, para provar que elas chegam ao arquivo baixado. Os arquivos gerados ficam em `tests/output/`.

Para provar o ambiente de deploy (Debian com os pacotes do `packages.txt`):

```bash
docker build --load -f tests/Dockerfile.smoke -t cdr-odg-smoke . && docker run --rm cdr-odg-smoke
```

Medido em 14/09/2026: **27 testes passam** no Windows e os mesmos 27 no contêiner Debian trixie.

## ☁️ Deploy no Streamlit Cloud

1. Faça push para o GitHub
2. Em [share.streamlit.io](https://share.streamlit.io), conecte o repositório
3. Em **Advanced settings**, escolha **Python 3.13** (ou 3.12). Com Python 3.14 a instalação falha: o Streamlit 1.39 exige pillow abaixo da versão 11, que não tem pacote pronto para 3.14. A versão do Python não pode ser trocada depois; é preciso apagar o app e implantar de novo.
4. O `packages.txt` (incluído) instala o LibreOffice Draw, que já traz a libcdr, e as fontes substitutas
5. Deploy

App no ar: https://cdr-para-odg.streamlit.app/

## 📋 Estrutura

```
cdr-para-odg/
├── app.py              # Aplicação principal
├── requirements.txt    # streamlit, pymupdf, defusedxml, fonttools
├── packages.txt        # Pacotes do sistema (LibreOffice Draw, fontes)
├── odg_crop.py         # Reaplica recortes de imagem perdidos pela libcdr
├── odg_text.py         # Corrige posição e largura do texto artístico
├── static/fonts/       # Fontes que o LibreOffice usa na conversão
├── tests/              # pytest + fixtures CDR reais + Dockerfile do smoke
├── NOTICE.md           # Licenças dos componentes
└── README.md
```

## 🛠️ Tecnologias

- **[Streamlit](https://streamlit.io/)** — interface web
- **[LibreOffice Draw](https://www.libreoffice.org/discover/draw/)** + **libcdr** (headless) — leitura do CorelDRAW e escrita do ODG
- **[PyMuPDF](https://pymupdf.readthedocs.io/)** — rasterização da prévia

## 🔒 Privacidade

Os arquivos são processados em diretórios temporários e removidos após a conversão. Nada é armazenado permanentemente.

---

Desenvolvido com ❤️ usando Python e Streamlit.
