"""On-chain DIA oracle activity poller (public EVM RPC, no key).

For each chain in ``config/oracles.yaml`` we ask a public JSON-RPC node for the
logs emitted by the DIA oracle contract over a recent block window and count
them. Oracle contracts emit ``OracleUpdate(string,uint128,uint128)`` on every
push, so the log count over a window is a direct, on-chain *usage* signal — the
real thing the TVL "proxy" only approximates.

Design:
  * every call is graceful (returns a snapshot with ``error`` set, never raises);
  * we filter by contract address only (no topic), so no keccak dependency and
    it works for any oracle/adapter the user configures;
  * public RPCs cap ``eth_getLogs`` ranges (e.g. Astar = 1024 blocks). On a
    "range too wide"/"limit" error we halve the window once and retry.

A count of 0 is a legitimate reading (a quiet legacy oracle), not a failure.
"""

from __future__ import annotations

from typing import Optional

from dia_alpha_monitor.http_client import post_json
from dia_alpha_monitor.models import OracleActivitySnapshot, today_str, utcnow

# Substrings that indicate the RPC rejected the block range and we should shrink.
_RANGE_ERR_MARKERS = ("range", "too wide", "limit", "too large", "exceed")


def _rpc(url: str, method: str, params: list) -> tuple[Optional[object], str]:
    data, err = post_json(url, {"jsonrpc": "2.0", "method": method, "params": params, "id": 1})
    if err:
        return None, err
    if not isinstance(data, dict):
        return None, "malformed rpc response"
    if "error" in data and data["error"]:
        return None, str(data["error"])[:160]
    return data.get("result"), ""


def _get_logs(url: str, address: str, frm: int, to: int) -> tuple[Optional[int], str]:
    res, err = _rpc(
        url,
        "eth_getLogs",
        [{"address": address, "fromBlock": hex(frm), "toBlock": hex(to)}],
    )
    if err:
        return None, err
    if not isinstance(res, list):
        return None, "unexpected getLogs result"
    return len(res), ""


def poll_oracle(chain_cfg: dict, cache=None) -> OracleActivitySnapshot:
    """Poll one chain's DIA oracle for update logs over a recent block window."""
    snap = OracleActivitySnapshot(
        date=today_str(),
        ts=utcnow().isoformat(),
        chain=chain_cfg.get("name", "?"),
        oracle_address=chain_cfg.get("oracle_address", ""),
        rpc_url=chain_cfg.get("rpc_url", ""),
    )
    if not snap.rpc_url or not snap.oracle_address:
        snap.error = "rpc_url or oracle_address not configured"
        return snap

    lookback = int(chain_cfg.get("lookback_blocks", 1000) or 1000)

    bn_res, err = _rpc(snap.rpc_url, "eth_blockNumber", [])
    if err or not isinstance(bn_res, str):
        snap.error = f"blockNumber: {err or 'no result'}"
        return snap
    try:
        latest = int(bn_res, 16)
    except ValueError:
        snap.error = f"bad block number: {bn_res!r}"
        return snap
    snap.latest_block = latest

    frm = max(0, latest - lookback)
    count, lerr = _get_logs(snap.rpc_url, snap.oracle_address, frm, latest)
    # On a range-limit rejection, shrink the window once and retry.
    if lerr and any(m in lerr.lower() for m in _RANGE_ERR_MARKERS):
        lookback = max(1, lookback // 2)
        frm = max(0, latest - lookback)
        count, lerr = _get_logs(snap.rpc_url, snap.oracle_address, frm, latest)

    snap.from_block = frm
    snap.to_block = latest
    if lerr:
        snap.error = f"getLogs: {lerr}"
    else:
        snap.update_count = count
    return snap


def poll_all(chains: list[dict], cache=None) -> list[OracleActivitySnapshot]:
    return [poll_oracle(c, cache=cache) for c in chains]
