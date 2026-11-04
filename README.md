# yarg-lyrics

Automatically adds synced lyrics to [YARG](https://yarg.in) / Clone Hero song charts.

For each song folder it fetches lyrics from [LRCLIB](https://lrclib.net), isolates the vocals, force-aligns
the text word by word and writes the result as `notes.autolyrics.chart` / `notes.autolyrics.mid`, never
touching your original chart until you apply it. A local web UI lets you review each song karaoke-style,
fix timing, paste lyrics manually and apply/restore. Works with English and Portuguese songs.

On a held-out set of 98 songs, lines more than 0.5 s off dropped from 12.1% (htdemucs + MMS) to 6.2%.

> No songs, audio, charts or lyrics are included. You use your own library; lyrics are fetched from
> LRCLIB and written only into your local files.

## How it works

1. **Lyrics:** a `lyrics.txt` in the song folder (if present) or LRCLIB (searched by artist, title and duration).
2. **Vocals:** uses the song's vocal stem if it has one; otherwise separates the vocals from the mix with
   **MelBand RoFormer** (fallback: **htdemucs**).
3. **Alignment:** **wav2vec2-large-960h**, line by line, anchored on the LRC timestamps. For English songs,
   **ALT-DSing** (a model trained on singing) gives a second opinion: where the two disagree by more than
   0.5 s on a line's start, the one closer to the LRCLIB timestamp wins.
4. **Quality:** each line gets a suspicion level (0–2) and the song is marked `ok` or `REVISAR` (needs review);
   songs with no vocals in the audio are detected as instrumentals.
5. **Output:** `notes.autolyrics.*` next to the original. **Apply** replaces the chart (the original is kept as
   `notes.*.bak`); **Restore** undoes it.

Results, methodology and everything that was tested (Whisper, ALT-DALI, model consensus, beat-grid snapping):
[docs/experimentos-precisao.md](docs/experimentos-precisao.md) (in Portuguese).

## Installation

Requirements: **Python 3.12**, **ffmpeg** on your PATH and, ideally, a GPU (CPU works but is much slower).

### CPU or NVIDIA

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install torch==2.9.1 torchaudio==2.9.1 --index-url https://download.pytorch.org/whl/cu128   # NVIDIA
# or, CPU only:  .\.venv\Scripts\python -m pip install torch==2.9.1 torchaudio==2.9.1
.\.venv\Scripts\python -m pip install -r requirements.txt
```

torch/torchaudio are pinned to 2.9: newer torchaudio releases remove `forced_align` and the pipelines the
alignment relies on.

### AMD on Windows (ROCm 7.2.1, RX 7000/9000)

```powershell
py -3.12 -m venv .venv-rocm
$u = 'https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1'
.\.venv-rocm\Scripts\python -m pip install --no-cache-dir "$u/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl" "$u/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl" "$u/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl" "$u/rocm-7.2.1.tar.gz"
.\.venv-rocm\Scripts\python -m pip install --no-cache-dir "$u/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl" "$u/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl"
.\.venv-rocm\Scripts\python -m pip install --no-deps -r requirements-rocm.txt
```

`--no-deps` stops pip from replacing AMD's PyTorch with a different build; `requirements-rocm.txt` pins the
exact versions of a known-working environment.

Models are downloaded on first run into `cache\models\` (≈2.5 GB). ALT-DSing (the second opinion for English)
is optional: `python tools\get_alt_models.py` downloads the weights from the authors' Google Drive (requires
`requirements-experimentos.txt`). Without it, alignment uses wav2vec2 only.

## Web UI

Double-click `yarg-lyrics-ui.bat`: it opens `http://127.0.0.1:8765` in your browser.

The UI is in Portuguese; button names below are given as they appear, with a translation.

- **Procurar…** (Browse) picks a setlist folder; the list shows each song's status (has lyrics, pending, ok,
  needs review, no lyrics found, instrumental, applied).
- Select songs and click **Gerar letras** (Generate lyrics): the queue separates the vocals first and then
  aligns, on the GPU.
- Click a song to review it: plays the song (or just the vocals) with the lyrics lighting up word by word.
  **Próxima suspeita** (Next suspect, key N) jumps to flagged lines; **Ajustar tempo** (Adjust timing) shifts
  a line, a section or a word, or snaps it to the current playback position.
- **Marcar como ok** (Mark as ok), **Aplicar** (Apply), **Restaurar original** (Restore original),
  **Editar letra e ressincronizar** (Edit lyrics and resync — saves a `lyrics.txt`, which then takes priority
  over LRCLIB) and **Não tem letra** (No lyrics — creates a `.nolyrics` file so the song is skipped).
- **Outras versões** (Other versions): copies lyrics from another version with the same audio (e.g. a co-op
  chart), with the time offset adjusted automatically.

The UI only accepts connections from your own computer (127.0.0.1), since it writes files into the folders you
point it at.

## Command line

```powershell
$py = '.\.venv-rocm\Scripts\python.exe'
& $py run.py --scan "<setlist folder>"              # writes notes.autolyrics.* (original untouched)
& $py run.py --scan "<setlist folder>" --apply      # applies the songs marked "ok"
& $py run.py --restore --scan "<setlist folder>"    # restores the originals
& $py run.py --eval "<folder that already has lyrics>"  # measures accuracy against the existing lyrics
& $py tools\batch_folders.py "<library root>"       # every setlist, one at a time, through the UI queue
& $py tools\midi_scan.py "<library root>"           # finds .mid files with corrupted tracks (--consertar fixes them)
```

Reports go to `reports\` (`.jsonl` + `.csv`). If a song isn't on LRCLIB, put its lyrics in a `lyrics.txt` in the
song folder (one line per verse; LRC with timestamps also works).

## Configuration (environment variables)

| Variable | Effect |
|---|---|
| `YL_ALIGNER` | `w2v-960h` (default), `mms`, `alt-dsing`, `alt-dali`. An explicit value runs that single model. |
| `YL_SECOND` | `0` disables the second opinion; `1` forces it even with an explicit `YL_ALIGNER`. |
| `YL_SEPARATOR` | `vocals_mel_band_roformer.ckpt` (default), `htdemucs`, any other audio-separator model, or `none`. |
| `YL_DEVICE` | `cpu` or `cuda` (default: GPU if available). |
| `YL_IGNORE_VOCAL_STEM` | `1` ignores the vocal stem and separates from the mix (used in evaluations). |
| `YL_VERBOSE` | `1` shows library warnings that are normally hidden. |

## Evaluation

The tools in `tools/` (`exp_*.py`, `flag_check.py`, `sep_compare.ps1`, …) measure accuracy against songs that
already have official lyrics. They read a list of folders (`gold_all.json`, `gold_holdout.json`) that stays on
your machine; see `gold.example.json` for the format, and `tools\gold_candidates.py` finds candidates in your library.

## Models and licenses

This repository's code is MIT-licensed. Models are downloaded from their sources and have their own licenses:

| Model | Used for | Source | License |
|---|---|---|---|
| MelBand RoFormer (Kimberley Jensen) | vocal separation | [Hugging Face](https://huggingface.co/KimberleyJSN/melbandroformer), via [audio-separator](https://github.com/nomadkaraoke/python-audio-separator) | MIT |
| htdemucs | separation (fallback) | [Demucs](https://github.com/facebookresearch/demucs) | MIT |
| wav2vec2-large-960h-lv60-self | alignment | [facebook/wav2vec2-large-960h-lv60-self](https://huggingface.co/facebook/wav2vec2-large-960h-lv60-self) | Apache-2.0 |
| ALT-DSing / ALT-DALI | second opinion (English) / experiment | [ALT_SpeechBrain](https://github.com/guxm2021/ALT_SpeechBrain) (Ou, Gu & Wang, ISMIR 2022) | code Apache-2.0; no license stated for the weights |
| MMS_FA (`YL_ALIGNER=mms`) | previous aligner | [torchaudio](https://docs.pytorch.org/audio/stable/generated/torchaudio.pipelines.MMS_FA.html) | CC-BY-NC 4.0 (non-commercial) |
| Whisper (experiments only) | comparison | [openai-whisper](https://github.com/openai/whisper) / [stable-ts](https://github.com/jianfch/stable-ts) | MIT |

Lyrics come from [LRCLIB](https://lrclib.net) and belong to their authors. The tool only writes them into your
local files; no lyrics are part of this repository.

## Limitations

- Built and tested on Windows with an AMD GPU. Parts of the UI (the folder picker) and some scripts (`.ps1`,
  the server restart in `batch_folders.py`) are Windows-specific.
- Relies on torchaudio's `forced_align`, which is deprecated: that's why torch/torchaudio are pinned to 2.9.
- Portuguese: only 6 songs with official lyrics in the evaluation set. It works well on them, but the sample is small.
- The UI, code comments and the experiment write-up are in Portuguese.

## License

[MIT](LICENSE)
