"""Command-line interface for the Minecraft AI agent."""

import asyncio

import typer
from rich.console import Console

from .benchmark import BenchmarkRunner
from .config import Config
from .loop import AgentLoop

app = typer.Typer(help="Minecraft AI Agent - Control Minecraft using Qwen2.5-VL")
console = Console()


@app.command()
def run(
    goal: str = typer.Option(
        "explore and survive",
        "--goal",
        "-g",
        help="Goal for the agent to pursue",
    ),
):
    """
    Run the Minecraft AI agent.

    The agent will connect to the Minecraft bridge, capture screenshots,
    and send actions based on the VLM's decisions.
    """
    config = Config.from_env()

    console.print("[bold cyan]Minecraft AI Agent[/bold cyan]")
    console.print("=" * 50)

    loop = AgentLoop(config, goal)

    try:
        asyncio.run(loop.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent stopped by user[/yellow]")


@app.command()
def benchmark(
    duration: int = typer.Option(
        60,
        "--duration",
        "-d",
        help="Duration of the benchmark in seconds",
    ),
):
    """
    Run performance benchmarks.

    Measures end-to-end latency, effective decision Hz, and component timings.
    Results are saved to agent/logs/bench.jsonl.
    """
    config = Config.from_env()

    console.print("[bold cyan]Minecraft AI Agent - Benchmark Mode[/bold cyan]")
    console.print("=" * 50)

    runner = BenchmarkRunner(config, duration)

    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Benchmark stopped by user[/yellow]")


@app.command()
def config():
    """
    Display the current configuration.

    Shows all configuration values loaded from environment variables.
    """
    cfg = Config.from_env()

    console.print("[bold cyan]Current Configuration[/bold cyan]")
    console.print("=" * 50)
    console.print(str(cfg))
    console.print("\n[dim]Set environment variables to override defaults[/dim]")


@app.command()
def test_capture(
    duration: int = typer.Option(
        10,
        "--duration",
        "-d",
        help="Duration to capture frames in seconds",
    ),
    save_screenshots: bool = typer.Option(
        True,
        "--save-screenshots/--no-save-screenshots",
        help="Save screenshots to disk",
    ),
):
    """
    Test screen capture without running the agent.

    Useful for verifying that screen capture works correctly.
    Screenshots are saved to agent/logs/screenshots/ by default.
    """
    config = Config.from_env()

    console.print("[bold cyan]Testing Screen Capture[/bold cyan]")
    console.print("=" * 50)
    console.print(f"Capture mode: {config.capture_mode}")
    console.print(f"Duration: {duration} seconds")
    console.print(f"Target FPS: {config.capture_fps}")
    console.print(f"Resolution: {config.capture_resolution[0]}x{config.capture_resolution[1]}")
    console.print(f"Save screenshots: {save_screenshots}\n")

    if config.capture_mode == "mod":
        # Use mod frame capture via WebSocket
        asyncio.run(_test_mod_capture(config, duration, save_screenshots))
    else:
        # Use screen/window capture
        _test_screen_capture(config, duration, save_screenshots)


async def _test_mod_capture(config: Config, duration: int, save_screenshots: bool):
    """Test frame capture from the Minecraft mod via WebSocket."""
    from .bridge_client import BridgeClient
    import time
    from pathlib import Path

    # Create screenshots directory if saving
    screenshots_dir = None
    if save_screenshots:
        screenshots_dir = Path(__file__).parent.parent.parent / "logs" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"Saving screenshots to: {screenshots_dir}\n")

    frame_count = 0
    start_time = time.time()

    def on_frame(frame_data: bytes, seq: int, ts: int):
        nonlocal frame_count
        frame_count += 1

        # Save screenshot if enabled
        if save_screenshots and screenshots_dir:
            screenshot_path = screenshots_dir / f"frame_{frame_count:05d}.jpg"
            with open(screenshot_path, "wb") as f:
                f.write(frame_data)

        if frame_count % config.capture_fps == 0:
            elapsed = time.time() - start_time
            actual_fps = frame_count / elapsed
            console.print(
                f"Received {frame_count} frames in {elapsed:.1f}s "
                f"(avg {actual_fps:.1f} FPS, seq={seq})"
            )

    async with BridgeClient(config.bridge_ws_url) as bridge:
        try:
            await bridge.connect()
            console.print("[green]Connected to Minecraft bridge[/green]")

            # Configure frame capture
            await bridge.configure_frames(
                enabled=True,
                width=config.capture_resolution[0],
                height=config.capture_resolution[1],
                capture_every_n_frames=1,
                jpeg_quality=config.jpeg_quality,
            )
            console.print("[green]Frame capture configured[/green]\n")

            # Set frame callback
            bridge.set_frame_callback(on_frame)

            # Start receiving messages
            receive_task = asyncio.create_task(bridge.receive_messages())

            # Wait for duration
            await asyncio.sleep(duration)

            # Stop receiving
            receive_task.cancel()

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return

    total_time = time.time() - start_time
    avg_fps = frame_count / total_time if total_time > 0 else 0

    console.print(f"\n[green]Test complete![/green]")
    console.print(f"Total frames: {frame_count}")
    console.print(f"Average FPS: {avg_fps:.2f}")
    if save_screenshots and screenshots_dir:
        console.print(f"Screenshots saved to: {screenshots_dir}")


