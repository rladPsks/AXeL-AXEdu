"""One trusted handler factory shared by API and worker processes."""
import importlib
import os
import re

from .agents import Registry


def build_registry():
    target = os.getenv('SCHOOL_AGENT_REGISTRY_FACTORY', 'backend.openai_provider:create_registry')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*',target):
        raise ValueError('Registry factory must be a trusted local module:function')
    module, function = target.split(':')
    registry = getattr(importlib.import_module(module),function)()
    if not isinstance(registry,Registry):
        raise TypeError('Registry factory must return backend.agents.Registry')
    return registry
