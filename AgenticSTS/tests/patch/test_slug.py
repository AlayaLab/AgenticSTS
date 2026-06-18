from src.patch.slug import slug


def test_slug_lowercase():
    assert slug("Strike") == "strike"


def test_slug_strips_punctuation():
    assert slug("Neow's Talisman") == "neows talisman"


def test_slug_collapses_whitespace():
    assert slug("  Blade  of   Ink  ") == "blade of ink"


def test_slug_handles_plus_upgrade_marker():
    assert slug("Strike+") == "strike"


def test_slug_idempotent():
    assert slug(slug("Neow's Talisman")) == slug("Neow's Talisman")


def test_slug_handles_empty():
    assert slug("") == ""
    assert slug("   ") == ""
