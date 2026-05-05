"""Unit tests for template_engine: variable schema validator, Jinja2 sandbox,
and whitelisted field walker."""

from __future__ import annotations

import pytest

from app.services.template_engine import (
    TemplateExpansionError,
    TemplateVariableError,
    expand_template,
    validate_variable_schema,
)

# ---------------------------------------------------------------------------
# Variable Schema Validator
# ---------------------------------------------------------------------------


class TestValidateVariableSchema:
    def test_none_schema_returns_merge_copy(self):
        merge = {"key": "value"}
        result = validate_variable_schema(None, merge)
        assert result == {"key": "value"}
        assert result is not merge

    def test_empty_schema_returns_merge_copy(self):
        merge = {"key": "value"}
        result = validate_variable_schema({}, merge)
        assert result == {"key": "value"}

    def test_required_field_present(self):
        schema = {"name": {"type": "string", "required": True}}
        result = validate_variable_schema(schema, {"name": "Alice"})
        assert result["name"] == "Alice"

    def test_required_field_missing_raises(self):
        schema = {"name": {"type": "string", "required": True}}
        with pytest.raises(TemplateVariableError) as exc_info:
            validate_variable_schema(schema, {})
        assert "Missing required variable" in exc_info.value.errors[0]

    def test_optional_field_missing_no_default(self):
        schema = {"name": {"type": "string", "required": False}}
        result = validate_variable_schema(schema, {})
        assert "name" not in result

    def test_optional_field_with_default(self):
        schema = {"name": {"type": "string", "default": "World"}}
        result = validate_variable_schema(schema, {})
        assert result["name"] == "World"

    def test_string_type_validation(self):
        schema = {"title": {"type": "string", "required": True}}
        result = validate_variable_schema(schema, {"title": "Hello"})
        assert result["title"] == "Hello"

    def test_string_type_coerces_number(self):
        schema = {"val": {"type": "string", "required": True}}
        result = validate_variable_schema(schema, {"val": 42})
        assert result["val"] == "42"

    def test_url_type_accepts_string(self):
        schema = {"link": {"type": "url", "required": True}}
        result = validate_variable_schema(
            schema, {"link": "https://example.com/img.jpg"}
        )
        assert result["link"] == "https://example.com/img.jpg"

    def test_number_type_accepts_int(self):
        schema = {"price": {"type": "number", "required": True}}
        result = validate_variable_schema(schema, {"price": 42})
        assert result["price"] == 42

    def test_number_type_accepts_float(self):
        schema = {"price": {"type": "number", "required": True}}
        result = validate_variable_schema(schema, {"price": 9.99})
        assert result["price"] == 9.99

    def test_number_type_coerces_string_int(self):
        schema = {"price": {"type": "number", "required": True}}
        result = validate_variable_schema(schema, {"price": "42"})
        assert result["price"] == 42

    def test_number_type_coerces_string_float(self):
        schema = {"price": {"type": "number", "required": True}}
        result = validate_variable_schema(schema, {"price": "9.99"})
        assert result["price"] == 9.99

    def test_number_type_rejects_non_numeric_string(self):
        schema = {"price": {"type": "number", "required": True}}
        with pytest.raises(TemplateVariableError) as exc_info:
            validate_variable_schema(schema, {"price": "not-a-number"})
        assert "expected type 'number'" in exc_info.value.errors[0]

    def test_boolean_type_accepts_bool(self):
        schema = {"visible": {"type": "boolean", "required": True}}
        result = validate_variable_schema(schema, {"visible": True})
        assert result["visible"] is True

    def test_boolean_type_coerces_string_true(self):
        schema = {"visible": {"type": "boolean", "required": True}}
        result = validate_variable_schema(schema, {"visible": "true"})
        assert result["visible"] is True

    def test_boolean_type_coerces_string_false(self):
        schema = {"visible": {"type": "boolean", "required": True}}
        result = validate_variable_schema(schema, {"visible": "false"})
        assert result["visible"] is False

    def test_boolean_type_rejects_invalid_string(self):
        schema = {"visible": {"type": "boolean", "required": True}}
        with pytest.raises(TemplateVariableError):
            validate_variable_schema(schema, {"visible": "maybe"})

    def test_number_type_rejects_bool(self):
        schema = {"count": {"type": "number", "required": True}}
        with pytest.raises(TemplateVariableError) as exc_info:
            validate_variable_schema(schema, {"count": True})
        assert "expected type 'number'" in exc_info.value.errors[0]

    def test_multiple_errors_collected(self):
        schema = {
            "name": {"type": "string", "required": True},
            "price": {"type": "number", "required": True},
        }
        with pytest.raises(TemplateVariableError) as exc_info:
            validate_variable_schema(schema, {})
        assert len(exc_info.value.errors) == 2

    def test_extra_variables_pass_through(self):
        schema = {"name": {"type": "string", "required": True}}
        result = validate_variable_schema(schema, {"name": "Alice", "extra": "ignored"})
        assert result["name"] == "Alice"
        assert result["extra"] == "ignored"

    def test_invalid_schema_definition(self):
        schema = {"name": "not_a_dict"}
        with pytest.raises(TemplateVariableError):
            validate_variable_schema(schema, {})


