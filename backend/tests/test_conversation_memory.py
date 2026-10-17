from types import SimpleNamespace

from app.api.routes.analyses import _render_recent_history


def _message(role: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, content=content)


def test_history_preserves_dialogue_order_and_roles() -> None:
    history = _render_recent_history(
        [_message("user", "谁提出了方案？"), _message("assistant", "张三提出。")]
    )

    assert history == "用户：谁提出了方案？\n助手：张三提出。"


def test_history_trims_old_content_to_budget() -> None:
    history = _render_recent_history(
        [_message("user", "较早问题" * 10), _message("assistant", "最新回答")],
        max_chars=20,
    )

    assert history.startswith("…（较早对话已裁剪）")
    assert history.endswith("助手：最新回答")
