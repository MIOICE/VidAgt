from app.services.ai_provider import _model_extra_body


def test_qwen3_disables_thinking_for_structured_outputs() -> None:
    assert _model_extra_body("Qwen/Qwen3.8-27B") == {"enable_thinking": False}
    assert _model_extra_body("qwen3.8-27b") == {"enable_thinking": False}


def test_other_model_does_not_receive_provider_specific_options() -> None:
    assert _model_extra_body("deepseek-ai/DeepSeek-V3.2") is None
