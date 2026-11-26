"""One operator-funded pass per private state file. No wallet material enters MCP."""
import json
import os
import re
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

from eth_account import Account
from x402 import x402Client
from x402.http.utils import decode_payment_required_header, encode_payment_signature_header
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.mechanisms.evm.signers import EthAccountSigner

from handoff import ORIGIN, FEED, public_tags
NETWORK = "eip155:8453"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
RECIPIENT = "0xb779af773acfe6306070bf0b2fabbe2ab0b100f6"
DAY_PASS_USDC = Decimal("5")
STATUS_PATH = re.compile(r"/api/v1/x402/payments/[a-zA-Z0-9_-]{1,128}")


def private_file(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("A private regular file is required.")
    return path.read_text()


def state_path():
    value = os.getenv("NEURALIQUID_PASS_FILE")
    if not value:
        raise ValueError("Configure a persistent NEURALIQUID_PASS_FILE for this agent.")
    path = Path(value)
    if not path.is_absolute() or not path.parent.is_dir() or path.parent.stat().st_mode & 0o077:
        raise ValueError("Use an absolute pass path in a private directory (0700).")
    return path


def load_state(path):
    if not path.exists() and not path.is_symlink():
        return {}
    saved = json.loads(private_file(path))
    if not isinstance(saved, dict) or not (saved.get("token") or saved.get("authorization")):
        raise ValueError("Unrecognized pass state. Keep the file for recovery.")
    return saved


def save_state(path, data, *, first=False):
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        if first:
            # Only the winner of this race may send its signature to the merchant.
            os.link(name, path)
        else:
            os.replace(name, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def budget_limit():
    try:
        budget = Decimal(os.environ.get("NEURALIQUID_MAX_USDC", "0"))
    except InvalidOperation:
        raise ValueError("Configure a finite positive USDC budget.") from None
    if not budget.is_finite() or budget <= 0:
        raise ValueError("Configure a finite positive USDC budget.")
    return min(budget, DAY_PASS_USDC)


def buyer_account():
    key = os.getenv("NEURALIQUID_BUYER_KEY_FILE")
    if not key:
        raise ValueError("Configure the agent's dedicated buyer key via its local secret store.")
    account = Account.from_key(private_file(Path(key)).strip())
    if account.address.lower() == RECIPIENT:
        raise ValueError("Use a separate buyer wallet.")
    return account


def purchase_readiness(wallet_mode):
    """Inspect local configuration without creating a state file or contacting any service."""
    token = os.getenv("NEURALIQUID_ACCESS_TOKEN")
    if token:
        if re.fullmatch(r"[a-f0-9]{64}", token):
            return {"status": "existing_pass_configured", "next_tool": "read_agent_events"}
        return {"status": "invalid_pass_config", "action": "Check the locally configured NEURALIQUID_ACCESS_TOKEN."}

    blockers = []
    if os.getenv("NEURALIQUID_PASS_FILE"):
        try:
            path = state_path()
            saved = load_state(path)
            if saved:
                token = saved.get("token")
                if token:
                    if not re.fullmatch(r"[a-f0-9]{64}", token) or not STATUS_PATH.fullmatch(saved.get("status_path", "")):
                        raise ValueError("Invalid pass state.")
                    return {"status": "saved_pass_configured", "next_tool": "read_agent_events",
                            "action": "Check the saved pass. If pending, resume the same purchase."}
                if not isinstance(saved.get("authorization"), str) or not saved["authorization"]:
                    raise ValueError("Invalid authorization state.")
                return {"status": "saved_authorization", "next_tool": "buy_or_resume_pass",
                        "action": "Only resume the existing authorization with the same pass file."}
            if not os.access(path.parent, os.W_OK | os.X_OK):
                raise ValueError("State directory is not writable.")
        except (ValueError, OSError, TypeError):
            return {"status": "pass_state_unusable",
                    "action": "Check the private pass file and directory permissions locally. Preserve existing state for recovery."}
    elif wallet_mode == "local":
        blockers.append("pass_file_missing")

    if wallet_mode == "external_x402":
        return {"status": "external_client_required", "next_tool": "inspect_offer",
                "action": "Verify Base USDC funds and the 5 USDC spending limit in your x402 client. Request operator approval before signing there."}
    if wallet_mode != "local":
        raise ValueError("Use local or external_x402 wallet mode.")
    if os.getenv("NEURALIQUID_ENABLE_PURCHASE") != "1":
        blockers.append("operator_opt_in_missing")
    try:
        if budget_limit() < DAY_PASS_USDC:
            blockers.append("budget_below_day_price")
    except ValueError:
        blockers.append("budget_missing_or_invalid")
    if not os.getenv("NEURALIQUID_BUYER_KEY_FILE"):
        blockers.append("local_signer_missing")
    else:
        try:
            buyer_account()
        except Exception:
            # Third-party key parsing errors may embed secret material. Expose only the category.
            blockers.append("local_signer_unusable")
    if blockers:
        actions = {
            "pass_file_missing": "Set NEURALIQUID_PASS_FILE to a persistent absolute path in a private directory.",
            "operator_opt_in_missing": "The operator must enable NEURALIQUID_ENABLE_PURCHASE locally to allow purchasing.",
            "budget_below_day_price": "The configured NEURALIQUID_MAX_USDC is below the 5 USDC day-pass price.",
            "budget_missing_or_invalid": "Have the operator set a finite positive NEURALIQUID_MAX_USDC within their policy.",
            "local_signer_missing": "Supply a dedicated buyer key via the host secret store or select external_x402 mode.",
            "local_signer_unusable": "Check the dedicated buyer account, key format and private permissions of NEURALIQUID_BUYER_KEY_FILE locally.",
        }
        return {"status": "local_setup_required", "blockers": blockers,
                "actions": [actions[blocker] for blocker in blockers]}
    return {"status": "local_setup_ready", "next_tool": "inspect_offer",
            "action": "Inspect the live offer, verify Base USDC funds and obtain operator approval before buying."}


async def prepare(http, tags):
    if os.getenv("NEURALIQUID_ENABLE_PURCHASE") != "1":
        raise ValueError("Purchases require an explicit operator budget and opt-in.")
    budget = budget_limit()
    response = await http.get(FEED, params=tags)
    if response.status_code != 402:
        raise ValueError("Payment offer unavailable.")
    if tags.get("ref") and (response.headers.get("X-FutureCast-Referral") != tags["ref"]
                            or response.headers.get("X-FutureCast-Source") != tags["utm_source"]):
        raise ValueError("The merchant did not recognize this referral and source.")
    offer = decode_payment_required_header(response.headers["PAYMENT-REQUIRED"])
    if len(offer.accepts) != 1 or not offer.resource or offer.resource.url != ORIGIN + FEED:
        raise ValueError("Unexpected offered resource.")
    terms = offer.accepts[0]
    extra = terms.extra or {}
    if (terms.network != NETWORK or terms.scheme != "exact" or terms.asset.lower() != USDC
            or terms.pay_to.lower() != RECIPIENT or not re.fullmatch(r"[1-9][0-9]{0,15}", terms.amount)
            or int(terms.amount) > budget * 1_000_000
            or not 0 < terms.max_timeout_seconds <= 600
            or extra.get("assetTransferMethod") != "eip3009"
            or extra.get("name") != "USD Coin" or extra.get("version") != "2"):
        raise ValueError("Merchant, amount, chain or USDC authorization is outside the configured policy.")
    account = buyer_account()
    client = x402Client()
    client.set_spend_controls({"max_amount_per_payment": str(budget)})
    client.register(NETWORK, ExactEvmClientScheme(EthAccountSigner(account)))
    return encode_payment_signature_header(await client.create_payment_payload(offer))


async def buy_or_resume(http, path, handoff_url=None):
    saved = load_state(path)
    if not saved:
        if os.environ.get("NEURALIQUID_ACCESS_TOKEN"):
            return {"status": "existing_pass_configured", "next_tool": "read_agent_events"}
        tags = public_tags(handoff_url)
        authorization = await prepare(http, tags)
        try:
            save_state(path, {"authorization": authorization, "tags": tags}, first=True)
        except FileExistsError:
            pass
        saved = load_state(path)
    if "token" in saved:
        status = saved.get("status_path", "")
        if not STATUS_PATH.fullmatch(status):
            raise ValueError("Invalid local payment status path.")
        response = await http.get(status, headers={"Authorization": "Bearer " + saved["token"]})
    else:
        response = await http.get(FEED, params=saved.get("tags", {}), headers={"PAYMENT-SIGNATURE": saved["authorization"]})
    data = response.json()
    token = data.get("access_token")
    status = data.get("status_url", "")
    if token and re.fullmatch(r"[0-9a-f]{64}", token) and STATUS_PATH.fullmatch(status):
        save_state(path, {"token": token, "status_path": status})
    result = data.get("status")
    if result in {"pending", "confirmed", "source_unavailable"}:
        return {"status": result, "expires_in": data.get("expires_in"),
                "next_tool": "read_agent_events" if result == "confirmed" else "buy_or_resume_pass"}
    return {"status": "expired" if response.status_code == 410 else "unavailable",
            "http_status": response.status_code, "authorization_retained": True}
