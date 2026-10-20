# Testes do ALT-DALI: mix original x voz separada, checkpoint de fim x meio de época.  -> logs\dali_*.log
Set-Location (Split-Path $PSScriptRoot)
$py = (Resolve-Path '.\.venv-rocm\Scripts\python.exe').Path
$env:YL_IGNORE_VOCAL_STEM = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:YL_ALIGNER = 'alt-dali'
foreach ($cfg in @(@('none', 'end'), @('none', 'mid'), @('vocals_mel_band_roformer.ckpt', 'mid'))) {
    $env:YL_SEPARATOR = $cfg[0]; $env:YL_ALT_CKPT = $cfg[1]
    Start-Process -Wait -WindowStyle Hidden -FilePath $py -ArgumentList @('-u', 'run.py', '--list', 'gold_all.json', '--eval') `
        -RedirectStandardOutput "logs\dali_$($cfg[0].Substring(0,4))_$($cfg[1]).log" -RedirectStandardError "logs\dali_$($cfg[0].Substring(0,4))_$($cfg[1]).err"
}
# MMS e w2v-960h no mix original, como referência
$env:YL_SEPARATOR = 'none'; $env:YL_ALT_CKPT = ''
foreach ($a in @('mms', 'w2v-960h')) {
    $env:YL_ALIGNER = $a
    Start-Process -Wait -WindowStyle Hidden -FilePath $py -ArgumentList @('-u', 'run.py', '--list', 'gold_all.json', '--eval') `
        -RedirectStandardOutput "logs\dali_ref_$a.log" -RedirectStandardError "logs\dali_ref_$a.err"
}
'fim' | Set-Content logs\dali_done.txt
