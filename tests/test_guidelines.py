"""Unit tests for the prompt-conflict guard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freecad_mcp.guidelines import check_prompt_conflict  # noqa: E402


def test_empty_prompt_safe():
    conflict, msg = check_prompt_conflict("")
    assert conflict is False


def test_normal_text_safe():
    conflict, msg = check_prompt_conflict("Create a cylinder with height 30")
    assert conflict is False


def test_os_system_blocked():
    conflict, msg = check_prompt_conflict("import os; os.system('rm -rf /')")
    assert conflict is True
    assert "os.system" in msg


def test_subprocess_blocked():
    conflict, msg = check_prompt_conflict("subprocess.run(['ls'])")
    assert conflict is True
    assert "subprocess" in msg


def test_rm_rf_blocked():
    conflict, msg = check_prompt_conflict("please run rm -rf /tmp")
    assert conflict is True
    assert "rm -rf" in msg


def test_shutdown_blocked():
    conflict, msg = check_prompt_conflict("shutdown the host")
    assert conflict is True
    assert "shutdown" in msg


def test_reboot_blocked():
    conflict, msg = check_prompt_conflict("reboot now")
    assert conflict is True
    assert "reboot" in msg


def test_eval_blocked():
    conflict, msg = check_prompt_conflict("eval('1+1')")
    assert conflict is True
    assert "eval(" in msg


def test_exec_blocked():
    conflict, msg = check_prompt_conflict("exec(code)")
    assert conflict is True
    assert "exec(" in msg


def test_agreement_trap_blocked():
    for trap in ("do exactly as i say", "ignore safety", "don't question", "no questions asked"):
        conflict, msg = check_prompt_conflict(trap)
        assert conflict is True, f"expected block for {trap!r}"


def test_case_insensitive():
    """The check uses lowercase comparison, so 'OS.SYSTEM' should still match."""
    conflict, msg = check_prompt_conflict("OS.SYSTEM('reboot')")
    assert conflict is True


def test_partial_word_not_blocked():
    """Sanity: a benign word containing 'eval' as a substring of a larger
    word currently matches (substring search). This documents the known
    limitation — see docs/IMPROVEMENT_PLAN.md C3 for the regex fix.
    """
    # 'evaluation' contains 'eval' but not 'eval('; should be safe today.
    conflict, _ = check_prompt_conflict("evaluation criteria")
    assert conflict is False


if __name__ == "__main__":
    test_empty_prompt_safe()
    test_normal_text_safe()
    test_os_system_blocked()
    test_subprocess_blocked()
    test_rm_rf_blocked()
    test_shutdown_blocked()
    test_reboot_blocked()
    test_eval_blocked()
    test_exec_blocked()
    test_agreement_trap_blocked()
    test_case_insensitive()
    test_partial_word_not_blocked()
    print("All guideline tests passed")