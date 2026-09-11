from types import SimpleNamespace


def _cfg(**overrides):
    data = {"language": "en", "translate_target": "", "aipp_provider": "ollama",
            "aipp_selected_models": {"ollama": "llama3.2:latest"}}
    data.update(overrides)
    return SimpleNamespace(data=data, whisper_model_path="/models/ggml-small.bin",
                           whisper_binary="/bin/whisper-cli")


def test_resolve_translate_absent():
    from voxd.__main__ import _resolve_translate_target
    assert _resolve_translate_target(None, _cfg()) is None


def test_resolve_translate_explicit():
    from voxd.__main__ import _resolve_translate_target
    assert _resolve_translate_target("ru", _cfg()) == "ru"
    assert _resolve_translate_target("EN", _cfg()) == "en"


def test_resolve_translate_rejects_bad():
    from voxd.__main__ import _resolve_translate_target
    for bad in ("auto", "xx", "", "  "):
        try:
            _resolve_translate_target(bad, _cfg())
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should raise ValueError")


def test_resolve_translate_bare_prefers_configured_target():
    from voxd.__main__ import _resolve_translate_target, _TRANSLATE_USE_CONFIG
    assert _resolve_translate_target(_TRANSLATE_USE_CONFIG, _cfg(translate_target="de")) == "de"
    assert _resolve_translate_target(_TRANSLATE_USE_CONFIG, _cfg()) == "en"  # cfg language
    try:
        _resolve_translate_target(_TRANSLATE_USE_CONFIG, _cfg(language="auto"))
    except ValueError:
        pass
    else:
        raise AssertionError("bare flag with auto language should raise")


def _make_fake_bin(tmp_path, name="whisper-cli"):
    import os
    import stat
    binary = tmp_path / name
    binary.write_bytes(b"#!/bin/sh\n")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    assert os.access(str(binary), os.X_OK)
    return str(binary)


def test_transcriber_native_translate_cmd(tmp_path, monkeypatch):
    from pathlib import Path as _P
    from voxd.core import transcriber as tr

    seen = {}

    class FakeResult:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return FakeResult()

    monkeypatch.setattr(tr.subprocess, "run", fake_run)

    model = tmp_path / "ggml-small.bin"
    model.write_bytes(b"fake")
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF")
    from voxd.paths import OUTPUT_DIR
    out_txt = _P(OUTPUT_DIR) / "clip.txt"
    out_txt.write_text("[00:00.000] Hello world\n")
    try:
        t = tr.WhisperTranscriber(str(model), _make_fake_bin(tmp_path),
                                   delete_input=False, language="en", translate=True)
        assert t.translate is True
        tscript, _ = t.transcribe(str(audio))
        assert "--translate" in seen["cmd"]
        assert seen["cmd"][seen["cmd"].index("-l") + 1] == "auto"
        assert tscript == "Hello world"
    finally:
        try:
            out_txt.unlink()
        except OSError:
            pass


def test_transcriber_en_model_disables_translate(tmp_path, monkeypatch):
    from voxd.core import transcriber as tr

    assert tr.model_is_english_only("/m/ggml-base.en.bin") is True
    assert tr.model_is_english_only("/m/ggml-small.bin") is False

    model = tmp_path / "ggml-base.en.bin"
    model.write_bytes(b"fake")
    t = tr.WhisperTranscriber(str(model), _make_fake_bin(tmp_path),
                               delete_input=False, language="en", translate=True)
    assert t.translate is False


def test_translation_helpers():
    from voxd.core.transcriber import translation_target, translation_source, use_native_translate
    assert translation_target(_cfg()) == ""
    assert translation_target(_cfg(translate_target="ru")) == "ru"
    assert translation_source(_cfg()) == "en"
    assert translation_source(_cfg(translate_target="ru")) == "auto"
    assert use_native_translate(_cfg(translate_target="en")) is True
    assert use_native_translate(_cfg(translate_target="ru")) is False
    assert use_native_translate(_cfg()) is False


