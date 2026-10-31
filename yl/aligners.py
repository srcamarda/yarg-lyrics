"""Modelos CTC alternativos ao MMS_FA, com a mesma interface que align.py espera.

YL_ALIGNER:
  mms           MMS_FA do torchaudio (padrão, multilíngue)
  w2v-960h      facebook/wav2vec2-large-960h-lv60-self (inglês, fala) — base do ALT e do singscope-align
  alt-dsing     ALT (Ou/Gu et al., ISMIR 2022) ajustado em canto solo (DSing) — inglês
  alt-dali      ALT ajustado em música mixada (DALI) — inglês

Interface (igual ao bundle MMS com star):
  model(wav[1, n]) -> (emissão [1, T, V+1] em log-prob, None); a última coluna é o coringa '*'
  tokenizer(lista_de_palavras_normalizadas) -> lista de listas de ids ('*' -> id do coringa)
Quadros de 20 ms (hop 320 a 16 kHz) e blank = 0 em todos.
"""
import os, glob
import torch
import torch.nn.functional as F

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HF_REPO = 'facebook/wav2vec2-large-960h-lv60-self'
HF_CACHE = os.path.join(ROOT, 'cache', 'models', 'hf')

import contextlib, importlib.util

# padrão: wav2vec2-960h (melhor no gabarito: linhas ruins 12,1% -> 5,7% contra o MMS); MMS se faltar o transformers
DEFAULT = 'w2v-960h' if importlib.util.find_spec('transformers') else 'mms'
# viés mediano medido no gabarito (s; positivo = atrasado): descontado de todas as palavras
BIAS = {'mms': -0.020, 'w2v-960h': 0.013, 'alt-dsing': 0.009, 'alt-dali': 0.018}
# 2ª opinião por idioma (consenso por linha com desempate pelo LRCLIB); YL_SECOND=0 desliga
SECOND = {'en': 'alt-dsing'}
_override = None

def name():
    return _override or os.environ.get('YL_ALIGNER') or DEFAULT

@contextlib.contextmanager
def using(n):
    """Troca o aligner dentro de um bloco (o modelo de cada um fica carregado em cache)."""
    global _override
    old, _override = _override, n
    try:
        yield
    finally:
        _override = old

def available(n):
    if n in ('mms',):
        return True
    if n == 'w2v-960h':
        return importlib.util.find_spec('transformers') is not None
    return bool(glob.glob(os.path.join(ROOT, 'cache', 'models', 'alt', n.split('-')[1], 'CKPT+*', 'wav2vec2.ckpt')))

def second_for(lang):
    """Só no modo padrão: com YL_ALIGNER explícito (experimentos) roda um modelo só, a não ser com YL_SECOND=1."""
    if os.environ.get('YL_SECOND') == '0' or (os.environ.get('YL_ALIGNER') and os.environ.get('YL_SECOND') != '1'):
        return None
    n = SECOND.get(lang)
    return n if n and n != name() and available(n) else None

class _Tok:
    """Mapa de caracteres (minúsculos a-z e ') -> ids do modelo; opcionalmente acrescenta o separador de palavra."""
    def __init__(self, char2id, star_id, boundary_id=None):
        self.c, self.star, self.b = char2id, star_id, boundary_id

    def __call__(self, words):
        out = []
        for w in words:
            if w == '*':
                out.append([self.star]); continue
            ids = [self.c[ch] for ch in w if ch in self.c]
            if self.b is not None:
                ids = ids + [self.b]
            out.append(ids or [self.star])
        return out

