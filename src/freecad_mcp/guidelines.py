from typing import Tuple
import logging

logger = logging.getLogger("FreeCADMCPguidelines")


def check_prompt_conflict(prompt: str) -> Tuple[bool, str]:
    """Return (conflict, message). Detects dangerous tokens and agreement-bias requests.

    This is intentionally conservative: any match returns a conflict message that can be
    surfaced to the user and logged.
    """
    if not prompt:
        return False, ""

    p = prompt.lower()

    dangerous = ["os.system", "subprocess", "rm -rf", "shutdown", "reboot", "eval(", "exec("]
    for tok in dangerous:
        if tok in p:
            msg = "Request contains potentially dangerous operations ({}). Refusing or requesting safer alternative.".format(tok)
            logger.warning(msg + " Prompt excerpt: %s", prompt[:200])
            return True, msg

    # Detect explicit 'do exactly' or 'ignore safety' style instructions (agreement trap)
    agreement_traps = ["do exactly as i say", "ignore safety", "don't question", "no questions asked"]
    for tok in agreement_traps:
        if tok in p:
            msg = "Request asks to bypass safeguards or unquestioningly follow instructions; will not comply as-is."
            logger.warning(msg + " Prompt excerpt: %s", prompt[:200])
            return True, msg

    return False, ""
