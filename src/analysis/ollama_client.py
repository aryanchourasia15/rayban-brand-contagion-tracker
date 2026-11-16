"""Loopback-only Ollama transport; no pull endpoint, tools or cloud fallback."""
import ipaddress
import json
import re
from urllib.parse import urlsplit

import requests


class LocalModelError(RuntimeError):
    pass


def local_model_status():
    """Explicit metadata-only connectivity check, without inference or downloads."""
    client = OllamaClient('inventory:latest', timeout=3)
    try:
        inventory = client._call('GET', '/api/tags').get('models')
        if not isinstance(inventory, list) or any(not isinstance(m, dict) for m in inventory):
            raise LocalModelError('Malformed installed-model inventory.')
        names = []
        for item in inventory:
            name = item.get('name') or item.get('model')
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]+', name) or 'cloud' in name.lower() or '://' in name:
                continue
            if item.get('remote_host') or item.get('remote_model') or type(item.get('size')) is not int or item['size'] <= 0 or not item.get('digest'):
                continue
            names.append(name)
        version = client._call('GET', '/api/version').get('version')
        if not isinstance(version, str) or not version:
            raise LocalModelError('Cannot identify local Ollama runtime.')
        return {'version': version, 'models': sorted(set(names))}
    finally:
        client.close()


class OllamaClient:
    def __init__(self, model, base_url='http://127.0.0.1:11434', timeout=120):
        parsed = urlsplit(base_url)
        try:
            local = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            local = False
        if not local or parsed.scheme != 'http' or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
            raise ValueError('Only literal loopback HTTP addresses are permitted.')
        if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9_.:/-]+', model) or 'cloud' in model.lower() or '://' in model:
            raise ValueError('Select an installed local model, not a cloud identifier.')
        self.model, self.base_url, self.timeout = model, base_url.rstrip('/'), timeout
        self.session = requests.Session()
        self.session.trust_env = False
        self.metadata = None

    def _call(self, method, path, payload=None):
        try:
            response = self.session.request(method, self.base_url + path, json=payload,
                                            timeout=self.timeout, allow_redirects=False)
            if response.status_code != 200:
                raise LocalModelError(f'Local Ollama returned HTTP {response.status_code}.')
            data = response.json()
            if not isinstance(data, dict):
                raise LocalModelError('Malformed local Ollama response.')
            return data
        except (requests.RequestException, ValueError):
            raise LocalModelError('Local Ollama unavailable or returned invalid JSON.') from None

    def inspect(self):
        """Check an installed GGUF model and reject remote stubs before sending text."""
        models = self._call('GET', '/api/tags').get('models', [])
        if not isinstance(models, list) or any(not isinstance(m, dict) for m in models):
            raise LocalModelError('Invalid local model inventory.')
        model = next((m for m in models if m.get('name') == self.model or m.get('model') == self.model), None)
        if not model or not isinstance(model.get('digest'), str) or not model.get('digest') or type(model.get('size')) is not int or model['size'] <= 0:
            raise LocalModelError('Model is not installed locally; no downloads will be attempted.')
        details = self._call('POST', '/api/show', {'model': self.model})
        model_details = details.get('details')
        if model.get('remote_host') or model.get('remote_model') or details.get('remote_host') or details.get('remote_model') or not isinstance(model_details, dict) or model_details.get('format') != 'gguf':
            raise LocalModelError('Remote or unverifiable model routing is prohibited.')
        version = self._call('GET', '/api/version').get('version')
        if not isinstance(version, str) or not version:
            raise LocalModelError('Cannot identify Ollama runtime version.')
        self.metadata = dict(model_name=self.model, model_version=model['digest'], runtime_version=version)
        return dict(self.metadata)

    def generate(self, system_prompt, text, schema):
        if self.metadata is None:
            raise LocalModelError('Inspect the installed model before generation.')
        result = self._call('POST', '/api/chat', {
            'model': self.model, 'stream': False, 'format': schema,
            'messages': [{'role': 'system', 'content': system_prompt},
                         {'role': 'user', 'content': json.dumps({'discussion_text': text})}],
            'options': {'temperature': 0, 'seed': 0},
        })
        if result.get('done') is not True or result.get('done_reason') not in (None, 'stop') or result.get('model') != self.model:
            raise LocalModelError('Incomplete generation or unexpected model identity.')
        message = result.get('message')
        output = message.get('content') if isinstance(message, dict) else None
        if not isinstance(output, str):
            raise LocalModelError('Local model returned no classification text.')
        return output

    def close(self):
        self.session.close()
