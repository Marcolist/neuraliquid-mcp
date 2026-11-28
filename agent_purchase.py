"""One operator-funded purchase per private state file. No wallet material enters MCP."""
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

from handoff import ORIGIN, FEED, SNAPSHOT, public_tags
NETWORK = "eip155:8453"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
RECIPIENT = "0xb779af773acfe6306070bf0b2fabbe2ab0b100f6"
DAY_PASS_USDC = Decimal("5")
SNAPSHOT_USDC = Decimal("0.05")
STATUS_PATH = re.compile(r"/api/v1/x402/payments/[a-zA-Z0-9_-]{1,128}")


def private_file(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("A private regular file is required.")
    return path.read_text()


def state_path(setting="NEURALIQUID_PASS_FILE"):
    value = os.getenv(setting)
    if not value:
        raise ValueError(f"Configure a persistent {setting} for this agent.")
    path = Path(value)
    if not path.is_absolute() or not path.parent.is_dir() or path.parent.stat().st_mode & 0o077:
        raise ValueError("Use an absolute purchase-state path in a private directory (0700).")
    return path


def load_state(path, *, resource=FEED):
    if not path.exists() and not path.is_symlink():
        return {}
    saved = json.loads(private_file(path))
    if not isinstance(saved, dict) or not (saved.get("token") or saved.get("authorization")):
        raise ValueError("Unrecognized pass state. Keep the file for recovery.")
    if saved.get("resource", FEED) != resource:
        raise ValueError("The state file belongs to another product.")
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


def purchase_readiness(wallet_mode, product="day_pass"):
    """Inspect local configuration without creating a state file or contacting any service."""
    if product not in ("day_pass", "btc_eth_snapshot"):
        raise ValueError("Use day_pass or btc_eth_snapshot.")
    snapshot = product == "btc_eth_snapshot"
    state_setting = "NEURALIQUID_SNAPSHOT_FILE" if snapshot else "NEURALIQUID_PASS_FILE"
    state_name = "snapshot" if snapshot else "pass"
    price = SNAPSHOT_USDC if snapshot else DAY_PASS_USDC
    inspect_tool = "inspect_btc_eth_snapshot" if snapshot else "inspect_offer"
    resume_tool = "buy_or_resume_btc_eth_snapshot" if snapshot else "buy_or_resume_pass"
    token = None if snapshot else os.getenv("NEURALIQUID_ACCESS_TOKEN")
    if token:
        if re.fullmatch(r"[a-f0-9]{64}", token):
            return {"status": "existing_pass_configured", "next_tool": "read_agent_events"}
        return {"status": "invalid_pass_config", "action": "Check the locally configured NEURALIQUID_ACCESS_TOKEN."}

    blockers = []
    if os.getenv(state_setting):
        try:
            path = state_path(state_setting)
            if snapshot and os.getenv("NEURALIQUID_PASS_FILE") and path.resolve() == state_path().resolve():
                return {"status": "snapshot_state_unusable", "action": "Use separate private files for the snapshot and pass. Preserve existing state for recovery."}
            saved = load_state(path, resource=SNAPSHOT if snapshot else FEED)
            if saved:
                token = saved.get("token")
                if token:
                    if not re.fullmatch(r"[a-f0-9]{64}", token) or not STATUS_PATH.fullmatch(saved.get("status_path", "")):
                        raise ValueError("Invalid pass state.")
                    if snapshot:
                        return {"status": "saved_snapshot_configured", "next_tool": resume_tool,
                                "action": "Use the same snapshot file to retrieve the original result or check finality."}
                    return {"status": "saved_pass_configured", "next_tool": "read_agent_events",
                            "action": "Check the saved pass. If pending, resume the same purchase."}
                if not isinstance(saved.get("authorization"), str) or not saved["authorization"]:
                    raise ValueError("Invalid authorization state.")
                return {"status": "saved_authorization", "next_tool": resume_tool,
                        "action": f"Only resume the existing authorization with the same {state_name} file."}
            if not os.access(path.parent, os.W_OK | os.X_OK):
                raise ValueError("State directory is not writable.")
        except (ValueError, OSError, TypeError):
            return {"status": f"{state_name}_state_unusable",
                    "action": f"Check the private {state_name} file and directory permissions locally. Preserve existing state for recovery."}
    elif wallet_mode == "local":
        blockers.append(f"{state_name}_file_missing")

    if wallet_mode == "external_x402":
        return {"status": "external_client_required", "next_tool": inspect_tool,
                "action": f"Verify Base USDC funds and the {price} USDC spending limit in your x402 client. Request operator approval before signing there."}
    if wallet_mode != "local":
        raise ValueError("Use local or external_x402 wallet mode.")
    if os.getenv("NEURALIQUID_ENABLE_PURCHASE") != "1":
        blockers.append("operator_opt_in_missing")
    try:
        if budget_limit() < price:
            blockers.append("budget_below_snapshot_price" if snapshot else "budget_below_day_price")
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
            "snapshot_file_missing": "Set NEURALIQUID_SNAPSHOT_FILE to a separate persistent absolute path in a private directory.",
            "operator_opt_in_missing": "The operator must enable NEURALIQUID_ENABLE_PURCHASE locally to allow purchasing.",
            "budget_below_day_price": "The configured NEURALIQUID_MAX_USDC is below the 5 USDC day-pass price.",
            "budget_below_snapshot_price": "The configured NEURALIQUID_MAX_USDC is below the 0.05 USDC snapshot price.",
            "budget_missing_or_invalid": "Have the operator set a finite positive NEURALIQUID_MAX_USDC within their policy.",
            "local_signer_missing": "Supply a dedicated buyer key via the host secret store or select external_x402 mode.",
            "local_signer_unusable": "Check the dedicated buyer account, key format and private permissions of NEURALIQUID_BUYER_KEY_FILE locally.",
        }
        return {"status": "local_setup_required", "blockers": blockers,
                "actions": [actions[blocker] for blocker in blockers]}
    return {"status": "local_setup_ready", "next_tool": inspect_tool,
            "action": "Inspect the live offer, verify Base USDC funds and obtain operator approval before buying."}


