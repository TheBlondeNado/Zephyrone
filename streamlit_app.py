import streamlit as st
from web3 import Web3
import requests
import time
import json
from streamlit_javascript import st_javascript

st.set_page_config(page_title="Zephyr", page_icon="⚡", layout="centered")

# ===================== CONFIG =====================
ZEPHYR_ADDRESS = "0xYourDeployedZephyrAddressHere"  # ← REPLACE WITH YOUR REAL CONTRACT ADDRESS ON BASE

RPC_URL = "https://mainnet.base.org"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

ZEPHYR_ABI = [
    {"inputs": [{"internalType": "bytes32", "name": "intentId", "type": "bytes32"}], "name": "postIntent", "outputs": [], "stateMutability": "payable", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "intentId", "type": "bytes32"}, {"internalType": "string", "name": "transport", "type": "string"}, {"internalType": "uint256", "name": "gasEstimate", "type": "uint256"}], "name": "submitBid", "outputs": [], "stateMutability": "payable", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "intentId", "type": "bytes32"}], "name": "selectBestRoute", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
]

contract = w3.eth.contract(address=ZEPHYR_ADDRESS, abi=ZEPHYR_ABI)

if "account" not in st.session_state:
    st.session_state.account = None
if "last_tx_data" not in st.session_state:
    st.session_state.last_tx_data = None

# ===================== UI =====================
st.title("⚡ Zephyr")
st.markdown("**The wireless layer for crypto.** Connecting the best specialized networks seamlessly — no bridges, no wrapping.")

# Live Routing - Bright Red Bars
st.subheader("Live Routing — Specialized Satellites")
transports = [
    {"name": "Glacis", "score": 96, "gas": "0.0004", "time": "<9s"},
    {"name": "LayerZero", "score": 93, "gas": "0.0011", "time": "<10s"},
    {"name": "Chainlink CCIP", "score": 95, "gas": "0.0005", "time": "<13s", "desc": "Data + Messaging"},
    {"name": "Pyth", "score": 94, "gas": "0.0003", "time": "<6s", "desc": "Ultra-low latency prices"},
    {"name": "XRPL", "score": 91, "gas": "0.0007", "time": "<14s", "desc": "Settlement"},
    {"name": "Flare", "score": 92, "gas": "0.0004", "time": "<8s", "desc": "Oracles + FAssets"},
    {"name": "Sui", "score": 93, "gas": "0.0006", "time": "<7s", "desc": "Parallel execution"},
    {"name": "Stellar", "score": 90, "gas": "0.0002", "time": "<5s", "desc": "Payments"},
]
for t in transports:
    badge = f" 🌐 {t.get('desc', '')}" if t.get("desc") else ""
    st.markdown(f"""
    <div style="padding:16px; border-radius:12px; background:#ef4444; margin-bottom:12px; color:white; font-weight:600; box-shadow:0 4px 6px -1px rgb(0 0 0 / 0.1);">
        <strong>{t['name']}{badge}</strong> • Security: {t['score']} • {t['gas']} ETH • {t['time']}
    </div>
    """, unsafe_allow_html=True)

# Destination & Recipient
col1, col2 = st.columns([3, 2])
with col1:
    destination = st.selectbox("Destination Satellite", [
        "Solana", "XRPL Mainnet", "Flare Network", "Sui", "Stellar", 
        "Bitcoin", "Cosmos", "Polkadot"
    ])
with col2:
    recipient = st.text_input("Recipient Address", placeholder="Enter address...")

# Flare Enhancements
if destination == "Flare Network":
    st.subheader("Flare Live Oracle Data")
    try:
        flr_resp = requests.get("https://ftso.flare.network/api/v1/ftso/price/FLRUSD", timeout=5)
        flr_price = flr_resp.json().get("price")
        if flr_price:
            st.success(f"FLR/USD: **${flr_price:.4f}**")
        fxrp_resp = requests.get("https://ftso.flare.network/api/v1/ftso/price/FXRPUSD", timeout=5)
        fxrp_price = fxrp_resp.json().get("price")
        if fxrp_price:
            st.success(f"FXRP/USD: **${fxrp_price:.4f}**")
    except:
        pass
    st.info("💡 Flare → Flare uses local execution (fast & cheap)")

# Wallet Connection
if st.button("🔗 Connect MetaMask", type="primary", use_container_width=True):
    try:
        account = st_javascript("""
            if (window.ethereum) {
                return window.ethereum.request({ method: 'eth_requestAccounts' }).then(accounts => accounts[0]);
            } else {
                return "No MetaMask";
            }
        """)
        if account and account != "No MetaMask":
            st.session_state.account = account
            st.success(f"✅ Connected: {account[:6]}...{account[-4:]}")
        else:
            st.error("MetaMask not detected. Please open this in a browser with MetaMask installed.")
    except Exception as e:
        st.error(f"Connection error: {str(e)}")

# Full Intent Button
if st.button("🚀 Send Full Intent Across Satellites", type="primary", use_container_width=True):
    if not st.session_state.get("account"):
        st.error("Please connect MetaMask first")
    elif not recipient:
        st.error("Please enter a recipient address")
    else:
        with st.spinner("Preparing full intent for MetaMask..."):
            try:
                intent_id = w3.keccak(text=f"intent-{st.session_state.account}-{int(time.time())}")
                transport = "Flare" if "Flare" in destination else "Glacis"

                # Build postIntent transaction
                tx = contract.functions.postIntent(intent_id).build_transaction({
                    'from': st.session_state.account,
                    'gas': 250000,
                    'nonce': w3.eth.get_transaction_count(st.session_state.account),
                    'chainId': 8453,
                })

                tx_data = {
                    "to": ZEPHYR_ADDRESS,
                    "value": "0",
                    "data": tx['data'],
                    "gas": hex(tx['gas']),
                    "gasPrice": hex(w3.eth.gas_price),
                    "nonce": hex(tx['nonce']),
                    "chainId": "0x2105"
                }

                st.session_state.last_tx_data = tx_data

                st.success("✅ Transaction prepared for MetaMask!")
                st.markdown("**Copy the JSON below and paste into MetaMask → Advanced → Custom Transaction**")
                st.json(tx_data)

                st.info("After signing in MetaMask, you can paste the transaction hash here to track it.")

            except Exception as e:
                st.error(f"Failed to prepare transaction: {str(e)}")

# Show last prepared transaction
if st.session_state.last_tx_data:
    st.caption("Last prepared transaction (ready for MetaMask):")
    st.json(st.session_state.last_tx_data)

st.caption("Zephyr — Wireless mesh connecting specialized satellites. Real MetaMask connection via JS injection.")
