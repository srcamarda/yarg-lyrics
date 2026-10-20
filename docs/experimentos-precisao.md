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

## Rodada 2: outros modelos CTC (`YL_ALIGNER`, yl/aligners.py)

Mesma condição (voz do mix pelo RoFormer). `tools/aligner_compare.ps1` + `tools/exp_aligners.py`. Todos ~6,5 s/música.
- `w2v-960h`: facebook/wav2vec2-large-960h-lv60-self (inglês, fala; base do ALT e do singscope-align).
- `alt-dsing` / `alt-dali`: ALT (Ou/Gu et al., ISMIR 2022) ajustados em canto solo (DSing) / música mixada (DALI); inglês.

| Variante (56 músicas: 50 en + 6 pt) | med | ≤100 | ≤250 | >1 s | linhas ruins | mús >10% |
|---|---|---|---|---|---|---|
| MMS (atual) | 47 | 0,778 | 0,872 | 0,093 | 0,121 | 19 |
| ALT-DSing | 37 | 0,805 | 0,877 | 0,084 | 0,104 | 13 |
| ALT-DSing só em inglês (pt = MMS) | 34 | 0,852 | 0,909 | 0,061 | 0,080 | 11 |
| ALT-DALI | 604 | 0,352 | 0,419 | 0,427 | 0,484 | 55 |
| **w2v-960h** | 37 | 0,825 | 0,925 | 0,046 | 0,057 | 9 |
| Consenso MMS×Whisper (rodada 1) | 44 | 0,759 | 0,888 | 0,068 | 0,079 | 13 |
| **Consenso w2v-960h×ALT-DSing** (base w2v; pt só w2v) | 36 | 0,838 | 0,929 | 0,043 | 0,052 | 7 |
| idem + grade 1/8 ±60 ms | 23 | 0,838 | 0,929 | 0,043 | 0,052 | 7 |
| Consenso w2v×MMS×Whisper | 39 | 0,812 | 0,915 | 0,052 | 0,059 | 9 |

Por idioma
- Inglês (50): MMS 12,7% linhas ruins → w2v 5,8% → consenso w2v×ALT-DSing 5,3%.
- Português (6, amostra pequena): MMS 7,3% → w2v 5,0%; ALT-DSing 30,5% (não serve fora do inglês).

Conclusões
- O wav2vec2-960h da Meta (fala em inglês) é o melhor modelo único, inclusive nas poucas músicas em português.
- ALT-DSing (canto) é bom em inglês e ruim em português; como 2ª opinião do w2v melhora um pouco.
- ALT-DALI foi muito mal com voz separada — foi treinado com música mixada; não testado com o mix original.
- Whisper deixa de ajudar quando a base é o w2v.
- Viés mediano: MMS −20 ms, w2v +13 ms, ALT-DSing +9 ms, Whisper −290 ms.

## Rodada 3: padrão novo, ALT-DALI, calibração e validação (20/out/2026)

**Padrão novo** (sem variáveis de ambiente): RoFormer (só sem stem de voz) + wav2vec2-960h, viés de cada modelo descontado,
e nas músicas em inglês o ALT-DSing como 2ª opinião (por linha: discordância > 0,5 s -> fica o mais perto do LRCLIB).
Modo antigo: `YL_SEPARATOR=htdemucs YL_ALIGNER=mms` (as regras antigas de suspeita voltam junto com o MMS).

**ALT-DALI** (50 músicas en, linhas ruins): voz separada 48,5% (fim de época) / 25,4% (meio de época);
mix original 64,5% / 51,8%. Não serve para alinhar. Mix sem separação piora todos (w2v 61,1%, MMS 28,9%).

**Incerteza** (bootstrap por música, 56 músicas): MMS -> w2v −6,4 p.p. [−9,2; −3,9] (sólido);
w2v -> consenso −0,5 p.p. [−1,0; 0,0] (marginal); português com 6 músicas: IC de ~0,4% a ~19% (inconclusivo).

**Detector de instrumental**: 11 instrumentais conhecidas: w2v ≤ 0,11 caractere/s em 10, 0,48 na outra;
músicas com voz ≥ 0,79. Limiar 0,5 mantido. A marcada com .nolyrics engana todos os modelos.

**Suspeitas** recalibradas p/ o w2v (regras antigas: nível 2 só 18% de acerto / 15% de cobertura no modelo novo).
Nível 2: discordância entre os aligners > 0,8 s, desvio do LRCLIB > 3 s, duração > 1,5× a do LRCLIB, > 30 caracteres/s
ou linha colada (< 0,02 s) na anterior. Nível 1: score < 0,05, discordância > 0,3 s, desvio > 2 s ou < 4 caracteres/s.
Veredito: REVISAR se > 12% das linhas em nível 2 (mesmo limiar de antes).

### Validação (gold_holdout.json: 100 músicas novas, nunca usadas p/ ajustar nada)

| | antigo (htdemucs+MMS) | padrão novo |
|---|---|---|
| **Voz do mix** (97 músicas): linhas ruins | 15,7% | 6,4% |
| palavras > 1 s | 13,0% | 4,7% |
| palavras ≤ 100 ms | 72,4% | 84,6% |
| músicas com >10% erradas | 35 | 16 |
| **Uso normal, com stem** (98 músicas): linhas ruins | 12,1% | 6,2% |
| palavras > 1 s | 9,5% | 4,6% |
| palavras ≤ 100 ms | 76,9% | 85,1% |
| músicas com >10% erradas | 33 | 13 |
| português (6 músicas, stem): linhas ruins | 6,4% | 4,1% |

Gabarito (stem): 12,2% -> 5,4% linhas ruins; músicas ruins 21 -> 9.

Suspeitas na validação (stem): nível 2 marca 11% das linhas, 29% delas ruins, cobre 52% das ruins; sem flag 2,4% ruins.
Veredito: 30 de 98 REVISAR, pega 8 de 13 músicas ruins (antigo: 47 REVISAR, 30 de 33 ruins).
