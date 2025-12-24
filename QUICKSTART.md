# Quick Start Guide

Get the Minecraft AI agent up and running in under 10 minutes.

## Prerequisites

- Ubuntu 22.04+ (or similar Linux distribution)
- Python 3.11+
- Java 17+
- Docker and Docker Compose
- NVIDIA GPU with 48GB VRAM (or adjust model size)
- Minecraft Java Edition 1.20.1

## Step 1: Initial Setup

Run the setup script to install dependencies:

```bash
./setup.sh
```

This will:
- Check your Python and Java versions
- Install the Python agent package
- Create a `.env` configuration file

## Step 2: Start the vLLM Server

Launch the Qwen2.5-VL model server:

```bash
cd docker
docker-compose up -d
```

The first run will download the model (~15GB). Monitor progress:

```bash
docker-compose logs -f vllm
```

Wait until you see "Application startup complete" in the logs.

## Step 3: Build the Minecraft Mod

```bash
cd minecraft-mod
./gradlew build
```

The built mod will be in `build/libs/mcagent_bridge-0.1.0.jar`.

## Step 4: Install the Mod

1. Install Fabric Loader 1.20.1 if you haven't already
2. Download Fabric API for 1.20.1 from CurseForge or Modrinth
3. Copy both JAR files to your Minecraft `mods/` folder:
   - `mcagent_bridge-0.1.0.jar` (from Step 3)
   - `fabric-api-*.jar` (Fabric API)

## Step 5: Launch Minecraft

Start Minecraft 1.20.1 with Fabric. You should see:

```
[mcagent_bridge] Minecraft Agent Bridge Mod initializing...
[mcagent_bridge] WebSocket server started on port 8765
```

Join or create a world.

## Step 6: Test the Connection

In a new terminal, test the bridge connection:

```bash
mcagent test-connection
```

You should see:
```
✓ Successfully connected to bridge
✓ Received state update
```

## Step 7: Run the Agent

Start the AI agent with a goal:

```bash
mcagent run --goal "explore and gather wood"
```

The agent will:
- Connect to Minecraft via WebSocket
- Capture screenshots at 10 FPS
- Send them to the VLM for decision-making
- Execute actions in the game

Press **Ctrl+C** or **F10** to stop.

## Troubleshooting

### Agent can't connect to Minecraft

**Problem:** `Failed to connect to bridge`

**Solution:**
- Make sure Minecraft is running with the mod loaded
- Check the Minecraft console for WebSocket server messages
- Verify port 8765 is not blocked by a firewall

### VLM server not responding

**Problem:** `Connection refused on port 8000`

**Solution:**
```bash
# Check if container is running
docker ps | grep vllm

# Check logs
docker-compose logs vllm

# Restart if needed
docker-compose restart vllm
```

### Low FPS / High latency

**Problem:** Agent runs slower than 2 Hz

**Solution:**
1. Reduce `MAX_NEW_TOKENS` in `.env` (try 32 or 24)
2. Lower `CAPTURE_FPS` (try 5)
3. Check GPU utilization: `nvidia-smi`
4. Consider using a smaller model

### Python package issues

**Problem:** `ModuleNotFoundError`

**Solution:**
```bash
cd agent
pip install -e .
```

## Running Benchmarks

Measure performance:

```bash
mcagent benchmark --duration 60
```

This will run for 60 seconds and report:
- Average capture time
- Average VLM inference time
- Average WebSocket latency
- End-to-end latency
- Effective decision Hz

Results are saved to `agent/logs/bench.jsonl`.

## Configuration

Edit `.env` to customize:

```bash
# Adjust decision frequency (1-10 Hz)
DECISION_HZ=6

# Adjust output length (lower = faster)
MAX_NEW_TOKENS=64

# Adjust capture rate
CAPTURE_FPS=10
```

## Next Steps

- Try different goals: "build a house", "mine diamonds", "fight zombies"
- Adjust the system prompt in `agent/src/mcagent/policy.py` for different behaviors
- Monitor performance with `mcagent benchmark`
- Check logs in `agent/logs/bench.jsonl`

## Getting Help

- Check the full [README.md](README.md) for detailed information
- Review [spec.yaml](spec.yaml) for architecture details
- Test individual components:
  - `mcagent test-capture` - Test screen capture
  - `mcagent test-connection` - Test Minecraft connection
  - `mcagent config` - View current configuration

Enjoy your AI Minecraft agent!
