# Verificação do padrão novo (RoFormer + w2v-960h + 2ª opinião ALT-DSing em inglês) x pipeline antigo (htdemucs + MMS).
# Gabarito (mix e stem) e conjunto de validação novo (gold_holdout.json, nunca usado p/ ajustar nada). -> logs\vd_*.log
Set-Location (Split-Path $PSScriptRoot)
while (-not (Test-Path logs\dali_done.txt)) { Start-Sleep 30 }      # espera os testes do ALT-DALI
$py = (Resolve-Path '.\.venv-rocm\Scripts\python.exe').Path
$env:PYTHONIOENCODING = 'utf-8'
function Run($name, $argList) {
    Start-Process -Wait -WindowStyle Hidden -FilePath $py -ArgumentList $argList `
        -RedirectStandardOutput "logs\vd_$name.log" -RedirectStandardError "logs\vd_$name.err"
}
function Cfg($ign, $sep, $al) {
    $env:YL_IGNORE_VOCAL_STEM = $ign
    if ($sep) { $env:YL_SEPARATOR = $sep } else { Remove-Item Env:YL_SEPARATOR -ErrorAction SilentlyContinue }
    if ($al) { $env:YL_ALIGNER = $al } else { Remove-Item Env:YL_ALIGNER -ErrorAction SilentlyContinue }
}
Remove-Item Env:YL_ALT_CKPT -ErrorAction SilentlyContinue
# 1) gabarito, padrão novo: mix (caso difícil) e com stem (uso normal)
Cfg '1' $null $null;  Run 'gold_mix_padrao' @('-u', 'run.py', '--list', 'gold_all.json', '--eval')
Cfg '0' $null $null;  Run 'gold_stem_padrao' @('-u', 'run.py', '--list', 'gold_all.json', '--eval')
Cfg '0' 'htdemucs' 'mms'; Run 'gold_stem_antigo' @('-u', 'run.py', '--list', 'gold_all.json', '--eval')
# 2) validação: separa antes (processo só p/ isso), depois avalia novo x antigo
Cfg '1' $null $null;  Run 'hold_presep_roformer' @('-u', 'tools\presep.py', 'gold_holdout.json')
Cfg '1' 'htdemucs' $null; Run 'hold_presep_htdemucs' @('-u', 'tools\presep.py', 'gold_holdout.json')
Cfg '1' $null $null;  Run 'hold_mix_padrao' @('-u', 'run.py', '--list', 'gold_holdout.json', '--eval')
Cfg '1' 'htdemucs' 'mms'; Run 'hold_mix_antigo' @('-u', 'run.py', '--list', 'gold_holdout.json', '--eval')
Cfg '0' $null $null;  Run 'hold_stem_padrao' @('-u', 'run.py', '--list', 'gold_holdout.json', '--eval')
Cfg '0' 'htdemucs' 'mms'; Run 'hold_stem_antigo' @('-u', 'run.py', '--list', 'gold_holdout.json', '--eval')
'fim' | Set-Content logs\vd_done.txt
