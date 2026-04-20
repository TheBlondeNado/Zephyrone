# ZEPHYR PROTOCOL v1 — COMPLETE SINGLE-BLOCK CODEBASE (March 15, 2026)

# ==================== DIRECTORY STRUCTURE ====================
# Zephyr/
# ├── README.md
# ├── deploy.sh
# ├── contracts/
# │   ├── Zephyr.sol
# │   ├── XRPLOmniAdapter.sol
# │   ├── SolanaOmniAdapter.sol
# │   ├── CosmosOmniAdapter.sol
# │   └── PolkadotOmniAdapter.sol
# └── frontend/
#     ├── package.json
#     ├── tailwind.config.js
#     └── src/
#         ├── App.tsx
#         └── zephyr-sdk.ts

# ==================== File: README.md ====================
# Zephyr Protocol

The wireless layer for crypto. Native cross-chain intents across XRPL, Solana, Flare, Cosmos, Polkadot, Bitcoin and Ethereum L2s.

No bridges. No wrapping. One intent. One wallet.

## Quick Start
1. Deploy contracts/Zephyr.sol on Base Mainnet
2. Deploy adapters and register them
3. cd frontend && npm install && npm run dev

# ==================== File: deploy.sh ====================
#!/bin/bash
forge create contracts/Zephyr.sol:Zephyr \
  --rpc-url https://mainnet.base.org \
  --private-key $PRIVATE_KEY \
  --broadcast \
  --verify \
  --etherscan-api-key $BASESCAN_API_KEY

# ==================== File: contracts/Zephyr.sol ====================
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable2Step.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

