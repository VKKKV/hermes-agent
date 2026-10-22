"""DSML must not eat Markdown examples, promote private reasoning, or replay argument tails."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.agent_runtime_helpers import strip_think_blocks
from agent.dsml import has_unexecuted_dsml, sanitize_dsml
from tests.agent.test_run_agent import _make_tool_defs, _mock_response, _mock_tool_call

CALL = '<|DSML|invoke name="terminal">'
CLOSE = '</|DSML|invoke>'
EXAMPLE = f'```xml\n{CALL}\n{CLOSE}\n```'
ANSWER = 'Here is the final answer.'


@pytest.mark.parametrize('text', [
    EXAMPLE,
    f'- ```xml\n  {CALL}\n  {CLOSE}\n  ```',
    f'1. ```xml\n   {CALL}\n   ```',
    f'> - ```xml\n>   {CALL}\n>   ```',
    f'```xml\n{CALL}',
    f'    {CALL}\n    {CLOSE}',
    f'Use `{CALL}` as a syntax example.',
    f'Use ``first line\n{CALL}`` as a syntax example.',
    f'> `first line\n> {CALL}`',
])
def test_markdown_code_survives_storage_and_display(text):
    from hermes_cli.cli_render import _strip_reasoning_tags

    assert not has_unexecuted_dsml(text)
    assert sanitize_dsml(text) == text
    assert strip_think_blocks(None, text) == text
    assert _strip_reasoning_tags(text) == text.strip()


@pytest.mark.parametrize('text', [
    CALL,
    f'prefix {CALL} with unknown arguments',
    f'`example\n\n{CALL}\n\n`',
    f'- `example\n- {CALL}\n- `',
    f'\\` {CALL} `',
    f'[label]({CALL})',
    f'[label]: {CALL}',
    f'<div>\n{CALL}\n</div>',
    f'{EXAMPLE}\n{CALL}',
    '> ' * 30 + CALL,
    '<｜DSML｜invoke name="terminal">',
])
def test_protocol_outside_real_code_is_rejected(text):
    from hermes_cli.cli_render import _strip_reasoning_tags

    assert has_unexecuted_dsml(text)
    assert sanitize_dsml(text) == ''
    assert strip_think_blocks(None, text) == ''
    assert _strip_reasoning_tags(text) == ''


@pytest.fixture()
def loop_agent(monkeypatch):
    from run_agent import AIAgent

    monkeypatch.setattr('hermes_cli.plugins.discover_plugins', lambda: None)
    monkeypatch.setattr('agent.turn_empty_response.interruptible_backoff_sleep', lambda *a, **k: None)
    with (
        patch('model_tools.get_tool_definitions', return_value=_make_tool_defs('todo_list')),
        patch('model_tools.check_toolset_requirements', return_value={}),
        patch('agent.process_bootstrap.OpenAI'),
    ):
        agent = AIAgent(
            api_key='test-key-1234567890', base_url='https://openrouter.ai/api/v1',
            quiet_mode=True, skip_context_files=True, skip_memory=True,
        )
    agent.client = MagicMock()
    agent._cached_system_prompt = 'You are helpful.'
    agent._use_prompt_caching = False
    agent.compression_enabled = False
    agent.save_trajectories = False
    agent._stall_guards = False
    agent._codex_ack_mode = 'off'
    return agent


def _run(agent, script, history=None):
    agent.client.chat.completions.create.side_effect = script
    with (
        patch.object(agent, '_persist_session'),
        patch.object(agent, '_save_trajectory'),
        patch.object(agent, '_cleanup_task_resources'),
        patch('model_tools.handle_function_call', return_value='{"ok":true}'),
    ):
        return agent.run_conversation('Explain the syntax, then tidy the task list.', conversation_history=history)


@pytest.mark.parametrize('details', [
    None,
    [{'type': 'thinking', 'thinking': CALL, 'signature': 'synthetic-signature'}],
    [{'type': 'example.native_assistant', 'messages': []}],
])
def test_private_reasoning_does_not_discard_stream(loop_agent, details):
    if details is not None:
        # Even a trusted route cannot promote signed/native private thinking.
        loop_agent.base_url = 'http://127.0.0.1:8000/v1'
        loop_agent.provider = 'vllm'
        loop_agent.model = 'nvidia/Nemotron-3.5-Lightning-30B'

    def response(**_kwargs):
        loop_agent._current_streamed_assistant_text = ANSWER
        return _mock_response(content='', reasoning_content=f'Private analysis mentions {CALL}',
                              reasoning_details=details)

    result = _run(loop_agent, response)
    assert ANSWER in result['final_response']
    assert loop_agent.client.chat.completions.create.call_count == 1
    assert any(m.get('content') == ANSWER for m in result['messages'])


def test_private_reasoning_does_not_discard_housekeeping_answer(loop_agent):
    result = _run(loop_agent, [
        _mock_response(content=ANSWER, finish_reason='tool_calls',
                       tool_calls=[_mock_tool_call('todo_list', '{"todos": []}', 'call_tidy')]),
        _mock_response(content='', reasoning_content=f'Private analysis mentions {CALL}'),
        _mock_response(content='Unnecessary replacement.'),
    ])
    assert result['final_response'] == ANSWER
    assert result['response_reused'] is True
    assert loop_agent.client.chat.completions.create.call_count == 2


def test_trusted_reasoning_leak_retries_instead_of_promoting(loop_agent):
    loop_agent.base_url = 'http://127.0.0.1:8000/v1'
    loop_agent.provider = 'vllm'
    loop_agent.model = 'nvidia/Nemotron-3.5-Lightning-30B'
    result = _run(loop_agent, [
        _mock_response(content='', reasoning_content=CALL),
        _mock_response(content=ANSWER),
    ])
    assert result['final_response'] == ANSWER
    assert loop_agent.client.chat.completions.create.call_count == 2
    assert not any(CALL in (m.get('content') or '') for m in result['messages'])


def test_valid_content_ignores_private_reasoning_and_stale_fallback(loop_agent):
    def response(**_kwargs):
        loop_agent._current_streamed_assistant_text = CALL
        loop_agent._last_content_with_tools = CALL
        loop_agent._last_content_tools_all_housekeeping = True
        return _mock_response(content=ANSWER, reasoning_content=CALL)

    assert _run(loop_agent, response)['final_response'] == ANSWER
    assert loop_agent.client.chat.completions.create.call_count == 1


@pytest.mark.parametrize('middle_finish', ['stop', 'length'])
def test_fenced_example_across_continuations_keeps_context(loop_agent, middle_finish):
    script = [_mock_response(content=f'```xml\n{CALL}\n', finish_reason='length')]
    if middle_finish == 'length':
        script += [_mock_response(content=f'{CLOSE}\n', finish_reason='length'),
                   _mock_response(content='```')]
    else:
        script += [_mock_response(content=f'{CLOSE}\n```')]
    result = _run(loop_agent, script)
    assert result['completed'] is True
    assert result['final_response'] == EXAMPLE
    assert loop_agent.client.chat.completions.create.call_count == len(script)
    assert CLOSE in '\n'.join(m.get('content') or '' for m in result['messages'])
    if middle_finish == 'length':
        wire = loop_agent.client.chat.completions.create.call_args.kwargs['messages']
        assert any(CLOSE in (m.get('content') or '') for m in wire if m['role'] == 'assistant')


def test_rejected_truncation_never_continues_unknown_argument_tail(loop_agent):
    result = _run(loop_agent, [
        _mock_response(content='Unexecuted call: <|DSML|invoke', finish_reason='length'),
        _mock_response(content=' name="terminal">not executed'),
    ])
    assert result['completed'] is False
    assert result['partial'] is True
    assert result['failure_reason'] == 'invalid_response'
    assert result['failure_retryable'] is True
    assert loop_agent.client.chat.completions.create.call_count == 1
    assert 'name="terminal"' not in result['final_response']
    assert not any('DSML' in (m.get('content') or '') for m in result['messages'])
    assert not any(m.get('_length_continuation_nudge') for m in result['messages'])

    # Rejection is turn-local; a later user request can receive a real answer.
    result = _run(loop_agent, [_mock_response(content=ANSWER)], history=result['messages'])
    assert result['completed'] is True
    assert result['final_response'] == ANSWER


def test_list_example_and_cross_paragraph_leak_use_real_loop(loop_agent):
    example = f'- ```xml\n  {CALL}\n  ```'
    result = _run(loop_agent, [_mock_response(content=example)])
    assert result['final_response'] == example

    leak = f'`example\n\n{CALL}\n\n`'
    result = _run(loop_agent, [_mock_response(content=leak), _mock_response(content=ANSWER)])
    assert result['final_response'] == ANSWER
    assert not any(CALL in (m.get('content') or '') for m in result['messages'])


@pytest.mark.parametrize('stream, cache, eligible', [
    (ANSWER, CALL, False),
    (ANSWER, CALL, True),
    (CALL, ANSWER, True),
    ('', CALL, False),
    (CALL, '', False),
])
def test_fallback_selection_ignores_unused_sources(loop_agent, stream, cache, eligible):
    def response(**_kwargs):
        loop_agent._current_streamed_assistant_text = stream
        loop_agent._last_content_with_tools = cache
        loop_agent._last_content_tools_all_housekeeping = eligible
        return _mock_response(content='')

    pending = iter([response, _mock_response(content=ANSWER)])

    def create(**kwargs):
        reply = next(pending)
        return reply(**kwargs) if callable(reply) else reply

    result = _run(loop_agent, create)
    assert ANSWER in result['final_response']
    assert not any(CALL in (m.get('content') or '') for m in result['messages'])


def test_content_block_list_is_flattened_before_joining(loop_agent):
    def block_response(text, finish='stop'):
        response = _mock_response(content='', finish_reason=finish)
        response.choices[0].message.content = [{'type': 'text', 'text': text}]
        return response

    result = _run(loop_agent, [block_response(ANSWER)])
    assert result['final_response'] == ANSWER
    loop_agent.client.chat.completions.create.reset_mock()
    result = _run(loop_agent, [
        block_response(CALL),
        _mock_response(content=ANSWER),
    ])
    assert result['final_response'] == ANSWER
    assert loop_agent.client.chat.completions.create.call_count == 2
    loop_agent.client.chat.completions.create.reset_mock()
    result = _run(loop_agent, [
        block_response('First part.\n', 'length'),
        _mock_response(content=ANSWER),
    ])
    assert result['final_response'] == 'First part.\n' + ANSWER


def test_continuation_storage_preserves_context_and_scrubs_private_text(loop_agent, monkeypatch):
    from agent.chat_completion_helpers import build_assistant_message

    monkeypatch.setenv('HERMES_REDACT_SECRETS', '1')
    secret = 'sk-' + 'syntheticprivatevalue' * 4
    tail = f'{CLOSE}\n```\n<think>hidden analysis</think>\n{secret}'
    message = _mock_response(content=tail).choices[0].message
    stored = build_assistant_message(loop_agent, message, 'stop', dsml_context=f'```xml\n{CALL}\n{tail}')
    assert CLOSE in stored['content']
    assert 'hidden analysis' not in stored['content']
    assert secret not in stored['content']


def test_fenced_continuation_is_durable_in_session_db(loop_agent, tmp_path):
    from hermes_state import SessionDB

    with SessionDB(db_path=tmp_path / 'state.db') as db:
        loop_agent._session_db = db
        loop_agent._session_db_created = False
        loop_agent.session_id = 'synthetic-dsml-continuation'
        result = _run(loop_agent, [
            _mock_response(content=f'```xml\n{CALL}\n', finish_reason='length'),
            _mock_response(content=f'{CLOSE}\n```'),
        ])
        rows = db.get_messages_as_conversation(loop_agent.session_id)
        assert result['final_response'] == EXAMPLE
        assert any(CLOSE in (m.get('content') or '') for m in rows if m['role'] == 'assistant')


def test_empty_final_after_truncation_still_uses_empty_recovery(loop_agent):
    result = _run(loop_agent, [
        _mock_response(content='Prefix that is not the answer.\n', finish_reason='length'),
        _mock_response(content=''),
        _mock_response(content=ANSWER),
    ])
    assert ANSWER in result['final_response']
    assert loop_agent.client.chat.completions.create.call_count == 3