def _test_screen_capture(config: Config, duration: int, save_screenshots: bool):
    """Test screen/window capture."""
    from .capture import ScreenCapture
    import time
    import cv2
    from pathlib import Path

    # Create screenshots directory if saving
    screenshots_dir = None
    if save_screenshots:
        screenshots_dir = Path(__file__).parent.parent.parent / "logs" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"Saving screenshots to: {screenshots_dir}\n")

    with ScreenCapture(
        mode=config.capture_mode,
        target_resolution=config.capture_resolution,
        window_title=config.capture_window_title,
    ) as capture:
        frame_count = 0
        start_time = time.time()
        interval = 1.0 / config.capture_fps

        while time.time() - start_time < duration:
            iter_start = time.time()

            frame = capture.capture_frame()
            frame_count += 1

            # Save screenshot if enabled
            if save_screenshots and screenshots_dir:
                screenshot_path = screenshots_dir / f"frame_{frame_count:05d}.png"
                cv2.imwrite(str(screenshot_path), frame)

            if frame_count % config.capture_fps == 0:
                elapsed = time.time() - start_time
                actual_fps = frame_count / elapsed
                console.print(
                    f"Captured {frame_count} frames in {elapsed:.1f}s "
                    f"(avg {actual_fps:.1f} FPS, "
                    f"last capture: {capture.get_last_capture_time_ms():.1f}ms)"
                )

            # Maintain target FPS
            sleep_time = max(0, interval - (time.time() - iter_start))
            if sleep_time > 0:
                time.sleep(sleep_time)

    total_time = time.time() - start_time
    avg_fps = frame_count / total_time

    console.print(f"\n[green]Test complete![/green]")
    console.print(f"Total frames: {frame_count}")
    console.print(f"Average FPS: {avg_fps:.2f}")
    if save_screenshots and screenshots_dir:
        console.print(f"Screenshots saved to: {screenshots_dir}")


@app.command()
def test_connection():
    """
    Test connection to the Minecraft bridge WebSocket server.

    Verifies that the bridge mod is running and responsive.
    """
    from .bridge_client import BridgeClient

    config = Config.from_env()

    console.print("[bold cyan]Testing Bridge Connection[/bold cyan]")
    console.print("=" * 50)
    console.print(f"Bridge URL: {config.bridge_ws_url}\n")

    async def test():
        async with BridgeClient(config.bridge_ws_url) as bridge:
            try:
                await bridge.connect()
                console.print("[green]✓ Successfully connected to bridge[/green]")
                console.print(f"Bridge capabilities: {bridge.capabilities}")

                # Wait for a state message
                console.print("\nWaiting for state message (5 seconds)...")
                await asyncio.sleep(5)

                if bridge.latest_state:
                    console.print("[green]✓ Received state update[/green]")
                    player = bridge.latest_state.player
                    console.print(f"  Position: ({player.x:.1f}, {player.y:.1f}, {player.z:.1f})")
                    console.print(f"  Health: {player.health:.1f}")
                    console.print(f"  Hunger: {player.food:.1f}")
                else:
                    console.print("[yellow]⚠ No state message received[/yellow]")

            except Exception as e:
                console.print(f"[red]✗ Connection failed: {e}[/red]")

    try:
        asyncio.run(test())
    except KeyboardInterrupt:
        console.print("\n[yellow]Test interrupted[/yellow]")


if __name__ == "__main__":
    app()
