# Backend Config Package
# Re-export settings from parent config.py for backward compatibility
import sys
import os

# Import settings from sibling config.py file (backend/config.py)
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_config_file = os.path.join(_parent_dir, 'config.py')

if os.path.exists(_config_file):
    import importlib.util
    spec = importlib.util.spec_from_file_location("_backend_config", _config_file)
    _config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_config_module)
    settings = _config_module.settings
else:
    # Fallback - try importing as if config is a module
    from backend import config as _config_module
    settings = _config_module.settings