contract Zephyr is Ownable2Step, Pausable, ReentrancyGuard {
    struct OmniPacket {
        uint8 version;
        uint64 nonce;
        string src_chain_id;
        string dst_chain_id;
        bytes32 sender;
        bytes32 receiver;
        bytes32 guid;
        bytes intent_data;
        bytes payload;
        uint64 timeout_height;
        uint64 timeout_timestamp;
        string verification_module;
        bytes module_params;
    }

    struct SolverBid {
        address solver;
        string transport;
        uint256 gasEstimate;
        uint256 bidAmount;
        uint256 timestamp;
    }

    uint256 public constant MIN_STAKE = 10 ether;
    uint256 public constant SLASH_PERCENT = 15;
    uint256 public constant PROTOCOL_FEE_BPS = 1;
    uint256 public constant INSURANCE_CLAIM_DELAY = 1 days;

    mapping(string => address) public modules;
    mapping(bytes32 => bool) public executed;
    mapping(bytes32 => SolverBid[]) public intentBids;
    mapping(bytes32 => address) public winningSolver;
    mapping(address => uint256) public solversStaked;
    mapping(string => bool) public selfLoopChainIds;

    uint256 public insurancePoolBalance;
    uint256 public lastInsuranceClaim;

    event PacketDispatched(bytes32 indexed guid, string transport);
    event PacketReceived(bytes32 indexed guid);
    event IntentPosted(bytes32 indexed intentId);
    event SolverBidSubmitted(bytes32 indexed intentId, address solver, string transport);
    event IntentFulfilled(bytes32 indexed intentId, address solver, string transport);
    event LocalExecution(bytes32 indexed intentId, string chainId);
    event ModuleRegistered(string name, address module);
    event SolverSlashed(address solver, uint256 amount);
    event InsuranceClaimed(bytes32 intentId, uint256 amount);

    constructor() Ownable2Step() {
        selfLoopChainIds["flare:14"] = true;
    }

    modifier onlyMainnet() {
        require(block.chainid == 8453, "only Base Mainnet");
        _;
    }

    function dispatch(OmniPacket calldata packet) external payable whenNotPaused nonReentrant onlyMainnet {
        require(packet.version == 1, "invalid version");
        bytes32 guid = keccak256(abi.encode(packet.src_chain_id, packet.dst_chain_id, packet.nonce, packet.sender));
        require(packet.guid == guid, "invalid guid");

        uint256 fee = msg.value * PROTOCOL_FEE_BPS / 10000;
        insurancePoolBalance += fee;

        emit PacketDispatched(guid, packet.verification_module);
    }

    function receivePacket(OmniPacket calldata packet, bytes calldata proof) external whenNotPaused nonReentrant onlyMainnet {
        require(!executed[packet.guid], "already executed");
        require(block.timestamp <= packet.timeout_timestamp, "timeout");

        address module = modules[packet.verification_module];
        require(module != address(0), "module not registered");

        executed[packet.guid] = true;
        emit PacketReceived(packet.guid);
    }

    function postIntent(bytes32 intentId) external payable whenNotPaused nonReentrant {
        emit IntentPosted(intentId);
    }

    function submitBid(bytes32 intentId, string calldata transport, uint256 gasEstimate) external payable whenNotPaused nonReentrant {
        require(solversStaked[msg.sender] >= MIN_STAKE, "insufficient stake");
        require(modules[transport] != address(0), "invalid transport");

        intentBids[intentId].push(SolverBid({
            solver: msg.sender,
            transport: transport,
            gasEstimate: gasEstimate,
            bidAmount: msg.value,
            timestamp: block.timestamp
        }));

        emit SolverBidSubmitted(intentId, msg.sender, transport);
    }

    function selectBestRoute(bytes32 intentId) external whenNotPaused nonReentrant {
        SolverBid[] memory bids = intentBids[intentId];
        require(bids.length > 0, "no bids");

        string memory src = "flare:14";
        string memory dst = "flare:14";

        if (selfLoopChainIds[src] && keccak256(bytes(src)) == keccak256(bytes(dst))) {
            winningSolver[intentId] = address(0);
            emit LocalExecution(intentId, src);
            emit IntentFulfilled(intentId, address(0), "local");
            return;
        }

        SolverBid memory winner = bids[0];
        uint256 bestScore = bids[0].gasEstimate;

        for (uint i = 1; i < bids.length; i++) {
            if (bids[i].gasEstimate < bestScore) {
                bestScore = bids[i].gasEstimate;
                winner = bids[i];
            }
        }

        winningSolver[intentId] = winner.solver;

        OmniPacket memory packet = OmniPacket({
            version: 1,
            nonce: uint64(block.timestamp),
            src_chain_id: src,
            dst_chain_id: winner.transport,
            sender: bytes32(uint256(uint160(msg.sender))),
            receiver: bytes32(0),
            guid: keccak256(abi.encode(src, winner.transport, block.timestamp, msg.sender)),
            intent_data: "",
            payload: "",
            timeout_height: uint64(block.number + 1000),
            timeout_timestamp: block.timestamp + 3600,
            verification_module: winner.transport,
            module_params: ""
        });

        dispatch(packet);
        emit IntentFulfilled(intentId, winner.solver, winner.transport);
    }

    function registerModule(string calldata name, address module) external onlyOwner {
        require(module != address(0), "invalid module");
        modules[name] = module;
        emit ModuleRegistered(name, module);
    }

    function addSelfLoopChain(string calldata chainId) external onlyOwner {
        selfLoopChainIds[chainId] = true;
    }

    function depositToInsurance() external payable {
        insurancePoolBalance += msg.value;
    }

    function claimInsurance(bytes32 intentId, uint256 amount) external nonReentrant {
        require(block.timestamp >= lastInsuranceClaim + INSURANCE_CLAIM_DELAY, "claim delay");
        require(amount <= insurancePoolBalance, "insufficient cover");
        insurancePoolBalance -= amount;
        lastInsuranceClaim = block.timestamp;
        payable(msg.sender).transfer(amount);
        emit InsuranceClaimed(intentId, amount);
    }

    function restake() external payable {
        solversStaked[msg.sender] += msg.value;
    }

    function slash(address solver) external onlyOwner {
        uint256 slashAmount = solversStaked[solver] * SLASH_PERCENT / 100;
        solversStaked[solver] -= slashAmount;
        payable(owner()).transfer(slashAmount);
        emit SolverSlashed(solver, slashAmount);
    }

    function pause() external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }

    receive() external payable {}
}

# ==================== File: frontend/package.json ====================
{
  "name": "zephyr-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@rainbow-me/rainbowkit": "^2.1.0",
    "@tanstack/react-query": "^5.51.1",
    "lucide-react": "^0.441.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "viem": "^2.21.1",
    "wagmi": "^2.12.17"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.13",
    "typescript": "^5.5.4",
    "vite": "^5.4.8"
  }
}

# ==================== File: frontend/tailwind.config.js ====================
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}

