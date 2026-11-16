from src.ui.contagion import render_contagion
from src.ui.runtime import app_mode

render_contagion(force_demo=app_mode() != 'local')
