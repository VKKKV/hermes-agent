"""Leaked DSML is an unexecuted tool attempt, never a completed answer.

Regression for #119261; fixtures are synthetic, including doubled-pipe orphan
closers with spaces and the `calls` spelling emitted by compatible gateways.
"""
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, patch

import pytest

from agent.agent_runtime_helpers import strip_think_blocks
from hermes_cli.cli_render import _strip_reasoning_tags
from run_agent import AIAgent


@pytest.mark.parametrize('pipes', ['｜', '｜｜', '|', '||'])
def test_closed_cut_orphan_and_prose(pipes):
    opener = '<' + pipes + 'DSML' + pipes
    closer = '</' + pipes + 'DSML' + pipes
    block = (opener + 'calls>' + opener + 'invoke name="terminal">'
             + opener + 'parameter name="command">print(1)\nprint(2)'
             + closer + 'parameter>' + closer + 'invoke>' + closer + 'calls>')
    for scrub in (lambda s: strip_think_blocks(None, s).strip(), _strip_reasoning_tags):
        assert scrub(block) == ''
        assert scrub('before\n' + block + '\nafter') == 'before\n\nafter'
        assert scrub(closer + ' parameter>' + closer + ' invoke>' + closer + ' calls>') == ''
        assert scrub('before\n' + opener + 'invoke name="terminal"') == 'before'
        assert scrub('DSML is a protocol; a || b; <function> remains') == 'DSML is a protocol; a || b; <function> remains'


def _response(text):
    message = NS(content=text, tool_calls=None, reasoning_content=None, reasoning=None)
    return NS(choices=[NS(message=message, finish_reason='stop')], model='test/model', usage=None)


@pytest.fixture
def agent():
    with (patch('model_tools.get_tool_definitions', return_value=[]),
          patch('model_tools.check_toolset_requirements', return_value={}),
          patch('agent.process_bootstrap.OpenAI')):
        agent = AIAgent(api_key='test-key-1234567890', base_url='https://example.invalid/v1',
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
    return agent


@pytest.mark.parametrize('leak', [
    '<｜DSML｜tool_calls><｜DSML｜invoke name="terminal"><｜DSML｜parameter name="command">print(1)\nprint(2)</｜DSML｜parameter></｜DSML｜invoke></｜DSML｜tool_calls>',
    'python payload\nprint(1)\n</｜｜DSML｜｜parameter></｜｜DSML｜｜invoke></｜｜DSML｜｜tool_calls>',
    '<｜DSML｜invoke name="terminal"',
    'Let me update the script.</｜｜DSML｜｜ parameter>\n</｜｜DSML｜｜ invoke>\n</｜｜DSML｜｜ calls>',
])
def test_real_turn_retries_unexecuted_dsml(agent, leak):
    agent.client.chat.completions.create.side_effect = [_response(leak), _response('Recovered final answer.')]
    # External boundaries only: run the real final-response and recovery ladder.
    with (patch.object(agent, '_persist_session'), patch.object(agent, '_save_trajectory'),
          patch.object(agent, '_cleanup_task_resources'),
          patch('agent.turn_empty_response.interruptible_backoff_sleep', return_value=None),
          patch('model_tools.handle_function_call') as tool):
        result = agent.run_conversation('Run the requested task.')
    assert agent.client.chat.completions.create.call_count == 2
    assert result['final_response'] == 'Recovered final answer.'
    assert result['completed'] is True
    assert not any('DSML' in str(m.get('content')) or 'python payload' in str(m.get('content')) for m in result['messages'])
    tool.assert_not_called()


def test_repeated_dsml_is_bounded_and_not_executed(agent):
    leak = 'unexecuted\n</｜｜DSML｜｜ invoke></｜｜DSML｜｜ calls>'
    agent.client.chat.completions.create.side_effect = [_response(leak) for _ in range(8)]
    with (patch.object(agent, '_persist_session'), patch.object(agent, '_save_trajectory'),
          patch.object(agent, '_cleanup_task_resources'),
          patch('agent.turn_empty_response.interruptible_backoff_sleep', return_value=None),
          patch('model_tools.handle_function_call') as tool):
        result = agent.run_conversation('Run the requested task.')
    assert 1 < agent.client.chat.completions.create.call_count <= 4
    assert result['turn_exit_reason'] == 'empty_response_exhausted'
    assert 'DSML' not in str(result.get('final_response'))
    tool.assert_not_called()