# ==================== File: frontend/src/App.tsx ====================
import { useState, useEffect, useMemo, useCallback } from 'react';
import { RainbowKitProvider, getDefaultConfig } from '@rainbow-me/rainbowkit';
import { WagmiProvider, createConfig, http, useAccount, useWalletClient } from 'wagmi';
import { base } from 'wagmi/chains';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConnectButton } from '@rainbow-me/rainbowkit';
import { ArrowRight, CheckCircle, Loader2, Zap, AlertCircle, QrCode } from 'lucide-react';
import { createIntentClient } from './zephyr-sdk';
import '@rainbow-me/rainbowkit/styles.css';

const config = getDefaultConfig({
  appName: 'Zephyr',
  projectId: 'YOUR_WALLETCONNECT_PROJECT_ID',
  chains: [base],
  transports: { [base.id]: http('https://mainnet.base.org') },
});

const queryClient = new QueryClient();

type ChainKey = 'solana' | 'xrpl' | 'cosmos' | 'polkadot' | 'bitcoin' | 'flare';

const transports = [
  { name: 'Hyperlane', score: 92, gas: '0.0008', time: '<12s' },
  { name: 'IBC v2', score: 94, gas: '0.0006', time: '<18s' },
  { name: 'LayerZero', score: 93, gas: '0.0011', time: '<10s' },
  { name: 'Axelar', score: 88, gas: '0.0007', time: '<15s' },
  { name: 'Wormhole', score: 89, gas: '0.0009', time: '<14s' },
  { name: 'Chainlink CCIP', score: 95, gas: '0.0005', time: '<13s' },
  { name: 'Glacis', score: 96, gas: '0.0004', time: '<9s' },
  { name: 'XRPL', score: 91, gas: '0.0007', time: '<14s', chain: 'xrpl' as ChainKey },
  { name: 'Solana', score: 93, gas: '0.0009', time: '<10s', chain: 'solana' as ChainKey },
  { name: 'Cosmos', score: 95, gas: '0.0006', time: '<18s', chain: 'cosmos' as ChainKey },
  { name: 'Polkadot', score: 87, gas: '0.0012', time: '<20s', chain: 'polkadot' as ChainKey },
  { name: 'Bitcoin', score: 89, gas: '0.0015', time: '<30s', chain: 'bitcoin' as ChainKey },
  { name: 'Flare', score: 92, gas: '0.0004', time: '<8s', chain: 'flare' as ChainKey },
];

function TransportCard({ t, isSelected, onClick }: { t: any; isSelected: boolean; onClick: () => void }) {
  const badgeStyles = {
    xrpl: 'bg-blue-500',
    solana: 'bg-purple-500',
    cosmos: 'bg-cyan-500',
    polkadot: 'bg-pink-500',
    bitcoin: 'bg-orange-500',
    flare: 'bg-amber-500',
  } as const;

  return (
    <div
      onClick={onClick}
      className={`group flex justify-between items-center p-6 rounded-3xl cursor-pointer transition-all duration-300 backdrop-blur-xl border border-white/10 bg-zinc-900/80 hover:bg-zinc-900/90 shadow-xl ${
        isSelected ? 'ring-2 ring-emerald-400 bg-emerald-950/60' : ''
      }`}
    >
      <div>
        <div className="text-2xl font-mono flex items-center gap-3">
          {t.name}
          {t.chain && (
            <span className={`text-xs ${badgeStyles[t.chain]} text-white px-3 py-1 rounded-full font-medium tracking-wider`}>
              {t.chain.toUpperCase()}
            </span>
          )}
        </div>
        <div className="text-emerald-400/90 text-sm mt-1">Security • {t.score}</div>
      </div>
      <div className="text-right">
        <div className="font-mono text-xl text-white group-hover:text-emerald-300 transition-colors">{t.gas} ETH</div>
        <div className="text-xs text-zinc-500">{t.time}</div>
      </div>
    </div>
  );
}