def test_translate_text_success_and_fallback(monkeypatch):
    from voxd.core import aipp
    prompts = []
    monkeypatch.setattr(aipp, "_dispatch_provider",
                        lambda prompt, provider, model: (prompts.append(prompt), "  Я смотрю телевизор  ")[1])
    out = aipp.translate_text("Im watching tv", "ru", _cfg())
    assert out == "Я смотрю телевизор"
    assert "Russian" in prompts[0]

    def boom(prompt, provider, model):
        raise ConnectionError("down")
    monkeypatch.setattr(aipp, "_dispatch_provider", boom)
    assert aipp.translate_text("Im watching tv", "ru", _cfg()) == "Im watching tv"


def test_get_translated_text_routing(monkeypatch):
    from voxd.core import aipp
    assert aipp.get_translated_text("hi", _cfg()) == "hi"  # off
    assert aipp.get_translated_text("hi", _cfg(translate_target="en")) == "hi"  # native
    monkeypatch.setattr(aipp, "translate_text", lambda text, target, cfg: f"{text}=>{target}")
    assert aipp.get_translated_text("hi", _cfg(translate_target="ru")) == "hi=>ru"
    assert aipp.get_translated_text("", _cfg(translate_target="ru")) == ""


def test_pipeline_terminal_report(monkeypatch):
    import io
    from contextlib import redirect_stdout
    from datetime import datetime
    from voxd.core import voxd_core as vc, typer as ty, clipboard as cb

    class FakeTranscriber:
        def __init__(self, **kw):
            self.language = "auto"
        def transcribe(self, path):
            return "Im watching tv", "orig"

    seen = {}
    monkeypatch.setattr(vc, "WhisperTranscriber",
                        lambda **kw: FakeTranscriber(**kw))
    monkeypatch.setattr(vc, "get_translated_text",
                        lambda text, cfg: "Я смотрю телевизор")

    class FakeTyper:
        def __init__(self, **kw):
            pass
        def _typing_mode(self):
            return "auto"
        def type(self, text):
            seen["typed"] = text

    class FakeClip:
        def copy(self, text):
            seen["copied"] = text

    monkeypatch.setattr(ty, "SimulatedTyper", FakeTyper)
    monkeypatch.setattr(cb, "ClipboardManager", FakeClip)

    class FakeLogger:
        def __init__(self):
            self.entries = []
        def log_entry(self, e):
            self.entries.append(e)

    cfg = _cfg(translate_target="ru")
    cfg.typing_delay = 1
    cfg.typing_start_delay = 0
    cfg.typing = True
    cfg.aipp_enabled = False
    cfg.perf_collect = False

    buf = io.StringIO()
    with redirect_stdout(buf):
        out = vc._process_audio_file(cfg, FakeLogger(), "/tmp/x.wav",
                                     datetime.now(), datetime.now(),
                                     on_status=lambda s: None)
    report = buf.getvalue()
    assert out == "Я смотрю телевизор"
    assert seen["typed"] == "Я смотрю телевизор"
    assert "[voxd] Transcript (" in report and "Im watching tv" in report
    assert "[voxd] Translated (ru): Я смотрю телевизор" in report
    assert "[voxd] Typing (mode=auto" in report
    assert "[voxd] Done." in report


def test_config_env_override_session_only(tmp_path, monkeypatch):
    from voxd.core import config as cfgmod
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "language: en\ntranslate_target: ''\n"
        "aipp_provider: ollama\naipp_active_prompt: default\n"
        "aipp_prompts: {default: '', prompt1: '', prompt2: '', prompt3: ''}\n"
        "aipp_models: {ollama: []}\naipp_selected_models: {ollama: ''}\n"
        "llamacpp_server_timeout: 30\n"
    )
    monkeypatch.setattr(cfgmod, "CONFIG_PATH", cfg_file)
    monkeypatch.setenv("VOXD_TRANSLATE", "ru")
    monkeypatch.setenv("VOXD_LANG", "de")
    cfg = cfgmod.AppConfig()
    assert cfg.data["translate_target"] == "ru"
    assert cfg.data["language"] == "de"
    assert cfg.translate_target == "ru"
    # Session-only: save() must not persist env values to disk.
    cfg.save()
    import yaml
    on_disk = yaml.safe_load(cfg_file.read_text())
    assert on_disk.get("translate_target") in ("", None)
    assert on_disk.get("language") == "en"
    assert cfg.data["translate_target"] == "ru"  # still live in memory
