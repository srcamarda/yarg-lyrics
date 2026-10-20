# Experimentos de precisão (out/2026)

Conjunto de referência: `gold_all.json` (58 músicas com letra oficial; 56 avaliáveis, 10.731 palavras casadas).
Condição: voz separada **do mix** (`YL_IGNORE_VOCAL_STEM=1`), o caso difícil — músicas com stem de voz não dependem do separador.
Linha ruim = erro mediano das palavras da linha > 0,5 s. Ferramentas: `tools/sep_compare.ps1`, `tools/exp_whisper.py`, `tools/exp_eval.py`.

| Variante | med (ms) | ≤100 ms | ≤250 ms | >1 s | linhas ruins | músicas >10% erradas |
|---|---|---|---|---|---|---|
| htdemucs + MMS (antes) | 54 | 0,718 | 0,815 | 0,144 | 0,177 | 29 |
| **RoFormer + MMS** | 47 | 0,778 | 0,872 | 0,093 | 0,121 | 19 |
| RoFormer + MMS + grade 1/8 ±60 ms | 31 | 0,781 | 0,872 | 0,094 | 0,121 | 19 |
| RoFormer + MMS + grade 1/16 ±60 ms | 37 | 0,731 | 0,873 | 0,094 | 0,121 | 19 |
| Whisper large-v3 (stable-ts) sozinho | 310 | 0,081 | 0,401 | 0,288 | 0,309 | 43 |
| Whisper + 290 ms (viés descontado) | 166 | 0,308 | 0,628 | 0,280 | 0,276 | 42 |
| **Consenso MMS×Whisper(+290 ms), desempate pelo LRCLIB** | 50 | 0,761 | 0,890 | 0,068 | 0,078 | 13 |
| Consenso, só o início da linha do Whisper | 52 | 0,729 | 0,830 | 0,100 | 0,151 | 18 |

Conclusões
- Separador: RoFormer (MelBand, Kim) melhora tudo; 27 músicas melhores, 2 piores. ~50 s/música na RX 7800 XT.
  Precisa rodar em subprocesso novo por música (ROCm/Windows fica 4,5× mais lento reaproveitando o modelo) e às vezes
  devolve lixo na 1ª chamada — detectado pela correlação com o mix e repetido.
- Whisper: pior que o MMS para tempo de palavra e adianta ~290 ms de forma sistemática; serve como segunda opinião.
- Consenso: onde MMS e Whisper discordam > 0,5 s no início da linha, fica quem está mais perto do tempo do LRCLIB.
  Linhas ruins 12,1% → 7,8%; perde um pouco de precisão fina (≤100 ms 0,778 → 0,761). Custa ~25 s/música a mais.
  O viés de 290 ms foi medido neste mesmo conjunto (uma constante só, risco baixo de sobreajuste).
- Discordância como sinal de suspeita: precisão baixa (0,17–0,24) contra 0,61 do flag 2 atual — não vale como flag.
- Grade da música: só ajuda a precisão fina (mediana 47 → 31 ms com colcheia ±60 ms); semicolcheia piora.
- MMS adianta ~20 ms de forma sistemática.
