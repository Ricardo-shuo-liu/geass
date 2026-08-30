from __future__ import annotations

from geass.dispatch import commands_main, reset_main


def test_commands_lists_all(capsys):
    commands_main()
    out = capsys.readouterr().out

    assert "geass serve" in out
    assert "geass cli" in out
    assert "geass reset" in out
    assert "geass commands" in out


def test_reset_requires_double_confirmation(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    geass_dir = home / ".geass"
    for name in (".memory", ".rag", ".pot"):
        (geass_dir / name).mkdir(parents=True)
    (geass_dir / "env.toml").write_text("x=1", encoding="utf-8")
    monkeypatch.setenv("GEASS_HOME", str(home))

    answers = iter(["reset", "reset"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    reset_main()

    assert not (geass_dir / ".memory").exists()
    assert not (geass_dir / ".rag").exists()
    assert not (geass_dir / ".pot").exists()
    assert not (geass_dir / "env.toml").exists()
    assert "已重置" in capsys.readouterr().out


def test_reset_cancelled_without_confirmation(tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    geass_dir = home / ".geass"
    (geass_dir / ".memory").mkdir(parents=True)
    monkeypatch.setenv("GEASS_HOME", str(home))
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")

    reset_main()

    assert (geass_dir / ".memory").exists()
    assert "已取消" in capsys.readouterr().out
