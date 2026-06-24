import ast
import asyncio
from pathlib import Path

import messages
from callback_simple_flows import handle_pastdate_callback


class DummyQuery:
    def __init__(self):
        self.answers = []

    async def answer(self, text=None, show_alert=None):
        self.answers.append((text, show_alert))


def test_pastdate_callback_uses_centralized_message():
    query = DummyQuery()

    asyncio.run(handle_pastdate_callback(query=query))

    assert query.answers == [(messages.MSG_PAST_DATE_ALERT, True)]


def test_pastdate_message_is_exported():
    assert "MSG_PAST_DATE_ALERT" in messages.__all__


def test_callback_simple_flows_has_no_inline_pastdate_alert_literal():
    source = Path("callback_simple_flows.py").read_text()
    tree = ast.parse(source)

    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "Эта дата уже прошла. Выбери другую.":
            findings.append(node.lineno)

    assert findings == []
