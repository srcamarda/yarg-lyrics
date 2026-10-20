# Avalia aligners alternativos no gabarito (voz do mix separada pelo RoFormer, já no cache).
# Uso: powershell -File tools\aligner_compare.ps1 [aligners...]   -> logs\al_<nome>.log, reports\*-eval.jsonl
param([string[]]$Aligners = @('alt-dsing', 'alt-dali', 'w2v-960h'))
Set-Location (Split-Path $PSScriptRoot)
$py = (Resolve-Path '.\.venv-rocm\Scripts\python.exe').Path
$env:YL_IGNORE_VOCAL_STEM = '1'
$env:YL_SEPARATOR = 'vocals_mel_band_roformer.ckpt'
$env:PYTHONIOENCODING = 'utf-8'
foreach ($a in $Aligners) {
    $env:YL_ALIGNER = $a
    Start-Process -Wait -WindowStyle Hidden -FilePath $py -ArgumentList @('-u', 'run.py', '--list', 'gold_all.json', '--eval') `
        -RedirectStandardOutput "logs\al_$a.log" -RedirectStandardError "logs\al_$a.err"
}
'fim' | Set-Content logs\al_done.txt
