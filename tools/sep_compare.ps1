# Compara separadores no gabarito (forçando separação do mix).
# Uso: powershell -File tools\sep_compare.ps1 [modelo]   -> logs\sep_*.log ; relatórios em reports\*-eval.jsonl
# Separa tudo primeiro num processo só (sem o alinhador na GPU), depois avalia usando o cache.
param([string]$Model = 'vocals_mel_band_roformer.ckpt')
Set-Location (Split-Path $PSScriptRoot)
$py = (Resolve-Path '.\.venv-rocm\Scripts\python.exe').Path
$env:YL_IGNORE_VOCAL_STEM = '1'
$env:PYTHONIOENCODING = 'utf-8'
function Run($name, $argList) {
    Start-Process -Wait -WindowStyle Hidden -FilePath $py -ArgumentList $argList `
        -RedirectStandardOutput "logs\sep_$name.log" -RedirectStandardError "logs\sep_$name.err"
}
$env:YL_SEPARATOR = $Model
Run 'presep' @('-u', 'tools\presep.py', 'gold_all.json')
Run 'eval_model' @('-u', 'run.py', '--list', 'gold_all.json', '--eval')
$env:YL_SEPARATOR = 'htdemucs'
Run 'presep_htdemucs' @('-u', 'tools\presep.py', 'gold_all.json')
Run 'eval_htdemucs' @('-u', 'run.py', '--list', 'gold_all.json', '--eval')
'fim' | Set-Content logs\sep_done.txt