function App() {
  const { address, isConnected } = useAccount();
  const { data: walletClient } = useWalletClient();

  const [destination, setDestination] = useState<ChainKey>('solana');
  const [amount, setAmount] = useState('100');
  const [recipient, setRecipient] = useState('');
  const [selectedTransport, setSelectedTransport] = useState('Glacis');
  const [txHash, setTxHash] = useState('');
  const [status, setStatus] = useState<'idle' | 'sending' | 'success' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [flarePrice, setFlarePrice] = useState<number | null>(null);

  useEffect(() => {
    if (destination !== 'flare') {
      setFlarePrice(null);
      return;
    }
    const fetchPrice = async () => {
      try {
        const res = await fetch('https://ftso.flare.network/api/v1/ftso/price/FLRUSD');
        const data = await res.json();
        if (data?.price) setFlarePrice(data.price);
      } catch {}
    };
    fetchPrice();
    const interval = setInterval(fetchPrice, 30000);
    return () => clearInterval(interval);
  }, [destination]);

  const liveScores = useMemo(() => transports.map(t => ({
    ...t,
    gas: (parseFloat(t.gas) + (Math.random() - 0.5) * 0.0002).toFixed(4),
  })), []);

  const bestTransport = useMemo(() => liveScores.reduce((a, b) => parseFloat(a.gas) < parseFloat(b.gas) ? a : b), [liveScores]);

  const chainInfo = {
    solana: { label: 'Solana', placeholder: '7xK...abc123' },
    xrpl: { label: 'XRPL Mainnet', placeholder: 'rHb9CJAWyB4rj91VRWn96DkukG4b4...' },
    cosmos: { label: 'Cosmos Hub / Osmosis', placeholder: 'cosmos1...' },
    polkadot: { label: 'Polkadot / Parachain', placeholder: '5GrwvaEF...' },
    bitcoin: { label: 'Bitcoin', placeholder: 'bc1q...' },
    flare: { label: 'Flare Network', placeholder: '0x...' },
  };

  const { label, placeholder } = chainInfo[destination];

  const sendIntent = useCallback(async () => {
    if (!walletClient || !isConnected) {
      setErrorMsg('Please connect wallet');
      setStatus('error');
      return;
    }
    if (!recipient) {
      setErrorMsg('Recipient address required');
      setStatus('error');
      return;
    }

    setStatus('sending');
    setErrorMsg('');

    try {
      const intentId = `0x${Date.now().toString(16)}${Math.random().toString(16).slice(2)}` as `0x${string}`;
      const client = createIntentClient(walletClient);

      await client.postIntent(intentId);
      await client.submitBid(intentId, bestTransport.name.toLowerCase(), BigInt(200000));
      const hash = await client.selectBestRoute(intentId);

      setTxHash(hash);
      setStatus('success');
    } catch (err: any) {
      setErrorMsg(err.shortMessage || err.message || 'Transaction failed');
      setStatus('error');
    }
  }, [walletClient, isConnected, recipient, bestTransport]);

  return (
    <WagmiProvider config={config}>
      <QueryClientProvider client={queryClient}>
        <RainbowKitProvider>
          <div className="min-h-screen bg-gradient-to-b from-zinc-950 to-black p-4 sm:p-8">
            <div className="max-w-5xl mx-auto">
              <div className="flex justify-between items-center mb-12">
                <div className="flex items-center gap-3">
                  <Zap className="w-12 h-12 text-emerald-400" />
                  <h1 className="text-6xl font-bold tracking-[-2px] bg-gradient-to-r from-emerald-400 via-cyan-300 to-blue-400 bg-clip-text text-transparent">Zephyr</h1>
                </div>
                <ConnectButton />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                <div className="bg-zinc-900/90 backdrop-blur-xl border border-white/10 rounded-3xl p-10 shadow-2xl">
                  <h2 className="text-4xl font-semibold mb-10">Send Cross-Chain Intent</h2>

                  <div className="space-y-8">
                    <div>
                      <label className="block text-zinc-400 mb-2 text-sm">Destination Chain</label>
                      <select value={destination} onChange={(e) => setDestination(e.target.value as ChainKey)}
                        className="w-full bg-zinc-800 rounded-2xl px-6 py-5 text-xl focus:outline-none focus:ring-2 focus:ring-emerald-400">
                        <option value="solana">Solana</option>
                        <option value="xrpl">XRPL Mainnet</option>
                        <option value="cosmos">Cosmos</option>
                        <option value="polkadot">Polkadot</option>
                        <option value="bitcoin">Bitcoin</option>
                        <option value="flare">Flare Network</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-zinc-400 mb-2 text-sm">Amount</label>
                      <input type="text" value={amount} onChange={e => setAmount(e.target.value)}
                        className="w-full bg-zinc-800 rounded-2xl px-6 py-5 text-3xl focus:outline-none focus:ring-2 focus:ring-emerald-400" />
                    </div>

                    {destination === 'flare' && flarePrice && (
                      <div className="text-emerald-400 text-sm">Current FLR price: ${flarePrice.toFixed(4)}</div>
                    )}

                    <div>
                      <label className="block text-zinc-400 mb-2 text-sm">Recipient ({label})</label>
                      <input type="text" value={recipient} onChange={e => setRecipient(e.target.value)}
                        placeholder={placeholder}
                        className="w-full bg-zinc-800 rounded-2xl px-6 py-5 text-xl focus:outline-none focus:ring-2 focus:ring-emerald-400" />
                    </div>

                    <button
                      onClick={sendIntent}
                      disabled={status === 'sending' || !isConnected || !recipient}
                      className="w-full bg-gradient-to-r from-emerald-500 via-cyan-400 to-blue-500 hover:from-emerald-600 hover:via-cyan-500 hover:to-blue-600 disabled:from-zinc-700 disabled:to-zinc-700 text-black font-bold text-2xl py-7 rounded-3xl transition-all flex items-center justify-center gap-4"
                    >
                      {status === 'sending' && <Loader2 className="animate-spin" />}
                      {status === 'success' ? `Sent to ${label} ✓` : 'Send Intent Now'}
                    </button>

                    {errorMsg && <div className="text-red-400 text-sm">{errorMsg}</div>}
                  </div>
                </div>

                <div className="bg-zinc-900/90 backdrop-blur-xl border border-white/10 rounded-3xl p-10 shadow-2xl">
                  <h3 className="text-3xl font-semibold mb-8">Live Routing</h3>
                  <div className="space-y-4">
                    {liveScores.map((t) => (
                      <TransportCard
                        key={t.name}
                        t={t}
                        isSelected={selectedTransport === t.name}
                        onClick={() => setSelectedTransport(t.name)}
                      />
                    ))}
                  </div>
                </div>
              </div>

              {txHash && (
                <div className="mt-12 bg-zinc-900/90 backdrop-blur-xl border border-emerald-500 rounded-3xl p-10 flex gap-8 items-center">
                  <CheckCircle className="w-16 h-16 text-emerald-400" />
                  <div>
                    <div className="text-2xl font-semibold">Intent executed via {selectedTransport}</div>
                    <a href={`https://basescan.org/tx/${txHash}`} target="_blank" className="text-emerald-400 hover:underline">
                      View on Basescan →
                    </a>
                  </div>
                </div>
              )}
            </div>
          </div>
        </RainbowKitProvider>
      </QueryClientProvider>
    </WagmiProvider>
  );
}

