"""Explicit deployment selection. Missing configuration always selects the safe demo."""
import os


def app_mode(*, cloud=False):
    if cloud:
        return 'demo'
    mode = os.environ.get('RAYBAN_APP_MODE', 'demo').strip().lower()
    if mode not in ('local', 'demo'):
        raise ValueError('RAYBAN_APP_MODE must be local or demo. No research operations were started.')
    return mode
