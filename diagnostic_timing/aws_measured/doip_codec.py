#!/usr/bin/env python3
"""Small DoIP framing helper used by the AWS timing research harness.

Implements the common 8-byte DoIP header, routing activation request/response,
and diagnostic-message payload framing. This is intentionally not a complete
ISO 13400 conformance implementation.
"""
from __future__ import annotations

import socket
import struct

PROTOCOL_VERSION = 0x03  # ISO 13400-2:2019 framing version
HEADER = struct.Struct("!BBHI")
PT_ROUTING_ACTIVATION_REQUEST = 0x0005
PT_ROUTING_ACTIVATION_RESPONSE = 0x0006
PT_DIAGNOSTIC_MESSAGE = 0x8001
PT_DIAGNOSTIC_ACK = 0x8002
PT_DIAGNOSTIC_NACK = 0x8003
ROUTING_ACTIVATION_SUCCESS = 0x10


def recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError("socket closed while receiving DoIP frame")
        chunks.extend(chunk)
    return bytes(chunks)


def encode_frame(payload_type: int, payload: bytes, version: int = PROTOCOL_VERSION) -> bytes:
    inverse = version ^ 0xFF
    return HEADER.pack(version, inverse, payload_type, len(payload)) + payload


def recv_frame(sock: socket.socket) -> tuple[int, bytes]:
    raw = recv_exact(sock, HEADER.size)
    version, inverse, payload_type, payload_length = HEADER.unpack(raw)
    if (version ^ inverse) != 0xFF:
        raise ValueError("invalid DoIP inverse protocol version")
    if payload_length > 4 * 1024 * 1024:
        raise ValueError("DoIP payload exceeds research-harness limit")
    return payload_type, recv_exact(sock, payload_length)


def routing_activation_request(source_address: int, activation_type: int = 0x00) -> bytes:
    payload = struct.pack("!HB4s", source_address, activation_type, b"\x00" * 4)
    return encode_frame(PT_ROUTING_ACTIVATION_REQUEST, payload)


def parse_routing_activation_request(payload: bytes) -> tuple[int, int]:
    if len(payload) < 7:
        raise ValueError("short DoIP routing activation request")
    source, activation_type = struct.unpack("!HB", payload[:3])
    return source, activation_type


def routing_activation_response(client_address: int, entity_address: int, response_code: int = ROUTING_ACTIVATION_SUCCESS) -> bytes:
    payload = struct.pack("!HHB4s", client_address, entity_address, response_code, b"\x00" * 4)
    return encode_frame(PT_ROUTING_ACTIVATION_RESPONSE, payload)


def parse_routing_activation_response(payload: bytes) -> tuple[int, int, int]:
    if len(payload) < 9:
        raise ValueError("short DoIP routing activation response")
    client, entity, code = struct.unpack("!HHB", payload[:5])
    return client, entity, code


def diagnostic_message(source_address: int, target_address: int, uds_payload: bytes) -> bytes:
    return encode_frame(PT_DIAGNOSTIC_MESSAGE, struct.pack("!HH", source_address, target_address) + uds_payload)


def parse_diagnostic_message(payload: bytes) -> tuple[int, int, bytes]:
    if len(payload) < 4:
        raise ValueError("short DoIP diagnostic message")
    source, target = struct.unpack("!HH", payload[:4])
    return source, target, payload[4:]
