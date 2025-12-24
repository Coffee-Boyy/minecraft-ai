# Minecraft Qwen AI Agent

A real-time vision-language AI agent that plays Minecraft using the Qwen2.5-VL model. The agent captures screenshots from the game, sends them to a VLM for decision-making, and executes actions through a custom Fabric mod.

## Architecture

The project consists of three main components:

1. **vLLM Server** - Serves Qwen2.5-VL-7B-Instruct via OpenAI-compatible API
2. **Agent Service** (Python) - Captures frames, calls VLM, produces actions
3. **Minecraft Bridge Mod** (Fabric) - Receives actions via WebSocket and applies them in-game

## System Requirements

- Ubuntu 22.04+
- Python 3.11+
- Java 17
- NVIDIA GPU with 48GB VRAM (RTX 6000 Ada or equivalent)
- Minecraft Java Edition 1.20.1
- Docker and Docker Compose

## Quick Start

### 1. Start the vLLM Server

```bash
cd docker
docker-compose up -d
```

The server will download and serve the Qwen2.5-VL-7B-Instruct model on port 8000.

### 2. Install the Minecraft Mod

```bash
cd minecraft-mod
./gradlew build
```

Copy `build/libs/mcagent_bridge-*.jar` to your Minecraft `mods/` folder along with Fabric API.

### 3. Install System Dependencies (Wayland only)

If you're using Wayland, install window management tools:

```bash
sudo apt install wmctrl xdotool
```

These are already included on X11 systems.

### 4. Install and Run the Agent

```bash
cd agent
pip install -e .

# Start the agent (make sure Minecraft is running)
mcagent run --goal "explore and gather wood"
```

### 5. Controls

- **F10** - Emergency kill switch to stop the agent
- The agent operates at ~6 Hz decision frequency

## Development

### Python Agent

The agent is structured as follows:

- `config.py` - Configuration management
- `capture.py` - Screen capture at 480p/10fps
- `policy.py` - VLM interaction and action generation
- `protocol.py` - WebSocket message schemas
- `bridge_client.py` - WebSocket client for Minecraft communication
- `loop.py` - Main agent control loop
- `benchmark.py` - Performance measurement
- `cli.py` - Command-line interface

### Minecraft Mod

Located in `minecraft-mod/`:

- `BridgeMod.java` - Main mod entry point
- `WsServer.java` - WebSocket server (port 8765)
- `ActionApplier.java` - Applies actions to the player
- `ActionTypes.java` - Action type definitions

## Configuration

Environment variables (set in `.env` or export):

```bash
VLLM_BASE_URL=http://127.0.0.1:8000/v1
VLLM_MODEL=Qwen2.5-VL-7B-Instruct
BRIDGE_WS_URL=ws://127.0.0.1:8765/ws
CAPTURE_MODE=window              # 'window' to capture Minecraft window only, 'screen' for full screen
CAPTURE_WINDOW_TITLE=Minecraft   # Window title to search for (case-insensitive substring match)
CAPTURE_FPS=10
DECISION_HZ=6
MAX_NEW_TOKENS=64
OUTPUT_STRICT_JSON=1
```

### Display Server Support

**X11 (Recommended for Best Performance):**
- ✅ Full window-specific capture support
- ✅ High performance with `mss` library (~10 FPS)
- ✅ Captures only the Minecraft window (efficient on 4K displays)
- **To switch to X11:** Log out → Select "Pop on Xorg" at login screen

**Wayland (Fully Supported):**
- ✅ Window-specific capture working via `wmctrl` + `xdotool`
- ✅ Captures only the Minecraft window (~6 FPS)
- ✅ Automatic window detection and tracking
- Requires: `wmctrl` (install with `sudo apt install wmctrl`)
- Note: Slightly slower than X11 due to GNOME screenshot API

## Benchmarking

Run benchmarks to measure performance:

```bash
mcagent benchmark --duration 60
```

Metrics measured:
- Frame capture time
- VLM inference time
- WebSocket send time
- Action acknowledgment time
- End-to-end latency
- Effective decision frequency

Results are logged to `agent/logs/bench.jsonl`.

## Safety Features

- **Kill Switch**: Press F10 to immediately stop the agent
- **Rate Limiting**: Maximum 1200 actions per minute
- **Action Duration**: 20-2000ms bounds on all actions
- **Mouse Movement**: Limited to ±12 degrees per action

## Acceptance Criteria

- ✓ Agent connects to WebSocket bridge
- ✓ Captures 854x480 frames at 10 FPS
- ✓ VLM returns valid JSON actions
- ✓ Minecraft applies movement, look, click actions
- ✓ End-to-end latency < 250ms (3+ Hz) or < 400ms (2+ Hz)

## Troubleshooting

### Agent can't connect to Minecraft
- Ensure Minecraft is running with the mod loaded
- Check that port 8765 is not blocked
- Look for WebSocket server logs in Minecraft console

### VLM server errors
- Verify GPU has enough VRAM
- Check Docker logs: `docker-compose logs vllm`
- Ensure model downloaded successfully

### Low FPS / High latency
- Reduce `MAX_NEW_TOKENS` for faster inference
- Lower `CAPTURE_FPS` to reduce load
- Check GPU utilization

## License

MIT
