import subprocess
import os
from pathlib import Path
import re
from voxd.utils.libw import verbo, verr
from voxd.paths import find_whisper_cli, find_base_model
from voxd.utils.languages import normalize_lang_code, is_valid_lang


def model_is_english_only(model_path: str | None) -> bool:
    """English-only Whisper models (*.en) can neither detect other languages
    nor translate – they only transcribe English."""
    try:
        return str(model_path or "").lower().endswith(".en.bin")
    except Exception:
        return False


def translation_target(cfg) -> str:
    """Normalized translate target code, or "" when translation is off."""
    try:
        from voxd.utils.languages import normalize_lang_code, is_valid_lang
        target = normalize_lang_code((cfg.data.get("translate_target", "") if cfg else "") or "")
        return target if target and is_valid_lang(target) else ""
    except Exception:
        return ""


def translation_source(cfg) -> str:
    """Source language to transcribe with: auto-detect while translating
    (so any spoken language lands in the target), else the configured one."""
    try:
        if translation_target(cfg):
            return "auto"
        lang = (cfg.data.get("language", "en") if cfg else "en") or "en"
        from voxd.utils.languages import normalize_lang_code
        return normalize_lang_code(lang)
    except Exception:
        return "en"


def use_native_translate(cfg) -> bool:
    """True when whisper itself can do the job: target is English and the
    model is multilingual (whisper --translate only outputs English)."""
    try:
        if translation_target(cfg) != "en":
            return False
        return not model_is_english_only(cfg.whisper_model_path if cfg else "")
    except Exception:
        return False


class WhisperTranscriber:
    def __init__(self, model_path, binary_path, delete_input=True, language: str | None = None, translate: bool = False):
        # --- Model path: try config, else auto-discover ---
        if model_path and Path(model_path).is_file():
            self.model_path = model_path
        else:
            # Try to use the default model in cache
            self.model_path = find_base_model()
            verbo(f"[transcriber] Falling back to cached model: {self.model_path}")

        # --- Binary path: try config, else auto-discover ---
        if binary_path and Path(binary_path).is_file() and os.access(binary_path, os.X_OK):
            self.binary_path = binary_path
        else:
            self.binary_path = find_whisper_cli()
            verbo(f"[transcriber] Falling back to auto-detected whisper-cli: {self.binary_path}")

        self.delete_input = delete_input
        # Native speech-to-English translation needs a multilingual model;
        # English-only (*.en) models silently degrade to plain transcription.
        self.translate = bool(translate) and not model_is_english_only(model_path)
        if translate and not self.translate:
            verr("[transcriber] --translate needs a multilingual model; "
                 "English-only (*.en) model configured – transcribing without translation.")
        from voxd.paths import OUTPUT_DIR
        self.output_dir = OUTPUT_DIR

        # Language (default en)
        lang = normalize_lang_code(language or "en")
        if not is_valid_lang(lang):
            verr(f"[transcriber] Invalid language '{language}', using 'en'")
            lang = "en"
        self.language = lang

        # Warn if likely mismatch with an English-only model
        try:
            mp = str(self.model_path).lower()
            if self.language != "en" and mp.endswith(".en.bin"):
                verr("[transcriber] Non-English language selected but an English-only (*.en) model is configured.")
        except Exception:
            pass

    def transcribe(self, audio_path):
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"[transcriber] Audio file not found: {audio_file}")

        verbo(f"[transcriber] Using binary: {self.binary_path}")
        verbo(f"[transcriber] Using model: {self.model_path}")
        verbo("[transcriber] Starting transcription...")

        # Output prefix (no extension!)
        output_prefix = self.output_dir / audio_file.stem
        output_txt = output_prefix.with_suffix(".txt")

        # In translate mode whisper detects the source language itself.
        lang_arg = "auto" if self.translate else self.language
        cmd = [
            self.binary_path,
            "-m", self.model_path,
            "-f", str(audio_file),
            "-l", lang_arg,
            "-of", str(self.output_dir / audio_file.stem),
            "-otxt"  # <-- THIS is necessary to actually generate the .txt file
        ]
        if self.translate:
            cmd.append("--translate")

        verbo(f"[transcriber] Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            verr("[transcriber] whisper.cpp failed:")
            verr(f"stderr: {result.stderr}")
            verr(f"stdout: {result.stdout}")
            return None, None

        if not output_txt.exists():
            verr(f"[transcriber] Transcription failed: Expected output not found at {output_txt}")
            return None, None

        verbo(f"[transcriber] Transcription complete: {output_txt}")

        # Optionally delete the input audio
        if self.delete_input:
            try:
                audio_file.unlink()
                verbo(f"[transcriber] Deleted input file: {audio_file}")
            except Exception as e:
                verr(f"[transcriber] Could not delete input file: {e}")

        return self._parse_transcript(output_txt)

    def _parse_transcript(self, path: Path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            print(f"[transcriber] Failed to read transcript file: {e}")
            return None, None

        orig_tscript = "".join(lines)

        # Strip timestamps like [00:00.000] or (00:00)
        tscript = re.sub(r"\[\d{2}:\d{2}[\.:]\d{3}\]|\(\d{2}:\d{2}\)", "", orig_tscript)
        tscript = re.sub(r"\s+", " ", tscript).strip()

        return tscript, orig_tscript
