# yarg-lyrics

Busca letras no [LRCLIB](https://lrclib.net), separa a voz (Demucs), alinha palavra a palavra
(MMS_FA, multilíngue) e grava a letra em `notes.chart` / `notes.mid` no padrão Clone Hero / YARG.

## Ambientes

| venv | Python | Uso |
|---|---|---|
| `.venv-rocm` | 3.12 | **padrão** — GPU AMD (ROCm 7.2.1 para Windows, RX 7000/9000) |
| `.venv` | 3.11 | fallback só CPU (`requirements.txt`) |

Instalação do ambiente GPU (PowerShell):

```powershell
py -3.12 -m venv .venv-rocm
$u = 'https://repo.radeon.com/rocm/windows/rocm-rel-7.2.1'
.\.venv-rocm\Scripts\python -m pip install --no-cache-dir "$u/rocm_sdk_core-7.2.1-py3-none-win_amd64.whl" "$u/rocm_sdk_devel-7.2.1-py3-none-win_amd64.whl" "$u/rocm_sdk_libraries_custom-7.2.1-py3-none-win_amd64.whl" "$u/rocm-7.2.1.tar.gz"
.\.venv-rocm\Scripts\python -m pip install --no-cache-dir "$u/torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl" "$u/torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl"
.\.venv-rocm\Scripts\python -m pip install -r requirements-rocm.txt
.\.venv-rocm\Scripts\python -m pip install --no-deps demucs
```

`demucs` vai com `--no-deps` para o pip não trocar o PyTorch da AMD pelo de CPU.
O dispositivo é escolhido sozinho (`cuda` se a GPU existir); force com `$env:YL_DEVICE='cpu'`.

## Interface

Dê dois cliques em `yarg-lyrics-ui.bat`: abre `http://127.0.0.1:8765` no navegador.

- **Procurar…** escolhe a pasta da setlist; a lista marca o status de cada música (já tem letra, pendente, ok, revisar, sem letra, instrumental, aplicada).
- Selecione algumas (ou *Selecionar visíveis*) e clique **Gerar letras**; a fila roda na GPU e a tabela atualiza sozinha.
- Clique numa música para revisar: toca a música (ou só a voz separada) com a letra acendendo palavra por palavra.
  Espaço toca/pausa, ← → pulam 5 s, clique numa frase para ir até ela.
- **Marcar como ok** aprova uma `REVISAR`; **Aplicar** grava no chart (original vira `notes.*.bak`); **Restaurar original** desfaz.
- **Editar letra e ressincronizar** / **Adicionar letra**: cola a letra (texto simples ou LRC com tempos), salva como `lyrics.txt` na pasta da música — que passa a ter prioridade sobre o LRCLIB — e sincroniza de novo.
- **Não tem letra** cria um `.nolyrics` na pasta: a música é ignorada nas próximas execuções.

## Uso pela linha de comando

```powershell
$py = '.\.venv-rocm\Scripts\python.exe'
& $py run.py --scan "D:\Jogos\Setlists\<setlist>"          # gera notes.autolyrics.* (não mexe no original)
& $py run.py --scan "<setlist>" --apply                     # aplica as "ok" (original vira notes.*.bak)
& $py run.py --restore --scan "<setlist>"                   # volta os originais
& $py run.py --eval "<pasta que já tem letra>"              # mede precisão contra a letra existente
```

Relatórios em `reports\` (`.jsonl` + `.csv`). Se uma música não estiver no LRCLIB, coloque a letra
num `lyrics.txt` na pasta dela (uma linha por verso; aceita LRC com tempos).
