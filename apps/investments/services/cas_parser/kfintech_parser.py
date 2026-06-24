import logging
from .cams_parser import _normalize, _mask_pan
from .base import CASData

logger = logging.getLogger('apps.investments')


def parse_kfintech_cas(pdf_path: str, password: str) -> CASData:
    """Parse KFintech CAS PDF using the casparser library."""
    try:
        import casparser
        data = casparser.read_cas_pdf(pdf_path, password=password, output='dict')
        result = _normalize(data)
        result.cas_type = 'KFINTECH'
        return result
    except ImportError:
        raise RuntimeError('casparser library not installed. Run: pip install casparser')
    except Exception as e:
        raise ValueError(f'KFintech CAS parse error: {e}')