# ---------------------------------------------------------------------------
# Jinja2 Sandbox Engine and Whitelisted Field Walker
# ---------------------------------------------------------------------------


class TestExpandTemplate:
    def test_basic_expansion(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "image",
                                    "src": "{{ product_image }}",
                                }
                            }
                        ]
                    }
                ]
            }
        }
        result = expand_template(comp, {"product_image": "https://example.com/img.jpg"})
        asset = result["timeline"]["tracks"][0]["clips"][0]["asset"]
        assert asset["src"] == "https://example.com/img.jpg"

    def test_text_field_expansion(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "text",
                                    "text": "Hello {{ name }}!",
                                }
                            }
                        ]
                    }
                ]
            }
        }
        result = expand_template(comp, {"name": "World"})
        asset = result["timeline"]["tracks"][0]["clips"][0]["asset"]
        assert asset["text"] == "Hello World!"

    def test_color_field_expansion(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "text",
                                    "text": "Hi",
                                    "color": "{{ brand_color }}",
                                }
                            }
                        ]
                    }
                ]
            }
        }
        result = expand_template(comp, {"brand_color": "#ff0000"})
        asset = result["timeline"]["tracks"][0]["clips"][0]["asset"]
        assert asset["color"] == "#ff0000"

    def test_background_field_expansion(self):
        comp = {
            "timeline": {
                "background": "{{ bg_color }}",
                "tracks": [{"clips": [{"asset": {"type": "color", "color": "#000"}}]}],
            }
        }
        result = expand_template(comp, {"bg_color": "#112233"})
        assert result["timeline"]["background"] == "#112233"

    def test_font_family_expansion(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "text",
                                    "text": "Hi",
                                    "font_family": "{{ font }}",
                                }
                            }
                        ]
                    }
                ]
            }
        }
        result = expand_template(comp, {"font": "Roboto"})
        asset = result["timeline"]["tracks"][0]["clips"][0]["asset"]
        assert asset["font_family"] == "Roboto"

    def test_callback_field_expansion(self):
        comp = {"callback": "{{ webhook_url }}", "timeline": {"tracks": []}}
        result = expand_template(comp, {"webhook_url": "https://example.com/hook"})
        assert result["callback"] == "https://example.com/hook"

    def test_non_whitelisted_field_preserved(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "image",
                                    "src": "{{ img }}",
                                },
                                "start": 0.0,
                                "length": 3.0,
                                "fit": "{{ should_not_expand }}",
                            }
                        ]
                    }
                ]
            }
        }
        result = expand_template(
            comp,
            {"img": "https://example.com/x.jpg", "should_not_expand": "cover"},
        )
        clip = result["timeline"]["tracks"][0]["clips"][0]
        assert clip["asset"]["src"] == "https://example.com/x.jpg"
        assert clip["fit"] == "{{ should_not_expand }}"

    def test_numeric_field_not_expanded(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {"type": "image", "src": "a.jpg"},
                                "start": 0.0,
                                "length": 3.0,
                                "opacity": 0.5,
                            }
                        ]
                    }
                ]
            }
        }
        result = expand_template(comp, {"anything": "value"})
        clip = result["timeline"]["tracks"][0]["clips"][0]
        assert clip["opacity"] == 0.5

    def test_strict_undefined_raises(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "image",
                                    "src": "{{ missing_var }}",
                                }
                            }
                        ]
                    }
                ]
            }
        }
        with pytest.raises(TemplateExpansionError):
            expand_template(comp, {})

    def test_sandbox_prevents_python_access(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "text",
                                    "text": "{{ ''.__class__.__mro__ }}",
                                }
                            }
                        ]
                    }
                ]
            }
        }
        with pytest.raises(TemplateExpansionError):
            expand_template(comp, {})

    def test_empty_variables_returns_unchanged(self):
        comp = {"timeline": {"tracks": []}, "output": {"format": "mp4"}}
        result = expand_template(comp, {})
        assert result == comp

    def test_no_template_syntax_passthrough(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "image",
                                    "src": "https://example.com/img.jpg",
                                }
                            }
                        ]
                    }
                ]
            }
        }
        result = expand_template(comp, {"unused": "val"})
        asset = result["timeline"]["tracks"][0]["clips"][0]["asset"]
        assert asset["src"] == "https://example.com/img.jpg"

    def test_nested_structures_expanded(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "image",
                                    "src": "{{ img1 }}",
                                }
                            },
                            {
                                "asset": {
                                    "type": "text",
                                    "text": "{{ headline }}",
                                }
                            },
                        ]
                    },
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "video",
                                    "src": "{{ video_url }}",
                                }
                            }
                        ]
                    },
                ]
            }
        }
        result = expand_template(
            comp,
            {
                "img1": "https://img.com/1.jpg",
                "headline": "Breaking News",
                "video_url": "https://vid.com/v.mp4",
            },
        )
        t = result["timeline"]["tracks"]
        assert t[0]["clips"][0]["asset"]["src"] == "https://img.com/1.jpg"
        assert t[0]["clips"][1]["asset"]["text"] == "Breaking News"
        assert t[1]["clips"][0]["asset"]["src"] == "https://vid.com/v.mp4"

    def test_jinja2_in_value_no_double_expansion(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "text",
                                    "text": "{{ user_input }}",
                                }
                            }
                        ]
                    }
                ]
            }
        }
        result = expand_template(comp, {"user_input": "{{ should_not_expand }}"})
        asset = result["timeline"]["tracks"][0]["clips"][0]["asset"]
        assert asset["text"] == "{{ should_not_expand }}"

    def test_multiple_variables_in_one_field(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "text",
                                    "text": "{{ greeting }} {{ name }}!",
                                }
                            }
                        ]
                    }
                ]
            }
        }
        result = expand_template(comp, {"greeting": "Hello", "name": "World"})
        asset = result["timeline"]["tracks"][0]["clips"][0]["asset"]
        assert asset["text"] == "Hello World!"

    def test_empty_string_variable(self):
        comp = {
            "timeline": {
                "tracks": [
                    {
                        "clips": [
                            {
                                "asset": {
                                    "type": "text",
                                    "text": "{{ content }}",
                                }
                            }
                        ]
                    }
                ]
            }
        }
        result = expand_template(comp, {"content": ""})
        asset = result["timeline"]["tracks"][0]["clips"][0]["asset"]
        assert asset["text"] == ""