class _W2V(torch.nn.Module):
    """wav2vec2 + (opcional) camada densa do ALT + saída CTC; devolve log-probs com coluna coringa no fim."""
    def __init__(self, kind):
        super().__init__()
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Model, Wav2Vec2Config
        from yl import quiet
        quiet.transformers_loaded()
        self.kind = kind
        if kind == 'w2v-960h':
            self.net = Wav2Vec2ForCTC.from_pretrained(HF_REPO, cache_dir=HF_CACHE)
        else:
            cfg = Wav2Vec2Config.from_pretrained(HF_REPO, cache_dir=HF_CACHE)
            self.w2v = Wav2Vec2Model(cfg)
            d = glob.glob(os.path.join(ROOT, 'cache', 'models', 'alt', kind.split('-')[1], 'CKPT+*'))
            # YL_ALT_CKPT=mid usa o checkpoint do meio da época (DALI tem dois); padrão: o de fim de época
            pref = os.environ.get('YL_ALT_CKPT', 'end')
            d = sorted(d, key=lambda p: (('end-of-epoch: true' in open(os.path.join(p, 'CKPT.yaml')).read()) == (pref == 'end'), p))[-1]
            sd = torch.load(os.path.join(d, 'wav2vec2.ckpt'), map_location='cpu', weights_only=True)
            sd = {k[6:]: v for k, v in sd.items() if k.startswith('model.')}
            missing, unexpected = self.w2v.load_state_dict(sd, strict=False)
            assert not [m for m in missing if 'masked_spec' not in m], missing[:5]
            m = torch.load(os.path.join(d, 'model.ckpt'), map_location='cpu', weights_only=True)
            self.enc = torch.nn.Linear(1024, 1024)
            self.enc.load_state_dict({'weight': m['0.linear.w.weight'], 'bias': m['0.linear.w.bias']})
            self.ctc = torch.nn.Linear(1024, 31)
            self.ctc.load_state_dict({'weight': m['3.w.weight'], 'bias': m['3.w.bias']})
            self.ckpt = os.path.basename(d)

    def forward(self, wav):
        wav = F.layer_norm(wav, wav.shape[-1:])               # normalização do feature extractor (do_normalize)
        if self.kind == 'w2v-960h':
            logits = self.net(wav).logits
        else:
            h = self.w2v(wav).last_hidden_state
            h = F.layer_norm(h, h.shape[-1:])                  # output_norm do SpeechBrain
            logits = self.ctc(F.leaky_relu(self.enc(h)))
        lp = torch.log_softmax(logits.float(), -1)
        return F.pad(lp, (0, 1), value=0.0), None              # coringa '*' na última coluna (como o MMS with_star)

def load(device):
    """-> (model, tokenizer) do aligner escolhido."""
    import torchaudio
    k = name()
    if k == 'mms':
        b = torchaudio.pipelines.MMS_FA
        return b.get_model(with_star=True).eval().to(device), b.get_tokenizer()
    m = _W2V(k).eval().to(device)
    if k == 'w2v-960h':
        from transformers import Wav2Vec2Processor
        vocab = Wav2Vec2Processor.from_pretrained(HF_REPO, cache_dir=HF_CACHE).tokenizer.get_vocab()
        assert vocab['<pad>'] == 0                              # blank do CTC
        c2i = {ch.lower(): i for ch, i in vocab.items() if len(ch) == 1 and (ch.isalpha() or ch == "'")}
        V = m.net.config.vocab_size
        return m, _Tok(c2i, V, vocab.get('|') if os.environ.get('YL_W2V_BOUNDARY') == '1' else None)
    labels = {}
    for line in open(os.path.join(ROOT, 'cache', 'models', 'alt', k.split('-')[1], 'label_encoder.txt'), encoding='utf-8'):
        if line.startswith('='):
            break                                               # depois disso vêm só metadados
        if '=>' in line and line.strip()[0] in "'\"":
            lab, idx = line.rsplit('=>', 1)
            labels[lab.strip()[1:-1]] = int(idx)
    assert labels['<blank>'] == 0
    c2i = {ch.lower(): i for ch, i in labels.items() if len(ch) == 1 and (ch.isalpha() or ch == "'")}
    return m, _Tok(c2i, 31, labels[' '] if os.environ.get('YL_W2V_BOUNDARY') == '1' else None)
