"""
Client for the vLLM model management agent running on the GPU server.

The agent is a small standalone HTTP service (deployed separately on the GPU
server - see scripts/gpu_server/) that manages the vllm-70b container:
listing/downloading/activating/deleting Hugging Face models, without needing
SSH access from Django.
"""

import os
import requests

AGENT_BASE_URL = os.getenv('VLLM_UPDATE_AGENT_URL', 'http://192.168.1.32:8090')
AGENT_TOKEN = os.getenv('VLLM_UPDATE_AGENT_TOKEN', '')


def _headers():
    return {'Authorization': f'Bearer {AGENT_TOKEN}'}


def _error_message(resp):
    try:
        return resp.json().get('error', f'Agent returned HTTP {resp.status_code}')
    except ValueError:
        return f'Agent returned HTTP {resp.status_code}: {resp.text[:200]}'


def list_models(timeout=10):
    """Fetch every model known to the agent (downloaded, downloading, active). Returns (success, models_or_error)."""
    try:
        resp = requests.get(f'{AGENT_BASE_URL}/models', headers=_headers(), timeout=timeout)
        if resp.status_code == 200:
            return True, resp.json().get('models', [])
        return False, _error_message(resp)
    except requests.RequestException as e:
        return False, f'Could not reach update agent at {AGENT_BASE_URL}: {e}'


def download_model(model, timeout=10):
    """Pre-fetch a model's weights into the shared HF cache without touching the live container."""
    try:
        resp = requests.post(f'{AGENT_BASE_URL}/models/download', json={'model': model}, headers=_headers(), timeout=timeout)
        if resp.status_code == 202:
            return True, f'Download started for {model}'
        if resp.status_code == 409:
            return False, 'Already downloading'
        return False, _error_message(resp)
    except requests.RequestException as e:
        return False, f'Could not reach update agent at {AGENT_BASE_URL}: {e}'


def activate_model(model=None, timeout=10):
    """Switch the live container to serve `model` (or just restart the current one if None)."""
    try:
        payload = {'model': model} if model else {}
        resp = requests.post(f'{AGENT_BASE_URL}/models/activate', json=payload, headers=_headers(), timeout=timeout)
        if resp.status_code == 202:
            return True, 'Activation started on GPU server' + (f' (switching to {model})' if model else '')
        if resp.status_code == 409:
            return False, 'An activation is already in progress'
        return False, _error_message(resp)
    except requests.RequestException as e:
        return False, f'Could not reach update agent at {AGENT_BASE_URL}: {e}'


def delete_model(model, timeout=30):
    """Remove a model's weights from the HF cache to free disk space."""
    try:
        resp = requests.post(f'{AGENT_BASE_URL}/models/delete', json={'model': model}, headers=_headers(), timeout=timeout)
        if resp.status_code == 200:
            return True, f'Deleted {model}'
        return False, _error_message(resp)
    except requests.RequestException as e:
        return False, f'Could not reach update agent at {AGENT_BASE_URL}: {e}'


def stop_model(timeout=15):
    """Stop the live vLLM container without starting another model, to free
    GPU memory when requests are being routed elsewhere (e.g. OpenAI).

    Requires the agent to expose POST /models/stop - see do_stop() in
    scripts/gpu_server/vllm_update_agent.py. Older/undeployed agents will
    404, which is reported as a normal failure rather than raised, since
    this is a best-effort call from the provider-switch flow."""
    try:
        resp = requests.post(f'{AGENT_BASE_URL}/models/stop', json={}, headers=_headers(), timeout=timeout)
        if resp.status_code == 202:
            return True, 'Stop requested on GPU server'
        if resp.status_code == 404:
            return False, 'Update agent does not support /models/stop yet (needs redeploying)'
        return False, _error_message(resp)
    except requests.RequestException as e:
        return False, f'Could not reach update agent at {AGENT_BASE_URL}: {e}'


def get_status(timeout=10):
    """Fetch current/last activate-operation status from the agent. Returns (success, status_dict)."""
    try:
        resp = requests.get(f'{AGENT_BASE_URL}/status', headers=_headers(), timeout=timeout)
        if resp.status_code == 200:
            return True, resp.json()
        return False, {'error': _error_message(resp)}
    except requests.RequestException as e:
        return False, {'error': f'Could not reach update agent: {e}'}


# Backwards-compatible alias used by earlier code / the compare_llm_models command
def trigger_update(model=None, timeout=10):
    return activate_model(model=model, timeout=timeout)
