"""Validate an extracted pacman payload without importing the installed /opt tree.

Usage: /path/to/extracted/opt/hermes-agent/venv/bin/python -S validate-package.py \
       /path/to/extracted/opt/hermes-agent

-S deliberately prevents the packaged absolute hermes.pth from importing the
operator's installed /opt. The module path and bundled dependency path are
constructed explicitly; only fake response boundaries are used (no LLM calls).
"""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

root = Path(sys.argv[1]).resolve()
assert (root / 'run_agent.py').is_file()
assert sys.flags.no_site, 'Use python -S to avoid the installed absolute .pth'
site = root / 'venv/lib' / f'python{sys.version_info.major}.{sys.version_info.minor}/site-packages'
sys.path[:0] = [str(root), str(site)]
home = Path(tempfile.mkdtemp(prefix='hermes-fork-pkg-', dir=os.environ['TMPDIR']))
os.environ['HERMES_HOME'] = str(home)
os.environ['HERMES_SKIP_DOTENV'] = '1'
os.environ['HERMES_DISABLE_LAZY_INSTALLS'] = '1'
sys.dont_write_bytecode = True

import run_agent
from agent.agent_runtime_helpers import strip_think_blocks
from hermes_cli.cli_render import _strip_reasoning_tags

assert Path(run_agent.__file__).resolve().is_relative_to(root), run_agent.__file__
for rel in ('agent/agent_runtime_helpers.py', 'agent/turn_final_response.py', 'hermes_cli/cli_render.py'):
    ast.parse((root / rel).read_text())
for module in ('openai', 'anthropic', 'edge_tts', 'ddgs', 'lark_oapi', 'mautrix', 'defusedxml'):
    imported = __import__(module)
    assert Path(imported.__file__).resolve().is_relative_to(site), (module, imported.__file__)
assert (root / 'hermes_cli/web_dist/index.html').stat().st_size > 0
assert (root / 'hermes_cli/tui_dist/entry.js').stat().st_size > 0
stamp = json.loads((root / 'install-stamp.json').read_text())
assert stamp['distribution'] == 'package-manager'
assert stamp['displayVersion'] == '0.22.2+kita.dsml'
assert stamp['commit'] == 'ac8235dce42bc11a7d854161a9fee6e4e6a38d35'

leaks = [
    '<｜DSML｜tool_calls><｜DSML｜invoke name="terminal">print(1)\nprint(2)</｜DSML｜invoke></｜DSML｜tool_calls>',
    'Let me update it.</｜｜DSML｜｜ parameter>\n</｜｜DSML｜｜ invoke>\n</｜｜DSML｜｜ calls>',
    '<|DSML|invoke name="terminal"',
]


def response(text):
    return NS(choices=[NS(message=NS(content=text, tool_calls=None, reasoning_content=None, reasoning=None),
                          finish_reason='stop')], model='test/model', usage=None)


for candidate, leak in [('content', text) for text in leaks] + [
    (kind, 'print(123)\n</｜｜DSML｜｜ invoke>\n</｜｜DSML｜｜ calls>')
    for kind in ('reasoning', 'stream', 'housekeeping', 'length')
]:
    with (patch('model_tools.get_tool_definitions', return_value=[]),
          patch('model_tools.check_toolset_requirements', return_value={}),
          patch('agent.process_bootstrap.OpenAI')):
        agent: Any = run_agent.AIAgent(api_key='test-key-1234567890', base_url='https://example.invalid/v1',
                                  model='test/model', quiet_mode=True, skip_context_files=True,
                                  skip_memory=True, max_iterations=10)
    agent.client = MagicMock()
    agent._cached_system_prompt = 'Test prompt.'
    agent._use_prompt_caching = False
    agent._disable_streaming = True
    agent.compression_enabled = False
    agent.save_trajectories = False
    agent.tool_delay = 0
    agent._fallback_chain = []
    first = response(leak if candidate in ('content', 'length') else '')
    if candidate == 'reasoning':
        first.choices[0].message.reasoning_content = leak
    if candidate == 'length':
        first.choices[0].finish_reason = 'length'
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            if candidate == 'stream':
                agent._current_streamed_assistant_text = leak
            if candidate == 'housekeeping':
                agent._last_content_with_tools = leak
                agent._last_content_tools_all_housekeeping = True
            return first
        return response('Recovered final answer.')
    agent.client.chat.completions.create.side_effect = create
    with (patch.object(agent, '_persist_session'), patch.object(agent, '_save_trajectory'),
          patch.object(agent, '_cleanup_task_resources'),
          patch('agent.turn_final_response.answer_in_reasoning_capability', return_value=True),
          patch('agent.turn_empty_response.interruptible_backoff_sleep', return_value=None),
          patch('model_tools.handle_function_call') as tool):
        result = agent.run_conversation('Run the requested task.')
    assert agent.client.chat.completions.create.call_count == 2
    assert result['final_response'] == 'Recovered final answer.'
    assert not any('DSML' in str(m.get('content')) for m in result['messages'])
    tool.assert_not_called()

for scrub in (lambda text: strip_think_blocks(None, text).strip(), _strip_reasoning_tags):
    assert scrub('</｜｜DSML｜｜ parameter>\n</｜｜DSML｜｜ invoke>\n</｜｜DSML｜｜ calls>') == ''
print(json.dumps({'source_root': str(root), 'source_commit': stamp['commit'],
                  'module': run_agent.__file__, 'home': str(home),
                  'dsml_real_loop_cases': len(leaks) + 4, 'bundled_dependencies': 'passed',
                  'web_tui': 'passed', 'sanitizers': 'passed'}, indent=2))
