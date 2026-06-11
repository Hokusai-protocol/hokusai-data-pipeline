from __future__ import annotations

from src.eip712.onchain_head import read_attester_threshold, read_is_attester


def test_read_attester_threshold(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.eip712.onchain_head._eth_call_bytes32",
        lambda *args, **kwargs: "0x" + ("0" * 63) + "2",
    )

    assert (
        read_attester_threshold(
            "https://rpc.test.local",
            contract_address="0xcccccccccccccccccccccccccccccccccccccccc",
        )
        == 2
    )


def test_read_is_attester(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.eip712.onchain_head._eth_call_bytes32",
        lambda *args, **kwargs: "0x" + ("0" * 63) + "1",
    )

    assert read_is_attester(
        "https://rpc.test.local",
        contract_address="0xcccccccccccccccccccccccccccccccccccccccc",
        address="0x1111111111111111111111111111111111111111",
    )
