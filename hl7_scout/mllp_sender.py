# Copyright © 2026 Sebastian Bąk. All rights reserved.

"""
MLLP (Minimum Lower Layer Protocol) client for HL7 v2.x message transmission.

MLLP wraps HL7 messages for TCP transport:
  - Start Block:  \x0b  (VT)
  - HL7 payload
  - End Block:    \x1c\x0d  (FS + CR)

This is the same protocol used by HAPI HL7v2, Mirth Connect, and other
HL7 integration engines.
"""

import socket
from dataclasses import dataclass

MLLP_START = b'\x0b'
MLLP_END = b'\x1c\x0d'

DEFAULT_TIMEOUT = 10  # seconds


@dataclass
class MLLPResponse:
    success: bool
    raw_response: str  # decoded HL7 ACK/NAK or error description
    ack_code: str      # "AA", "AE", "AR", or "" if not parseable


def send(host: str, port: int, hl7_message: str,
         timeout: float = DEFAULT_TIMEOUT) -> MLLPResponse:
    """Send an HL7 message via MLLP and return the response.

    The message should use \\r as segment separator (HL7 standard).
    """
    # Ensure HL7 uses \r as segment terminator
    payload = hl7_message.replace('\n', '\r').replace('\r\r', '\r')
    if not payload.endswith('\r'):
        payload += '\r'

    frame = MLLP_START + payload.encode('utf-8') + MLLP_END

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((host, port))
            sock.sendall(frame)

            # Read response (ACK/NAK)
            response_data = _recv_mllp(sock, timeout)

        if response_data is None:
            return MLLPResponse(
                success=True,
                raw_response="(brak odpowiedzi — wiadomość wysłana)",
                ack_code="",
            )

        raw_resp = response_data.decode('utf-8', errors='replace')
        ack_code = _extract_ack_code(raw_resp)
        success = ack_code in ("AA", "CA", "")

        return MLLPResponse(
            success=success,
            raw_response=raw_resp,
            ack_code=ack_code,
        )

    except socket.timeout:
        return MLLPResponse(
            success=False,
            raw_response="Timeout — brak odpowiedzi w wyznaczonym czasie.",
            ack_code="",
        )
    except ConnectionRefusedError:
        return MLLPResponse(
            success=False,
            raw_response="Połączenie odrzucone — sprawdź host i port.",
            ack_code="",
        )
    except OSError as e:
        return MLLPResponse(
            success=False,
            raw_response=f"Błąd sieciowy: {e}",
            ack_code="",
        )


def _recv_mllp(sock: socket.socket, timeout: float) -> bytes | None:
    """Receive an MLLP-wrapped response. Returns payload without MLLP framing."""
    buf = b''
    sock.settimeout(timeout)
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            # Check for MLLP end marker
            end_pos = buf.find(MLLP_END)
            if end_pos != -1:
                # Strip MLLP framing
                start = 1 if buf.startswith(MLLP_START) else 0
                return buf[start:end_pos]
    except socket.timeout:
        pass

    if buf:
        start = 1 if buf.startswith(MLLP_START) else 0
        return buf[start:]
    return None


def _extract_ack_code(response: str) -> str:
    """Extract the acknowledgment code from an MSA segment.

    MSA|AA|... -> "AA"
    MSA|AE|... -> "AE"
    MSA|AR|... -> "AR"
    """
    for line in response.replace('\r', '\n').split('\n'):
        line = line.strip()
        if line.startswith('MSA') and '|' in line:
            parts = line.split('|')
            if len(parts) >= 2:
                return parts[1].strip()
    return ""
