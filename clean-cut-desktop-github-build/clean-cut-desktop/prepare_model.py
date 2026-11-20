"""Download a verified U2NetP model through rembg into project/models."""
import os
from pathlib import Path

base = Path(__file__).resolve().parent
models = base / 'models'
models.mkdir(exist_ok=True)
os.environ['U2NET_HOME'] = str(models)
print('Downloading / checking the u2netp model...')
from rembg import new_session
new_session('u2netp')
file = models / 'u2netp.onnx'
if not file.exists():
    raise RuntimeError('Expected model was not found: ' + str(file))
print('Model ready:', file, 'bytes:', file.stat().st_size)
