from types import SimpleNamespace


def _typer(mode="auto", tool="/usr/bin/ydotool"):
    from voxd.core.typer import SimulatedTyper
    t = SimulatedTyper.__new__(SimulatedTyper)
    t.enabled = True
    t.delay_ms = 1.0
    t.delay_str = "1"
    t.start_delay = 0
    t.tool = tool
    t.cfg = SimpleNamespace(data={"typing_mode": mode, "append_trailing_space": False})
    return t


def test_typing_mode_defaults_to_auto():
    from voxd.core.typer import SimulatedTyper
    t = SimulatedTyper.__new__(SimulatedTyper)
    t.cfg = None
    assert t._typing_mode() == "auto"
    t.cfg = SimpleNamespace(data={"typing_mode": "weird"})
    assert t._typing_mode() == "auto"
    t.cfg = SimpleNamespace(data={"typing_mode": "TYPE"})
    assert t._typing_mode() == "type"


def test_paste_mode_never_types(monkeypatch):
    t = _typer(mode="paste")
    calls = []
    t._paste = lambda text, _from_fallback=False: calls.append(text)
    t._type_via_tool = lambda text: calls.append(("type", text)) or True
    t.type("Hello world")
    assert calls == ["Hello world"]


def test_auto_pastes_cyrillic_but_types_english(monkeypatch):
    t = _typer(mode="auto")
    calls = []
    t._paste = lambda text, _from_fallback=False: calls.append(("paste", text))
    t._type_via_tool = lambda text: calls.append(("type", text)) or True
    t.type("Hello world")
    t.type("Привет мир")
    assert calls[0] == ("type", "Hello world")
    assert calls[1] == ("paste", "Привет мир")


def test_force_type_mode_types_even_cyrillic(monkeypatch):
    t = _typer(mode="type")
    calls = []
    t._paste = lambda text, _from_fallback=False: calls.append(("paste", text))
    t._type_via_tool = lambda text: calls.append(("type", text)) or True
    t.type("Привет мир")
    assert calls == [("type", "Привет мир")]


def test_failed_typing_retries_then_pastes(monkeypatch):
    t = _typer(mode="type")
    t._ensure_daemon = lambda: True
    attempts = []
    t._type_via_tool = lambda text: (attempts.append(text), False)[1]
    pasted = []
    t._paste = lambda text, _from_fallback=False: pasted.append(text)
    monkeypatch.setattr("time.sleep", lambda s: None)
    t.type("hello")
    assert attempts == ["hello"] * 3
    assert pasted == ["hello"]


def test_dash_leading_text_uses_separator(monkeypatch):
    t = _typer(mode="type")
    seen = []
    t._run_tool = lambda cmd: seen.append(cmd) or True
    assert t._type_via_tool("-foo bar") is True
    assert seen[0][:3] == ["/usr/bin/ydotool", "type", "-d"]
    assert seen[0][-2:] == ["--", "-foo bar"]
    t._type_via_tool("plain")
    assert seen[1][-1] == "plain"
    assert "--" not in seen[1]
