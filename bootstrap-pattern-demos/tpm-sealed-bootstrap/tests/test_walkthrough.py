"""Tests for walkthrough.py — verify the deck data manifest is well-formed."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import walkthrough as wt  # noqa: E402


class TestWalkthroughStructure:
    """Verify the SLIDES manifest is well-formed for build_deck.py."""

    def test_has_slides(self):
        """SLIDES list exists and is non-empty."""
        assert hasattr(wt, "SLIDES")
        assert len(wt.SLIDES) > 0

    def test_has_demo_prompt(self):
        """DEMO_PROMPT is defined."""
        assert hasattr(wt, "DEMO_PROMPT")
        assert wt.DEMO_PROMPT.endswith("$ ")

    def test_each_slide_has_beats(self):
        """Every slide has a 'beats' key with at least one beat."""
        for i, slide in enumerate(wt.SLIDES):
            assert "beats" in slide, f"Slide {i} missing 'beats'"
            assert len(slide["beats"]) > 0, f"Slide {i} has empty beats"

    def test_cover_slide(self):
        """First slide is the cover with title/tagline/kicker."""
        cover = wt.SLIDES[0]
        assert cover["title"] is None  # cover slides have no section title
        beats = cover["beats"]
        assert "title" in beats[0]
        assert "tagline" in beats[0]
        assert "kicker" in beats[0]

    def test_all_cmd_beats_have_out(self):
        """Every cmd beat has a corresponding out (even if empty string)."""
        for slide in wt.SLIDES:
            for beat in slide["beats"]:
                if "cmd" in beat:
                    assert "out" in beat, f"cmd beat missing 'out': {beat['cmd'][:40]}"

    def test_verdict_beats_have_ok(self):
        """Every verdict beat has an 'ok' boolean."""
        for slide in wt.SLIDES:
            for beat in slide["beats"]:
                if "verdict" in beat:
                    assert "ok" in beat, f"verdict beat missing 'ok': {beat['verdict'][:40]}"
                    assert isinstance(beat["ok"], bool)

    def test_no_real_secrets(self):
        """No real secrets in the walkthrough — only S3cr3t-Pg-Pass."""
        import json
        content = Path(HERE / "walkthrough.py").read_text()
        # The only "secret" should be the obvious fake
        assert "S3cr3t-Pg-Pass" in content
        # No common real-secret patterns
        for pattern in ["AKIA", "ghp_", "glpat-", "sk-", "-----BEGIN"]:
            assert pattern not in content, f"Possible real secret pattern found: {pattern}"
