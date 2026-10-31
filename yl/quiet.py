"""Silencia avisos conhecidos e inofensivos das bibliotecas, p/ que erros de verdade apareçam no console.

Chamado no import de yl.align (antes do transformers ser importado: as variáveis de ambiente são lidas no import).
YL_VERBOSE=1 desliga tudo isso.
"""
import os, warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def apply():
    if os.environ.get('YL_VERBOSE') == '1':
        return
    # Hugging Face: com o modelo já no cache não precisa de rede (some o aviso "unauthenticated requests")
    if os.path.isdir(os.path.join(ROOT, 'cache', 'models', 'hf', 'models--facebook--wav2vec2-large-960h-lv60-self')):
        os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
    # "LOAD REPORT ... masked_spec_embed MISSING": esse parâmetro só é usado no treino (máscara do SpecAugment)
    os.environ.setdefault('TRANSFORMERS_VERBOSITY', 'error')
    os.environ.setdefault('TRANSFORMERS_NO_ADVISORY_WARNINGS', '1')
    os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '1')     # barra "Loading weights" (ver também transformers_loaded)
    # atenção "Flash/Mem Efficient ... experimental" no ROCm: o PyTorch só avisa e usa a implementação padrão
    warnings.filterwarnings('ignore', message=r'.*(Flash|Mem) Efficient attention on Current AMD GPU.*')
    # forced_align do torchaudio marcado como obsoleto: ainda funciona na 2.9.1 (ver requirements-rocm.txt)
    warnings.filterwarnings('ignore', message=r'.*forced_align has been deprecated.*')
    warnings.filterwarnings('ignore', message=r'.*torchaudio\._backend.*deprecated.*')

def transformers_loaded():
    """Chamado logo depois de importar o transformers: tira as barras de progresso dele."""
    if os.environ.get('YL_VERBOSE') == '1':
        return
    try:
        from transformers.utils import logging as tl
        tl.set_verbosity_error()
        tl.disable_progress_bar()
    except Exception:
        pass
