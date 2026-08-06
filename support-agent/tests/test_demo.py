from triage.demo import demo


def test_demo_prints_full_trace(capsys):
    result = demo()

    out = capsys.readouterr().out
    for section in (
        "=== SPAN TREE",
        "=== CORRELATED LOGS ===",
        "=== GUARDRAIL DECISIONS ===",
        "=== RESULT ===",
        "=== METRICS SUMMARY ===",
    ):
        assert section in out, f"missing section {section!r}"

    # The scripted ticket is a refund request: escalated, with a real KB
    # citation and a drafted (never executed) high-risk action.
    assert "escalation: ESCALATED" in out
    assert "issue_refund  risk=high  executed=False" in out
    assert "help.ubuntu.com" in out
    assert result["result"].escalation is not None
