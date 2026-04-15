from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from warden.engine.models import (
    ActionResult,
    Rule,
    Match,
)
from warden.engine.templates import build_template_context, render_value



def _make_match(**overrides) -> Match:
    defaults = {
        "rule_id": "test-rule",
        "description": "test description",
        "file": "/tmp/test.txt",
        "matched_content": "bad-content",
        "file_content": "full file content with bad-content inside",
    }
    defaults.update(overrides)
    return Match(**defaults)


class TestTemplateRendering:
    def test_render_plain_string(self):
        ctx = build_template_context([_make_match()])
        result = render_value("no placeholders here", ctx)
        assert result == "no placeholders here"

    def test_render_string_with_placeholder(self):
        ctx = build_template_context([_make_match(rule_id="my-rule")])
        result = render_value("Rule: ${{rule_id}}", ctx)
        assert result == "Rule: my-rule"

    def test_render_matched_content_placeholder(self):
        ctx = build_template_context([_make_match(matched_content="secret-key")])
        result = render_value("Found: ${{matched_content}}", ctx)
        assert result == "Found: secret-key"

    def test_render_dict_values(self):
        ctx = build_template_context([_make_match(file="/etc/config.json")])
        result = render_value({"key": "file=${{file}}", "static": "no-change"}, ctx)
        assert result == {"key": "file=/etc/config.json", "static": "no-change"}

    def test_render_list_values(self):
        ctx = build_template_context([_make_match(rule_id="r1")])
        result = render_value(["${{rule_id}}", "literal"], ctx)
        assert result == ["r1", "literal"]

    def test_render_nested_structure(self):
        ctx = build_template_context([_make_match(description="alert")])
        result = render_value({"outer": {"inner": "${{description}}"}}, ctx)
        assert result == {"outer": {"inner": "alert"}}

    def test_non_string_passthrough(self):
        ctx = build_template_context([_make_match()])
        assert render_value(42, ctx) == 42
        assert render_value(None, ctx) is None
        assert render_value(True, ctx) is True


class TestRequestAction:
    @patch("warden.engine.actions.requests.request")
    def test_basic_post_request(self, mock_request: MagicMock):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        rule = Rule(
            rule_id="test-request",
            files=["dummy.txt"],
            actions=[{
                "request": {
                    "url": "https://hooks.example.com/alert",
                    "method": "POST",
                    "body": "Rule triggered",
                },
            }],
        )

        match = _make_match()
        result = rule.apply_actions([match])

        assert result is ActionResult.REQUEST_SENT
        mock_request.assert_called_once_with(
            method="POST",
            url="https://hooks.example.com/alert",
            headers={},
            data="Rule triggered",
            timeout=30,
        )

    @patch("warden.engine.actions.requests.request")
    def test_request_with_placeholders(self, mock_request: MagicMock):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        rule = Rule(
            rule_id="alert-rule",
            files=["config.json"],
            actions=[{
                "request": {
                    "url": "https://hooks.example.com/notify",
                    "method": "POST",
                    "headers": {"X-Rule": "${{rule_id}}"},
                    "body": '{"text": "Violation in ${{file}}: ${{matched_content}}", "rule": "${{rule_id}}"}',
                },
            }],
        )

        match = _make_match(
            rule_id="alert-rule",
            file="/etc/config.json",
            matched_content="leaked-secret",
        )
        result = rule.apply_actions([match])

        assert result is ActionResult.REQUEST_SENT
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["url"] == "https://hooks.example.com/notify"
        assert call_kwargs["headers"] == {"X-Rule": "alert-rule"}
        body = json.loads(call_kwargs["data"])
        assert body["text"] == "Violation in /etc/config.json: leaked-secret"
        assert body["rule"] == "alert-rule"

    @patch("warden.engine.actions.requests.request")
    def test_request_default_method_is_post(self, mock_request: MagicMock):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        rule = Rule(
            rule_id="test",
            files=["dummy.txt"],
            actions=[{"request": {"url": "https://example.com/hook"}}],
        )

        rule.apply_actions([_make_match()])
        assert mock_request.call_args.kwargs["method"] == "POST"

    @patch("warden.engine.actions.requests.request")
    def test_request_with_string_body(self, mock_request: MagicMock):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        rule = Rule(
            rule_id="test",
            files=["dummy.txt"],
            actions=[{
                "request": {
                    "url": "https://example.com/hook",
                    "body": "plain text body about ${{rule_id}}",
                },
            }],
        )

        rule.apply_actions([_make_match(rule_id="test")])
        call_kwargs = mock_request.call_args.kwargs
        assert call_kwargs["data"] == "plain text body about test"

    @patch("warden.engine.actions.requests.request")
    def test_request_get_method(self, mock_request: MagicMock):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response

        rule = Rule(
            rule_id="test",
            files=["dummy.txt"],
            actions=[{
                "request": {
                    "url": "https://example.com/status",
                    "method": "GET",
                },
            }],
        )

        rule.apply_actions([_make_match()])
        assert mock_request.call_args.kwargs["method"] == "GET"
