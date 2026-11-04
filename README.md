# yarg-lyrics

**English summary.** Automatically adds synced lyrics to [YARG](https://yarg.in) / Clone Hero song charts.
For each song folder it fetches lyrics from [LRCLIB](https://lrclib.net), isolates the vocals
(MelBand RoFormer, htdemucs as fallback), force-aligns the text word by word (wav2vec2-large-960h, with
ALT-DSing as a second opinion for English songs) and writes the result as `notes.autolyrics.chart` /
`notes.autolyrics.mid`, never touching your original chart until you apply it. A local web UI lets you
review each song karaoke-style, fix timing, paste lyrics manually and apply/restore. Supports English and
Portuguese. Built and tested on Windows 11 with an AMD GPU (ROCm); CPU and NVIDIA should work but are less tested.
On a held-out set of 98 songs, lines more than 0.5 s off dropped from 12.1% (htdemucs + MMS) to 6.2%.

> No songs, audio, charts or lyrics are included. You use your own library, and lyrics are fetched
> from LRCLIB and written only into your local files.

---

Busca letras no [LRCLIB](https://lrclib.net), separa a voz, alinha palavra a palavra e grava a letra
no chart (`notes.chart` / `notes.mid`) no padrão Clone Hero / YARG. Funciona em inglês e português.

## Como funciona

1. **Letra:** `lyrics.txt` na pasta da música (se existir) ou o LRCLIB (busca por artista/título/duração).
2. **Voz:** usa o stem de voz da música, se houver; senão separa do mix com o **MelBand RoFormer**
   (plano B: **htdemucs**).
3. **Alinhamento:** **wav2vec2-large-960h** linha a linha, ancorado nos tempos do LRC. Nas músicas em inglês,
   o **ALT-DSing** (treinado com canto) dá uma 2ª opinião: onde os dois discordam mais de 0,5 s no início da
   linha, fica o que está mais perto do tempo do LRCLIB.
4. **Qualidade:** cada linha recebe um nível de suspeita (0–2) e a música sai como `ok` ou `REVISAR`;
   músicas sem voz no áudio são detectadas como instrumentais.
5. **Saída:** `notes.autolyrics.*` ao lado do original. **Aplicar** troca o chart (o original vira `notes.*.bak`);
   **Restaurar** desfaz.

Resultados, metodologia e o que foi testado (Whisper, ALT-DALI, consenso, grade rítmica):
[docs/experimentos-precisao.md](docs/experimentos-precisao.md).

## Instalação

Pré-requisitos: **Python 3.12**, **ffmpeg** no PATH e, de preferência, uma GPU (CPU funciona, mas é bem mais lento).

### CPU ou NVIDIA

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install torch==2.9.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cu128   # NVIDIA
# ou, só CPU:  .\.venv\Scripts\python -m pip install torch==2.9.1 torchaudio==2.9.1
.\.venv\Scripts\python -m pip install -r requirements.txt
```

O torch/torchaudio ficam fixos na 2.9: versões mais novas do torchaudio removem o `forced_align` e as
pipelines que o alinhamento usa.

### AMD no Windows (ROCm 7.2.1, RX 7000/9000)

```powershell
py -3.12 -m venv .venv-rocm
$u = 'https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1'
.\.venv-rocm\Scripts\python -m pip install --no-cache-dir "$u/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl" "$u/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl" "$u/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl" "$u/rocm-7.2.1.tar.gz"
.\.venv-rocm\Scripts\python -m pip install --no-cache-dir "$u/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl" "$u/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl"
.\.venv-rocm\Scripts\python -m pip install --no-deps -r requirements-rocm.txt
```

`--no-deps` impede o pip de trocar o PyTorch da AMD por outro; `requirements-rocm.txt` tem as versões exatas
de um ambiente que funciona.

Os modelos são baixados na primeira execução para `cache\models\` (≈2,5 GB). O ALT-DSing (2ª opinião em inglês)
é opcional: `python tools\get_alt_models.py` baixa os pesos do Google Drive dos autores (precisa de
`requirements-experimentos.txt`). Sem ele, o alinhamento usa só o wav2vec2.

## Interface

Dois cliques em `yarg-lyrics-ui.bat`: abre `http://127.0.0.1:8765` no navegador.

- **Procurar…** escolhe a pasta da setlist; a lista mostra o status de cada música (já tem letra, pendente,
  ok, revisar, sem letra, instrumental, aplicada).
- Selecione músicas e clique **Gerar letras**: a fila separa as vozes e depois alinha, na GPU.
- Clique numa música para revisar: toca a música (ou só a voz) com a letra acendendo palavra por palavra.
  **Próxima suspeita** (N) pula para as linhas marcadas; **Ajustar tempo** move linha, trecho ou palavra
  (ou "aqui", no ponto em que o áudio está).
- **Marcar como ok**, **Aplicar**, **Restaurar original**, **Editar letra e ressincronizar** (salva um
  `lyrics.txt`, que passa a ter prioridade sobre o LRCLIB) e **Não tem letra** (cria `.nolyrics`).
- **Outras versões:** copia a letra de uma versão com o mesmo áudio (ex.: co-op), com ajuste de defasagem.

A interface só aceita conexões do próprio computador (127.0.0.1) — ela grava arquivos nas pastas indicadas.

## Linha de comando

```powershell
$py = '.\.venv-rocm\Scripts\python.exe'
& $py run.py --scan "<pasta da setlist>"            # gera notes.autolyrics.* (não mexe no original)
& $py run.py --scan "<pasta da setlist>" --apply    # aplica as que saíram "ok"
& $py run.py --restore --scan "<pasta da setlist>"  # volta os originais
& $py run.py --eval "<pasta que já tem letra>"      # mede a precisão contra a letra existente
& $py tools\batch_folders.py "<raiz da biblioteca>" # todas as setlists, uma por vez, pela fila da interface
& $py tools\midi_scan.py "<raiz da biblioteca>"     # procura .mid com trilhas corrompidas (--consertar)
```

Relatórios em `reports\` (`.jsonl` + `.csv`). Se uma música não estiver no LRCLIB, coloque a letra num
`lyrics.txt` na pasta dela (uma linha por verso; aceita LRC com tempos).

## Configuração (variáveis de ambiente)

| Variável | Efeito |
|---|---|
| `YL_ALIGNER` | `w2v-960h` (padrão), `mms`, `alt-dsing`, `alt-dali`. Com valor explícito roda um modelo só. |
| `YL_SECOND` | `0` desliga a 2ª opinião; `1` força mesmo com `YL_ALIGNER` explícito. |
| `YL_SEPARATOR` | `vocals_mel_band_roformer.ckpt` (padrão), `htdemucs`, outro modelo do audio-separator, ou `none`. |
| `YL_DEVICE` | `cpu` ou `cuda` (padrão: GPU se existir). |
| `YL_IGNORE_VOCAL_STEM` | `1` ignora o stem de voz e separa do mix (usado nas avaliações). |
| `YL_VERBOSE` | `1` mostra os avisos das bibliotecas que normalmente ficam ocultos. |

## Avaliação

As ferramentas em `tools/` (`exp_*.py`, `flag_check.py`, `sep_compare.ps1`…) medem a precisão contra músicas que
já têm letra oficial. Elas leem uma lista de pastas (`gold_all.json`, `gold_holdout.json`) que fica só no seu PC;
o formato está em `gold.example.json`, e `tools\gold_candidates.py` encontra candidatas na sua biblioteca.

## Modelos e licenças

O código deste repositório é MIT. Os modelos são baixados de suas fontes e têm licenças próprias:

| Modelo | Uso | Fonte | Licença |
|---|---|---|---|
| MelBand RoFormer (Kimberley Jensen) | separação de voz | [Hugging Face](https://huggingface.co/KimberleyJSN/melbandroformer), via [audio-separator](https://github.com/nomadkaraoke/python-audio-separator) | MIT |
| htdemucs | separação (plano B) | [Demucs](https://github.com/facebookresearch/demucs) | MIT |
| wav2vec2-large-960h-lv60-self | alinhamento | [facebook/wav2vec2-large-960h-lv60-self](https://huggingface.co/facebook/wav2vec2-large-960h-lv60-self) | Apache-2.0 |
| ALT-DSing / ALT-DALI | 2ª opinião (inglês) / experimento | [ALT_SpeechBrain](https://github.com/guxm2021/ALT_SpeechBrain) (Ou, Gu & Wang, ISMIR 2022) | código Apache-2.0; pesos sem licença declarada |
| MMS_FA (`YL_ALIGNER=mms`) | alinhador antigo | [torchaudio](https://docs.pytorch.org/audio/stable/generated/torchaudio.pipelines.MMS_FA.html) | CC-BY-NC 4.0 (uso não comercial) |
| Whisper (só experimentos) | comparação | [openai-whisper](https://github.com/openai/whisper) / [stable-ts](https://github.com/jianfch/stable-ts) | MIT |

Letras: vêm do [LRCLIB](https://lrclib.net) e pertencem a seus autores. A ferramenta só as grava nos seus arquivos
locais; nenhuma letra faz parte deste repositório.

## Limitações

- Feito e testado no Windows com GPU AMD. Partes da interface (seletor de pasta) e alguns scripts (`.ps1`,
  reinício do servidor no `batch_folders.py`) são específicos do Windows.
- Depende do `forced_align` do torchaudio, que está marcado como obsoleto: por isso o torch/torchaudio
  ficam fixos na 2.9.
- Português: só 6 músicas com letra oficial na avaliação — funciona bem nelas, mas a amostra é pequena.

## Licença

[MIT](LICENSE)
