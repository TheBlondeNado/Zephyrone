import streamlit as st
import requests
import time
from web3 import Web3
from streamlit_wallet_connect import wallet_connect

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
if "history" not in st.session_state:
    st.session_state.history = []

# ===================== UI =====================
st.title("⚡ Zephyr")
st.markdown("**The wireless layer for crypto.** Connecting the best specialized networks seamlessly — no bridges, no wrapping.")

# Satellite Routing Table
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

# Satellite-Specific Info
if destination == "Flare Network":
    st.subheader("Flare Live Oracle Data")
    try:
        flr_resp = requests.get("https://ftso.flare.network/api/v1/ftso/price/FLRUSD", timeout=5)
        flr_price = flr_resp.json().get("price")
        if flr_price: st.success(f"FLR/USD: **${flr_price:.4f}**")
        fxrp_resp = requests.get("https://ftso.flare.network/api/v1/ftso/price/FXRPUSD", timeout=5)
        fxrp_price = fxrp_resp.json().get("price")
        if fxrp_price: st.success(f"FXRP/USD: **${fxrp_price:.4f}**")
    except:
        pass
    st.info("💡 Local execution on Flare (fast & cheap)")

if destination == "Stellar":
    st.info("🌟 Optimized for fast payments and stablecoins")
if destination == "Sui":
    st.info("⚡ Parallel execution satellite — ideal for high-volume intents")

# Wallet & Full Intent Flow
st.subheader("Wallet & Send Intent")

connect_result = wallet_connect(label="connect", key="zephyr_connect", message="Connect MetaMask")

if connect_result and connect_result.get("address"):
    st.session_state.account = connect_result["address"]
    st.success(f"✅ Connected: {st.session_state.account[:6]}...{st.session_state.account[-4:]}")

if st.button("🚀 Send Full Intent Across Satellites", type="primary", use_container_width=True):
    if not st.session_state.get("account"):
        st.error("Please connect MetaMask first")
    elif not recipient:
        st.error("Please enter a recipient address")
    else:
        with st.spinner("Routing through optimal satellite..."):
            try:
                intent_id = w3.keccak(text=f"intent-{st.session_state.account}-{int(time.time())}")
                transport = "Flare" if "Flare" in destination else "Glacis"

                # Simplified full flow for demo
                post_tx = contract.functions.postIntent(intent_id).build_transaction({
                    'from': st.session_state.account,
                    'gas': 250000,
                    'nonce': w3.eth.get_transaction_count(st.session_state.account),
                    'chainId': 8453,
                })

                result = wallet_connect(
                    label="send",
                    key="zephyr_send",
                    message="Sign Intent",
                    contract_address=ZEPHYR_ADDRESS,
                    data=post_tx['data'],
                    value="0",
                    gas=hex(post_tx['gas']),
                    chain_id="0x2105"
                )

                if result and result.get("txHash"):
                    st.success("🎉 Intent successfully routed!")
                    st.balloons()
                    st.markdown(f"[View on Basescan](https://basescan.org/tx/{result['txHash']})")
                    
                    # Add to history
                    st.session_state.history.append({
                        "time": time.strftime("%H:%M"),
                        "destination": destination,
                        "tx": result['txHash'][:8] + "..."
                    })
                else:
                    st.error("Signing cancelled or failed")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# Intent History
if st.session_state.history:
    st.subheader("Recent Intents")
    for item in reversed(st.session_state.history[-5:]):
        st.markdown(f"**{item['time']}** → {item['destination']} • tx: `{item['tx']}`")

st.caption("Zephyr — The wireless mesh connecting specialized satellites: XRPL (settlement), Flare (oracles), Sui (speed), Stellar (payments), Chainlink/Pyth (data).")