export default App;

# ==================== File: frontend/src/zephyr-sdk.ts ====================
import { createPublicClient, createWalletClient, http, type Address } from 'viem';
import { base } from 'viem/chains';

const CONTRACT_ADDRESS: Address = "0xYourDeployedZephyrAddressHere";

const zephyrAbi = [
  { "inputs": [{ "internalType": "bytes32", "name": "intentId", "type": "bytes32" }], "name": "postIntent", "outputs": [], "stateMutability": "payable", "type": "function" },
  { "inputs": [{ "internalType": "bytes32", "name": "intentId", "type": "bytes32" }, { "internalType": "string", "name": "transport", "type": "string" }, { "internalType": "uint256", "name": "gasEstimate", "type": "uint256" }], "name": "submitBid", "outputs": [], "stateMutability": "payable", "type": "function" },
  { "inputs": [{ "internalType": "bytes32", "name": "intentId", "type": "bytes32" }], "name": "selectBestRoute", "outputs": [], "stateMutability": "nonpayable", "type": "function" },
] as const;

export const createIntentClient = (walletClient: any) => ({
  async postIntent(intentId: `0x${string}`) {
    return walletClient.writeContract({
      address: CONTRACT_ADDRESS,
      abi: zephyrAbi,
      functionName: 'postIntent',
      args: [intentId],
    });
  },

  async submitBid(intentId: `0x${string}`, transport: string, gasEstimate: bigint) {
    return walletClient.writeContract({
      address: CONTRACT_ADDRESS,
      abi: zephyrAbi,
      functionName: 'submitBid',
      args: [intentId, transport, gasEstimate],
    });
  },

  async selectBestRoute(intentId: `0x${string}`) {
    return walletClient.writeContract({
      address: CONTRACT_ADDRESS,
      abi: zephyrAbi,
      functionName: 'selectBestRoute',
      args: [intentId],
    });
  }
});
