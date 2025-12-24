"""Main agent control loop."""

import asyncio
import base64
import time
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.table import Table

from .bridge_client import BridgeClient
from .capture import ScreenCapture
from .config import Config
from .policy import VLMPolicy
from .protocol import AckMessage, StateMessage


class AgentLoop:
    """Main control loop for the Minecraft AI agent."""

    def __init__(self, config: Config, goal: str = "explore and survive"):
        """Initialize the agent loop."""
        self.config = config
        self.goal = goal
        self.console = Console()
        self.use_mod_frames = config.capture_mode == "mod"

        # Components
        if self.use_mod_frames:
            self.capture = None
        else:
            self.capture = ScreenCapture(
                mode=config.capture_mode,
                target_resolution=config.capture_resolution,
                window_title=config.capture_window_title,
            )
        self.policy = VLMPolicy(config)
        self.bridge = BridgeClient(config.bridge_ws_url)

        # State
        self.running = False
        self.latest_state: Optional[StateMessage] = None
        self.latest_ack: Optional[AckMessage] = None
        self.latest_frame: Optional[bytes] = None
        self.stats = {
            "iterations": 0,
            "actions_sent": 0,
            "actions_acked": 0,
            "errors": 0,
            "frames_received": 0,
            "total_capture_ms": 0.0,
            "total_inference_ms": 0.0,
            "total_send_ms": 0.0,
        }

    async def run(self):
        """Run the main agent loop."""
        self.running = True

        # Set up callbacks
        self.bridge.set_state_callback(self._on_state)
        self.bridge.set_ack_callback(self._on_ack)
        if self.use_mod_frames:
            self.bridge.set_frame_callback(self._on_frame)

        # Connect to bridge
        self.console.print("[cyan]Connecting to Minecraft bridge...[/cyan]")
        try:
            await self.bridge.connect()
            self.console.print("[green]Connected to Minecraft bridge![/green]")
        except Exception as e:
            self.console.print(f"[red]Failed to connect: {e}[/red]")
            return

        # Configure mod frame capture if using mod frames
        if self.use_mod_frames:
            # Calculate capture rate: frames to skip based on target FPS vs assumed 60 FPS game
            capture_every_n = max(1, 60 // self.config.capture_fps)
            await self.bridge.configure_frames(
                enabled=True,
                width=self.config.capture_resolution[0],
                height=self.config.capture_resolution[1],
                capture_every_n_frames=capture_every_n,
                jpeg_quality=self.config.jpeg_quality,
            )
            self.console.print(
                f"[green]Mod frame capture enabled: "
                f"{self.config.capture_resolution[0]}x{self.config.capture_resolution[1]} "
                f"@ 1/{capture_every_n} frames[/green]"
            )

        # Start receiving messages in background
        receive_task = asyncio.create_task(self.bridge.receive_messages())

        # Display configuration
        self.console.print("\n" + str(self.config))
        self.console.print(f"\n[yellow]Goal: {self.goal}[/yellow]")
        self.console.print(f"[yellow]Kill switch: Press {self.config.kill_switch_key} to stop[/yellow]\n")

        # Calculate loop interval
        loop_interval = 1.0 / self.config.decision_hz

        # Run the main loop with live stats display
        with Live(self._generate_stats_table(), console=self.console, refresh_per_second=4) as live:
            try:
                while self.running:
                    iteration_start = time.perf_counter()

                    # Execute one iteration
                    await self._run_iteration()

                    # Update display
                    live.update(self._generate_stats_table())

                    # Maintain target Hz
                    elapsed = time.perf_counter() - iteration_start
                    sleep_time = max(0, loop_interval - elapsed)
                    if sleep_time > 0:
                        await asyncio.sleep(sleep_time)

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Received interrupt signal[/yellow]")
            finally:
                self.running = False
                receive_task.cancel()
                await self.bridge.close()
                if self.capture:
                    self.capture.close()
                self.policy.close()

        # Print final stats
        self._print_final_stats()

    async def _run_iteration(self):
        """Execute one iteration of the agent loop."""
        try:
            self.stats["iterations"] += 1

            # 1. Get frame (from mod or screen capture)
            if self.use_mod_frames:
                # Use frame from mod via WebSocket
                if self.latest_frame is None:
                    # No frame yet, skip this iteration
                    return

                # Convert JPEG bytes to base64 data URL
                capture_start = time.perf_counter()
                b64_data = base64.b64encode(self.latest_frame).decode("utf-8")
                image_data_url = f"data:image/jpeg;base64,{b64_data}"
                self.stats["total_capture_ms"] += (time.perf_counter() - capture_start) * 1000
            else:
                # Use screen capture
                frame = self.capture.capture_frame()
                self.stats["total_capture_ms"] += self.capture.get_last_capture_time_ms()
                image_data_url = self.capture.frame_to_png_base64(frame)

            # 2. Get state dict for context
            state_dict = None
            if self.latest_state:
                state_dict = {
                    "pos": self.latest_state.payload.player.pos,
                    "health": self.latest_state.payload.hud.health,
                    "hunger": self.latest_state.payload.hud.hunger,
                }

            # 3. Get action from policy
            action = self.policy.get_action(image_data_url, self.goal, state_dict)
            self.stats["total_inference_ms"] += self.policy.get_last_inference_time_ms()

            # 4. Send action to bridge
            sent = await self.bridge.send_action(action)
            if sent:
                self.stats["actions_sent"] += 1
                self.stats["total_send_ms"] += self.bridge.get_last_send_time_ms()

        except Exception as e:
            self.stats["errors"] += 1
            self.console.print(f"[red]Error in iteration: {e}[/red]")

    def _on_state(self, state: StateMessage):
        """Callback for state updates."""
        self.latest_state = state

    def _on_frame(self, frame_data: bytes, seq: int, ts: int):
        """Callback for frame updates from mod."""
        self.latest_frame = frame_data
        self.stats["frames_received"] += 1

    def _on_ack(self, ack: AckMessage):
        """Callback for action acknowledgments."""
        self.latest_ack = ack
        if ack.payload.applied:
            self.stats["actions_acked"] += 1

    def _generate_stats_table(self) -> Table:
        """Generate a stats table for display."""
        table = Table(title="Agent Statistics", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        # Calculate averages
        iters = max(self.stats["iterations"], 1)
        avg_capture = self.stats["total_capture_ms"] / iters
        avg_inference = self.stats["total_inference_ms"] / iters
        avg_send = self.stats["total_send_ms"] / iters
        avg_total = avg_capture + avg_inference + avg_send

        table.add_row("Iterations", str(self.stats["iterations"]))
        table.add_row("Actions Sent", str(self.stats["actions_sent"]))
        table.add_row("Actions Acked", str(self.stats["actions_acked"]))
        if self.use_mod_frames:
            table.add_row("Frames Received", str(self.stats["frames_received"]))
        table.add_row("Errors", str(self.stats["errors"]))
        table.add_row("---", "---")
        table.add_row("Avg Capture (ms)", f"{avg_capture:.1f}")
        table.add_row("Avg Inference (ms)", f"{avg_inference:.1f}")
        table.add_row("Avg Send (ms)", f"{avg_send:.1f}")
        table.add_row("Avg Total (ms)", f"{avg_total:.1f}")
        table.add_row("Effective Hz", f"{1000.0 / avg_total:.2f}" if avg_total > 0 else "0.00")

        # Add latest state info if available
        if self.latest_state:
            table.add_row("---", "---")
            player = self.latest_state.payload.player
            hud = self.latest_state.payload.hud
            table.add_row("Position", f"({player.pos[0]:.1f}, {player.pos[1]:.1f}, {player.pos[2]:.1f})")
            table.add_row("Health", f"{hud.health:.1f}")
            table.add_row("Hunger", f"{hud.hunger:.1f}")

        return table

    def _print_final_stats(self):
        """Print final statistics."""
        self.console.print("\n[cyan]Final Statistics:[/cyan]")
        self.console.print(self._generate_stats_table())

    def stop(self):
        """Stop the agent loop."""
        self.running = False
