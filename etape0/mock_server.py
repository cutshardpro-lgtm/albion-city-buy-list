"""City Buy List - serveur websocket MOCK pour tester le harnais etape 0 SANS le jeu.

Ce serveur imite le websocket local d'albiondata-client sur ws://127.0.0.1:8099/ws :
- meme port, meme check d'Origin que le vrai client (ws_client.go : Origin "null"
  rejete, hostname compare a une liste autorisee) ;
- memes trames : plusieurs messages JSON dans une seule trame texte, separes par \n
  (ws_client.go writePump) ;
- meme enveloppe : {"topic": "...", "data": {...}} avec des ordres realistes.

ATTENTION : les donnees emises sont FICTIVES. Ce mock valide uniquement que la page
test_ws.html parse et affiche correctement. Les 4 preuves du gate exigent le VRAI
client + le jeu ouvert au marche. Ne jamais lancer ce mock en meme temps que le vrai
client (conflit de port 8099).

Usage : python mock_server.py   (Ctrl+C pour arreter)
"""

import base64
import hashlib
import json
import socket
import threading
import time

HOST, PORT = "127.0.0.1", 8099
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
ALLOWED_HOSTNAMES = {"localhost", "127.0.0.1"}

# Ordres fictifs, structure identique a lib/market.go (MarketOrder, JSON tags).
# UnitPriceSilver en dix-milliemes de silver si l'hypothese x10000 est vraie :
# 24980000 = 2498 silver affiches en jeu.
MOCK_BATCHES = [
    [
        {"Id": 990000001, "ItemTypeId": "T4_BAG", "ItemGroupTypeId": "T4_BAG",
         "LocationId": "3003", "QualityLevel": 1, "EnchantmentLevel": 0,
         "UnitPriceSilver": 24980000, "Amount": 3, "AuctionType": "offer",
         "Expires": "2026-07-16T00:00:00.000000"},
        {"Id": 990000002, "ItemTypeId": "T6_HEAD_LEATHER_SET1@1",
         "ItemGroupTypeId": "T6_HEAD_LEATHER_SET1", "LocationId": "3003",
         "QualityLevel": 3, "EnchantmentLevel": 1, "UnitPriceSilver": 187650000,
         "Amount": 1, "AuctionType": "offer", "Expires": "2026-07-16T00:00:00.000000"},
        {"Id": 990000003, "ItemTypeId": "T8_MAIN_SWORD",
         "ItemGroupTypeId": "T8_MAIN_SWORD", "LocationId": "3003",
         "QualityLevel": 2, "EnchantmentLevel": 0, "UnitPriceSilver": 890000000,
         "Amount": 1, "AuctionType": "request", "Expires": "2026-07-16T00:00:00.000000"},
    ],
    [
        {"Id": 990000004, "ItemTypeId": "T5_ARMOR_CLOTH_SET2",
         "ItemGroupTypeId": "T5_ARMOR_CLOTH_SET2", "LocationId": "0007",
         "QualityLevel": 1, "EnchantmentLevel": 0, "UnitPriceSilver": 51200000,
         "Amount": 2, "AuctionType": "offer", "Expires": "2026-07-17T00:00:00.000000"},
        {"Id": 990000005, "ItemTypeId": "T7_CAPEITEM_FW_MARTLOCK",
         "ItemGroupTypeId": "T7_CAPEITEM_FW_MARTLOCK", "LocationId": "4002",
         "QualityLevel": 4, "EnchantmentLevel": 0, "UnitPriceSilver": 412870000,
         "Amount": 1, "AuctionType": "offer", "Expires": "2026-07-17T00:00:00.000000"},
    ],
]


def handshake(conn):
    """HTTP -> websocket upgrade, avec le meme comportement d'Origin que le vrai client."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return False
        data += chunk

    headers = {}
    for line in data.decode("latin1").split("\r\n")[1:]:
        if ": " in line:
            k, v = line.split(": ", 1)
            headers[k.lower()] = v

    origin = headers.get("origin", "")
    allowed = False
    if origin and origin != "null" and "//" in origin:
        hostname = origin.split("//", 1)[1].split(":")[0].split("/")[0]
        allowed = hostname in ALLOWED_HOSTNAMES

    if not allowed or "sec-websocket-key" not in headers:
        print(f"[MOCK] REJETE  origin={origin!r}")
        conn.send(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        return False

    accept = base64.b64encode(
        hashlib.sha1((headers["sec-websocket-key"] + WS_GUID).encode()).digest()
    ).decode()
    conn.send(
        (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        ).encode()
    )
    print(f"[MOCK] ACCEPTE origin={origin!r}")
    return True


def text_frame(payload: bytes) -> bytes:
    """Trame texte serveur, FIN=1, opcode=1, sans masque (RFC 6455)."""
    n = len(payload)
    if n < 126:
        header = bytes([0x81, n])
    elif n < 65536:
        header = bytes([0x81, 126]) + n.to_bytes(2, "big")
    else:
        header = bytes([0x81, 127]) + n.to_bytes(8, "big")
    return header + payload


def serve_client(conn, addr):
    try:
        if not handshake(conn):
            conn.close()
            return
        # draine les trames entrantes du navigateur sans les traiter
        conn.settimeout(0.05)
        i = 0
        while True:
            try:
                if conn.recv(4096) == b"":
                    break
            except socket.timeout:
                pass
            except OSError:
                break

            batch = MOCK_BATCHES[i % len(MOCK_BATCHES)]
            # une seule trame, deux messages JSON separes par \n,
            # comme ws_client.go writePump quand la file contient plusieurs messages
            msg1 = json.dumps({"topic": "marketorders.ingest", "data": {"Orders": batch}})
            msg2 = json.dumps({"topic": "goldprices.ingest", "data": {"Prices": [9999], "Timestamps": [638564000000000000]}})
            payload = (msg1 + "\n" + msg2).encode()
            try:
                conn.send(text_frame(payload))
                print(f"[MOCK] trame envoyee : {len(batch)} ordres + goldprices, {len(payload)} octets")
            except OSError:
                break
            i += 1
            time.sleep(2)
    finally:
        conn.close()
        print(f"[MOCK] connexion fermee {addr}")


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(4)
    print(f"[MOCK] en ecoute sur ws://{HOST}:{PORT}/ws  (donnees FICTIVES, Ctrl+C pour arreter)")
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=serve_client, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    main()