async def prepare(http, tags, *, resource=FEED):
    if os.getenv("NEURALIQUID_ENABLE_PURCHASE") != "1":
        raise ValueError("Purchases require an explicit operator budget and opt-in.")
    budget = budget_limit()
    if resource == SNAPSHOT and budget < SNAPSHOT_USDC:
        raise ValueError("The configured budget is below the snapshot price.")
    response = await http.get(resource, params=tags)
    if resource == SNAPSHOT and response.status_code in (409, 503):
        return None
    if response.status_code != 402:
        raise ValueError("Payment offer unavailable.")
    if tags.get("ref") and (response.headers.get("X-FutureCast-Referral") != tags["ref"]
                            or response.headers.get("X-FutureCast-Source") != tags["utm_source"]):
        raise ValueError("The merchant did not recognize this referral and source.")
    offer = decode_payment_required_header(response.headers["PAYMENT-REQUIRED"])
    if len(offer.accepts) != 1 or not offer.resource or offer.resource.url != ORIGIN + resource:
        raise ValueError("Unexpected offered resource.")
    terms = offer.accepts[0]
    extra = terms.extra or {}
    if (terms.network != NETWORK or terms.scheme != "exact" or terms.asset.lower() != USDC
            or terms.pay_to.lower() != RECIPIENT or not re.fullmatch(r"[1-9][0-9]{0,15}", terms.amount)
            or (resource == SNAPSHOT and terms.amount != "50000")
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


async def buy_or_resume(http, path, handoff_url=None, *, resource=FEED):
    snapshot = resource == SNAPSHOT
    saved = load_state(path, resource=resource)
    if not saved:
        if not snapshot and os.environ.get("NEURALIQUID_ACCESS_TOKEN"):
            return {"status": "existing_pass_configured", "next_tool": "read_agent_events"}
        tags = public_tags(handoff_url, resource=resource)
        authorization = await prepare(http, tags, resource=resource)
        if authorization is None:
            return {"status": "snapshot_unavailable", "signed": False}
        try:
            save_state(path, {"authorization": authorization, "tags": tags, "resource": resource}, first=True)
        except FileExistsError:
            pass
        saved = load_state(path, resource=resource)
    if "token" in saved:
        status = saved.get("status_path", "")
        if not STATUS_PATH.fullmatch(status):
            raise ValueError("Invalid local payment status path.")
        response = await http.get(status, headers={"Authorization": "Bearer " + saved["token"]})
    else:
        response = await http.get(resource, params=saved.get("tags", {}), headers={"PAYMENT-SIGNATURE": saved["authorization"]})
    data = response.json()
    token = data.get("access_token")
    status = data.get("status_url", "")
    if token and re.fullmatch(r"[0-9a-f]{64}", token) and STATUS_PATH.fullmatch(status):
        save_state(path, {"token": token, "status_path": status, "resource": resource})
    result = data.get("status")
    if snapshot:
        if result == "confirmed" and response.status_code == 200:
            captured = data["data"]
            rows = captured["signals"]
            if not rows or any(row.get("token") not in ("BTC", "ETH") or
                               row.get("direction") not in ("long", "short") for row in rows):
                raise ValueError("Unexpected snapshot data.")
            return {"status": "confirmed", "expires_in": data.get("expires_in"),
                    "signals": [{k: row[k] for k in ("token", "direction", "time")} for row in rows]}
        if result == "pending":
            return {"status": "pending", "next_tool": "buy_or_resume_btc_eth_snapshot"}
        if response.status_code == 422 and response.headers.get("X-FutureCast-Payment-State") == "rejected":
            return {"status": "rejected", "authorization_retained": True}
        return {"status": "expired" if response.status_code == 410 else "unavailable",
                "http_status": response.status_code, "authorization_retained": True}
    if result in {"pending", "confirmed", "source_unavailable"}:
        return {"status": result, "expires_in": data.get("expires_in"),
                "next_tool": "read_agent_events" if result == "confirmed" else "buy_or_resume_pass"}
    return {"status": "expired" if response.status_code == 410 else "unavailable",
            "http_status": response.status_code, "authorization_retained": True}
